"""The supervisor resumes plans whose process is gone and leaves paused, finished and live ones alone."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import execute  # noqa: E402
import orchestrate  # noqa: E402
import supervisor  # noqa: E402


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.spawned = []

    def spawn(self, args, repo, plan_id):
        self.spawned.append(plan_id)
        return {"detached": True, "pid": 1, "plan_id": plan_id}

    def plan(self, pid, statuses, **state):
        orchestrate.write_json(orchestrate.home() / "plans" / f"{pid}.json",
                               {"plan_id": pid, "repo": str(self.repo), "units": [{"id": k} for k in statuses]})
        orchestrate.write_json(execute.state_file(pid), {"plan_id": pid, "units": {k: {"status": v} for k, v in statuses.items()}, **state})

    def tick(self, alive=lambda pid: False):
        return supervisor.tick(self.spawn, alive)

    def test_a_plan_with_pending_work_and_no_process_is_resumed(self):
        self.plan("a", {"u1": "passed", "u2": "running"})
        self.assertEqual([r["plan_id"] for r in self.tick()], ["a"])

    def test_finished_paused_and_live_plans_are_left_alone(self):
        self.plan("done", {"u1": "passed"}, finished="2026-11-16")
        self.plan("paused", {"u1": "pending"})
        orchestrate.write_json(execute.control_file("paused"), {"paused": True})
        self.plan("live", {"u1": "running"})
        supervisor.pid_file("live").parent.mkdir(parents=True, exist_ok=True)
        supervisor.pid_file("live").write_text("4242")
        self.assertEqual(self.tick(alive=lambda pid: pid == 4242), [])

    def test_a_pause_survives_a_restart_of_the_supervisor(self):
        self.plan("p", {"u1": "pending"})
        execute.set_control("p", paused=True)
        self.assertEqual(self.tick(), [])
        execute.set_control("p", paused=False)
        self.assertEqual(len(self.tick()), 1)

    def test_a_plan_that_never_progresses_is_not_resumed_forever(self):
        self.plan("loop", {"u1": "running"})
        rows = [self.tick() for _ in range(supervisor.MAX_STALLS + 2)]
        self.assertEqual([bool(r[0].get("detached")) for r in rows], [True] * supervisor.MAX_STALLS + [False, False])
        self.assertIn("without progress", rows[-1][0]["skipped"])
        self.assertEqual(len(self.spawned), supervisor.MAX_STALLS)

    def test_a_plan_whose_units_are_all_blocked_waits_for_the_owner(self):
        self.plan("b", {"u1": "blocked", "u2": "skipped"})
        self.assertEqual(self.tick(), [])

    def test_only_one_supervisor_holds_the_lock(self):
        supervisor.lock_path().parent.mkdir(parents=True, exist_ok=True)
        supervisor.lock_path().write_text("999999")
        self.assertFalse(supervisor.take_lock(lambda pid: True))
        self.assertTrue(supervisor.take_lock(lambda pid: False))

    def test_a_second_session_joins_a_running_plan_instead_of_starting_another(self):
        import plan_autopilot
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(sleeper.kill)
        supervisor.pid_file("same").parent.mkdir(parents=True, exist_ok=True)
        supervisor.pid_file("same").write_text(str(sleeper.pid))
        # wraps: on Windows alive() itself starts tasklist, so only a start of plan_autopilot.py counts.
        with mock.patch.object(plan_autopilot.subprocess, "Popen", wraps=subprocess.Popen) as popen:
            joined = plan_autopilot.detach(["run", "x"], self.repo, "same")
        script = str(Path(plan_autopilot.__file__).resolve())
        self.assertEqual([c for c in popen.call_args_list if script in map(str, c.args[0])], [])
        self.assertEqual(joined["already_running"], sleeper.pid)

    def test_install_names_the_windows_task_scheduler(self):
        command = supervisor.install_command()
        self.assertEqual(command[:2], ["schtasks", "/Create"])
        self.assertIn(supervisor.TASK_NAME, command)

    def interpreters(self, *names):
        folder = Path(self.tmp.name) / "py"
        folder.mkdir(exist_ok=True)
        for name in names:
            (folder / name).write_text("", encoding="utf-8")
        return folder

    def test_the_task_runs_pythonw_so_no_console_opens_every_few_minutes(self):
        folder = self.interpreters("python.exe", "pythonw.exe")
        with mock.patch.object(supervisor, "windows", return_value=True), \
                mock.patch.object(supervisor.sys, "executable", str(folder / "python.exe")):
            run = supervisor.install_command()[-1]
        self.assertTrue(run.startswith(f'"{folder / "pythonw.exe"}" '), run)

    def test_without_pythonw_the_task_keeps_the_current_interpreter(self):
        folder = self.interpreters("python.exe")
        with mock.patch.object(supervisor, "windows", return_value=True), \
                mock.patch.object(supervisor.sys, "executable", str(folder / "python.exe")):
            run = supervisor.install_command()[-1]
        self.assertTrue(run.startswith(f'"{folder / "python.exe"}" '), run)

    def test_a_resumed_plan_runs_in_a_hidden_console_that_its_tools_share(self):
        import plan_autopilot
        folder = self.interpreters("python.exe", "pythonw.exe")
        started = mock.MagicMock(pid=4321)
        with mock.patch.object(supervisor, "windows", return_value=True), \
                mock.patch.object(supervisor, "alive", return_value=False), \
                mock.patch.object(plan_autopilot.sys, "executable", str(folder / "pythonw.exe")), \
                mock.patch.object(plan_autopilot.subprocess, "Popen", return_value=started) as popen:
            result = plan_autopilot.detach(["run", "x"], self.repo, "hidden")
        self.assertEqual(result["pid"], 4321)
        self.assertEqual(popen.call_args.args[0][0], str(folder / "python.exe"))
        flags = popen.call_args.kwargs["creationflags"]
        self.assertTrue(flags & 0x08000000, "CREATE_NO_WINDOW")
        self.assertFalse(flags & 0x00000008, "DETACHED_PROCESS")


if __name__ == "__main__":
    unittest.main()
