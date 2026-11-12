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
        origin = (item.get("provider"), item["executor"], item.get("status"))
        key = (*origin, item["why"], item.get("fix")) if shared else (*origin, item["model"], item["why"])
        if key in merged:
            merged[key]["names"].append(item["model"])
        else:
            merged[key] = {**item, "names": [item["model"]]}
    for item in merged.values():
        count = len(item["names"])
        place = item.get("provider") or item["executor"]
        item["label"] = f"{place} {item['names'][0]}" if count == 1 else \
            f"{place}, {count} models ({', '.join(str(n) for n in item['names'][:3])}{'...' if count > 3 else ''})"
    return list(merged.values())


# What can be tested

STATUS_TEXT = {"eligible": "eligible", "not-installed": "not installed", "unavailable": "not reachable", "not-chat": "not a chat model",
               "resources": "not enough resources", "blocked": "blocked in the catalog", "owner-check": "waiting for your check",
               "no-key": "no key", "no-adapter": "no adapter", "retired": "retired", "unknown-cost": "cost unknown", "paid": "not free",
               "privacy": "privacy does not allow it", "cost-mode": "outside the cost mode", "discovery-failed": "could not be listed"}


def discover_providers(conf: dict, local: dict, mode: str | None = None, known: dict | None = None) -> dict:
    """Ask every provider that has an adapter, a free offer and a key for its models. Nothing is asked in local-only mode."""
    known = known if known is not None else orchestrate.providers.load()
    mode_name, _ = orchestrate.cost_mode(conf, local, mode)
    listings = {}
    if conf["cost"]["modes"][mode_name]["remote_free"] != "allow":
        return listings
    for name, pconf in known.items():
        free = pconf.get("cost") in conf["cost"]["free_categories"]
        if pconf.get("status") == "adapter" and free and not orchestrate.providers.missing_env(pconf):
            listings[name] = orchestrate.providers.refresh(name, pconf)
    return listings


def local_coverage(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None, folder: Path, consent: dict) -> list[dict]:
    """Every model the local Ollama lists, plus the catalog entries that are not installed."""
    oconf = conf["executors"]["ollama"]
    info = caps.get("ollama") or {}
    url = info.get("url") or oconf.get("url")
    named = [e for e in catalog.get("models") or [] if e.get("executor") == "ollama"]
    out = []
    if not info.get("up"):
        return [{"provider": "ollama-local", "model": e["id"], "endpoint": url, "executor": "ollama", "remote": False,
                 "status": "unavailable", "why": "Ollama is not running, start it first", "fix": None} for e in named]
    for found in orchestrate.classify_ollama(conf, caps, catalog):
        name = found["model"]
        record = {"provider": found["provider"], "model": name, "endpoint": found["endpoint"], "executor": "ollama",
                  "remote": found["remote"], "size": found["size"], "in_catalog": found["in_catalog"], "fix": None, "tasks": [], "cannot": []}
        ok, why, code = orchestrate.explain("ollama", name, folder, conf, consent, mode, caps, catalog)
        if found["remote"] or not ok:
            record.update(status=code if not ok else "unknown-cost", why=why)
        elif found["blocked"]:
            record.update(status="blocked", why=str(found["blocked"]))
        elif found["kind"] == "embedding":
            record.update(status="not-chat", why="embedding model, it serves search only")
        elif found["fits"] is False:
            record.update(status="resources", why=found["memory"])
        else:
            for task, needs in bench_tasks.CHAT_TASKS.items():
                missing = [need for need in needs if found[need] is not True]
                if not missing:
                    record["tasks"].append(task)
                elif any(found[need] is None for need in missing):
                    record["cannot"].append(f"{task}: capability not evaluated, Ollama does not report {', '.join(missing)} for it")
                else:
                    record["cannot"].append(f"{task}: the model does not report {', '.join(missing)}")
            record.update(status="eligible", why=("in the catalog" if found["in_catalog"] else "found installed, not in the catalog")
                          + (f", memory {found['memory']}" if found["fits"] else ", memory not measured"))
        out.append(record)
    installed = {record["model"] for record in out}
    for entry in named:
        if not orchestrate.is_installed(entry["id"], info) and entry["id"] not in installed:
            out.append({"provider": "ollama-local", "model": entry["id"], "endpoint": url, "executor": "ollama", "remote": False,
                        "status": "not-installed", "why": "not installed", "fix": f"ollama pull {entry['id']}",
                        "note": f"size and license: {entry.get('source') or 'see the model page'}"})
    return out


def opencode_coverage(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None, folder: Path, consent: dict,
                      local_ready: list[str], local_agents: bool) -> list[dict]:
    """The free models served through OpenCode: the catalog entries and the ones the owner checked."""
    opencode = caps.get("opencode") or {}
    offered = opencode.get("models") or []
    fresh = orchestrate.fresh_free_models(local, conf)
    entries = [e for e in catalog.get("models") or [] if e.get("executor") == "opencode"]
    known_ids = {e["id"] for e in entries}
    providers_known = set(orchestrate.providers.load())
    entries += [{"id": item["id"], "provider": "unlisted"} for item in fresh
                if not item["id"].startswith("ollama/") and item["id"].split("/")[0] not in providers_known
                and item["id"].split("/")[-1] not in known_ids]
    out = []
    for entry in entries:
        short = entry["id"].split("/")[-1]
        listed = next((name for name in offered if name.split("/")[-1] == short), None)
        mine = next((item["id"] for item in fresh if item["id"].split("/")[-1] == short), None)
        name = mine or listed or short
        use = DATA_TEXT[orchestrate.data_use(entry)]
        record = {"provider": entry.get("provider", "unlisted"), "model": name, "endpoint": "through the OpenCode client",
                  "executor": "opencode", "remote": True, "limit": entry.get("requests_per_day"), "fix": None, "tasks": [], "cannot": []}
        if not opencode.get("path"):
            record.update(status="unavailable", why="OpenCode is not installed")
        elif offered and not listed:
            record.update(status="retired", why="`opencode models` does not list it any more")
        elif not mine:
            record.update(status="owner-check", why=f"needs your check that it is still free. It {use}",
                          fix=consent_command(listed or f"<its name in `opencode models`, ending in {short}>"),
                          note=f"read first: {entry.get('source') or 'the provider page'}")
        else:
            ok, why, code = orchestrate.explain("opencode", name, folder, conf, consent, mode, caps, catalog)
            if ok:
                cannot = (["vision: capability not evaluated, sending an image through OpenCode is not confirmed"]
                          if "vision" in (entry.get("capabilities") or []) else [])
                record.update(status="eligible", why=use, tasks=list(bench_tasks.AGENT_TASKS), cannot=cannot, data=use)
            else:
                record.update(status=code, why=why)
        out.append(record)
    if local_agents and opencode.get("path"):
        out += [{"provider": "ollama-local", "model": f"ollama/{name}", "endpoint": "through the OpenCode client", "executor": "opencode",
                 "remote": False, "status": "eligible", "why": "local model as a coding agent", "fix": None,
                 "tasks": list(bench_tasks.AGENT_TASKS), "cannot": []} for name in local_ready]
    return out


def provider_coverage(conf: dict, local: dict, mode: str | None, folder: Path, consent: dict, listings: dict,
                      known: dict | None = None) -> list[dict]:
    """Every provider of settings/providers.yml and every model it lists, each with one status and its reason."""
    known = known if known is not None else orchestrate.providers.load()
    mode_name, mode_source = orchestrate.cost_mode(conf, local, mode)
    out = []
    for name, pconf in known.items():
        label = pconf.get("name", name)
        base = {"provider": name, "model": "(the service)", "endpoint": pconf.get("base_url") or "-", "executor": "api", "remote": True,
                "fix": None, "tasks": [], "cannot": []}
        cost = pconf.get("cost") or "unknown"
        said = pconf.get("confirmed") or pconf.get("notes") or ""
        if pconf.get("status") == "retired":
            out.append({**base, "status": "retired", "why": said})
        elif pconf.get("status") != "adapter":
            out.append({**base, "status": "no-adapter", "why": pconf.get("notes") or said})
        elif cost not in conf["cost"]["free_categories"]:
            out.append({**base, "status": "unknown-cost" if cost == "unknown" else "paid", "why": f"{label} is listed as {cost} cost. {said}"})
        elif conf["cost"]["modes"][mode_name]["remote_free"] != "allow":
            out.append({**base, "status": "cost-mode", "why": f"cost mode {mode_name} ({mode_source}) sends nothing to a provider"})
        elif orchestrate.providers.missing_env(pconf):
            lacking = orchestrate.providers.missing_env(pconf)
            out.append({**base, "status": "no-key", "why": f"missing in the environment: {', '.join(lacking)}. It is pending and was not called",
                        "fix": f"set {', '.join(lacking)} in the environment of this window"})
        else:
            listing = listings.get(name) or {}
            if listing.get("error") or "models" not in listing:
                error = listing.get("error") or {"kind": "not asked", "message": "its models were not listed in this run"}
                out.append({**base, "status": "discovery-failed", "why": f"{error['kind']}: {error['message']}"})
                continue
            features = pconf.get("features") or []
            for model in listing["models"]:
                full = f"{name}/{model['id']}"
                record = {**base, "model": full, "limit": (pconf.get("limits") or {}).get("requests_per_day")}
                if model["kind"] != "chat":
                    record.update(status="not-chat", why="a router, not one model" if model["kind"] == "router" else "not a chat model by its name or its outputs")
                elif not model.get("active", True):
                    record.update(status="retired", why=f"{label} lists it as not active")
                else:
                    ok, why, code = orchestrate.explain("api", full, folder, conf, consent, mode)
                    if not ok:
                        record.update(status=code, why=why)
                        if code == "owner-check":
                            record["fix"] = f"python scripts/orchestrate.py consent --free-provider {name}"
                            record["note"] = f"read first: {(pconf.get('sources') or ['the provider page'])[0]}"
                    else:
                        tasks, cannot = [], []
                        for task, needs in bench_tasks.CHAT_TASKS.items():
                            unsent = [need for need in needs if need not in features]
                            unlisted = [need for need in needs if model.get(need) is False]
                            if unsent:
                                cannot.append(f"{task}: capability not evaluated, the adapter does not send {', '.join(unsent)} to {label}")
                            elif unlisted:
                                cannot.append(f"{task}: {label} does not list it with {', '.join(unlisted)}")
                            else:
                                tasks.append(task)
                        record.update(status="eligible", why=why, tasks=tasks, cannot=cannot, data=DATA_TEXT[orchestrate.data_use(pconf)])
                out.append(record)
    return out


def coverage(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None = None, local_agents: bool = False,
             listings: dict | None = None, known: dict | None = None) -> list[dict]:
    """Everything that was found, local and remote. Nothing is counted against a fixed list."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        consent = orchestrate.bench_local(folder, local)
        found = local_coverage(conf, local, caps, catalog, mode, folder, consent)
        ready = [r["model"] for r in found if r["status"] == "eligible"]
        found += opencode_coverage(conf, local, caps, catalog, mode, folder, consent, ready, local_agents)
        found += provider_coverage(conf, local, mode, folder, consent, listings or {}, known)
    return found


def candidates(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None = None, local_agents: bool = False,
               listings: dict | None = None, known: dict | None = None) -> tuple[list[dict], list[dict]]:
    """The coverage split into what is ready to test and what was left out."""
    found = coverage(conf, local, caps, catalog, mode, local_agents, listings, known)
    return [r for r in found if r["status"] == "eligible"], [r for r in found if r["status"] != "eligible"]


def build_plan(ready: list[dict], conf: dict, runs: int | None = None, tasks: list[str] | None = None,
               models: list[str] | None = None, quotas: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Baselines first, then each local model with all its work, then the remote models. Returns the steps and what a budget cut.

    A coding agent gets a number of sessions per model. A provider API gets a number of requests for the whole account.
    """
    settings = conf["analysis"]
    runs = runs or settings["runs"]
    wanted = lambda task: not tasks or task in tasks  # noqa: E731
    steps = [{"key": f"{task}|tools|-|1", "task": task, "executor": "tools", "model": None, "run": 1, "limit_s": 60,
              "remote": False, "provider": "program"} for task in sorted(bench_tasks.BASELINES) if wanted(task)]
    cut, spent = [], {}
    known = orchestrate.providers.load()
    soon: dict[tuple, str] = {}
    for bench, executor, model, expires in orchestrate.expiring_evidence(conf, conf["limits"].get("refresh_before_days", 7)):
        soon[(executor, model, bench)] = expires
    lapsing = {(executor, model) for executor, model, _ in soon}
    for item in sorted(ready, key=lambda r: ((r["executor"], r["model"]) not in lapsing, r["remote"], r["executor"] == "api")):
        if models and not any(text.lower() in item["model"].lower() for text in models):
            continue
        mine = [task for task in item["tasks"] if wanted(task)]
        mine.sort(key=lambda task: (item["executor"], item["model"], task) not in soon)
        agent_limit = conf["limits"]["opencode_timeout_s"] + 120
        api = item["executor"] == "api"
        allowed, unit = None, "sessions this model gets"
        if api:
            day = ((known.get(item["provider"]) or {}).get("limits") or {}).get("requests_per_day")
            allowed = int(day * settings["api_budget_share"]) if day else settings["api_requests_when_unknown"]
            left = (quotas or {}).get(item["provider"])
            allowed = min(allowed, left) if isinstance(left, int) else allowed
            unit = f"requests {item['provider']} gives this account"
        elif item["remote"]:
            per_day = item.get("limit")
            allowed = per_day // settings["requests_per_agent_run"] if per_day else settings["remote_runs_per_model"]
        bucket = item["provider"] if api else f"{item['executor']}:{item['model']}"
        dropped = 0
        for number in range(1, runs + 1):
            for task in mine:
                cost = bench_tasks.request_estimate(task) if api else 1
                if allowed is not None and spent.get(bucket, 0) + cost > allowed:
                    dropped += 1
                    continue
                spent[bucket] = spent.get(bucket, 0) + cost
                steps.append({"key": f"{task}|{item['executor']}|{item['model']}|{number}", "task": task,
                              "executor": item["executor"], "model": item["model"], "run": number, "remote": item["remote"],
                              "provider": item["provider"], "refresh": soon.get((item["executor"], item["model"], task)),
                              "own_limit": bool(item.get("limit")) and not api, "requests": cost if api else None,
                              "limit_s": agent_limit if task in bench_tasks.AGENT_TASKS else settings["chat_run_timeout_s"]})
        if dropped:
            cut.append({"executor": item["executor"], "model": item["model"], "provider": item["provider"], "fix": None,
                        "status": "budget", "why": f"{dropped} runs left out, over the {allowed} {unit} in one night"})
    return steps, cut


def plan_lines(steps: list[dict], cut: list[dict], left_out: list[dict], conf: dict, mode: str, done: dict | None = None) -> list[str]:
    done = done or {}
    todo = [s for s in steps if s["key"] not in done]
    budget = conf["analysis"]["night_budget_s"]
    longest = sum(s["limit_s"] for s in todo)
    lines = [f"Cost mode: {mode}. Steps: {len(todo)} to run, {len(steps) - len(todo)} already done."]
    lines.append(f"Longest it can take: {hours(min(longest, budget))}. Every time limit added up is {hours(longest)} "
                 f"and one run stops by itself after {hours(budget)}. It normally ends much sooner.")
    for title, pick in (("Local, one model at a time:", lambda s: not s["remote"]),
                        ("Remote free models as a coding agent, sessions this night:", lambda s: s["remote"] and s["executor"] != "api"),
                        ("Remote free models by API, requests this night:", lambda s: s["executor"] == "api")):
        group: dict[str, list[dict]] = {}
        for step in todo:
            if pick(step) and step["executor"] != "tools":
                group.setdefault(f"{step['executor']}:{step['model']}", []).append(step)
        if group:
            lines.append(title)
            for name, items in group.items():
                requests = sum(s.get("requests") or 0 for s in items)
                lines.append(f"  {name}: {len(items)} runs of {', '.join(sorted({s['task'] for s in items}))}"
                             + (f", about {requests} requests" if requests else ""))
    again = sorted({(s["executor"], s["model"], s["task"], s["refresh"]) for s in todo if s.get("refresh")})
    if again:
        lines.append("Measured again before the evidence lapses, first in the plan:")
        lines += [f"  {executor}:{model} on {task}, expires {expires}" for executor, model, task, expires in again]
    sessions = sum(1 for s in todo if s["remote"] and s["executor"] != "api")
    requests = sum(s.get("requests") or 0 for s in todo)
    if sessions or requests:
        lines.append(f"Remote in total: {sessions} agent sessions, each of several requests, and about {requests} API requests.")
    else:
        lines.append("Remote: none. Nothing leaves this machine.")
    if cut:
        lines.append("Cut by a budget:")
        lines += [f"  {item['label']}: {item['why']}" for item in grouped(cut)]
    if left_out:
        places: dict[str, dict[str, int]] = {}
        for item in left_out:
            counts = places.setdefault(item.get("provider") or item["executor"], {})
            counts[item.get("status") or "left out"] = counts.get(item.get("status") or "left out", 0) + 1
        lines.append("Not in the plan, by provider. The reason and the fix for each one: python scripts/analyze.py prepare")
        lines += [f"  {place}: " + ", ".join(f"{count} {STATUS_TEXT.get(status, status)}" for status, count in counts.items())
                  for place, counts in places.items()]
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
             local_agents: bool = False, say=print, models: list[str] | None = None, listings: dict | None = None,
             known: dict | None = None) -> dict:
    """Run every step that is not done yet. One failing model or provider never stops the others."""
    conf = conf or orchestrate.policy()
    local = local if local is not None else orchestrate.local_config()
    catalog = catalog if catalog is not None else orchestrate.model_catalog()
    mode_name, _ = orchestrate.cost_mode(conf, local, mode)
    caps = caps or probe(conf, mode_name)
    listings = listings if listings is not None else discover_providers(conf, local, mode, known)
    ready, left_out = candidates(conf, local, caps, catalog, mode, local_agents, listings, known)
    steps, cut = build_plan(ready, conf, runs, tasks, models, account_quotas(listings, known))
    state = load_state(mode_name)
    state["left_out"] = [*left_out, *cut]
    state["cannot"] = [{"model": f"{r['provider']} {r['model']}", "task": c} for r in ready for c in r["cannot"]]
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
            one = f"{step['executor']}:{step['model']}"
            scope = one if step.get("own_limit") else step["provider"]
            halted = next((name for name in (one, scope) if name in state["stopped"]), None)
            if step["remote"] and halted:
                state["done"][step["key"]] = {"skipped": f"{state['stopped'][halted]}, so it was not used again this night"}
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
                if step["remote"] and row.get("rate_limited"):
                    target = one if row.get("stop_scope") == "model" else scope
                    state["stopped"][target] = f"{target} stopped answering for free ({row['skipped'][:80]})"
                    say(f"stopped: {target} is not used again this night")
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
    state["planned"] = len(steps)
    if state["complete"]:
        state["finished"] = orchestrate.now()
        orchestrate.write_json(state_file().with_name(f"{state['id']}.json"), state)
        state_file().unlink(missing_ok=True)
    return state


def account_quotas(listings: dict, known: dict | None = None) -> dict:
    """Free requests each provider reports as left today, where an endpoint reports it. A failed check plans nothing for it."""
    known = known if known is not None else orchestrate.providers.load()
    quotas = {}
    for name, listing in (listings or {}).items():
        if listing.get("error") or (known.get(name) or {}).get("preflight") == "owner":
            continue
        try:
            answer = orchestrate.providers.preflight(name, known[name])
        except orchestrate.providers.ProviderError:
            quotas[name] = 0
            continue
        if not answer["ok"]:
            quotas[name] = 0
        elif answer.get("remaining") is not None:
            quotas[name] = answer["remaining"]
    return quotas


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
    if executor == "api":
        pconf = orchestrate.providers.load().get(orchestrate.providers.split(model or "")[0]) or {}
        return DATA_TEXT[orchestrate.data_use(pconf)], "measured here, by API"
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
        known = orchestrate.providers.load()

        def data_rank(executor: str, model: str) -> int:
            if executor == "opencode":
                return orchestrate.DATA_RANK[orchestrate.data_use(orchestrate.catalog_entry(executor, model, catalog))]
            if executor == "api":
                return orchestrate.DATA_RANK[orchestrate.data_use(known.get(orchestrate.providers.split(model)[0]))]
            return 0
        ranked = sorted(passed.items(), key=lambda kv: (data_rank(*kv[0]), kv[1]["p50_s"]))
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
    outdated = len(rows) - len(orchestrate.current_rows(rows))
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
    how = {"api": "API", "agent": "full agent", "program": "program"}
    for title, note, wanted in (
            ("Inference by API or by a program", "One request per item, straight to the model. This measures the model, not an agent around it.",
             lambda task: task not in bench_tasks.AGENT_TASKS),
            ("Full agent", "A coding agent works in a repository with its own tools. This measures the agent and the model together, "
             "so it is not comparable with the runs above.", lambda task: task in bench_tasks.AGENT_TASKS)):
        names = sorted({row["task"] for row in summary if wanted(row["task"])})
        if not names:
            continue
        out += [f"## {title}", "", note, ""]
        for task in names:
            out += [f"### {task}", ""]
            body = []
            for row in sorted((r for r in summary if r["task"] == task), key=lambda r: (-r["pass_rate"], r["p50_s"] or 9e9)):
                use, evidence = describe(row["executor"], row["model"], catalog)
                ok = row["runs"] >= limits["bench_min_runs"] and row["pass_rate"] >= limits["bench_min_pass_rate"]
                body.append([row["executor"], row["model"], how.get(row.get("via"), row.get("via")),
                             f"{round(row['pass_rate'] * row['runs'])} of {row['runs']}", row["p50_s"], row["errors"], use, evidence,
                             "yes" if ok else "no"])
            out += table(["Executor", "Model", "How", "Accepted runs", "Median s to an accepted result", "Errors", "Data use", "Evidence",
                          "Passed the threshold"], body) + [""]
            if task == "design-judge-sample":
                out += ["These pairs are a made-up sample that only proves the mechanism. They are nobody's taste and never decide who reviews design.", ""]
    if outdated:
        out += [f"{outdated} older runs are left out: the rule that graded them was corrected since, so they no longer count.", ""]
    out += ["A model and a task that do not appear above were not measured. That is not a score of zero: the reason is under Not tested or not evaluated.", ""]
    out += ["## Proposed split", "", "The router already reads this history: among the models you allowed, it takes the one that "
            "passed and is fastest. What stays your decision is which models you allow, and the order in `settings/orchestration.yml`.", ""]
    out += proposal(conf, catalog) + [""]
    failed = [row for row in summary if row["executor"] != "tools"
              and not (row["runs"] >= limits["bench_min_runs"] and row["pass_rate"] >= limits["bench_min_pass_rate"])]
    out += ["## Below the threshold", ""]
    out += [f"- {row['executor']} `{row['model']}` on `{row['task']}`: {round(row['pass_rate'] * row['runs'])} of {row['runs']} accepted. "
            + (f"Most common failure: {row['why_failed']}." if row["why_failed"] else "Too few runs so far.") for row in failed] or ["- None."]
    out += ["", "## Not tested or not evaluated", ""]
    skipped = []
    if state:
        skipped += [f"- {item['label']}: [{STATUS_TEXT.get(item.get('status'), item.get('status') or 'left out')}] {item['why'].rstrip('.')}."
                    + (f" To add it: `{item['fix']}`." if item.get("fix") else "") for item in grouped(state.get("left_out") or [])]
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


def prepare_lines(conf: dict, local: dict, caps: dict, catalog: dict, mode: str | None = None, listings: dict | None = None,
                  known: dict | None = None, every: bool = False) -> list[str]:
    """The coverage in words: every model found, by provider, model and endpoint, with its state and the reason."""
    mode_name, source = orchestrate.cost_mode(conf, local, mode)
    found = coverage(conf, local, caps, catalog, mode, False, listings, known)
    info, opencode = caps.get("ollama") or {}, caps.get("opencode") or {}
    lines = [f"Cost mode: {mode_name} ({source}).",
             f"Ollama at {info.get('url')}: {'running' if info.get('up') else 'not running'}. "
             f"OpenCode: {opencode.get('version') or ('installed' if opencode.get('path') else 'not installed')}.", "",
             "Found, by provider:"]
    places: dict[str, dict[str, int]] = {}
    for record in found:
        counts = places.setdefault(f"{record['provider']} ({record['endpoint']})", {})
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    for place, counts in places.items():
        lines.append(f"  {place}: " + ", ".join(f"{count} {STATUS_TEXT.get(status, status)}" for status, count in counts.items()))
    ready = [r for r in found if r["status"] == "eligible"]
    lines += ["", "Eligible, ready to test:"]
    for item in ready:
        size = f", {item['size'] / 1e9:.1f} GB" if item.get("size") else ""
        lines.append(f"  {item['provider']}  {item['model']}{size}  at {item['endpoint']}. {item['why']}. Tasks: {', '.join(item['tasks']) or 'none'}")
        lines += [f"      {text}" for text in item["cannot"]]
    if not ready:
        lines.append("  nothing yet")
    rest = [r for r in found if r["status"] != "eligible"]
    lines += ["", "Not eligible, with the reason. Nothing here runs by itself:"]
    for item in (rest if every else grouped(rest)):
        label = item.get("label") or f"{item['provider']} {item['model']}"
        lines.append(f"  {label}: [{STATUS_TEXT.get(item['status'], item['status'])}] {item['why']}")
        if item.get("note"):
            lines.append(f"      {item['note']}")
        if item.get("fix"):
            lines.append(f"      {item['fix']}")
    if not every and any(len(item["names"]) > 3 for item in grouped(rest)):
        lines.append("  Groups show their first three names. Add --all for one line per model, or --json for the data.")
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
        if name == "prepare":
            p.add_argument("--all", action="store_true", help="one line per model instead of groups")
            p.add_argument("--json", action="store_true", help="print every model found as data")
        if name != "prepare":
            p.add_argument("--models", nargs="*", help="only models whose name contains one of these texts")
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
    caps = probe(conf, mode_name)
    listings = discover_providers(conf, local, args.mode)
    if args.command == "prepare":
        if args.json:
            print(json.dumps(coverage(conf, local, caps, catalog, args.mode, False, listings), indent=2, ensure_ascii=False))
        else:
            print("\n".join(prepare_lines(conf, local, caps, catalog, args.mode, listings, every=args.all)))
        return 0
    if args.command == "plan":
        ready, left_out = candidates(conf, local, caps, catalog, args.mode, args.local_agents, listings)
        steps, cut = build_plan(ready, conf, args.runs, args.tasks, args.models, account_quotas(listings))
        state = load_state(mode_name) if state_file().exists() else {"done": {}}
        print("\n".join(plan_lines(steps, cut, left_out, conf, mode_name, state["done"])))
        print("\nNothing ran. To run it: python scripts/analyze.py run")
        return 0
    if args.restart and state_file().exists():
        state_file().rename(state_file().with_name(f"abandoned-{int(time.time())}.json"))
    state = run_plan(conf, local, caps, catalog, args.mode, args.runs, args.tasks,
                     args.hours * 3600 if args.hours else None, args.local_agents, models=args.models, listings=listings)
    path = write_report(None, conf=conf, catalog=catalog, state=state)
    if not state.get("planned"):
        print("\nNothing ran: no model was ready to test. The lines above say why, and "
              "python scripts/analyze.py prepare gives the fix for each one.")
    print(f"\n{'Finished' if state['complete'] else 'Not finished'}. Report: {path}")
    return 0 if state["complete"] else 4


if __name__ == "__main__":
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
