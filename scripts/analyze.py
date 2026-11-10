#!/usr/bin/env python3
"""Test every allowed model candidate on the bench tasks, unattended, and say which one fits each kind of task.

Commands:
  prepare   by day: what is installed, what is missing and what needs the owner's check, with the exact commands
  plan      preview of the night: the steps, the longest it can take and the remote sessions. Runs nothing
  run       run the plan, one local model at a time. Stop it at any moment and run it again to continue
  report    write the report of the history to a file outside the repository

It uses the catalog (settings/models.yml), the same gate as the router and the same history as `orchestrate.py bench`.
It tests only what is installed and allowed. It never pulls a model, creates an account, asks for a key or
moves to a paid endpoint. Three runs per combination are a first signal, not strong statistics.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench_tasks  # noqa: E402
import orchestrate  # noqa: E402

DATA_TEXT = orchestrate.DATA_TEXT


def hours(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    return f"{minutes // 60} h {minutes % 60:02d} min"


def consent_command(model: str) -> str:
    return f"python scripts/orchestrate.py consent --free-model {model}"


def grouped(items: list[dict]) -> list[dict]:
    """Merge the models left out for the same reason and the same fix into one line."""
    merged: dict[tuple, dict] = {}
    for item in items:
        shared = item.get("fix") is None or item["model"] not in str(item["fix"])
        key = (item["executor"], item["why"], item.get("fix")) if shared else (item["executor"], item["model"], item["why"])
        if key in merged:
            merged[key]["names"].append(item["model"])
        else:
            merged[key] = {**item, "names": [item["model"]]}
    for item in merged.values():
        count = len(item["names"])
        item["label"] = f"{item['executor']}:{item['names'][0]}" if count == 1 else \
            f"{item['executor']}, {count} models ({', '.join(str(n) for n in item['names'][:3])}{'...' if count > 3 else ''})"
    return list(merged.values())


# What can be tested


def candidates(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None = None,
               local_agents: bool = False) -> tuple[list[dict], list[dict]]:
    """Split the catalog into models ready to test, with their tasks, and models left out, with the reason and the fix."""
    ready, left_out = [], []
    oconf = conf["executors"]["ollama"]
    info = caps.get("ollama") or {}
    entries = catalog.get("models") or []
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        consent = orchestrate.bench_local(folder, local)
        local_names = [e["id"] for e in entries if e.get("executor") == "ollama"]
        local_names += [name for name in oconf.get("prefer", []) if name not in local_names]
        for name in local_names:
            entry = orchestrate.catalog_entry("ollama", name, catalog) or {}
            base = {"executor": "ollama", "model": name, "provider": entry.get("provider", "ollama-local"), "remote": False}
            if not info.get("up"):
                left_out.append({**base, "why": "Ollama is not running, start it first", "fix": None})
            elif not orchestrate.is_installed(name, info):
                left_out.append({**base, "why": "not installed", "fix": f"ollama pull {name}",
                                 "note": f"size and license: {entry.get('source') or 'see the model page'}"})
            elif orchestrate.is_embedding(name, oconf, info, catalog):
                left_out.append({**base, "why": "embedding model, it serves search only", "fix": None})
            else:
                ok, why = orchestrate.gate("ollama", name, folder, conf, consent, mode, caps, catalog)
                if not ok:
                    left_out.append({**base, "why": why, "fix": None})
                    continue
                tasks, cannot = [], []
                for task, needs in bench_tasks.CHAT_TASKS.items():
                    missing = [need for need in needs if not orchestrate.model_can(name, need, info, catalog)]
                    (cannot if missing else tasks).append(task if not missing else f"{task} (does not report {', '.join(missing)})")
                ready.append({**base, "tasks": tasks, "cannot": cannot, "size": (info.get("sizes") or {}).get(name)})
                if local_agents and (caps.get("opencode") or {}).get("path"):
                    ready.append({"executor": "opencode", "model": f"ollama/{name}", "provider": "ollama-local", "remote": False,
                                  "tasks": list(bench_tasks.AGENT_TASKS), "cannot": []})
        opencode = caps.get("opencode") or {}
        offered = opencode.get("models") or []
        fresh = orchestrate.fresh_free_models(local, conf)
        remote = [e for e in entries if e.get("executor") == "opencode"]
        known = {e["id"] for e in remote}
        remote += [{"id": item["id"], "provider": "unlisted"} for item in fresh
                   if not item["id"].startswith("ollama/") and item["id"].split("/")[-1] not in known]
        for entry in remote:
            short = entry["id"].split("/")[-1]
            listed = next((name for name in offered if name.split("/")[-1] == short), None)
            mine = next((item["id"] for item in fresh if item["id"].split("/")[-1] == short), None)
            name = mine or listed or short
            base = {"executor": "opencode", "model": name, "provider": entry.get("provider", "unlisted"), "remote": True,
                    "limit": entry.get("requests_per_day")}
            use = DATA_TEXT[orchestrate.data_use(entry)]
            if not opencode.get("path"):
                left_out.append({**base, "why": "OpenCode is not installed", "fix": None})
            elif offered and not listed:
                left_out.append({**base, "why": "`opencode models` does not list it any more", "fix": None})
            elif not mine:
                left_out.append({**base, "why": f"needs your check that it is still free. It {use}",
                                 "fix": consent_command(listed or f"<its name in `opencode models`, ending in {short}>"),
                                 "note": f"read first: {entry.get('source') or 'the provider page'}"})
            else:
                ok, why = orchestrate.gate("opencode", name, folder, conf, consent, mode, caps, catalog)
                if not ok:
                    left_out.append({**base, "why": why, "fix": None})
                    continue
                cannot = (["vision (sending an image through OpenCode is not implemented here)"]
                          if "vision" in (entry.get("capabilities") or []) else [])
                ready.append({**base, "tasks": list(bench_tasks.AGENT_TASKS), "cannot": cannot, "data": use})
    return ready, left_out


def build_plan(ready: list[dict], conf: dict, runs: int | None = None, tasks: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Baselines first, then each local model with all its work, then the remote models. Returns the steps and what a budget cut."""
    settings = conf["analysis"]
    runs = runs or settings["runs"]
    wanted = lambda task: not tasks or task in tasks  # noqa: E731
    steps = [{"key": f"{task}|tools|-|1", "task": task, "executor": "tools", "model": None, "run": 1, "limit_s": 60,
              "remote": False, "provider": "program"} for task in sorted(bench_tasks.BASELINES) if wanted(task)]
    cut = []
    for item in sorted(ready, key=lambda r: r["remote"]):
        mine = [task for task in item["tasks"] if wanted(task)]
        agent_limit = conf["limits"]["opencode_timeout_s"] + 120
        allowed = None
        if item["remote"]:
            per_day = item.get("limit")
            allowed = per_day // settings["requests_per_agent_run"] if per_day else settings["remote_runs_per_model"]
        used, dropped = 0, 0
        for task in mine:
            for number in range(1, runs + 1):
                if allowed is not None and used >= allowed:
                    dropped += 1
                    continue
                used += 1
                steps.append({"key": f"{task}|{item['executor']}|{item['model']}|{number}", "task": task,
                              "executor": item["executor"], "model": item["model"], "run": number, "remote": item["remote"],
                              "provider": item["provider"], "own_limit": bool(item.get("limit")),
                              "limit_s": agent_limit if task in bench_tasks.AGENT_TASKS else settings["chat_run_timeout_s"]})
        if dropped:
            cut.append({"executor": item["executor"], "model": item["model"], "fix": None,
                        "why": f"{dropped} runs left out, over the {allowed} sessions this model gets in one night"})
    return steps, cut


def plan_lines(steps: list[dict], cut: list[dict], left_out: list[dict], conf: dict, mode: str, done: dict | None = None) -> list[str]:
    done = done or {}
    todo = [s for s in steps if s["key"] not in done]
    budget = conf["analysis"]["night_budget_s"]
    longest = sum(s["limit_s"] for s in todo)
    lines = [f"Cost mode: {mode}. Steps: {len(todo)} to run, {len(steps) - len(todo)} already done."]
    lines.append(f"Longest it can take: {hours(min(longest, budget))}. Every time limit added up is {hours(longest)} "
                 f"and one run stops by itself after {hours(budget)}. It normally ends much sooner.")
    for remote in (False, True):
        group: dict[str, list[dict]] = {}
        for step in todo:
            if step["remote"] == remote and step["executor"] != "tools":
                group.setdefault(f"{step['executor']}:{step['model']}", []).append(step)
        if group:
            lines.append("Remote free models, sessions this night:" if remote else "Local, one model at a time:")
            for name, items in group.items():
                lines.append(f"  {name}: {len(items)} runs of {', '.join(sorted({s['task'] for s in items}))}")
    sessions = sum(1 for s in todo if s["remote"])
    lines.append(f"Remote sessions in total: {sessions}. Each one is an agent session that makes several requests."
                 if sessions else "Remote sessions: none. Nothing leaves this machine.")
    if cut or left_out:
        lines.append("Not in the plan:")
        lines += [f"  {item['label']}: {item['why']}" + (f". To add it: {item['fix']}" if item.get("fix") else "")
                  for item in grouped([*left_out, *cut])]
    return lines


# Running


def state_file() -> Path:
    return orchestrate.home() / "analysis" / "current.json"


def load_state(mode: str) -> dict:
    path = state_file()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            path.rename(path.with_name(f"broken-{int(time.time())}.json"))
    return {"id": dt.datetime.now().strftime("%Y%m%d-%H%M%S"), "started": orchestrate.now(), "mode": mode,
            "done": {}, "stopped": {}, "left_out": [], "cannot": []}


def unload_other_models(keep: str | None, conf: dict) -> None:
    """Ask Ollama to free the models that are not needed now, so two never share the card. It downloads nothing."""
    oconf = conf["executors"]["ollama"]
    url = oconf.get("url", "http://127.0.0.1:11434").rstrip("/")
    if not orchestrate.is_loopback(url):
        return
    for loaded in orchestrate.detect_ollama(oconf).get("loaded") or []:
        if loaded.get("name") and loaded["name"] != keep:
            try:
                orchestrate.http_json(f"{url}/api/generate", {"model": loaded["name"], "keep_alive": 0}, timeout=30)
            except (OSError, ValueError):
                pass


def run_plan(conf: dict | None = None, local: dict | None = None, caps: dict | None = None, catalog: dict | None = None,
             mode: str | None = None, runs: int | None = None, tasks: list[str] | None = None, budget_s: float | None = None,
             local_agents: bool = False, say=print) -> dict:
    """Run every step that is not done yet. One failing model or provider never stops the others."""
    conf = conf or orchestrate.policy()
    local = local if local is not None else orchestrate.local_config()
    catalog = catalog if catalog is not None else orchestrate.model_catalog()
    mode_name, _ = orchestrate.cost_mode(conf, local, mode)
    caps = caps or probe(conf, mode_name)
    ready, left_out = candidates(conf, local, caps, catalog, mode, local_agents)
    steps, cut = build_plan(ready, conf, runs, tasks)
    state = load_state(mode_name)
    state["left_out"] = [*left_out, *cut]
    state["cannot"] = [{"model": f"{r['executor']}:{r['model']}", "task": c} for r in ready for c in r["cannot"]]
    budget = budget_s if budget_s is not None else conf["analysis"]["night_budget_s"]
    started, current_local, interrupted = time.monotonic(), None, False
    for line in plan_lines(steps, cut, left_out, conf, mode_name, state["done"]):
        say(line)
    try:
        for step in steps:
            if step["key"] in state["done"]:
                continue
            if time.monotonic() - started >= budget:
                say(f"Stopped: this run used its {hours(budget)}. Run it again to continue.")
                break
            scope = f"{step['executor']}:{step['model']}" if step.get("own_limit") else step["provider"]
            if step["remote"] and scope in state["stopped"]:
                state["done"][step["key"]] = {"skipped": f"{state['stopped'][scope]}, so it was not used again this night"}
                continue
            if step["executor"] == "ollama" and step["model"] != current_local:
                unload_other_models(step["model"], conf)
                current_local = step["model"]
            try:
                row = orchestrate.bench_run(step["task"], step["executor"], step["model"], conf=conf, caps=caps.get("ollama"),
                                            local=local, mode=mode, catalog=catalog, time_limit_s=step["limit_s"])
            except Exception as error:  # noqa: BLE001 (one broken step is recorded and the night goes on)
                row = {"date": orchestrate.now(), "task": step["task"], "executor": step["executor"], "model": step["model"],
                       "seconds": 0.0, "verified": False, "error": f"{type(error).__name__}: {error}"[:300]}
            if row.get("skipped"):
                state["done"][step["key"]] = {"skipped": row["skipped"]}
                say(f"skip  {step['key']}: {row['skipped']}")
            else:
                row.update(night=state["id"], run=step["run"])
                orchestrate.append_bench(row)
                state["done"][step["key"]] = {"verified": bool(row.get("verified")), "seconds": row.get("seconds")}
                say(f"{'pass' if row.get('verified') else 'fail'}  {step['key']}: {row.get('seconds')}s"
                    + (f" ({row['error']})" if row.get("error") and not row.get("verified") else ""))
                if step["remote"] and row.get("rate_limited"):
                    state["stopped"][scope] = f"{step['executor']}:{step['model']} answered that its limit was reached"
                    say(f"limit reached: {scope} is not used again this night")
            orchestrate.write_json(state_file(), state)
    except KeyboardInterrupt:
        say("Interrupted. What finished is saved. Run it again to continue.")
        interrupted = True
    finally:
        if current_local:
            unload_other_models(None, conf)
        orchestrate.write_json(state_file(), state)
    state["complete"] = all(step["key"] in state["done"] for step in steps) and not interrupted
    if state["complete"]:
        state["finished"] = orchestrate.now()
        orchestrate.write_json(state_file().with_name(f"{state['id']}.json"), state)
        state_file().unlink(missing_ok=True)
    return state


def probe(conf: dict, mode: str) -> dict:
    """Look at the machine. In local-only mode it does not even ask OpenCode for its model list."""
    caps = orchestrate.doctor(full=mode != "local-only", conf=conf)
    caps["ollama"] = orchestrate.detect_ollama(conf["executors"]["ollama"], show=True)
    return caps


def last_state() -> dict | None:
    folder = orchestrate.home() / "analysis"
    files = [state_file()] if state_file().exists() else sorted(folder.glob("2*.json"))[-1:]
    try:
        return json.loads(files[0].read_text(encoding="utf-8")) if files else None
    except ValueError:
        return None


# Report


def table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    return lines + ["| " + " | ".join("-" if cell is None or cell == "" else str(cell) for cell in row) + " |" for row in rows]


def describe(executor: str, model: str | None, catalog: dict) -> tuple[str, str]:
    """Data use and evidence of a model, for the report."""
    if executor == "tools":
        return "nothing leaves the machine", "program"
    entry = orchestrate.catalog_entry(executor, model, catalog)
    if executor == "ollama" or (model or "").startswith("ollama/"):
        return "local, nothing leaves the machine", "measured here"
    return DATA_TEXT[orchestrate.data_use(entry)], "measured here" + ("" if entry else ", not in the catalog")


def proposal(conf: dict, catalog: dict) -> list[str]:
    """For each task type, the models that passed the existing threshold, the one that does not train and is fastest first."""
    lines = []
    prefer = conf["executors"]["ollama"].get("prefer", [])
    for task in conf["tasks"]:
        if task in orchestrate.TOOL_TASKS:
            continue
        passed = orchestrate.measured_models(task, conf)
        ranked = sorted(passed.items(), key=lambda kv: (orchestrate.DATA_RANK[orchestrate.data_use(
            orchestrate.catalog_entry(kv[0][0], kv[0][1], catalog))] if kv[0][0] == "opencode" else 0, kv[1]["p50_s"]))
        ranked = [(key, row) for key, row in ranked if key[0] != "tools"]
        if not ranked:
            lines.append(f"- `{task}`: nobody passed yet. It stays with {', '.join(conf['tasks'][task])}.")
            continue
        parts = []
        for (executor, model), row in ranked[:3]:
            note = "" if executor != "ollama" or model in prefer else ", add it to `executors.ollama.prefer` to use it"
            parts.append(f"{executor} `{model}` ({row['task']}: {row['runs']} runs, pass rate {row['pass_rate']}, median {row['p50_s']} s{note})")
        lines.append(f"- `{task}`: " + ". Then ".join(parts) + ".")
    return lines


def build_report(conf: dict | None = None, catalog: dict | None = None, rows: list[dict] | None = None,
                 state: dict | None = None) -> str:
    conf = conf or orchestrate.policy()
    catalog = catalog if catalog is not None else orchestrate.model_catalog()
    rows = rows if rows is not None else orchestrate.bench_rows()
    limits = conf["limits"]
    summary = orchestrate.summarize_bench(rows)
    hardware = next((r.get("hardware") for r in reversed(rows) if r.get("hardware")), {}) or {}
    gpu = hardware.get("gpu") or {}
    out = ["# Model analysis", "",
           f"Written {orchestrate.now()}. History: {orchestrate.bench_file()} ({len(rows)} runs).",
           f"Machine: {hardware.get('os', 'unknown')}, GPU {gpu.get('name', 'not seen')}"
           + (f" with {gpu.get('vram_total_mib')} MiB" if gpu else "") + f", OpenCode {hardware.get('opencode') or 'not seen'}.",
           "", f"A model counts for a task after {limits['bench_min_runs']} runs with a pass rate of {limits['bench_min_pass_rate']}. "
           "That is a first signal on this machine, not strong statistics. A program checked every result, no model graded another.", ""]
    if not summary:
        out += ["No runs yet. Start with `python scripts/analyze.py prepare`.", ""]
    for task in sorted({row["task"] for row in summary}):
        out += [f"## {task}", ""]
        body = []
        for row in sorted((r for r in summary if r["task"] == task), key=lambda r: (-r["pass_rate"], r["p50_s"] or 9e9)):
            use, evidence = describe(row["executor"], row["model"], catalog)
            ok = row["runs"] >= limits["bench_min_runs"] and row["pass_rate"] >= limits["bench_min_pass_rate"]
            body.append([row["executor"], row["model"], f"{round(row['pass_rate'] * row['runs'])} of {row['runs']}", row["p50_s"],
                         row["errors"], use, evidence, "yes" if ok else "no"])
        out += table(["Agent", "Model", "Accepted runs", "Median s to an accepted result", "Errors", "Data use", "Evidence",
                      "Passed the threshold"], body) + [""]
        if task == "design-judge-sample":
            out += ["These pairs are a made-up sample that only proves the mechanism. They are nobody's taste and never decide who reviews design.", ""]
    out += ["## Proposed split", "", "The router already reads this history: among the models you allowed, it takes the one that "
            "passed and is fastest. What stays your decision is which models you allow, and the order in `settings/orchestration.yml`.", ""]
    out += proposal(conf, catalog) + [""]
    failed = [row for row in summary if row["executor"] != "tools"
              and not (row["runs"] >= limits["bench_min_runs"] and row["pass_rate"] >= limits["bench_min_pass_rate"])]
    out += ["## Below the threshold", ""]
    out += [f"- {row['executor']} `{row['model']}` on `{row['task']}`: {round(row['pass_rate'] * row['runs'])} of {row['runs']} accepted. "
            + (f"Most common failure: {row['why_failed']}." if row["why_failed"] else "Too few runs so far.") for row in failed] or ["- None."]
    out += ["", "## Not tested", ""]
    skipped = []
    if state:
        skipped += [f"- {item['label']}: {item['why']}." + (f" To add it: `{item['fix']}`." if item.get("fix") else "")
                    for item in grouped(state.get("left_out") or [])]
        skipped += [f"- {item['model']}: {item['task']}." for item in state.get("cannot") or []]
        skipped += [f"- {key.replace('|', ' ')}: {value['skipped']}." for key, value in (state.get("done") or {}).items()
                    if value.get("skipped")]
        if not state.get("complete") and not state.get("finished"):
            skipped.append("- The last run did not finish. Run `python scripts/analyze.py run` again to continue it.")
    out += skipped or ["- Nothing was left out of the last run."]
    out += ["", "Planning, deep review and visual direction have no bench class yet, so no free model can earn them here."]
    due = orchestrate.stale_notes(conf, catalog)
    if due:
        out += ["", "## Due again", ""] + [f"- {note}." for note in due]
    return "\n".join(out) + "\n"


def write_report(out: Path | None = None, **options) -> Path:
    text = build_report(**options)
    path = out or orchestrate.home() / "reports" / f"model-analysis-{dt.datetime.now().strftime('%Y%m%d-%H%M')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# Day preparation


def prepare_lines(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None = None) -> list[str]:
    mode_name, source = orchestrate.cost_mode(conf, local, mode)
    ready, left_out = candidates(conf, local, caps, catalog, mode)
    info, opencode = caps.get("ollama") or {}, caps.get("opencode") or {}
    lines = [f"Cost mode: {mode_name} ({source}).",
             f"Ollama at {info.get('url')}: {'running' if info.get('up') else 'not running'}. "
             f"OpenCode: {opencode.get('version') or ('installed' if opencode.get('path') else 'not installed')}.", "", "Ready to test:"]
    for item in ready:
        size = f", {item['size'] / 1e9:.1f} GB" if item.get("size") else ""
        can = (info.get("capabilities") or {}).get(item["model"])
        lines.append(f"  {item['executor']}:{item['model']}{size}" + (f", reports {', '.join(can)}" if can else "")
                     + (f", {item['data']}" if item.get("data") else "") + f". Tasks: {', '.join(item['tasks'])}")
        lines += [f"      cannot be tested: {text}" for text in item["cannot"]]
    if not ready:
        lines.append("  nothing yet")
    lines += ["", "Left out, and what you can do about it. Nothing here runs by itself:"]
    for item in grouped(left_out):
        lines.append(f"  {item['label']}: {item['why']}")
        if item.get("note"):
            lines.append(f"      {item['note']}")
        if item.get("fix"):
            lines.append(f"      {item['fix']}")
    pairs, sample = bench_tasks.design_pairs()
    folder = orchestrate.home() / "design-pairs"
    lines += ["", f"Design pairs: {len(pairs)} of yours in {folder}." if not sample else
              f"Design pairs: none of yours yet, so the judge test uses a made-up sample that never counts. Put yours in {folder} "
              "(pairs.yml and the images, see docs/006-model-analyzer.md)."]
    lines += [f"due: {note}" for note in orchestrate.stale_notes(conf, catalog, local)]
    lines += ["", "Next: python scripts/analyze.py plan"]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    modes = ["local-only", "free-strict", "existing-subscription"]
    for name in ("prepare", "plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--mode", choices=modes, help="a stricter cost mode for this run")
        if name != "prepare":
            p.add_argument("--runs", type=int, help="runs per model and task (default from settings/orchestration.yml)")
            p.add_argument("--tasks", nargs="*", choices=orchestrate.BENCH_NAMES, help="only these bench tasks")
            p.add_argument("--local-agents", action="store_true", help="also run the agent tasks on local models through OpenCode (slow)")
        if name == "run":
            p.add_argument("--hours", type=float, help="stop by itself after this many hours")
            p.add_argument("--restart", action="store_true", help="forget the unfinished run and start a new one")
    p = sub.add_parser("report")
    p.add_argument("--out", type=Path, help="file to write (default: a new file in ~/.standards/reports)")
    args = parser.parse_args(argv)

    conf, local, catalog = orchestrate.policy(), orchestrate.local_config(), orchestrate.model_catalog()
    if args.command == "report":
        path = write_report(args.out, conf=conf, catalog=catalog, state=last_state())
        print(f"Report: {path}")
        return 0
    mode_name, _ = orchestrate.cost_mode(conf, local, args.mode)
    if args.command == "prepare":
        print("\n".join(prepare_lines(conf, local, probe(conf, mode_name), catalog, args.mode)))
        return 0
    if args.command == "plan":
        ready, left_out = candidates(conf, local, probe(conf, mode_name), catalog, args.mode, args.local_agents)
        steps, cut = build_plan(ready, conf, args.runs, args.tasks)
        state = load_state(mode_name) if state_file().exists() else {"done": {}}
        print("\n".join(plan_lines(steps, cut, left_out, conf, mode_name, state["done"])))
        print("\nNothing ran. To run it: python scripts/analyze.py run")
        return 0
    if args.restart and state_file().exists():
        state_file().rename(state_file().with_name(f"abandoned-{int(time.time())}.json"))
    state = run_plan(conf, local, None, catalog, args.mode, args.runs, args.tasks,
                     args.hours * 3600 if args.hours else None, args.local_agents)
    path = write_report(None, conf=conf, catalog=catalog, state=state)
    print(f"\n{'Finished' if state['complete'] else 'Not finished'}. Report: {path}")
    return 0 if state["complete"] else 4


if __name__ == "__main__":
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
