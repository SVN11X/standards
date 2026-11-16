#!/usr/bin/env python3
"""One supervisor per user: resume every started plan whose process is gone.

A plan needs a resume when its state exists, it has no `finished` mark, the owner has not paused it, work is
still pending and no live process holds its pid file. A pause or cancel the owner asked for is in the control file on
disk, so it survives a restart. Two supervisors never run at once: a lock file with the pid of the first one decides.
Run: python scripts/supervisor.py once | run [--every 60] | install | status
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import execute  # noqa: E402
import orchestrate  # noqa: E402

TERMINAL = {"passed", "failed", "blocked", "cancelled", "skipped"}
TASK_NAME = "StandardsSupervisor"


def alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_file(plan_id: str) -> Path:
    return orchestrate.home() / "autopilot" / f"{plan_id}.pid"


def read_pid(path: Path):
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def needs_resume(plan: dict, is_alive=alive) -> str | None:
    """The reason a plan must be resumed now, or None."""
    pid = plan["plan_id"]
    state = execute.load_state(pid)
    if not state.get("units") or state.get("finished"):
        return None
    control = execute.read_control(pid)
    if control.get("paused"):
        return None
    open_units = [u["id"] for u in plan.get("units", []) if (state["units"].get(u["id"]) or {}).get("status") not in TERMINAL]
    if not open_units:
        return None
    if is_alive(read_pid(pid_file(pid))):
        return None
    return f"{len(open_units)} unit(s) pending and no live process"


def plans() -> list[tuple[Path, dict]]:
    found = []
    for path in sorted((orchestrate.home() / "plans").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("plan_id") and data.get("repo"):
            found.append((path, data))
    return found


def resume(path: Path, plan: dict, spawn=None) -> dict:
    import plan_autopilot
    args = ["run", str(path), "--repo", plan["repo"]]
    return (spawn or plan_autopilot.detach)(args, Path(plan["repo"]), plan["plan_id"])


def tick(spawn=None, is_alive=alive) -> list[dict]:
    """Resume what needs it. Returns one row per plan acted on."""
    rows = []
    for path, plan in plans():
        why = needs_resume(plan, is_alive)
        if why and Path(plan["repo"]).is_dir():
            rows.append({"plan_id": plan["plan_id"], "why": why, **resume(path, plan, spawn)})
    return rows


def lock_path() -> Path:
    return orchestrate.home() / "supervisor.lock"


def take_lock(is_alive=alive) -> bool:
    path = lock_path()
    other = read_pid(path)
    if other and other != os.getpid() and is_alive(other):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def install_command(every_min: int = 5) -> list[str]:
    script = Path(__file__).resolve()
    run = f'"{sys.executable}" "{script}" once'
    return ["schtasks", "/Create", "/F", "/TN", TASK_NAME, "/SC", "MINUTE", "/MO", str(every_min), "/TR", run]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["once", "run", "install", "status"])
    parser.add_argument("--every", type=int, default=60, help="seconds between checks in run")
    args = parser.parse_args(argv)
    if args.command == "install":
        command = install_command()
        if os.name != "nt":
            print("Not Windows. On Windows this runs: " + " ".join(command))
            return 0
        return subprocess.run(command, check=False).returncode
    if args.command == "status":
        for path, plan in plans():
            print(json.dumps({"plan_id": plan["plan_id"], "resume": needs_resume(plan)}))
        return 0
    if not take_lock():
        print("another supervisor is running")
        return 0
    while True:
        for row in tick():
            print(json.dumps(row, ensure_ascii=False), flush=True)
        if args.command == "once":
            return 0
        time.sleep(max(5, args.every))


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
