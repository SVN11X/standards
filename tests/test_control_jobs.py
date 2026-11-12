"""No real model is started by these tests."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import control_jobs  # noqa: E402


class FakeProcess:
    pid = 12345

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15


class ControlJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "analyze.py").write_text("print('safe')\n", encoding="utf-8")
        self.calls = []
        self.instances = []

        def create(argv, **kwargs):
            self.calls.append((argv, kwargs))
            proc = FakeProcess()
            self.instances.append(proc)
            return proc

        self.manager = control_jobs.JobManager(self.repo, self.repo / "state", popen=create)

    def test_command_is_explicit_local_only_and_bounded(self):
        args = control_jobs.command("bench-run", self.repo)
        self.assertIn("local-only", args)
        self.assertIn("refactor-module", args)
        self.assertIn("review-diff", args)
        self.assertIn("decompose", args)
        self.assertIn("--hours", args)
        self.assertNotIn("--restart", args)
        self.assertNotIn("free-strict", args)
        with self.assertRaises(ValueError):
            control_jobs.command("shell", self.repo)

    def test_uses_a_single_job_and_cancels_only_owned_process(self):
        started = self.manager.start("bench-plan")
        self.assertTrue(started["active"])
        self.assertEqual(self.calls[0][1]["env"]["STANDARDS_COST_MODE"], "local-only")
        with self.assertRaises(RuntimeError):
            self.manager.start("bench-run")
        with self.assertRaises(ValueError):
            self.manager.cancel("unrelated")
        stopped = self.manager.cancel(started["job"]["id"])
        self.assertFalse(stopped["active"])
        self.assertEqual(stopped["job"]["state"], "cancelled")
        self.assertEqual(self.instances[0].returncode, -15)

    def test_result_and_log_are_reported_not_assumed(self):
        started = self.manager.start("bench-run")
        identity = started["job"]["id"]
        self.instances[0].returncode = 0
        result = self.manager.snapshot()
        self.assertEqual(result["job"]["state"], "passed")
        self.assertFalse(result["active"])
        (self.repo / "state" / (identity + ".log")).write_text("2 of 3 verified\n", encoding="utf-8")
        self.assertIn("2 of 3", self.manager.snapshot()["log"])

    def test_no_model_install_or_external_endpoint_is_possible(self):
        self.manager.start("bench-run")
        argv = self.calls[0][0]
        self.assertNotIn("pull", argv)
        self.assertNotIn("install", argv)
        self.assertNotIn("http", " ".join(argv))


if __name__ == "__main__":
    unittest.main()
