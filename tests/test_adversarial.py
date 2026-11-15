"""Each executor-loop scenario passes on the real code and fails on a deliberately broken one."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import adversarial  # noqa: E402
import execute  # noqa: E402
import orchestrate  # noqa: E402
import plan_autopilot  # noqa: E402
import plan_contract  # noqa: E402
import planner  # noqa: E402
import review  # noqa: E402
import workplan  # noqa: E402

IDS = ["X.planner-type-never-executes", "X.claude-never-a-unit-executor", "X.overlapping-units-never-parallel",
       "X.attempt-budget-stops", "X.invented-review-lines", "X.worktree-keeps-privacy-class", "X.stopped-colibri-no-fallback",
       "X.plan-repair-cannot-widen", "X.opus-needs-a-reason", "X.busy-gpu-never-sends-private-code-out",
       "X.failed-checks-never-merge"]


def status(check_id):
    found = adversarial.run_suite("quick", only=check_id)
    assert len(found) == 1, found
    return found[0]["status"]


class RealCode(unittest.TestCase):
    def test_all_pass(self):
        for check_id in IDS:
            with self.subTest(check_id):
                self.assertEqual(status(check_id), "PASS")


class BrokenInput(unittest.TestCase):
    def test_planner_type_listed_as_coding_task(self):
        broken = orchestrate.policy()
        broken["planner_tasks"] = []
        with mock.patch.object(orchestrate, "policy", return_value=broken):
            self.assertEqual(status(IDS[0]), "FAIL")

    def test_claude_started_as_unit_executor(self):
        stub = {"state": "verified"}
        with mock.patch.object(execute, "AGENTS", ("opencode", "colibri", "claude")), \
                mock.patch.object(orchestrate, "delegate_opencode", return_value=stub):
            self.assertEqual(status(IDS[1]), "FAIL")

    def test_overlap_not_detected(self):
        with mock.patch.object(workplan, "conflicts", return_value=[]):
            self.assertEqual(status(IDS[2]), "FAIL")

    def test_budget_ignored(self):
        original = execute.Executor.__init__

        def init(self, *args, **kwargs):
            original(self, *args, **kwargs)
            self.attempts = 99
        with mock.patch.object(execute.Executor, "__init__", init):
            self.assertEqual(status(IDS[3]), "FAIL")

    def test_review_lines_not_checked(self):
        with mock.patch.object(review, "validate_findings", lambda findings, shown: (findings, [])):
            self.assertEqual(status(IDS[4]), "FAIL")

    def test_worktree_loses_class(self):
        with mock.patch.object(execute, "inherit_folder", lambda local, source, target: local):
            self.assertEqual(status(IDS[5]), "FAIL")

    def test_stopped_colibri_silently_replaced(self):
        stub = {"state": "blocked", "note": "switched to another model"}
        with mock.patch.object(orchestrate, "delegate_opencode", return_value=stub):
            self.assertEqual(status(IDS[6]), "FAIL")

    def test_repair_guard_removed(self):
        with mock.patch.object(plan_contract, "guard", lambda before, after, issues: None):
            self.assertEqual(status(IDS[7]), "FAIL")

    def test_every_request_scored_as_advanced(self):
        with mock.patch.object(planner, "complexity", return_value=("advanced", 9, ["forced"])):
            self.assertEqual(status(IDS[8]), "FAIL")

    def test_privacy_gate_opened(self):
        with mock.patch.object(orchestrate, "gate", return_value=(True, "forced open")):
            self.assertEqual(status(IDS[9]), "FAIL")

    def test_failed_checks_read_as_passed(self):
        passed = {"state": "pass", "failed": [], "checks": 1}
        with mock.patch.object(plan_autopilot, "ci_status", return_value=passed):
            self.assertEqual(status(IDS[10]), "FAIL")


if __name__ == "__main__":
    unittest.main()
