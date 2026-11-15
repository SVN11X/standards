#!/usr/bin/env python3
"""Standards AI Control: a local dashboard and a compact Claude Code status line.

serve      http://127.0.0.1:8765, JSON at /api/state. It binds to loopback only. It reads state files and
           changes nothing, except the explicit operations of the page: local benchmarks, and Autopilot
           plans, runs, pause and cancel. Each needs the page token.
statusline reads the Claude Code status line JSON on stdin and prints one short line.
A metric a provider does not report is null in the JSON and shown as "Not available" in the page.
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrate  # noqa: E402
import control_jobs  # noqa: E402
import execute  # noqa: E402
import next_actions  # noqa: E402
import resources  # noqa: E402

PAGE = Path(__file__).resolve().parent.parent / "ui" / "control" / "index.html"
STAGES = ["planned", "approved", "running"]
FINAL = {"verified", "failed", "blocked"}
_cpu = {"last": None}


def cpu_percent() -> float | None:
    """Share of busy CPU time since the previous call. The first call has nothing to compare with."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    now = tuple((t.dwHighDateTime << 32) | t.dwLowDateTime for t in (idle, kernel, user))
    before, _cpu["last"] = _cpu["last"], now
    if not before:
        return None
    total = (now[1] - before[1]) + (now[2] - before[2])
    return round(100 * (1 - (now[0] - before[0]) / total), 1) if total else None


def gpu() -> dict | None:
    if not shutil.which("nvidia-smi"):
        return None
    result = orchestrate.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], timeout=10)
    if result["exit"] != 0 or not result["stdout"].strip():
        return None
    name, util, used, total, temp = [p.strip() for p in result["stdout"].splitlines()[0].split(",")]
    return {"name": name, "util_percent": float(util), "vram_used_mib": float(used), "vram_total_mib": float(total),
            "temperature_c": float(temp)}


def process_memory_mb(image: str) -> float | None:
    if os.name != "nt":
        return None
    result = orchestrate.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], timeout=10)
    total = 0.0
    for line in result["stdout"].splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 5 and parts[0].strip('"').lower() == image.lower():
            digits = "".join(ch for ch in parts[4] if ch.isdigit())
            total += int(digits) / 1024 if digits else 0
    return round(total, 1) if total else None


def read_jsonl(path: Path, limit: int = 500) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def run_summary(data: dict) -> dict:
    history = data.get("history") or []
    state = data.get("state", "unknown")
    checks = data.get("checks") or {}
    done = [s for s in STAGES if any(h.get("state") == s for h in history)]
    return {"id": data.get("id"), "executor": data.get("executor"), "model": data.get("model"), "state": state,
            "task": str(data.get("task", "")).splitlines()[0][:120] if data.get("task") else "",
            "started": history[0].get("at") if history else None,
            "seconds": (data.get("executor_result") or {}).get("seconds"),
            "stage_progress": 1.0 if state in FINAL else round(len(done) / (len(STAGES) + 1), 2),
            "checks_passed": sum(1 for v in checks.values() if v == "PASS"), "checks_total": len(checks),
            "changed": len(data.get("changed") or []), "branch": data.get("branch"), "commit": data.get("commit"),
            "note": history[-1].get("note") if history else ""}


def runs(limit: int = 60) -> list[dict]:
    out = []
    for path in sorted((orchestrate.home() / "runs").glob("*.json"))[-limit:]:
        try:
            out.append(run_summary(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return out[::-1]


def telemetry() -> dict:
    rows = read_jsonl(orchestrate.home() / "telemetry.jsonl")
    by_model: dict[str, dict] = {}
    for row in rows:
        key = f"{row.get('provider')}/{row.get('model')}"
        item = by_model.setdefault(key, {"requests": 0, "input": 0, "output": 0, "seconds": 0.0})
        item["requests"] += 1
        item["input"] += row.get("prompt_tokens") or 0
        item["output"] += row.get("completion_tokens") or 0
        item["seconds"] += row.get("seconds") or 0
    return {"recent": rows[-60:], "by_model": by_model}


def seconds_since(stamp: str | None) -> float | None:
    try:
        return round((dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(stamp)).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def plan_view(plan: dict, state: dict, control: dict, events: list[dict]) -> dict:
    """One plan as the page shows it. Every value comes from the plan file, the state file or the event log."""
    entries = state.get("units") or {}
    units = []
    for unit in plan.get("units") or []:
        entry = entries.get(unit["id"]) or {}
        status = entry.get("status", "pending")
        waits = [d for d in unit.get("depends_on", []) if (entries.get(d) or {}).get("status") != execute.DONE]
        units.append({"id": unit["id"], "title": unit.get("title"), "risk": unit.get("risk"), "status": status,
                      "executor": entry.get("executor"), "model": entry.get("model"), "channel": entry.get("channel"),
                      "depends_on": unit.get("depends_on", []), "waits_on": waits if status in ("pending", "skipped") else [],
                      "seconds": entry.get("seconds") if status != "running" else seconds_since(entry.get("at")),
                      "attempts": entry.get("attempts"), "note": entry.get("note"), "commit": entry.get("commit"),
                      "review": (entry.get("review") or {}).get("verdict"), "checks": entry.get("checks")})
    extra = [{"id": uid, "title": "Fix the failed checks", "status": e.get("status"), "model": e.get("model"),
              "executor": e.get("executor"), "channel": e.get("channel"), "depends_on": [], "waits_on": [],
              "seconds": e.get("seconds"), "attempts": e.get("attempts"), "note": e.get("note"), "risk": None,
              "commit": e.get("commit"), "review": (e.get("review") or {}).get("verdict"), "checks": e.get("checks")}
             for uid, e in entries.items() if uid not in {u["id"] for u in plan.get("units") or []}]
    publication = state.get("publication") or {}
    approvals = [f"{u['id']} is {u['risk']}: the owner reviews it before a merge" for u in units if u["risk"] in ("yellow", "red")]
    if publication.get("pr") and not publication.get("auto_merge_requested"):
        approvals.append("the pull request waits for the owner to merge it")
    done = sum(1 for u in units if u["status"] == execute.DONE)
    return {"plan_id": plan.get("plan_id"), "goal": str(plan.get("goal", "")).splitlines()[0][:200] if plan.get("goal") else "",
            "planner": {k: (plan.get("planner") or {}).get(k) for k in ("backend", "model", "tier", "reasons", "repair_calls", "fixes")},
            "paused": bool(control.get("paused")), "cancel": control.get("cancel") or [], "finished": state.get("finished"),
            "started": bool(entries), "done": done, "total": len(units), "units": units + extra,
            "metrics": state.get("metrics"), "publication": publication, "approvals": approvals,
            "orphans": state.get("orphans") or [], "events": events[-40:]}


def autopilot(limit: int = 8) -> dict:
    """Plans, newest first, with the state of every unit. Reading it starts nothing and asks no model."""
    home = orchestrate.home()
    plans = []
    for path in sorted((home / "plans").glob("auto-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        plan_id = str(plan.get("plan_id"))
        plans.append(plan_view(plan, execute.load_state(plan_id), execute.read_control(plan_id),
                               read_jsonl(execute.events_file(plan_id), 200)))
    agents = [{"plan_id": p["plan_id"], **u} for p in plans for u in p["units"] if u["status"] == "running"]
    limits = (orchestrate.policy().get("concurrency") or {})
    return {"plans": plans, "agents": agents, "limits": {"max_parallel": limits.get("max_parallel"), "pools": limits.get("pools"),
                                                          "tests": limits.get("tests")},
            "jobs": Handler.autopilot.snapshot() if Handler.autopilot else [], "planners": list(control_jobs.PLANNERS)}


def log_tail(name: str, lines: int = 80) -> list[str]:
    paths = {"colibri": Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "colibri" / "logs" / "serve.log",
             "colibri-install": Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "colibri" / "logs" / "install.log"}
    path = paths.get(name)
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:] if path and path.exists() else []


def collect(repo: Path) -> dict:
    conf, local = orchestrate.policy(), orchestrate.local_config()
    ollama = orchestrate.detect_ollama(conf["executors"]["ollama"])
    colibri = orchestrate.detect_colibri(conf["executors"]["colibri"])
    mode, mode_source = orchestrate.cost_mode(conf, local)
    cls, _ = orchestrate.privacy_class(repo, conf, local)
    total = orchestrate.memory_bytes()
    free = resources.ram_free_bytes()
    tasks = runs()
    return {"time": orchestrate.now(), "providers": {"ollama": ollama, "colibri": colibri,
                                                       "opencode": orchestrate.version_of(["opencode", "--version"])},
            "resources": {"cpu_percent": cpu_percent(), "ram_total_bytes": total, "ram_free_bytes": free, "gpu": gpu(),
                          "colibri_engine_mb": process_memory_mb("qwen36.exe"), "ollama_mb": process_memory_mb("ollama.exe")},
            "tasks": tasks,
            "counts": {state: sum(1 for t in tasks if t["state"] == state) for state in
                       ["planned", "approved", "running", "verified", "failed", "blocked"]},
            "telemetry": telemetry(),
            "cost": {"mode": mode, "mode_source": mode_source, "privacy": cls, "api_cost_usd": 0.0 if mode == "local-only" else None,
                     "note": "0 API cost is guaranteed only in local-only mode; electricity is excluded. "
                              "Other modes require provider-specific accounting."},
            "bench": orchestrate.summarize_bench(orchestrate.bench_rows())[:80],
             "next_actions": next_actions.snapshot(),
             "autopilot": autopilot(),
             "operations": Handler.manager.snapshot() if Handler.manager else {"active": False, "job": None, "log": ""}}


class Handler(http.server.BaseHTTPRequestHandler):
    repo = Path.cwd()
    manager: control_jobs.JobManager | None = None
    autopilot: control_jobs.AutopilotManager | None = None
    token = ""

    def send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def safe_host(self) -> bool:
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",
                                            f"localhost:{self.server.server_port}"}

    def do_GET(self):  # noqa: N802
        if not self.safe_host():
            self.send(403, b"loopback host required", "text/plain")
            return
        path, _, query = self.path.partition("?")
        if path == "/":
            # A per-process token is readable only from this loopback-served page.
            content = PAGE.read_text(encoding="utf-8").replace(
                "const NA=", "const CONTROL_TOKEN=" + json.dumps(self.token) + ";const NA=", 1)
            self.send(200, content.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            self.send(200, json.dumps(collect(self.repo), default=str).encode(), "application/json")
        elif path == "/api/logs":
            name = dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("name", "")
            self.send(200, json.dumps({"name": name, "lines": log_tail(name)}).encode(), "application/json")
        else:
            self.send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        expected = {f"http://127.0.0.1:{self.server.server_port}",
                    f"http://localhost:{self.server.server_port}"}
        authorized = (self.safe_host() and self.headers.get("Origin") in expected
                      and bool(self.token) and secrets.compare_digest(
                          self.headers.get("X-Standards-Token", ""), self.token))
        if not authorized:
            self.send(403, b"forbidden", "text/plain")
            return
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send(415, b"JSON required", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            # An instruction may hold 6000 characters, each up to four bytes.
            if not 0 < length <= (32768 if self.path == "/api/autopilot/plan" else 1024):
                raise ValueError("request too large or empty")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or self.manager is None:
                raise ValueError("invalid operation")
            if self.path.startswith("/api/autopilot/"):
                result = self.autopilot_action(self.path.rsplit("/", 1)[1], data)
            elif self.path == "/api/jobs/start":
                kind = data.get("kind")
                if kind == "bench-run" and data.get("confirmed") is not True:
                    raise ValueError("explicit benchmark confirmation required")
                result = self.manager.start(kind)
            elif self.path == "/api/jobs/cancel":
                result = self.manager.cancel(data.get("id", ""))
            else:
                self.send(404, b"not found", "text/plain")
                return
        except (ValueError, RuntimeError, FileNotFoundError, OSError) as error:
            self.send(409, json.dumps({"error": str(error)[:240]}).encode(), "application/json")
            return
        self.send(200, json.dumps(result).encode(), "application/json")

    def autopilot_action(self, action: str, data: dict) -> dict:
        """plan and start run a bounded job. pause, unpause and cancel only write the plan's control file."""
        if self.autopilot is None:
            raise ValueError("invalid operation")
        if action == "plan":
            return self.autopilot.plan(str(data.get("instruction", "")), str(data.get("planner", "auto")))
        plan_id = str(data.get("plan_id", ""))
        if not control_jobs.PLAN_ID.fullmatch(plan_id) or not (orchestrate.home() / "plans" / f"{plan_id}.json").is_file():
            raise ValueError("unknown plan")
        if action == "start":
            if data.get("confirmed") is not True:
                raise ValueError("explicit confirmation required")
            return self.autopilot.start(plan_id, str(data.get("publish", "none")))
        if action in ("pause", "unpause"):
            return execute.set_control(plan_id, paused=action == "pause")
        if action == "cancel":
            plan = json.loads((orchestrate.home() / "plans" / f"{plan_id}.json").read_text(encoding="utf-8"))
            if data.get("unit") not in {u["id"] for u in plan.get("units") or []}:
                raise ValueError("unknown unit")
            return execute.set_control(plan_id, cancel=str(data["unit"]))
        raise ValueError("invalid operation")

    def log_message(self, *args):
        pass


def statusline() -> str:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    conf = orchestrate.policy()
    ollama = orchestrate.detect_ollama(conf["executors"]["ollama"], timeout=0.5)
    colibri = orchestrate.detect_colibri(conf["executors"]["colibri"], timeout=0.5)
    active = [t for t in runs(10) if t["state"] in {"planned", "approved", "running"}]
    name = (data.get("model") or {}).get("display_name") or "Claude"
    return (f"{name} | ollama {'up' if ollama['up'] else 'down'} | colibri {'up' if colibri['up'] else 'down'}"
            f" | tasks running {len(active)} | plan units running {len(autopilot(3)['agents'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--repo", type=Path, default=Path.cwd())
    sub.add_parser("statusline")
    sub.add_parser("state")
    args = parser.parse_args(argv)
    if args.command == "statusline":
        print(statusline())
        return 0
    if args.command == "state":
        print(json.dumps(collect(Path.cwd()), indent=2, default=str))
        return 0
    Handler.repo = args.repo
    Handler.manager = control_jobs.JobManager(args.repo, orchestrate.home() / "control-jobs")
    Handler.autopilot = control_jobs.AutopilotManager(args.repo, orchestrate.home() / "control-jobs",
                                                      orchestrate.home() / "plans")
    Handler.token = secrets.token_urlsafe(32)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Standards AI Control on http://127.0.0.1:{args.port}", flush=True)
    threading.Thread(target=collect, args=(args.repo,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
