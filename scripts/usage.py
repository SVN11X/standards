#!/usr/bin/env python3
"""Token use of every model call and of every task, from what each tool reports. A value nobody reported is null.

Every call to a model appends one row to telemetry.jsonl under STANDARDS_HOME. The row names the task and the plan
it belongs to, the kind of call (plan, execute, review, bench) and the usage in one shape for every executor:
new input, cache read, cache write, output and reasoning tokens. When a unit ends, the executor loop appends one
outcome row with its attempts, tests, review and whether it was accepted. `tasks` joins both, so the cost of a task
includes its failed attempts and its reviews.

Two costs stay apart. `reported_cost_usd` is the price a tool prints for the call, such as the API price Claude Code
shows on a subscription. `extra_charge_usd` is money charged beyond what is already paid: 0 for a local model and
for a Claude Code subscription call (the planner removes every API key), the provider's own charge when it reports
one, and null when nothing says.

Usage: python scripts/usage.py tasks [--plan ID] [--json]
       python scripts/usage.py models [--json]
       python scripts/usage.py context [--json]   what the hooks added to sessions, in characters
       python scripts/usage.py compare BASELINE CANDIDATE [--metric auto|cost|tokens|new-tokens] [--json]
           BASELINE and CANDIDATE are telemetry files or STANDARDS_HOME folders of two runs of the same plans
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

KEYS = ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens")
SCHEMA = 2
# Who pays for a call of each executor. A local model costs electricity, which is not counted here.
BASIS = {"ollama": "local", "colibri": "local", "tools": "local", "claude": "subscription",
         "opencode": "free-model", "api": "free-model"}
_SCOPE: contextvars.ContextVar[dict] = contextvars.ContextVar("usage_scope", default={})


def empty() -> dict:
    return dict.fromkeys(KEYS)


def count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def total_of(values) -> int | None:
    """The sum of the values that were reported. None when none was."""
    seen = [v for v in (count(x) for x in values) if v is not None]
    return sum(seen) if seen else None


def reported(usage: dict | None) -> bool:
    return any(count((usage or {}).get(key)) is not None for key in KEYS)


def prompt_tokens(usage: dict | None) -> int | None:
    """Every prompt token the model read: new, written to the cache and read from it."""
    usage = usage or {}
    if count(usage.get("input_tokens")) is None:
        return None
    return total_of(usage.get(key) for key in ("input_tokens", "cache_read_tokens", "cache_write_tokens"))


def from_claude(reply: dict) -> dict:
    """The result of `claude -p --output-format json`. modelUsage also counts subagents and background calls,
    which usage leaves out, so it wins when present."""
    models = reply.get("modelUsage") if isinstance(reply, dict) else None
    entries = [m for m in models.values() if isinstance(m, dict)] if isinstance(models, dict) else []
    if entries:
        out = {"input_tokens": total_of(m.get("inputTokens") for m in entries),
               "output_tokens": total_of(m.get("outputTokens") for m in entries), "reasoning_tokens": None,
               "cache_read_tokens": total_of(m.get("cacheReadInputTokens") for m in entries),
               "cache_write_tokens": total_of(m.get("cacheCreationInputTokens") for m in entries)}
        if reported(out):
            return out
    usage = reply.get("usage") if isinstance(reply, dict) and isinstance(reply.get("usage"), dict) else {}
    return {"input_tokens": count(usage.get("input_tokens")), "output_tokens": count(usage.get("output_tokens")),
            "reasoning_tokens": None, "cache_read_tokens": count(usage.get("cache_read_input_tokens")),
            "cache_write_tokens": count(usage.get("cache_creation_input_tokens"))}


def from_opencode(stdout: str) -> dict:
    """The events of `opencode run --format json`, one JSON object per line. Each step_finish carries the tokens and
    the cost of one model step, so a run is their sum. OpenCode counts reasoning apart from output and its input
    leaves the cache out. Returns {usage, reported_cost_usd, session_id, steps}."""
    sums: dict[str, list] = {key: [] for key in KEYS}
    costs, session, steps = [], None, 0
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        session = session or event.get("sessionID") or part.get("sessionID")
        if event.get("type") != "step_finish" and part.get("type") != "step-finish":
            continue
        steps += 1
        tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        reasoning = count(tokens.get("reasoning"))
        output = count(tokens.get("output"))
        sums["input_tokens"].append(tokens.get("input"))
        sums["output_tokens"].append(None if output is None else output + (reasoning or 0))
        sums["reasoning_tokens"].append(reasoning)
        sums["cache_read_tokens"].append(cache.get("read"))
        sums["cache_write_tokens"].append(cache.get("write"))
        if isinstance(part.get("cost"), (int, float)) and not isinstance(part.get("cost"), bool):
            costs.append(float(part["cost"]))
    return {"usage": {key: total_of(values) for key, values in sums.items()},
            "reported_cost_usd": round(sum(costs), 6) if costs else None,
            "session_id": session if isinstance(session, str) else None, "steps": steps}


def from_ollama(reply: dict) -> dict:
    """Ollama counts the prompt tokens it evaluated and the tokens it generated. It reports no cache."""
    return {**empty(), "input_tokens": count(reply.get("prompt_eval_count")), "output_tokens": count(reply.get("eval_count"))}


def from_openai(usage: dict | None) -> dict:
    """An OpenAI-compatible usage block. prompt_tokens includes the cached part and completion_tokens the reasoning."""
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    produced = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    prompt, cached = count(usage.get("prompt_tokens")), count(details.get("cached_tokens"))
    written = count(details.get("cache_write_tokens"))
    fresh = prompt - (cached or 0) - (written or 0) if prompt is not None else None
    return {"input_tokens": fresh if fresh is None or fresh >= 0 else prompt,
            "output_tokens": count(usage.get("completion_tokens")),
            "reasoning_tokens": count(produced.get("reasoning_tokens")),
            "cache_read_tokens": cached, "cache_write_tokens": written}


@contextlib.contextmanager
def scope(**fields):
    """Name the task, plan and kind of every call made inside. Inner scopes add to outer ones, per thread."""
    token = _SCOPE.set({**_SCOPE.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def current() -> dict:
    return dict(_SCOPE.get())


def extra_charge(executor: str, charged) -> float | None:
    if isinstance(charged, (int, float)) and not isinstance(charged, bool):
        return round(float(charged), 6)
    return 0.0 if BASIS.get(executor) in ("local", "subscription") else None


def call_row(executor: str, model: str | None, usage: dict | None, source: str, seconds=None, *,
             provider: str | None = None, reported_cost_usd=None, charged_usd=None, **extra) -> dict:
    """One model call in the shape every reader expects. The task, plan and kind come from scope()."""
    usage = {key: count((usage or {}).get(key)) for key in KEYS}
    where = current()
    output = usage["output_tokens"]
    return {"schema": SCHEMA, "date": now(), "task_id": where.get("task_id"), "plan_id": where.get("plan_id"),
            "kind": where.get("kind", "call"), "attempt": where.get("attempt"), "executor": executor,
            "provider": provider or executor, "model": model, "usage": usage,
            "usage_source": source if reported(usage) else "none", "seconds": seconds,
            "tokens_per_second": round(output / seconds, 2) if output and seconds else None,
            "reported_cost_usd": reported_cost_usd, "extra_charge_usd": extra_charge(executor, charged_usd),
            "cost_basis": BASIS.get(executor, "unknown"), **extra}


def outcome_row(task_id: str, *, plan_id: str | None, accepted: bool, attempts: int | None, tests_passed: bool | None,
                review_passed: bool | None, duration_seconds=None, executor: str | None = None,
                model: str | None = None, status: str | None = None) -> dict:
    """How a task ended. It carries no tokens: those are in the call rows of the same task."""
    return {"schema": SCHEMA, "date": now(), "task_id": task_id, "plan_id": plan_id, "kind": "outcome",
            "executor": executor, "model": model, "status": status,
            "execution": {"duration_seconds": duration_seconds, "attempts": attempts, "tests_passed": tests_passed,
                          "review_passed": review_passed},
            "result": {"accepted": accepted}}


def now() -> str:
    import orchestrate
    return orchestrate.now()


def append(row: dict) -> dict:
    import orchestrate
    orchestrate.append_telemetry(row)
    return row


def record(executor: str, model: str | None, usage: dict | None, source: str, seconds=None, **fields) -> dict:
    """Append one call row. Telemetry never stops the work it measures."""
    row = call_row(executor, model, usage, source, seconds, **fields)
    try:
        append(row)
    except OSError:
        pass
    return row


def normalized(row: dict) -> dict:
    """A row of any schema in the current shape. Rows before schema 2 carried prompt_tokens and completion_tokens,
    and the planner's prompt_tokens already included the cache."""
    if row.get("schema") == SCHEMA:
        return row
    usage = {**empty(), "input_tokens": count(row.get("prompt_tokens")), "output_tokens": count(row.get("completion_tokens"))}
    executor = row.get("provider") or "unknown"
    return {"schema": 1, "date": row.get("date"), "task_id": None, "plan_id": None, "kind": row.get("kind", "call"),
            "attempt": None, "executor": executor, "provider": executor, "model": row.get("model"), "usage": usage,
            "usage_source": "legacy" if reported(usage) else "none", "seconds": row.get("seconds"),
            "tokens_per_second": row.get("tokens_per_second"), "reported_cost_usd": row.get("reported_cost_usd"),
            "extra_charge_usd": extra_charge(executor, None), "cost_basis": BASIS.get(executor, "unknown")}


def read_rows(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """The rows of a telemetry file, the last `limit` lines only when given."""
    import orchestrate
    path = path or orchestrate.home() / "telemetry.jsonl"
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit:] if limit else lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(normalized(row))
    return rows


def money(values) -> float | None:
    seen = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(seen), 6) if seen else None


def add_usage(rows: list[dict]) -> dict:
    return {key: total_of((r.get("usage") or {}).get(key) for r in rows) for key in KEYS}


def by_model(rows: list[dict]) -> dict:
    """Calls, tokens, seconds and reported cost per provider and model. A token kind nobody reported is null."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("kind") != "outcome":
            groups.setdefault(f"{row.get('provider')}/{row.get('model')}", []).append(row)
    out = {}
    for key, items in groups.items():
        usage = add_usage(items)
        out[key] = {"requests": len(items), "unreported": sum(1 for r in items if not reported(r.get("usage"))),
                    "input": usage["input_tokens"], "output": usage["output_tokens"],
                    "reasoning": usage["reasoning_tokens"], "cache_read": usage["cache_read_tokens"],
                    "cache_write": usage["cache_write_tokens"],
                    "seconds": round(sum(r.get("seconds") or 0 for r in items), 2),
                    "reported_cost_usd": money(r.get("reported_cost_usd") for r in items),
                    "extra_charge_usd": money(r.get("extra_charge_usd") for r in items)}
    return out


def tasks(rows: list[dict], plan_id: str | None = None) -> list[dict]:
    """One record per task: every call it made, its usage and how it ended. A plan's own planning calls are the
    task `<plan id>/plan`."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if plan_id and row.get("plan_id") != plan_id:
            continue
        key = row.get("task_id") or (f"{row['plan_id']}/plan" if row.get("plan_id") else None)
        if key:
            groups.setdefault(key, []).append(row)
    out = []
    for key, items in groups.items():
        calls = [r for r in items if r.get("kind") != "outcome"]
        ends = [r for r in items if r.get("kind") == "outcome"]
        last = ends[-1] if ends else {}
        execution = dict(last.get("execution") or {})
        kinds: dict[str, int] = {}
        for row in calls:
            kinds[row.get("kind", "call")] = kinds.get(row.get("kind", "call"), 0) + 1
        main = next((r for r in reversed(calls) if r.get("kind") == "execute"), calls[-1] if calls else last)
        out.append({"task_id": key, "plan_id": items[0].get("plan_id"), "executor": last.get("executor") or main.get("executor"),
                    "model": last.get("model") or main.get("model"), "calls": len(calls), "kinds": kinds,
                    "unreported_calls": sum(1 for r in calls if not reported(r.get("usage"))),
                    "usage": add_usage(calls),
                    "execution": {"duration_seconds": execution.get("duration_seconds"),
                                  "attempts": execution.get("attempts", kinds.get("execute")),
                                  "tests_passed": execution.get("tests_passed"),
                                  "review_passed": execution.get("review_passed")},
                    "result": {"accepted": (last.get("result") or {}).get("accepted") if ends else None,
                               "status": last.get("status"),
                               "reported_cost_usd": money(r.get("reported_cost_usd") for r in calls),
                               "extra_charge_usd": money(r.get("extra_charge_usd") for r in calls)}})
    return sorted(out, key=lambda t: t["task_id"])


# Thresholds of the first A/B pilot, proposed on 2026-11-22. Thirty pairs show a difference, they do not prove
# that quality is equal.
PILOT = {"min_saving": 0.15, "max_regressions": 0, "min_pairs": 30}


def p90(values: list[float]) -> float | None:
    ordered = sorted(v for v in values if isinstance(v, (int, float)))
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]


def plan_results(rows: list[dict]) -> dict[str, dict]:
    """The last outcome row of each plan, the one execute.py writes with the plan id as task id."""
    found = {}
    for row in rows:
        if row.get("kind") == "outcome" and row.get("task_id") and row.get("task_id") == row.get("plan_id"):
            found[row["plan_id"]] = row
    return found


def arm(rows: list[dict], plans: set[str]) -> dict:
    """Totals of one arm over the paired plans: every call of a plan counts, planning, attempts and reviews."""
    results = plan_results(rows)
    calls = [r for r in rows if r.get("kind") != "outcome" and r.get("plan_id") in plans]
    counted = add_usage(calls)
    accepted = sum(1 for plan in plans if (results[plan].get("result") or {}).get("accepted"))
    every = {key: counted[key] or 0 for key in KEYS}
    costs = [r.get("reported_cost_usd") for r in calls]
    by_kind: dict[str, int] = {}
    for row in calls:
        u = row.get("usage") or {}
        by_kind[row.get("kind", "call")] = by_kind.get(row.get("kind", "call"), 0) + sum(
            u.get(k) or 0 for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"))
    return {"plans": len(plans), "accepted": accepted, "acceptance_rate": round(accepted / len(plans), 3) if plans else None,
            "calls": len(calls), "unreported_calls": sum(1 for r in calls if not reported(r.get("usage"))),
            "usage": counted, "tokens": every["input_tokens"] + every["cache_read_tokens"] + every["cache_write_tokens"]
            + every["output_tokens"], "new_tokens": every["input_tokens"] + every["cache_write_tokens"] + every["output_tokens"],
            "tokens_by_kind": by_kind,
            "reported_cost_usd": money(costs) if all(c is not None for c in costs) and costs else None,
            "attempts": sum((results[p].get("execution") or {}).get("attempts") or 0 for p in plans),
            "p90_seconds": p90([(results[p].get("execution") or {}).get("duration_seconds") for p in plans
                                if (results[p].get("result") or {}).get("accepted")])}


def compare(baseline: list[dict], candidate: list[dict], metric: str = "auto", thresholds: dict | None = None) -> dict:
    """An A/B comparison of the same plans run twice, paired by plan id: the same repository folder, base commit and
    instruction give the same id. The candidate passes the pilot when it costs at least `min_saving` less per
    accepted plan, loses no plan the baseline delivered and has at least `min_pairs` pairs."""
    limits = {**PILOT, **(thresholds or {})}
    a_plans, b_plans = plan_results(baseline), plan_results(candidate)
    pairs = set(a_plans) & set(b_plans)
    a, b = arm(baseline, pairs), arm(candidate, pairs)
    if metric == "auto":
        metric = "cost" if a["reported_cost_usd"] is not None and b["reported_cost_usd"] is not None else "new-tokens"
    field = {"cost": "reported_cost_usd", "tokens": "tokens", "new-tokens": "new_tokens"}[metric]

    def each(side: dict):
        value = side[field]
        return round(value / side["accepted"], 6) if value is not None and side["accepted"] else None
    a["per_accepted"], b["per_accepted"] = each(a), each(b)
    lost = sorted(p for p in pairs if (a_plans[p].get("result") or {}).get("accepted")
                  and not (b_plans[p].get("result") or {}).get("accepted"))
    gained = sorted(p for p in pairs if (b_plans[p].get("result") or {}).get("accepted")
                    and not (a_plans[p].get("result") or {}).get("accepted"))
    saving = (round(1 - b["per_accepted"] / a["per_accepted"], 3)
              if a["per_accepted"] and b["per_accepted"] is not None else None)
    failed = []
    if len(pairs) < limits["min_pairs"]:
        failed.append(f"{len(pairs)} paired plans, {limits['min_pairs']} needed")
    if len(lost) > limits["max_regressions"]:
        failed.append(f"{len(lost)} plan(s) the baseline delivered and the candidate did not")
    if saving is None:
        failed.append(f"no {metric} per accepted plan to compare")
    elif saving < limits["min_saving"]:
        failed.append(f"saving {saving:.1%}, {limits['min_saving']:.0%} needed")
    if a["unreported_calls"] or b["unreported_calls"]:
        failed.append(f"{a['unreported_calls']} baseline and {b['unreported_calls']} candidate call(s) reported no usage")
    return {"metric": metric, "pairs": len(pairs), "baseline": a, "candidate": b, "saving": saving,
            "regressions": lost, "gained": gained, "thresholds": limits, "passes_pilot": not failed, "why_not": failed,
            "only_in_baseline": sorted(set(a_plans) - pairs), "only_in_candidate": sorted(set(b_plans) - pairs)}


def rows_at(path: str) -> list[dict]:
    where = Path(path)
    return read_rows(where / "telemetry.jsonl" if where.is_dir() else where)


def fmt(value) -> str:
    return "n/a" if value is None else f"{value:,}" if isinstance(value, int) else str(value)


def print_tasks(items: list[dict]) -> None:
    for t in items:
        u = t["usage"]
        print(f"{t['task_id']}  accepted {fmt(t['result']['accepted'])}  calls {t['calls']} {t['kinds']}  "
              f"new input {fmt(u['input_tokens'])}  cache read {fmt(u['cache_read_tokens'])}  "
              f"cache write {fmt(u['cache_write_tokens'])}  output {fmt(u['output_tokens'])}  "
              f"reported ${fmt(t['result']['reported_cost_usd'])}  charged ${fmt(t['result']['extra_charge_usd'])}"
              + (f"  ({t['unreported_calls']} call(s) reported no usage)" if t["unreported_calls"] else ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("tasks")
    listing.add_argument("--plan")
    listing.add_argument("--json", action="store_true")
    models = sub.add_parser("models")
    models.add_argument("--json", action="store_true")
    sub.add_parser("context").add_argument("--json", action="store_true")
    pair = sub.add_parser("compare")
    pair.add_argument("baseline")
    pair.add_argument("candidate")
    pair.add_argument("--metric", choices=["auto", "cost", "tokens", "new-tokens"], default="auto")
    pair.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compare":
        data = compare(rows_at(args.baseline), rows_at(args.candidate), args.metric)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            for name in ("baseline", "candidate"):
                side = data[name]
                print(f"{name}: {side['accepted']} of {side['plans']} plans accepted, {data['metric']} per accepted plan "
                      f"{fmt(side['per_accepted'])}, new input {fmt(side['usage']['input_tokens'])}, cache read "
                      f"{fmt(side['usage']['cache_read_tokens'])}, output {fmt(side['usage']['output_tokens'])}, "
                      f"p90 {fmt(side['p90_seconds'])} s, attempts {side['attempts']}")
            print(f"saving {fmt(data['saving'])}, regressions {len(data['regressions'])}, pairs {data['pairs']}")
            print("passes the pilot" if data["passes_pilot"] else "does not pass the pilot: " + "; ".join(data["why_not"]))
        return 0 if data["passes_pilot"] else 1
    if args.command == "context":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
        import context_log
        data = context_log.summary()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"injections {data['injections']}  characters sent {data['sent_chars']:,}  "
                  f"left out as already held {data['skipped_chars']:,}")
            for name, item in sorted(data["blocks"].items()):
                print(f"  {name}: {item['count']} times, {item['chars']:,} characters")
        return 0
    rows = read_rows()
    if args.command == "models":
        data = by_model(rows)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            for key, item in data.items():
                print(f"{key}  requests {item['requests']}  new input {fmt(item['input'])}  cache read {fmt(item['cache_read'])}  "
                      f"cache write {fmt(item['cache_write'])}  output {fmt(item['output'])}  "
                      f"reported ${fmt(item['reported_cost_usd'])}")
        return 0
    data = tasks(rows, args.plan)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_tasks(data)
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
