#!/usr/bin/env python3
"""Executor loop: run a work plan unit by unit, each in its own worktree, with tests and cross-model review.

Usage: python scripts/execute.py check PLAN.json [--repo DIR]
       python scripts/execute.py run PLAN.json --reviewer MODEL [--repo DIR] [--parallel N]
       python scripts/execute.py status PLAN.json
       python scripts/execute.py resume PLAN.json --reviewer MODEL [--repo DIR]
       python scripts/execute.py clean PLAN.json [--repo DIR]
       python scripts/execute.py report PLAN.json
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402
import review as review_mod  # noqa: E402
import workplan  # noqa: E402

DONE = "passed"
AGENTS = ("opencode", "colibri")


def state_file(plan_id: str) -> Path:
    return orchestrate.home() / "executions" / f"{plan_id}.json"


class StaleIntegration(RuntimeError):
    """The repository moved since the plan started, so dependent units would build on an old base."""


def load_state(plan_id: str) -> dict:
    path = state_file(plan_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"plan_id": plan_id, "units": {}}


def load_plan(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def unit_task(unit: dict) -> str:
    lines = [unit["goal"]]
    lines += [f"Acceptance: {c}" for c in (unit.get("acceptance") or {}).get("criteria", [])]
    return "\n".join(lines)


def unit_test(unit: dict, plan: dict) -> str | None:
    return (unit.get("acceptance") or {}).get("test") or (plan.get("defaults") or {}).get("test")


def input_size(unit: dict, repo: Path, files: list[str]) -> int:
    """Characters a model would read: the task text plus the files the unit may touch."""
    total = len(unit_task(unit))
    for name in workplan.expand(unit, files):
        try:
            total += (Path(repo) / name).stat().st_size
        except OSError:
            pass
    return total


def route_unit(unit: dict, plan: dict, repo: Path, conf: dict, local: dict) -> dict:
    files = len(workplan.expand(unit, workplan.tracked_files(repo))) or len(unit["allowed"])
    risk = unit.get("risk") or (plan.get("defaults") or {}).get("risk", "green")
    return orchestrate.route(unit["task_type"], repo, risk=risk, files=files, conf=conf, local=local)


def inherit_folder(local: dict, source: Path, target: Path) -> dict:
    """Give a worktree the owner's privacy entry of the repository it came from. Without it the worktree path
    matches no entry and falls back to the default class, which can be looser than the owner's choice."""
    entry = orchestrate.folder_entry(source, local)
    if not entry or Path(target).resolve() == Path(source).resolve():
        return local
    return {**local, "folders": [*(local.get("folders") or []), {**entry, "path": str(Path(target).resolve())}]}


def default_delegate(repo: Path, unit: dict, decision: dict, test: str | None, conf: dict, local: dict) -> dict:
    if decision["executor"] not in AGENTS:
        return {"state": "blocked", "note": f"routing gave {decision['executor']}, not a coding agent. "
                + "; ".join(decision.get("reasons", []))}
    return orchestrate.delegate_opencode(repo, unit_task(unit), unit["allowed"], test, model=decision.get("model"),
                                         protect=unit.get("protect"), keep=True, conf=conf, local=local,
                                         executor=decision["executor"])


def judge(data: dict, reviewer_model: str | None, reviewer) -> tuple[str, str]:
    """Returns (status, note). Only a review without a high finding passes. No reviewer blocks the unit."""
    if not reviewer or not reviewer_model:
        return "blocked", "no reviewer model: review is required"
    diff = orchestrate.git(Path(data["worktree"]), "diff", data["base"], data["commit"])
    result = review_mod.review(diff, data.get("model") or "", reviewer_model, reviewer)
    data["review"] = {"verdict": result["verdict"], "findings": result.get("findings", []), "rounds": result.get("rounds")}
    if result["verdict"] in ("pass", "warn"):
        return DONE, f"review {result['verdict']}"
    if result["verdict"] == "blocked":
        return "blocked", result.get("reason", "review blocked")
    return "failed", "review has a high finding"


class Executor:
    """Runs a plan. `delegate(repo, unit, decision, test)` and `route(unit)` are injected so tests need no model."""

    def __init__(self, plan: dict, repo: Path, reviewer_model: str | None = None, reviewer=None, delegate=None,
                 route=None, conf: dict | None = None, local: dict | None = None, parallel: int | None = None,
                 propose=None, clock=time.monotonic):
        self.plan, self.repo = plan, Path(repo)
        self.conf = conf or orchestrate.policy()
        self.local = local if local is not None else orchestrate.local_config()
        self.reviewer_model, self.reviewer, self.parallel = reviewer_model, reviewer, parallel
        self.route = route or (lambda unit: route_unit(unit, plan, self.repo, self.conf, self.local))
        self.delegate = delegate or (lambda r, u, d, t: default_delegate(r, u, d, t, self.conf, inherit_folder(self.local, self.repo, r)))
        self.lock = threading.Lock()
        self.units = {u["id"]: u for u in plan["units"]}
        self.state = load_state(plan["plan_id"])
        self.work_repo = self.repo
        self.budgets = plan.get("budgets") or {}
        self.attempts = max(1, self.budgets.get("max_attempts_per_unit", 1))
        self.propose, self.clock, self.started = propose, clock, clock()
        self.used = {"attempts": 0, "remote": 0}
        self.depth: dict[str, int] = {}
        self.split_parents: set[str] = set()

    def save(self) -> None:
        orchestrate.write_json(state_file(self.plan["plan_id"]), self.state)

    def mark(self, uid: str, status: str, **fields) -> None:
        with self.lock:
            self.state["units"][uid] = {"status": status, "at": orchestrate.now(), **fields}
            self.save()

    def integration(self) -> Path:
        """A worktree whose HEAD advances with each passed unit, so dependents build on earlier work."""
        path = orchestrate.home() / "worktrees" / f"execute-{self.plan['plan_id']}"
        branch = f"execute/{self.plan['plan_id']}"
        head = orchestrate.git(self.repo, "rev-parse", "HEAD").strip()
        if path.exists() and (self.state.get("integration") or {}).get("base") != head:
            raise StaleIntegration(f"the integration worktree {path} was built on another commit than {head[:12]}. "
                                   f"Run `python scripts/execute.py clean PLAN.json` and start the plan again")
        if not path.exists():
            orchestrate.git(self.repo, "worktree", "add", "-q", "-B", branch, str(path), "HEAD")
        self.state["integration"] = {"branch": branch, "worktree": str(path), "base": head}
        self.save()
        return path

    def take(self, commit: str) -> str | None:
        """Cherry-pick a passed unit into the integration branch. Returns a problem or None."""
        base = ["git", "-C", str(self.work_repo), "-c", "user.name=standards-execute", "-c", "user.email=execute@localhost"]
        with self.lock:
            result = orchestrate.run([*base, "cherry-pick", commit], timeout=120)
            if result["exit"] != 0:
                orchestrate.run([*base, "cherry-pick", "--abort"], timeout=60)
                return "cherry-pick conflict: " + orchestrate.tail(result["stderr"], 300)
        return None

    def reserve(self, choice: dict) -> str | None:
        """Count one attempt against the plan budgets. Returns the budget that refuses it, or None."""
        budgets = self.budgets
        with self.lock:
            if "max_wall_s" in budgets and self.clock() - self.started >= budgets["max_wall_s"]:
                return "max_wall_s"
            if "max_total_attempts" in budgets and self.used["attempts"] >= budgets["max_total_attempts"]:
                return "max_total_attempts"
            if "max_remote_sessions" in budgets:
                where = orchestrate.channel(choice.get("executor", ""), choice.get("model"), self.conf)
                if where not in ("local", "tools"):
                    if self.used["remote"] >= budgets["max_remote_sessions"]:
                        return "max_remote_sessions"
                    self.used["remote"] += 1
            self.used["attempts"] += 1
        return None

    def split(self, unit: dict) -> tuple[list[dict], str]:
        """Parts for a unit that is too large, or ([], reason). Split depth and total units are budgets."""
        uid = unit["id"]
        if self.depth.get(uid, 0) >= self.budgets.get("max_split_depth", 1):
            return [], "max_split_depth"
        method, parts = workplan.split_unit(unit, workplan.tracked_files(self.work_repo), self.propose, self.conf)
        if not parts:
            return [], "no valid split"
        with self.lock:
            left = len(self.units) - len(self.split_parents) - 1 + len(parts)
            if left > self.budgets.get("max_units_after_split", left):
                return [], "max_units_after_split"
            self.split_parents.add(uid)
            for part in parts:
                self.units[part["id"]] = part
                self.depth[part["id"]] = self.depth.get(uid, 0) + 1
        return parts, method

    def run_parts(self, uid: str, parts: list[dict], method: str) -> None:
        """Run the parts of a split unit in order. The parent passes only when every part passed."""
        ids = workplan.topo_order(parts)
        for part in ids:
            if self.state["units"].get(part, {}).get("status") != DONE:
                self.run_unit(part)
        bad = [p for p in ids if self.state["units"][p]["status"] != DONE]
        if bad:
            self.mark(uid, "failed", note=f"split by {method}, not passed: " + ", ".join(bad), split=ids)
        else:
            self.mark(uid, DONE, note=f"split by {method} into " + ", ".join(ids), split=ids, attempts=0)

    def attempt(self, unit: dict, decision: dict, test: str | None) -> tuple[str, str, dict]:
        data = self.delegate(self.work_repo, unit, decision, test)
        if data.get("state") == "blocked":
            history = data.get("history") or [{}]
            return "blocked", data.get("note") or history[-1].get("note", "blocked"), data
        if data.get("state") != "verified":
            history = data.get("history") or [{}]
            failed = [k for k, v in (data.get("checks") or {}).items() if v != "PASS"]
            return "failed", "checks not passed: " + ", ".join(failed) if failed else history[-1].get("note", "failed"), data
        status, note = judge(data, self.reviewer_model, self.reviewer)
        return status, note, data

    def run_unit(self, uid: str) -> None:
        unit = self.units[uid]
        waits = [d for d in unit.get("depends_on", []) if self.state["units"].get(d, {}).get("status") != DONE]
        if waits:
            self.mark(uid, "skipped", note="waits on " + ", ".join(waits))
            return
        self.mark(uid, "running")
        try:
            decision = self.route(unit)
            test = unit_test(unit, self.plan)
            limit = unit.get("max_input_chars")
            if limit and input_size(unit, self.work_repo, workplan.tracked_files(self.work_repo)) > limit:
                if decision.get("executor") == "colibri":
                    self.mark(uid, "blocked", note="too large for Colibri and a Colibri unit is never replaced by a split")
                    return
                parts, why = self.split(unit)
                if not parts:
                    self.mark(uid, "blocked", note=f"too large (max_input_chars {limit}) and not split: {why}")
                    return
                self.run_parts(uid, parts, why)
                return
            # A Colibri unit has no fallback: it never moves to another model on its own.
            choices = [decision]
            if decision.get("executor") != "colibri":
                choices += [{**decision, **f} for f in decision.get("fallbacks", [])]
            status, note, data = "blocked", "no executor", {}
            tried = 0
            for choice in choices[:self.attempts]:
                refused = self.reserve(choice)
                if refused:
                    status, note = "blocked", f"budget {refused} reached"
                    if refused == "max_remote_sessions":
                        continue
                    break
                tried += 1
                status, note, data = self.attempt(unit, choice, test)
                if status in (DONE, "blocked") or choice.get("executor") == "colibri":
                    break
            if status == DONE:
                problem = self.take(data["commit"])
                if problem:
                    status, note = "failed", problem
            self.mark(uid, status, note=note, executor=data.get("executor"), model=data.get("model"),
                      commit=data.get("commit"), branch=data.get("branch"), worktree=data.get("worktree"),
                      review=data.get("review"), checks=data.get("checks"), attempts=tried)
        except Exception as error:  # one broken unit must not stop the independent ones
            self.mark(uid, "failed", note=f"{type(error).__name__}: {error}")

    def run(self) -> dict:
        self.work_repo = self.integration()
        for batch in workplan.batches(self.plan, workplan.tracked_files(self.repo), max_parallel=self.parallel):
            todo = [u for u in batch if self.state["units"].get(u, {}).get("status") != DONE]
            if todo:
                with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                    list(pool.map(self.run_unit, todo))
        self.state["finished"] = orchestrate.now()
        self.save()
        return self.state


def summary(state: dict) -> dict:
    counts: dict[str, int] = {}
    for entry in state["units"].values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


def report(plan: dict, state: dict) -> dict:
    """One report per plan, built only from the saved state. A value the state does not hold is null."""
    units = []
    for unit in plan["units"]:
        entry = state["units"].get(unit["id"])
        if entry is None:
            units.append({"id": unit["id"], "status": "not_run", "commit": None, "tests": None, "review": None,
                          "findings": None, "retries": None, "executor": None, "model": None, "note": None})
            continue
        found = entry.get("review")
        checks = entry.get("checks")
        tried = entry.get("attempts")
        units.append({"id": unit["id"], "status": entry["status"], "commit": entry.get("commit"),
                      "tests": checks.get("tests") if checks else None,
                      "review": found.get("verdict") if found else None,
                      "findings": found.get("findings", []) if found else None,
                      "retries": max(0, tried - 1) if isinstance(tried, int) else None,
                      "executor": entry.get("executor"), "model": entry.get("model"), "note": entry.get("note")})
    counts: dict[str, int] = {}
    for item in units:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"schema": "standards/execution-report/v1", "plan_id": plan["plan_id"], "finished": state.get("finished"),
            "integration_branch": (state.get("integration") or {}).get("branch"), "counts": counts, "units": units}


def check(plan: dict, repo: Path, route=None, conf=None, local=None) -> dict:
    conf = conf or orchestrate.policy()
    local = local if local is not None else orchestrate.local_config()
    errors = workplan.validate(plan, conf)
    out = {"errors": errors, "batches": [], "routes": {}}
    if errors:
        return out
    out["batches"] = workplan.batches(plan, workplan.tracked_files(repo))
    route = route or (lambda u: route_unit(u, plan, repo, conf, local))
    for unit in plan["units"]:
        decision = route(unit)
        out["routes"][unit["id"]] = {"executor": decision.get("executor"), "model": decision.get("model"),
                                     "ready": decision.get("executor") in AGENTS}
    return out


def clean(plan: dict, repo: Path) -> list[str]:
    """Remove the unit worktrees, the integration worktree and the state file. Branches stay."""
    state = load_state(plan["plan_id"])
    paths = [e.get("worktree") for e in state["units"].values()] + [(state.get("integration") or {}).get("worktree")]
    removed = [p for p in paths if p]
    for path in removed:
        orchestrate.git(repo, "worktree", "remove", "--force", path, check=False)
    state_file(plan["plan_id"]).unlink(missing_ok=True)
    return removed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "run", "status", "resume", "clean", "report"])
    parser.add_argument("plan")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--reviewer", help="model that reviews each unit, different from the author")
    parser.add_argument("--parallel", type=int)
    args = parser.parse_args(argv)
    plan = load_plan(Path(args.plan))
    if args.command == "status":
        state = load_state(plan["plan_id"])
        print(json.dumps({"summary": summary(state), "units": state["units"]}, indent=2))
        return 0
    if args.command == "report":
        print(json.dumps(report(plan, load_state(plan["plan_id"])), indent=2))
        return 0
    repo = orchestrate.repo_root(Path(args.repo))
    if args.command == "clean":
        print("\n".join(clean(plan, repo)) or "nothing to clean")
        return 0
    if args.command == "check":
        result = check(plan, repo)
        print(json.dumps(result, indent=2))
        return 1 if result["errors"] or not all(r["ready"] for r in result["routes"].values()) else 0
    errors = workplan.validate(plan)
    if errors:
        print("\n".join(errors))
        return 1
    if args.command == "run":
        state_file(plan["plan_id"]).unlink(missing_ok=True)
    reviewer = review_mod.ollama_reviewer(repo, args.reviewer) if args.reviewer else None
    try:
        counts = summary(Executor(plan, repo, args.reviewer, reviewer, parallel=args.parallel).run())
    except StaleIntegration as error:
        print(error)
        return 1
    print(json.dumps(counts))
    return 0 if set(counts) <= {DONE} else 1


if __name__ == "__main__":
    sys.exit(main())
