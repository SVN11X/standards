"""The queue between the owner's remote VM and the notebook: who may add, one claim at a time, one result per task,
an expired lease that waits for a check, and a backup that restores without a second result. No SSH is used here.
Run: python -m unittest discover -s tests"""
import datetime as dt
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workqueue  # noqa: E402

START = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.timezone.utc)


class WorkQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.db = workqueue.connect(Path(self.tmp.name) / "queue.db")
        self.addCleanup(self.db.close)

    def test_a_cpu_worker_never_takes_gpu_work(self):
        workqueue.add(self.db, "site", "abc123", "gpu", "colibri fix-bug", "personal-public", "g1")
        workqueue.add(self.db, "site", "abc123", "cpu", "python -m unittest", "personal-public", "c1")
        task = workqueue.claim(self.db, "vps", ["cpu"], 600, START)
        self.assertEqual(task["id"], "c1")
        self.assertIsNone(workqueue.claim(self.db, "vps", ["cpu"], 600, START))
        self.assertEqual(workqueue.claim(self.db, "notebook", ["cpu", "gpu"], 600, START)["id"], "g1")

    def test_a_task_finishes_once_and_only_with_its_token(self):
        workqueue.add(self.db, "site", "abc123", "gpu", "colibri fix-bug", "personal-public", "g1")
        task = workqueue.claim(self.db, "notebook", ["gpu"], 600, START)
        self.assertFalse(workqueue.finish(self.db, "g1", "wrong", "passed", at=START)[0])
        self.assertTrue(workqueue.finish(self.db, "g1", task["token"], "tests passed at abc123", at=START)[0])
        ok, why = workqueue.finish(self.db, "g1", task["token"], "a second result", at=START)
        self.assertFalse(ok)
        self.assertIn("finishes once", why)

    def test_an_expired_lease_waits_for_a_check_before_it_runs_again(self):
        workqueue.add(self.db, "site", "abc123", "gpu", "colibri fix-bug", "personal-public", "g1")
        task = workqueue.claim(self.db, "notebook", ["gpu"], 60, START)
        later = START + dt.timedelta(minutes=5)
        self.assertIsNone(workqueue.claim(self.db, "notebook", ["gpu"], 60, later))
        ok, why = workqueue.finish(self.db, "g1", task["token"], "late result", at=later)
        self.assertFalse(ok)
        self.assertIn("retry --checked", why)
        self.assertFalse(workqueue.retry(self.db, "g1", checked=False)[0])
        self.assertTrue(workqueue.retry(self.db, "g1", checked=True)[0])
        again = workqueue.claim(self.db, "notebook", ["gpu"], 60, later)
        self.assertEqual((again["id"], again["attempts"]), ("g1", 2))

    def test_a_result_with_a_secret_is_refused(self):
        workqueue.add(self.db, "site", "abc123", "cpu", "tests", "personal-public", "c1")
        task = workqueue.claim(self.db, "vps", ["cpu"], 600, START)
        with self.assertRaises(ValueError):
            workqueue.finish(self.db, "c1", task["token"], "key sk-ant-" + "x" * 40, at=START)

    def test_a_restored_backup_keeps_one_result_per_task(self):
        workqueue.add(self.db, "site", "abc123", "cpu", "tests", "personal-public", "c1")
        workqueue.add(self.db, "site", "abc123", "gpu", "colibri", "personal-public", "g1")
        task = workqueue.claim(self.db, "vps", ["cpu"], 600, START)
        workqueue.finish(self.db, "c1", task["token"], "passed", at=START)
        workqueue.claim(self.db, "notebook", ["gpu"], 600, START)
        backup = workqueue.export(self.db)
        self.assertNotIn("token", backup[0])
        fresh = workqueue.connect(Path(self.tmp.name) / "new.db")
        self.addCleanup(fresh.close)
        self.assertEqual(workqueue.restore(fresh, backup), {"added": 2, "kept": 0})
        states = {row["id"]: row["state"] for row in workqueue.export(fresh)}
        self.assertEqual(states, {"c1": "done", "g1": "expired"})
        self.assertEqual(workqueue.restore(fresh, backup), {"added": 0, "kept": 2})

    def test_local_only_and_private_repositories_never_enter(self):
        repo = Path(self.tmp.name) / "private-repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        ok, why, cls = workqueue.may_enter(repo, "local-only")
        self.assertFalse(ok)
        self.assertIn("never enters the queue", why)
        ok, why, cls = workqueue.may_enter(repo)
        self.assertEqual((ok, cls), (False, "personal-private"))
        self.assertIn("does not go to the remote node", why)
        public = {"folders": [{"path": str(repo), "class": "personal-public"}]}
        with mock.patch("orchestrate.local_config", return_value=public):
            self.assertTrue(workqueue.may_enter(repo)[0])
        self.assertEqual(workqueue.main(["--db", str(Path(self.tmp.name) / "cli.db"), "add", "--repo", str(repo), "--commit", "abc",
                                         "--needs", "cpu", "--command", "tests"]), 1)
        self.assertFalse((Path(self.tmp.name) / "cli.db").exists())

    def test_a_busy_card_leaves_gpu_work_waiting(self):
        with mock.patch("resources.local_busy", return_value="the graphics card has 300 MiB free"):
            self.assertEqual(workqueue.gpu_ready(["cpu", "gpu"]), (["cpu"], "the graphics card has 300 MiB free"))
        with mock.patch("resources.local_busy", return_value=None):
            self.assertEqual(workqueue.gpu_ready(["gpu"]), (["gpu"], None))


if __name__ == "__main__":
    unittest.main()
