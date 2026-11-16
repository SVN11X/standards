#!/usr/bin/env python3
"""Executor loop: run a work plan unit by unit, each in its own worktree, with tests and cross-model review.

A unit starts as soon as its own dependencies passed and a resource slot is free (scripts/scheduler.py).
The loop needs no Claude session: it runs as a plain process and its state survives a restart.

Usage: python scripts/execute.py check PLAN.json [--repo DIR]
       python scripts/execute.py run PLAN.json --reviewer MODEL [--repo DIR] [--parallel N]
       python scripts/execute.py status PLAN.json
       python scripts/execute.py resume PLAN.json --reviewer MODEL [--repo DIR] [--parallel N]
       python scripts/execute.py pause PLAN.json | unpause PLAN.json | cancel PLAN.json --unit ID
       python scripts/execute.py clean PLAN.json [--repo DIR]
       python scripts/execute.py report PLAN.json
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))

import orchestrate  # noqa: E402
import resources  # noqa: E402
import review as review_mod  # noqa: E402
import scheduler  # noqa: E402
import secret_scan  # noqa: E402
import workplan  # noqa: E402

DONE = "passed"
# Reviewed and committed, waiting for its turn in the integration queue. A restart integrates it without a new run.
REVIEWED = "reviewed"
AGENTS = ("opencode", "colibri")
POOLS = {"remote_free": 2, "local": 1}


def state_file(plan_id: str) -> Path:
    return orchestrate.home() / "executions" / f"{plan_id}.json"


def control_file(plan_id: str) -> Path:
    return orchestrate.home() / "executions" / f"{plan_id}.control.json"


def events_file(plan_id: str) -> Path:
    return orchestrate.home() / "executions" / f"{plan_id}.events.jsonl"


def read_control(plan_id: str) -> dict:
    """What the owner asked of a running plan: {"paused": bool, "cancel": [unit ids]}."""
    try:
        data = json.loads(control_file(plan_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def set_control(plan_id: str, paused: bool | None = None, cancel: str | None = None) -> dict:
    data = read_control(plan_id)
    if paused is not None:
        data["paused"] = paused
    if cancel:
        data["cancel"] = sorted({*(data.get("cancel") or []), cancel})
    orchestrate.write_json(control_file(plan_id), data)
    return data


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


def default_delegate(repo: Path, unit: dict, decision: dict, test: str | None, conf: dict, local: dict,
                     stop=None, timeout_s: int | None = None, test_lock=None) -> dict:
    if decision["executor"] not in AGENTS:
        return {"state": "blocked", "note": f"routing gave {decision['executor']}, not a coding agent. "
                + "; ".join(decision.get("reasons", []))}
    return orchestrate.delegate_opencode(repo, unit_task(unit), unit["allowed"], test, model=decision.get("model"),
                                         protect=unit.get("protect"), untrusted=unit.get("context"), keep=True,
                                         conf=conf, local=local, executor=decision["executor"], stop=stop,
                                         timeout_s=timeout_s, test_lock=test_lock)


def secrets_added(data: dict) -> list[str]:
    """Kinds of credential in the lines a unit added. The patterns are the ones of hooks/secret_scan.py."""
    diff = orchestrate.git(Path(data["worktree"]), "diff", data["base"], data["commit"])
    added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return secret_scan.scan(added)


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


def log_choices(log: list[dict]) -> list[dict]:
    return [{"executor": row.get("executor"), "model": row.get("model")} for row in log]


def attempt_row(choice: dict, data: dict, status: str) -> dict:
    """What a resumed run and the owner need to know about one try: who, how long, where the work is and why it ended."""
    result = data.get("executor_result") or {}
    return {"id": data.get("id"), "executor": choice.get("executor"), "model": choice.get("model"), "status": status,
            "failure_code": result.get("failure_code"), "seconds": result.get("seconds"), "worktree": data.get("worktree"),
            "branch": data.get("branch"), "commit": data.get("commit"), "changed": data.get("changed"),
            "tests": (data.get("checks") or {}).get("tests"), "at": orchestrate.now()}


class Executor:
    """Runs a plan. `delegate(repo, unit, decision, test)` and `route(unit)` are injected so tests need no model."""

    def __init__(self, plan: dict, repo: Path, reviewer_model: str | None = None, reviewer=None, delegate=None,
                 route=None, conf: dict | None = None, local: dict | None = None, parallel: int | None = None,
                 propose=None, clock=time.monotonic):
        self.plan, self.repo = plan, Path(repo)
        self.conf = conf or orchestrate.policy()
        self.local = local if local is not None else orchestrate.local_config()
        self.reviewer_model, self.reviewer = reviewer_model, reviewer
        limits = self.conf.get("concurrency") or {}
        self.parallel = parallel or limits.get("max_parallel", 3)
        self.pools = scheduler.Pools({**POOLS, **(limits.get("pools") or {})}, grow_after=limits.get("grow_after", 3))
        self.test_lock = threading.BoundedSemaphore(max(1, limits.get("tests", 1)))
        self.stall_s = limits.get("stall_s", 900)
        self.local_busy = lambda choice: resources.local_busy(choice.get("model"), self.conf)
        self.route = route or (lambda unit: route_unit(unit, plan, self.repo, self.conf, self.local))
        self.delegate = delegate or (lambda r, u, d, t: default_delegate(
            r, u, d, t, self.conf, inherit_folder(self.local, self.repo, r), stop=self.stops.get(u["id"]),
            timeout_s=self.unit_timeout(u), test_lock=self.test_lock))
        self.lock = threading.Lock()
        self.stops: dict[str, threading.Event] = {}
        self.slots: dict[str, list[str]] = {}
        self.first: dict[str, int] = {}
        self.decisions: dict[str, dict] = {}
        self.waiting: dict[str, str] = {}
        self.counters = {"collisions": 0, "integration_s": 0.0}
        self.units = {u["id"]: u for u in plan["units"]}
        self.state = load_state(plan["plan_id"])
        self.work_repo = self.repo
        self.budgets = plan.get("budgets") or {}
        self.attempts = max(1, self.budgets.get("max_attempts_per_unit", 1))
        self.propose, self.clock, self.started = propose, clock, clock()
        saved = self.state.get("budget_used") or {}
        self.used = {"attempts": saved.get("attempts", 0), "remote": saved.get("remote", 0)}
        self.elapsed_before = saved.get("elapsed_s", 0.0)
        self.depth: dict[str, int] = {}
        self.split_parents: set[str] = set()

    def save(self) -> None:
        self.state["budget_used"] = {**self.used, "elapsed_s": round(self.elapsed_before + self.clock() - self.started, 2)}
        orchestrate.write_json(state_file(self.plan["plan_id"]), self.state)

    def mark(self, uid: str, status: str, **fields) -> None:
        with self.lock:
            self.state["units"][uid] = {"status": status, "at": orchestrate.now(), **fields}
            self.save()
        self.event({"event": "state", "unit": uid, "status": status, "model": fields.get("model"), "note": fields.get("note")})

    def event(self, row: dict) -> None:
        """One line per transition. The dashboard and `status` read this file, so watching a run asks no model."""
        path = events_file(self.plan["plan_id"])
        with self.lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": orchestrate.now(), **row}) + "\n")

    def unit_timeout(self, unit: dict) -> int | None:
        return (unit.get("budget") or {}).get("timeout_s") or self.budgets.get("unit_timeout_s")

    def pool_of(self, choice: dict) -> str:
        """The resource a choice loads: local (this machine's GPU and RAM) or remote_free (a provider's quota)."""
        try:
            where = orchestrate.channel(choice.get("executor", ""), choice.get("model"), self.conf)
        except (KeyError, TypeError):
            where = "local" if choice.get("executor") == "colibri" else "remote_free"
        return where if where in ("local", "remote_free") else "remote_free"

    @staticmethod
    def choices(decision: dict) -> list[dict]:
        # A Colibri unit has no fallback: it never moves to another model on its own.
        if decision.get("executor") == "colibri":
            return [decision]
        return [decision, *[{**decision, **f} for f in decision.get("fallbacks", [])]]

    def claim(self, uid: str) -> list[str] | None:
        """Pools the unit takes now, or None to wait. route() listed only choices that passed cost and privacy,
        so a busy GPU can move a unit to a free remote model only where the owner's policy already allows it."""
        entry = self.state["units"].get(uid) or {}
        if entry.get("status") == REVIEWED and entry.get("commit"):
            self.slots[uid] = []
            return []
        decision = self.decisions.get(uid)
        if decision is None:
            decision = self.decisions[uid] = self.route(self.units[uid])
        if decision.get("executor") not in AGENTS:
            self.slots[uid] = []
            return []
        for index, choice in enumerate(self.choices(decision)):
            pool = self.pool_of(choice)
            busy = self.local_busy(choice) if pool == "local" else None
            if busy or not self.pools.free([pool]):
                self.waiting[uid] = busy or f"every {pool} slot is in use"
                continue
            self.first[uid], self.slots[uid] = index, [pool]
            self.waiting.pop(uid, None)
            return [pool]
        return None

    def control(self) -> dict:
        wishes = read_control(self.plan["plan_id"])
        for uid in wishes.get("cancel") or []:
            if uid in self.stops:
                self.stops[uid].set()
        return wishes

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
        """Cherry-pick a passed unit into the integration branch, one unit at a time. Returns a problem or None."""
        base = ["git", "-C", str(self.work_repo), "-c", "user.name=standards-execute", "-c", "user.email=execute@localhost"]
        with self.lock:
            began = self.clock()
            try:
                # A restart can find the commit already integrated: git cherry marks an equal patch with "-".
                listed = orchestrate.run([*base, "cherry", "HEAD", commit, f"{commit}^"], timeout=60)
                if listed["exit"] == 0 and listed["stdout"].startswith("-"):
                    return None
                result = orchestrate.run([*base, "cherry-pick", commit], timeout=120)
                if result["exit"] != 0:
                    orchestrate.run([*base, "cherry-pick", "--abort"], timeout=60)
                    self.counters["collisions"] += 1
                    return "cherry-pick conflict: " + orchestrate.tail(result["stderr"], 300)
            finally:
                self.counters["integration_s"] += self.clock() - began
        return None

    def reserve(self, choice: dict) -> str | None:
        """Count one attempt against the plan budgets. Returns the budget that refuses it, or None."""
        budgets = self.budgets
        with self.lock:
            if "max_wall_s" in budgets and self.elapsed_before + self.clock() - self.started >= budgets["max_wall_s"]:
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
                _, info = self.run_unit(part)
                self.pools.give(info["pools"])
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
        found = secrets_added(data)
        data.setdefault("checks", {})["secrets"] = "FAIL" if found else "PASS"
        if found:
            return "failed", "security: the diff adds " + ", ".join(found), data
        status, note = judge(data, self.reviewer_model, self.reviewer)
        return status, note, data

    def run_unit(self, uid: str) -> tuple[str, dict]:
        """Run one unit. Returns its status and what the scheduler must know: the pools still held and a failure code."""
        info = {"pools": self.slots.pop(uid, [])}
        self.stops.setdefault(uid, threading.Event())
        try:
            self.do_unit(uid, info)
        except Exception as error:  # one broken unit must not stop the independent ones
            self.mark(uid, "failed", note=f"{type(error).__name__}: {error}")
        return self.state["units"][uid]["status"], info

    def do_unit(self, uid: str, info: dict) -> None:
        unit = self.units[uid]
        began = self.clock()
        waits = [d for d in unit.get("depends_on", []) if self.state["units"].get(d, {}).get("status") != DONE]
        if waits:
            self.mark(uid, "skipped", note="waits on " + ", ".join(waits))
            return
        saved = self.state["units"].get(uid) or {}
        if saved.get("status") == REVIEWED and saved.get("commit"):
            # The run was interrupted between review and integration. Only the integration is left.
            problem = self.take(saved["commit"])
            fields = {k: v for k, v in saved.items() if k not in ("status", "at", "note")}
            self.mark(uid, "failed" if problem else DONE, **fields,
                      note=problem or f"{saved.get('note', 'reviewed')}. Integrated after a restart")
            return
        self.mark(uid, "running")
        decision = self.decisions.get(uid) or self.route(unit)
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
            # Each part takes its own slot, so the parent gives its slot back first.
            self.pools.give(info["pools"])
            info["pools"] = []
            self.run_parts(uid, parts, why)
            return
        choices = self.choices(decision)
        start = self.first.pop(uid, 0)
        choices = choices[start:] + choices[:start]
        status, note, data = "blocked", "no executor", {}
        tried = 0
        pool = None
        partial = None
        log = list((self.state["units"].get(uid) or {}).get("attempt_log") or [])
        seen = {(c.get("executor"), c.get("model")) for c in log_choices(log)}
        index = 0
        while index < len(choices) and tried < self.attempts:
            choice = choices[index]
            index += 1
            runs = choice.get("executor") in AGENTS
            # A selection that never reaches a model costs no attempt, so a unit with no executor cannot starve the rest.
            refused = self.reserve(choice) if runs else None
            if refused:
                status, note = "blocked", f"budget {refused} reached"
                if refused == "max_remote_sessions":
                    continue
                break
            pool = self.pool_of(choice) if runs else None
            if pool and info["pools"] != [pool]:
                # A retry on another kind of resource waits for a slot there. It never runs on the old slot.
                self.pools.give(info["pools"])
                info["pools"] = []
                busy = self.local_busy(choice) if pool == "local" else None
                if busy or not self.pools.wait_take([pool], self.stall_s, self.stops[uid]):
                    status, note = "blocked", busy or f"no {pool} slot became free in {self.stall_s}s"
                    continue
                info["pools"] = [pool]
            tried += runs
            seen.add((choice.get("executor"), choice.get("model")))
            status, note, data = self.attempt(unit, choice, test)
            info["failure_code"] = (data.get("executor_result") or {}).get("failure_code")
            if runs:
                log.append(attempt_row(choice, data, status))
            if status in (DONE, "blocked") or choice.get("executor") == "colibri":
                break
            if info["failure_code"] == "timeout":
                if data.get("changed") or data.get("commit"):
                    # Partial work or an unknown state: keep the worktree and let the owner or a reviewer inspect it first.
                    partial = {"worktree": data.get("worktree"), "branch": data.get("branch"), "changed": data.get("changed")}
                    status, note = "blocked", (f"timed out after changing {len(data.get('changed') or [])} file(s). "
                                               f"Kept {data.get('worktree')} to inspect before any reassignment")
                    break
                # The attempt left the code intact: ask the router again, now that the failure is in the health data.
                self.decisions.pop(uid, None)
                fresh = [c for c in self.choices(self.route(unit)) if (c.get("executor"), c.get("model")) not in seen]
                if fresh:
                    choices, index = fresh, 0
        if self.stops[uid].is_set():
            status, note = "cancelled", "cancelled by the owner. Its worktree and branch are kept"
        fields = dict(executor=data.get("executor"), model=data.get("model"), channel=pool,
                      commit=data.get("commit"), branch=data.get("branch"), worktree=data.get("worktree"),
                      review=data.get("review"), checks=data.get("checks"), attempts=tried,
                      attempt_log=log, partial=True if partial else None, failure_code=info.get("failure_code"),
                      agent_s=(data.get("executor_result") or {}).get("seconds"),
                      tests_s=(data.get("test_result") or {}).get("seconds"),
                      tests_waited_s=(data.get("test_result") or {}).get("waited_s"))
        if status == DONE:
            self.mark(uid, REVIEWED, note=note, **fields)
            problem = self.take(data["commit"])
            if problem:
                status, note = "failed", problem
        if status != DONE:
            # A failure can start a cooldown, so the next unit asks the router again.
            self.decisions.clear()
        self.mark(uid, status, note=note, **fields, seconds=round(self.clock() - began, 2))

    def recover(self) -> None:
        """A unit a stopped process left running is run again. Its old worktree and branch stay where they are."""
        left = [uid for uid, entry in self.state["units"].items() if entry.get("status") == "running"]
        for uid in left:
            self.state["units"][uid] = {**self.state["units"][uid], "status": "interrupted",
                                        "note": "the process stopped while this unit ran"}
        runs = orchestrate.home() / "runs"
        orphans = []
        for path in sorted(runs.glob("*.json")) if left and runs.is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("state") in ("approved", "running") and data.get("repo") == str(self.work_repo) \
                    and data.get("worktree") and Path(data["worktree"]).exists():
                orphans.append({"run": data.get("id"), "worktree": data["worktree"], "branch": data.get("branch")})
        if orphans:
            self.state["orphans"] = orphans

    def run(self) -> dict:
        self.work_repo = self.integration()
        self.recover()
        order = workplan.topo_order(self.plan["units"])
        clash = {frozenset(c[:2]) for c in workplan.conflicts(self.plan, workplan.tracked_files(self.repo))}
        deps = {u["id"]: set(u.get("depends_on", [])) for u in self.plan["units"]}
        done = [uid for uid in order if self.state["units"].get(uid, {}).get("status") == DONE]
        before = resources.snapshot()
        self.event({"event": "plan-started", "unit": None, "parallel": self.parallel, "pools": dict(self.pools.limits)})
        loop = scheduler.Scheduler(order, deps, clash, self.run_unit, self.claim, self.pools, self.parallel, done,
                                   self.control, self.on_schedule, stall_s=self.stall_s)
        result = loop.run()
        for uid in result["pending"]:
            self.state["units"].setdefault(uid, {"status": "pending", "at": orchestrate.now(),
                                                 "note": "the owner paused new assignments"})
        entries = self.state["units"].values()
        self.state["metrics"] = {
            "total_s": result["total_s"], "parallel_limit": self.parallel, "peak_parallel": result["peak_parallel"],
            "pool_limits": dict(self.pools.ceiling), "pool_peak": result["pool_peak"], "pool_changes": result["pool_changes"],
            "collisions": self.counters["collisions"], "integration_s": round(self.counters["integration_s"], 3),
            "retries": sum(max(0, (e.get("attempts") or 1) - 1) for e in entries),
            "waited_s": round(sum(t.get("wait_s", 0) for t in result["units"].values()), 3),
            "units": result["units"], "resources": {"before": before, "after": resources.snapshot()}}
        self.state["paused"] = result["paused"]
        self.state["finished"] = None if result["paused"] else orchestrate.now()
        self.save()
        self.event({"event": "plan-paused" if result["paused"] else "plan-finished", "unit": None, "total_s": result["total_s"]})
        return self.state

    def on_schedule(self, row: dict) -> None:
        # A unit the scheduler ended without running it (cancelled, or its dependency failed) gets its state here.
        if row["event"] == "finished" and not row.get("ran"):
            self.mark(row["unit"], row["status"], note=row.get("note"))
        elif row["event"] == "started":
            self.event(row)


def summary(state: dict) -> dict:
    counts: dict[str, int] = {}
    for entry in state["units"].values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


def report(plan: dict, state: dict) -> dict:
    """One report per plan, built only from the saved state. A value the state does not hold is null."""
    units = []
    plan_deps = {u["id"]: list(u.get("depends_on", [])) for u in plan["units"]}
    for unit in plan["units"]:
        entry = state["units"].get(unit["id"])
        if entry is None:
            units.append({"id": unit["id"], "status": "not_run", "commit": None, "tests": None, "review": None,
                          "findings": None, "retries": None, "executor": None, "model": None, "note": None,
                          "channel": None, "seconds": None, "partial": None, "attempt_log": None,
                          "depends_on": plan_deps.get(unit["id"], [])})
            continue
        found = entry.get("review")
        checks = entry.get("checks")
        tried = entry.get("attempts")
        units.append({"id": unit["id"], "status": entry["status"], "commit": entry.get("commit"),
                      "tests": checks.get("tests") if checks else None,
                      "review": found.get("verdict") if found else None,
                      "findings": found.get("findings", []) if found else None,
                      "retries": max(0, tried - 1) if isinstance(tried, int) else None,
                      "executor": entry.get("executor"), "model": entry.get("model"), "note": entry.get("note"),
                      "channel": entry.get("channel"), "seconds": entry.get("seconds"),
                      "partial": entry.get("partial"), "attempt_log": entry.get("attempt_log"),
                      "depends_on": plan_deps.get(unit["id"], [])})
    counts: dict[str, int] = {}
    for item in units:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"schema": "standards/execution-report/v1", "plan_id": plan["plan_id"], "finished": state.get("finished"),
            "integration_branch": (state.get("integration") or {}).get("branch"), "counts": counts, "units": units,
            "metrics": state.get("metrics"), "publication": state.get("publication")}


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


def sweep(plan: dict, repo: Path) -> dict:
    """Remove the worktrees that hold nothing else, never by force. Branches stay.

    A worktree with uncommitted changes, or with a commit the integration branch lacks, is kept and named.
    The state file goes only when nothing was kept, so a kept unit can still be resumed.
    """
    state = load_state(plan["plan_id"])
    integration = (state.get("integration") or {}).get("worktree")
    removed, kept = [], []
    paths = [(uid, e.get("worktree"), e) for uid, e in state["units"].items()]
    paths += [(None, o.get("worktree"), {}) for o in state.get("orphans") or []]
    for uid, path, entry in [*paths, ("integration", integration, {})]:
        if not path or not Path(path).exists():
            continue
        dirty = orchestrate.git(Path(path), "status", "--porcelain", "--untracked-files=all", check=False)
        pending = uid not in (None, "integration") and entry.get("commit") and entry.get("status") != DONE
        if uid is None or dirty or pending:
            why = "work of an interrupted run" if uid is None else "uncommitted changes" if dirty else \
                f"commit {entry['commit'][:12]} is not integrated"
            kept.append({"worktree": path, "unit": uid, "why": why})
            continue
        orchestrate.git(repo, "worktree", "remove", path, check=False)
        (kept if Path(path).exists() else removed).append(
            {"worktree": path, "unit": uid, "why": "git refused to remove it"} if Path(path).exists() else path)
    if not kept:
        for path in (state_file(plan["plan_id"]), control_file(plan["plan_id"])):
            path.unlink(missing_ok=True)
    return {"removed": removed, "kept": kept}


def clean(plan: dict, repo: Path) -> list[str]:
    return sweep(plan, repo)["removed"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "run", "status", "resume", "pause", "unpause", "cancel",
                                            "clean", "report"])
    parser.add_argument("plan")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--reviewer", help="model that reviews each unit, different from the author")
    parser.add_argument("--parallel", type=int, help="units at once. Default: concurrency.max_parallel")
    parser.add_argument("--unit", help="the unit to cancel")
    args = parser.parse_args(argv)
    plan = load_plan(Path(args.plan))
    if args.command == "status":
        state = load_state(plan["plan_id"])
        print(json.dumps({"summary": summary(state), "units": state["units"], "metrics": state.get("metrics"),
                          "control": read_control(plan["plan_id"]), "orphans": state.get("orphans", [])}, indent=2))
        return 0
    if args.command in ("pause", "unpause", "cancel"):
        if args.command == "cancel" and args.unit not in {u["id"] for u in plan["units"]}:
            print("cancel needs --unit with an id of this plan")
            return 1
        print(json.dumps(set_control(plan["plan_id"], paused={"pause": True, "unpause": False}.get(args.command),
                                     cancel=args.unit if args.command == "cancel" else None)))
        return 0
    if args.command == "report":
        print(json.dumps(report(plan, load_state(plan["plan_id"])), indent=2))
        return 0
    repo = orchestrate.repo_root(Path(args.repo))
    if args.command == "clean":
        print(json.dumps(sweep(plan, repo), indent=2))
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
        for path in (state_file(plan["plan_id"]), control_file(plan["plan_id"])):
            path.unlink(missing_ok=True)
    reviewer = review_mod.ollama_reviewer(repo, args.reviewer) if args.reviewer else None
    try:
        counts = summary(Executor(plan, repo, args.reviewer, reviewer, parallel=args.parallel).run())
    except StaleIntegration as error:
        print(error)
        return 1
    print(json.dumps(counts))
    return 0 if set(counts) <= {DONE} else 1


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
