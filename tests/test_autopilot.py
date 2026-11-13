"""Offline tests for the natural-language planner and guarded PR publisher.

No Ollama, OpenCode, GitHub or network access is used in these tests.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_autopilot as autopilot

SHA_A = "a" * 40
SHA_B = "b" * 40
POLICY = {
    "tasks": {"fix-test": ["opencode", "colibri"], "edit-small": ["opencode", "colibri"],
              "test": ["tools"]},
    "planner_tasks": ["plan"], "protected": ["AGENTS.md", ".github/workflows/*"],
}
TEST = "python -m unittest discover -s tests"


def proposal(**overrides):
    unit = {"title": "Fix an issue", "goal": "Correct the bug in src.py", "task_type": "fix-test",
            "allowed": ["src.py"], "new_files": [], "criteria": ["All tests pass"], "risk": "green"}
    unit.update(overrides)
    return {"units": [unit]}


class TestAutopilot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        (self.repo / "src.py").write_text("print('hi')\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_src.py").write_text("pass\n")
        self.tracked = mock.patch.object(autopilot.workplan, "tracked_files", return_value=["src.py", "tests/test_src.py"])
        self.tracked.start()
        self.addCleanup(self.tracked.stop)

    def make(self, obj=None, instruction="Fix src.py"):
        return autopilot.to_workplan(obj or proposal(), instruction, self.repo, TEST, SHA_A, POLICY)

    def test_plan_is_contract_compatible(self):
        plan = self.make()
        self.assertEqual([], autopilot.workplan.validate(plan, POLICY))
        self.assertEqual(["src.py"], plan["units"][0]["allowed"])
        self.assertEqual([TEST], plan["final_regression"])
        self.assertEqual("green", plan["units"][0]["risk"])
        self.assertEqual(SHA_A, plan["base"])

    def test_no_untracked_wildcard_or_traversal(self):
        for name in ("../../unsafe.py", "C:/secret.py", "*.py", "not-tracked.py", ".git/config", "../AGENTS.md"):
            with self.subTest(name=name):
                with self.assertRaises(autopilot.Blocked):
                    self.make(proposal(allowed=[name]))

    def test_protected_file_rejected_by_workplan(self):
        (self.repo / "AGENTS.md").write_text("x")
        with mock.patch.object(autopilot.workplan, "tracked_files", return_value=["src.py", "AGENTS.md"]):
            with self.assertRaises(autopilot.Blocked):
                self.make(proposal(allowed=["AGENTS.md"]))

    def test_unlisted_commands_rejected(self):
        with self.assertRaises(autopilot.Blocked):
            self.make({"unexpected": "shape"})
        for candidate in ("rm -rf .", "powershell -Command evil", "python -c 'bad'"):
            with self.assertRaises(autopilot.Blocked):
                autopilot.checked_command(candidate)

    def test_risky_request_is_red(self):
        self.assertEqual("red", self.make(instruction="Corrige permisos y seguridad de src.py")["units"][0]["risk"])

    def test_red_cannot_be_downgraded(self):
        self.assertEqual("red", self.make(proposal(risk="green", goal="Remove credentials from src.py"))["units"][0]["risk"])

    def test_dependency_chain_and_unit_limit(self):
        plan = self.make({"units": [proposal()["units"][0] for _ in range(3)]})
        self.assertEqual([], plan["units"][0]["depends_on"])
        self.assertEqual(["u1"], plan["units"][1]["depends_on"])
        self.assertEqual(["u2"], plan["units"][2]["depends_on"])
        with self.assertRaises(autopilot.Blocked):
            self.make({"units": [proposal()["units"][0] for _ in range(9)]})

    def test_unknown_kind_rejected(self):
        with self.assertRaises(autopilot.Blocked):
            self.make(proposal(task_type="plan"))
        with self.assertRaises(autopilot.Blocked):
            self.make(proposal(task_type="test"))

    def test_local_planner_calls_loopback_only(self):
        remote = {"executors": {"ollama": {"url": "https://cloud.example.invalid"}}}
        with mock.patch.object(autopilot.orchestrate, "git", return_value=SHA_A):
            with self.assertRaises(autopilot.Blocked):
                autopilot.local_plan("Fix src.py", self.repo, "qwen3.5:9b", TEST, policy=remote, local={})

    def test_local_planner_rejects_remote_model(self):
        cfg = {"executors": {"ollama": {"url": "http://127.0.0.1:11434"}}}
        with mock.patch.object(autopilot.orchestrate, "git", return_value=SHA_A), \
             mock.patch.object(autopilot.orchestrate, "detect_ollama", return_value={"models": ["qwen3.5:9b"], "remote": ["qwen3.5:9b"]}):
            with self.assertRaises(autopilot.Blocked):
                autopilot.local_plan("Fix src.py", self.repo, "qwen3.5:9b", TEST, policy=cfg, local={})

    def test_local_planner_parses_structured_response(self):
        cfg = {**POLICY, "executors": {"ollama": {"url": "http://127.0.0.1:11434"}}}
        stub = {"message": {"content": json.dumps(proposal())}}
        with mock.patch.object(autopilot.orchestrate, "git", return_value=SHA_A), \
             mock.patch.object(autopilot.orchestrate, "detect_ollama", return_value={"models": ["qwen3.5:9b"], "remote": []}), \
             mock.patch.object(autopilot.orchestrate, "gate", return_value=(True, "allowed")):
            result = autopilot.local_plan("Fix src.py", self.repo, "qwen3.5:9b", TEST,
                                          policy=cfg, local={}, request=lambda u, p: stub)
        self.assertEqual(1, len(result["units"]))

    def test_failed_units_cannot_be_published(self):
        plan = self.make()
        with mock.patch.object(autopilot.execute, "load_state", return_value={"units": {"u1": {"status": "failed"}}}):
            with self.assertRaises(autopilot.Blocked):
                autopilot.integration_ready(plan, self.repo, auto_merge=False)

    def test_red_unit_cannot_auto_merge(self):
        plan = self.make(instruction="Corrige permisos de src.py")
        with mock.patch.object(autopilot.execute, "load_state", return_value={"units": {"u1": {"status": "passed"}}}):
            with self.assertRaisesRegex(autopilot.Blocked, "owner review"):
                autopilot.integration_ready(plan, self.repo, auto_merge=True)

    def test_unreviewed_unit_cannot_auto_merge(self):
        plan = self.make()
        with mock.patch.object(autopilot.execute, "load_state", return_value={"units": {"u1": {"status": "passed"}}}):
            with self.assertRaisesRegex(autopilot.Blocked, "independent review"):
                autopilot.integration_ready(plan, self.repo, auto_merge=True)

    def test_unprotected_branch_cannot_auto_merge(self):
        with mock.patch.object(autopilot, "checked_run", return_value=json.dumps({"required_status_checks": None})):
            with self.assertRaises(autopilot.Blocked):
                autopilot.required_checks(self.repo, "SVN11X/standards", "main")
        with mock.patch.object(autopilot, "checked_run", return_value=json.dumps({"required_status_checks": {"contexts": ["CI"], "strict": False}})):
            with self.assertRaises(autopilot.Blocked):
                autopilot.required_checks(self.repo, "SVN11X/standards", "main")

    def test_required_checks_strict_pass(self):
        data = {"required_status_checks": {"contexts": ["verify"], "strict": True}}
        with mock.patch.object(autopilot, "checked_run", return_value=json.dumps(data)):
            autopilot.required_checks(self.repo, "SVN11X/standards", "main")

    def test_save_plan_never_overwrites_different_content(self):
        plan = self.make()
        path = self.repo / "plan.json"
        autopilot.save_plan(plan, path)
        with self.assertRaises(autopilot.Blocked):
            autopilot.save_plan({**plan, "goal": "different"}, path)

    def test_publish_uses_native_auto_merge_no_admin(self):
        plan = self.make()
        branch = f"execute/{plan['plan_id']}"
        url = "https://github.com/SVN11X/standards/pull/99"
        calls = []
        def fake_run(args, *, cwd, timeout=120):
            calls.append(args)
            if args[:3] == ["gh", "pr", "list"]:
                return json.dumps([{"number": 99, "url": url, "headRefOid": SHA_B}])
            return ""
        with mock.patch.object(autopilot, "ensure_base"), \
             mock.patch.object(autopilot.orchestrate, "git", return_value="main"), \
             mock.patch.object(autopilot, "integration_ready", return_value=(self.repo, branch, SHA_B)), \
             mock.patch.object(autopilot, "gh_repo", return_value=("SVN11X/standards", "main")), \
             mock.patch.object(autopilot, "required_checks"), \
             mock.patch.object(autopilot, "regression"), \
             mock.patch.object(autopilot, "checked_run", side_effect=fake_run):
            response = autopilot.publish(plan, self.repo, auto_merge=True)
        self.assertEqual(url, response["pr"])
        merge = next(c for c in calls if c[:3] == ["gh", "pr", "merge"])
        self.assertIn("--auto", merge)
        self.assertIn("--match-head-commit", merge)
        self.assertNotIn("--admin", merge)
        self.assertNotIn("--delete-branch", merge)

    def test_unprotected_auto_merge_leaves_pr_open(self):
        plan = self.make()
        calls = []
        url = "https://github.com/SVN11X/standards/pull/99"
        def fake_run(args, *, cwd, timeout=120):
            calls.append(args)
            if args[:3] == ["gh", "pr", "list"]:
                return json.dumps([{"number": 99, "url": url, "headRefOid": SHA_B}])
            return ""
        with mock.patch.object(autopilot, "ensure_base"), \
             mock.patch.object(autopilot.orchestrate, "git", return_value="main"), \
             mock.patch.object(autopilot, "integration_ready", return_value=(self.repo, "execute/branch", SHA_B)), \
             mock.patch.object(autopilot, "gh_repo", return_value=("SVN11X/standards", "main")), \
             mock.patch.object(autopilot, "regression"), \
             mock.patch.object(autopilot, "required_checks", side_effect=autopilot.Blocked("no protection")), \
             mock.patch.object(autopilot, "checked_run", side_effect=fake_run):
            with self.assertRaisesRegex(autopilot.Blocked, "PR created at"):
                autopilot.publish(plan, self.repo, auto_merge=True)
        self.assertTrue(any(c[:2] == ["git", "push"] for c in calls))
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] for c in calls))


if __name__ == "__main__":
    unittest.main()
