"""Executor loop with fake executors and a temp home. Run: python -m unittest discover -s tests"""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execute  # noqa: E402
import orchestrate  # noqa: E402

CONF = {"tasks": {"edit-small": ["opencode"], "colibri-task": ["colibri"]}, "planner_tasks": ["plan"], "protected": []}
DIFF_OK = {"verdict": "pass", "findings": []}
HIGH = {"verdict": "fail", "findings": [{"severity": "high", "file": "a.txt", "line_start": 1, "line_end": 1, "message": "bad"}]}


def sh(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def unit(uid, files, deps=(), kind="edit-small"):
    return {"id": uid, "title": uid, "task_type": kind, "goal": f"edit {uid}", "allowed": list(files),
            "depends_on": list(deps), "acceptance": {"test": "true"}}


def plan(*units):
    return {"plan_id": "plan1", "goal": "g", "units": list(units)}


class FakeAgent:
    """Delegate that edits a file in a real worktree and commits. `fail` ids end failed, `block` ids blocked."""

    def __init__(self, fail=(), block=()):
        self.fail, self.block, self.calls, self.lock = set(fail), set(block), [], threading.Lock()

    def __call__(self, repo, unit, decision, test):
        with self.lock:
            self.calls.append((unit["id"], decision["executor"], Path(repo).name))
        if unit["id"] in self.block:
            return {"state": "blocked", "note": "Colibri is not running"}
        base = orchestrate.git(repo, "rev-parse", "HEAD")
        tree = Path(tempfile.mkdtemp(dir=os.environ["STANDARDS_HOME"])) / unit["id"]
        orchestrate.git(repo, "worktree", "add", "-q", "-b", f"u/{unit['id']}-{tree.parent.name}", str(tree), base)
        if unit["id"] in self.fail:
            return {"state": "failed", "checks": {"tests": "FAIL"}, "worktree": str(tree)}
        (tree / unit["allowed"][0]).write_text(unit["id"] + "\n")
        sh("git", "add", "-A", cwd=tree)
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", unit["id"], cwd=tree)
        return {"state": "verified", "base": base, "commit": orchestrate.git(tree, "rev-parse", "HEAD"), "worktree": str(tree),
                "branch": f"u/{unit['id']}", "model": "author:1b", "executor": decision["executor"]}


class Reviewer:
    def __init__(self, *replies):
        self.replies = list(replies)

    def __call__(self, prompt):
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        sh("git", "init", "-q", cwd=self.repo)
        for name in ("a.txt", "b.txt", "c.txt"):
            (self.repo / name).write_text("x\n")
        sh("git", "add", "-A", cwd=self.repo)
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init", cwd=self.repo)

    def executor(self, work, agent, reviewer=None, **kw):
        route = kw.pop("route", lambda u: {"executor": "colibri" if u["task_type"] == "colibri-task" else "opencode",
                                          "model": "m", "fallbacks": []})
        return execute.Executor(work, self.repo, "rev:1b", reviewer or Reviewer(DIFF_OK), agent, route, CONF, {}, **kw)

    def statuses(self, run):
        return {k: v["status"] for k, v in run.state["units"].items()}


class ExecuteTests(Base):
    def test_all_pass_and_each_unit_has_its_own_worktree(self):
        agent = FakeAgent()
        run = self.executor(plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"])), agent)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "passed", "u2": "passed"})
        trees = {v["worktree"] for v in run.state["units"].values()}
        self.assertEqual(len(trees), 2)
        self.assertEqual(execute.summary(run.state), {"passed": 2})

    def test_dependent_sees_earlier_work(self):
        run = self.executor(plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"], ["u1"])), FakeAgent())
        run.run()
        merged = Path(run.state["integration"]["worktree"])
        self.assertEqual((merged / "a.txt").read_text(), "u1\n")
        self.assertEqual((merged / "b.txt").read_text(), "u2\n")

    def test_high_finding_fails_the_unit(self):
        run = self.executor(plan(unit("u1", ["a.txt"])), FakeAgent(), Reviewer(HIGH))
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "failed"})

    def test_failed_tests_fail_the_unit_and_review_is_not_asked(self):
        reviewer = Reviewer(DIFF_OK)
        run = self.executor(plan(unit("u1", ["a.txt"])), FakeAgent(fail=["u1"]), reviewer)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "failed"})
        self.assertIn("tests", run.state["units"]["u1"]["note"])

    def test_same_model_reviewer_blocks(self):
        work = plan(unit("u1", ["a.txt"]))
        run = execute.Executor(work, self.repo, "author:1b", Reviewer(DIFF_OK), FakeAgent(),
                               lambda u: {"executor": "opencode", "model": "m", "fallbacks": []}, CONF, {})
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})

    def test_no_reviewer_blocks(self):
        run = execute.Executor(plan(unit("u1", ["a.txt"])), self.repo, None, None, FakeAgent(),
                               lambda u: {"executor": "opencode", "model": "m", "fallbacks": []}, CONF, {})
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})

    def test_blocked_unit_does_not_stop_independent_units(self):
        work = plan(unit("u1", ["a.txt"], kind="colibri-task"), unit("u2", ["b.txt"]), unit("u3", ["c.txt"], ["u1"]))
        run = self.executor(work, FakeAgent(block=["u1"]))
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked", "u2": "passed", "u3": "skipped"})

    def test_colibri_is_never_replaced(self):
        agent = FakeAgent(fail=["u1"])
        route = lambda u: {"executor": "colibri", "model": "q", "fallbacks": [{"executor": "opencode", "model": "o"}]}  # noqa: E731
        run = self.executor(plan(unit("u1", ["a.txt"], kind="colibri-task")), agent, route=route)
        run.attempts = 3
        run.run()
        self.assertEqual([c[1] for c in agent.calls], ["colibri"])
        self.assertEqual(self.statuses(run), {"u1": "failed"})

    def test_fallback_is_used_for_other_executors(self):
        agent = FakeAgent(fail=["u1"])
        route = lambda u: {"executor": "opencode", "model": "a", "fallbacks": [{"executor": "opencode", "model": "b"}]}  # noqa: E731
        run = self.executor(plan(unit("u1", ["a.txt"])), agent, route=route)
        run.attempts = 2
        run.run()
        self.assertEqual(len(agent.calls), 2)

    def test_resume_skips_finished_units(self):
        work = plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"]))
        first = self.executor(work, FakeAgent(fail=["u2"]))
        first.run()
        self.assertEqual(self.statuses(first), {"u1": "passed", "u2": "failed"})
        agent = FakeAgent()
        again = self.executor(work, agent)
        again.run()
        self.assertEqual([c[0] for c in agent.calls], ["u2"])
        self.assertEqual(self.statuses(again), {"u1": "passed", "u2": "passed"})

    def test_state_is_written_after_each_unit(self):
        work = plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"], ["u1"]))
        seen = []

        class Spy(FakeAgent):
            def __call__(inner, repo, u, decision, test):
                seen.append(sorted(execute.load_state("plan1")["units"]))
                return super().__call__(repo, u, decision, test)

        self.executor(work, Spy()).run()
        self.assertIn(["u1"], seen)

    def test_parallel_batch_runs_together(self):
        work = plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"]))
        files = execute.workplan.tracked_files(self.repo)
        self.assertEqual(execute.workplan.batches(work, files), [["u1", "u2"]])
        agent = FakeAgent()
        self.executor(work, agent).run()
        self.assertEqual(sorted(c[0] for c in agent.calls), ["u1", "u2"])

    def test_check_reports_routes_and_clean_removes_state(self):
        work = plan(unit("u1", ["a.txt"]))
        report = execute.check(work, self.repo, lambda u: {"executor": "blocked"}, CONF, {})
        self.assertFalse(report["routes"]["u1"]["ready"])
        run = self.executor(work, FakeAgent())
        run.run()
        removed = execute.clean(work, self.repo)
        self.assertTrue(removed)
        self.assertFalse(execute.state_file("plan1").exists())
        self.assertFalse(Path(run.state["integration"]["worktree"]).exists())

    def test_report_comes_from_saved_state_and_gaps_are_null(self):
        work = plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"]), unit("u3", ["c.txt"], ["u2"]))
        run = self.executor(work, FakeAgent(fail=["u2"]))
        run.run()
        rep = execute.report(work, execute.load_state("plan1"))
        by = {u["id"]: u for u in rep["units"]}
        self.assertEqual(rep["counts"], {"passed": 1, "failed": 1, "skipped": 1})
        self.assertEqual(by["u1"]["review"], "pass")
        self.assertEqual(by["u1"]["retries"], 0)
        self.assertEqual(by["u1"]["model"], "author:1b")
        self.assertRegex(by["u1"]["commit"], "^[0-9a-f]{40}$")
        self.assertEqual(by["u2"]["tests"], "FAIL")
        self.assertIsNone(by["u2"]["review"])
        self.assertIsNone(by["u3"]["executor"])
        empty = execute.report(work, {"plan_id": "plan1", "units": {}})
        self.assertEqual(empty["counts"], {"not_run": 3})
        self.assertIsNone(empty["units"][0]["tests"])
        self.assertIsNone(empty["finished"])

    def test_report_matches_its_schema_keys(self):
        import json
        schema = json.loads((ROOT / "schemas" / "execution-report.schema.json").read_text(encoding="utf-8"))
        rep = execute.report(plan(unit("u1", ["a.txt"])), {"plan_id": "plan1", "units": {}})
        self.assertTrue(set(schema["required"]) <= set(rep))
        self.assertTrue(set(schema["properties"]["units"]["items"]["required"]) <= set(rep["units"][0]))


class BudgetTests(Base):
    """Budgets of the work plan and the split of a unit that is too large."""

    def budget_plan(self, *units, **budgets):
        return {**plan(*units), "budgets": budgets}

    def big(self, uid, files, deps=(), kind="edit-small", limit=10):
        return {**unit(uid, files, deps, kind), "max_input_chars": limit}

    def test_too_large_unit_is_split_and_each_part_runs(self):
        agent = FakeAgent()
        run = self.executor(plan(self.big("u1", ["a.txt", "b.txt"]), unit("u2", ["c.txt"], ["u1"])), agent)
        run.run()
        self.assertNotIn("u1", [c[0] for c in agent.calls])
        self.assertEqual(self.statuses(run)["u1"], "passed")
        self.assertEqual(len(run.state["units"]["u1"]["split"]), 2)
        self.assertEqual(self.statuses(run)["u2"], "passed")
        self.assertEqual(len(agent.calls), 3)

    def test_failed_part_fails_the_parent_and_independent_units_go_on(self):
        agent = FakeAgent()
        first = self.executor(plan(self.big("u1", ["a.txt", "b.txt"]), unit("u2", ["c.txt"])), agent)
        part = workplan_parts(first, "u1")[0]
        agent.fail = {part}
        first.run()
        self.assertEqual(self.statuses(first)["u1"], "failed")
        self.assertEqual(self.statuses(first)["u2"], "passed")

    def test_split_depth_budget_blocks_instead_of_splitting(self):
        agent = FakeAgent()
        run = self.executor(self.budget_plan(self.big("u1", ["a.txt", "b.txt"]), max_split_depth=0), agent)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})
        self.assertIn("max_split_depth", run.state["units"]["u1"]["note"])
        self.assertEqual(agent.calls, [])

    def test_children_of_a_split_are_not_split_again_by_default(self):
        agent = FakeAgent()
        run = self.executor(plan(self.big("u1", ["a.txt", "b.txt"], limit=1)), agent)
        run.run()
        self.assertEqual(self.statuses(run)["u1"], "failed")
        self.assertEqual(agent.calls, [])

    def test_units_after_split_budget_blocks(self):
        agent = FakeAgent()
        run = self.executor(self.budget_plan(self.big("u1", ["a.txt", "b.txt"]), unit("u2", ["c.txt"]), max_units_after_split=2), agent)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked", "u2": "passed"})
        self.assertIn("max_units_after_split", run.state["units"]["u1"]["note"])

    def test_unit_with_nothing_to_split_is_blocked(self):
        agent = FakeAgent()
        run = self.executor(plan(self.big("u1", ["a.txt"], limit=5)), agent)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})
        self.assertEqual(agent.calls, [])

    def test_colibri_unit_too_large_is_never_split_or_replaced(self):
        agent = FakeAgent()
        run = self.executor(plan(self.big("u1", ["a.txt", "b.txt"], kind="colibri-task")), agent)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})
        self.assertEqual(agent.calls, [])

    def test_total_attempts_budget(self):
        agent = FakeAgent()
        run = self.executor(self.budget_plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"]), max_total_attempts=1), agent, parallel=1)
        run.run()
        self.assertEqual(len(agent.calls), 1)
        self.assertEqual(sorted(self.statuses(run).values()), ["blocked", "passed"])
        self.assertIn("max_total_attempts", [v["note"] for v in run.state["units"].values() if v["status"] == "blocked"][0])

    def test_wall_budget_blocks_before_the_attempt(self):
        agent = FakeAgent()
        now = [0]
        run = self.executor(self.budget_plan(unit("u1", ["a.txt"]), max_wall_s=10), agent, clock=lambda: now[0])
        now[0] = 11
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "blocked"})
        self.assertEqual(agent.calls, [])

    def test_wall_budget_lets_work_inside_the_limit_run(self):
        agent = FakeAgent()
        run = self.executor(self.budget_plan(unit("u1", ["a.txt"]), max_wall_s=10), agent, clock=lambda: 5)
        run.run()
        self.assertEqual(self.statuses(run), {"u1": "passed"})

    def test_remote_session_budget_skips_remote_and_uses_a_local_fallback(self):
        agent = FakeAgent(fail=["u1"])
        conf = {**CONF, "executors": {"ollama": {"url": "http://127.0.0.1:11434"}, "colibri": {"url": "http://127.0.0.1:1"}}}
        route = lambda u: {"executor": "opencode", "model": "cloud-model", "fallbacks": [{"model": "ollama/small"}]}  # noqa: E731
        work = self.budget_plan(unit("u1", ["a.txt"]), max_remote_sessions=0, max_attempts_per_unit=2)
        run = execute.Executor(work, self.repo, "rev:1b", Reviewer(DIFF_OK), agent, route, conf, {})
        run.run()
        self.assertEqual([c[0] for c in agent.calls], ["u1"])
        self.assertEqual(run.used["remote"], 0)

    def test_remote_session_budget_blocks_when_only_remote_is_left(self):
        agent = FakeAgent()
        work = self.budget_plan(unit("u1", ["a.txt"]), unit("u2", ["b.txt"]), max_remote_sessions=1)
        run = self.executor(work, agent, parallel=1)
        run.run()
        self.assertEqual(len(agent.calls), 1)
        self.assertEqual(sorted(self.statuses(run).values()), ["blocked", "passed"])


def workplan_parts(run, uid):
    unit_ = run.units[uid]
    return [p["id"] for p in execute.workplan.split_unit(unit_, execute.workplan.tracked_files(run.repo), None, CONF)[1]]


class PrivacyInheritanceTests(unittest.TestCase):
    def test_worktree_keeps_the_class_the_owner_set_for_the_repository(self):
        conf = orchestrate.policy()
        with tempfile.TemporaryDirectory() as tmp:
            repo, work = Path(tmp) / "repo", Path(tmp) / "work"
            repo.mkdir()
            work.mkdir()
            local = {"folders": [{"path": str(repo.resolve()), "class": "restricted"}]}
            self.assertEqual(orchestrate.privacy_class(work, conf, local)[0], conf["privacy"]["default"])
            inherited = execute.inherit_folder(local, repo, work)
            self.assertEqual(orchestrate.privacy_class(work, conf, inherited)[0], "restricted")
            self.assertEqual(execute.inherit_folder({}, repo, work), {})


if __name__ == "__main__":
    unittest.main()
