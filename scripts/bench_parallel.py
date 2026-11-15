#!/usr/bin/env python3
"""Measure the executor loop at several concurrency levels on the same plan, sequential first.

It answers one question with numbers from this machine: does running units at once shorten the whole
plan, and does it add failures, conflicts or retries. The agents are simulated: a process that waits
`--latency` seconds and edits its file, so no model, quota or graphics card is used. Everything around
the agent is the real code path: a worktree per unit, the scope and protected-file checks, the test
command, the secret scan, the review step, the integration queue and the saved state.

The result says what the scheduler gains for a given agent latency. It says nothing about how fast a
model is. Measure real agents with `execute.py report`, which prints the same metrics for a real run.

Usage: python scripts/bench_parallel.py [--units 6] [--latency 2.0] [--test-s 0.3] [--levels 1 2 3] [--out FILE]
       python scripts/bench_parallel.py --plan PLAN.json --repo DIR [--latency 2.0] [--levels 1 2]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execute  # noqa: E402
import orchestrate  # noqa: E402
import workplan  # noqa: E402

AGENT = r'''
import sys, time
from pathlib import Path
time.sleep(float(sys.argv[1]))
task = Path(".delegate-task.md").read_text(encoding="utf-8")
line = next(l for l in task.splitlines() if l.startswith("- You may change only: "))
for name in line[len("- You may change only: "):].rstrip(".").split(", "):
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    mark = "<!-- simulated change -->" if path.suffix in (".md", ".html") else "# simulated change"
    path.write_text((path.read_text(encoding="utf-8") if path.exists() else "") + mark + "\n", encoding="utf-8")
print("done")
'''
REVIEW = {"verdict": "pass", "findings": []}


def sh(*args, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def synthetic(root: Path, units: int, test_s: float) -> tuple[Path, dict]:
    """A repository with one file per unit. Every unit is independent, and the last one waits for the first."""
    repo = root / "repo"
    repo.mkdir()
    sh("git", "init", "-q", cwd=repo)
    for n in range(1, units + 1):
        (repo / f"module{n}.py").write_text(f"VALUE = {n}\n", encoding="utf-8")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "commit", "-q", "-m", "init", cwd=repo)
    test = f'{sys.executable} -c "import time; time.sleep({test_s})"'
    items = [{"id": f"u{n}", "title": f"unit {n}", "task_type": "edit-small", "goal": f"Edit module{n}.py",
              "allowed": [f"module{n}.py"], "depends_on": ["u1"] if n == units and units > 2 else [],
              "acceptance": {"test": test, "criteria": ["the file changed"]}} for n in range(1, units + 1)]
    return repo, {"plan_id": "bench", "goal": "parallel bench", "units": items}


def run_level(plan: dict, repo: Path, level: int, latency: float, root: Path) -> dict:
    """One run of the plan with `level` units at once, in a fresh clone and a fresh home, so runs do not share state."""
    home = root / f"home-{level}"
    clone = root / f"clone-{level}"
    sh("git", "clone", "-q", str(repo), str(clone), cwd=root)
    script = root / "sim_agent.py"
    script.write_text(AGENT, encoding="utf-8")
    old = os.environ.get("STANDARDS_HOME")
    os.environ["STANDARDS_HOME"] = str(home)
    conf = orchestrate.policy()
    conf["concurrency"] = {**(conf.get("concurrency") or {}), "max_parallel": level,
                           "pools": {"remote_free": level, "local": 1}}
    command = [sys.executable, str(script), str(latency)]
    work = copy.deepcopy(plan)
    work["plan_id"] = f"{plan['plan_id']}-p{level}"
    work.pop("base", None)
    work.pop("repo", None)

    def delegate(where, unit, decision, test):
        # The model name is a local one, so the gate sends nothing out. Only the latency is simulated.
        return orchestrate.delegate_opencode(where, execute.unit_task(unit), unit["allowed"], test, model="ollama/simulated-agent",
                                             keep=True, conf=conf, local={}, command=command, test_lock=runner.test_lock)

    route = lambda unit: {"executor": "opencode", "model": "opencode/simulated-agent", "fallbacks": []}  # noqa: E731
    runner = execute.Executor(work, clone, "simulated-reviewer", lambda prompt: REVIEW, delegate, route, conf, {}, parallel=level)
    runner.local_busy = lambda choice: None
    try:
        began = time.monotonic()
        state = runner.run()
        wall = round(time.monotonic() - began, 2)
    finally:
        if old is None:
            os.environ.pop("STANDARDS_HOME", None)
        else:
            os.environ["STANDARDS_HOME"] = old
    metrics = state["metrics"]
    counts = execute.summary(state)
    entries = state["units"].values()
    return {"parallel": level, "total_s": wall, "peak_parallel": metrics["peak_parallel"], "counts": counts,
            "failed": sum(v for k, v in counts.items() if k != execute.DONE), "collisions": metrics["collisions"],
            "retries": metrics["retries"], "waited_for_slots_s": metrics["waited_s"], "integration_s": metrics["integration_s"],
            "tests_waited_s": round(sum(e.get("tests_waited_s") or 0 for e in entries), 2),
            "agent_s": round(sum(e.get("agent_s") or 0 for e in entries), 2)}


def measure(plan: dict, repo: Path, levels: list[int], latency: float, root: Path) -> dict:
    errors = workplan.validate(plan)
    if errors:
        raise SystemExit("invalid plan: " + "; ".join(errors))
    rows = [run_level(plan, repo, level, latency, root) for level in levels]
    base = rows[0]["total_s"]
    for row in rows:
        row["speedup"] = round(base / row["total_s"], 2) if row["total_s"] else None
    return {"date": orchestrate.now(), "machine": {**orchestrate.hardware(), "cpus": os.cpu_count()},
            "agents": "simulated", "latency_s": latency, "units": len(plan["units"]),
            "dependencies": sum(1 for u in plan["units"] if u.get("depends_on")), "levels": rows,
            "note": "simulated agents with a fixed latency: this measures the scheduler, not a model"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--units", type=int, default=6)
    parser.add_argument("--latency", type=float, default=2.0, help="seconds each simulated agent works")
    parser.add_argument("--test-s", type=float, default=0.3, help="seconds the simulated test suite takes")
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 3], help="units at once. The first is the baseline")
    parser.add_argument("--plan", type=Path, help="measure this saved plan instead of the synthetic one")
    parser.add_argument("--repo", type=Path, help="the repository of --plan")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    root = Path(tempfile.mkdtemp(prefix="standards-bench-"))
    try:
        if args.plan:
            if not args.repo:
                parser.error("--plan needs --repo")
            plan, repo = json.loads(args.plan.read_text(encoding="utf-8")), orchestrate.repo_root(args.repo)
        else:
            repo, plan = synthetic(root, args.units, args.test_s)
        result = measure(plan, repo, args.levels, args.latency, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(row["failed"] == 0 for row in result["levels"]) else 1


if __name__ == "__main__":
    sys.exit(main())
