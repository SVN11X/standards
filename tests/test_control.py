"""Standards AI Control: run summaries, telemetry totals and the page file."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import control  # noqa: E402
import control_jobs  # noqa: E402
import orchestrate  # noqa: E402

PLAN = {"plan_id": "auto-" + "a" * 14, "goal": "Add a flag\nmore", "planner": {"backend": "claude", "model": "haiku", "tier": "light"},
        "units": [{"id": "u1", "title": "one", "risk": "green", "depends_on": []},
                  {"id": "u2", "title": "two", "risk": "red", "depends_on": ["u1"]}]}


class ControlTests(unittest.TestCase):
    def test_finished_run_is_complete_and_counts_its_checks(self):
        data = {"id": "x", "state": "failed", "task": "Fix it\nmore", "checks": {"a": "PASS", "b": "FAIL"},
                "history": [{"state": "planned", "at": "t0", "note": ""}, {"state": "failed", "at": "t1", "note": "tests failed"}]}
        row = control.run_summary(data)
        self.assertEqual((row["stage_progress"], row["checks_passed"], row["checks_total"]), (1.0, 1, 2))
        self.assertEqual(row["task"], "Fix it")

    def test_running_run_progress_comes_from_stages_reached(self):
        data = {"state": "running", "history": [{"state": "planned", "at": "t"}, {"state": "approved", "at": "t"}]}
        self.assertEqual(control.run_summary(data)["stage_progress"], 0.5)

    def test_telemetry_sums_tokens_per_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = orchestrate.home
            orchestrate.home = lambda: Path(tmp)
            try:
                for tokens in (3, 4):
                    orchestrate.append_telemetry({"provider": "colibri", "model": "m", "prompt_tokens": 10,
                                                  "completion_tokens": tokens, "seconds": 1.0})
                total = control.telemetry()["by_model"]["colibri/m"]
            finally:
                orchestrate.home = original
        self.assertEqual((total["requests"], total["input"], total["output"]), (2, 20, 7))

    def test_page_exists_and_names_unavailable_metrics(self):
        text = control.PAGE.read_text(encoding="utf-8")
        self.assertIn("Not available", text)
        self.assertNotIn("0.0.0.0", text)

    def test_bad_jsonl_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(json.dumps({"a": 1}) + "\nnot json\n", encoding="utf-8")
            self.assertEqual(control.read_jsonl(path), [{"a": 1}])


class AutopilotViewTests(unittest.TestCase):
    def test_a_plan_shows_each_unit_with_its_model_provider_and_what_it_waits_on(self):
        state = {"units": {"u1": {"status": "running", "at": orchestrate.now(), "model": "opencode/free-a",
                                  "executor": "opencode", "channel": "remote_free"}},
                 "publication": {"pr": "https://github.com/o/r/pull/1", "ci": {"state": "pending"}}}
        view = control.plan_view(PLAN, state, {"paused": True}, [{"event": "started", "unit": "u1"}])
        one, two = view["units"]
        self.assertEqual((one["status"], one["model"], one["executor"], one["channel"]), ("running", "opencode/free-a", "opencode", "remote_free"))
        self.assertIsInstance(one["seconds"], float)
        self.assertEqual((two["status"], two["waits_on"], two["model"]), ("pending", ["u1"], None))
        self.assertEqual((view["done"], view["total"], view["paused"], view["goal"]), (0, 2, True, "Add a flag"))
        self.assertEqual(len(view["approvals"]), 2)
        self.assertEqual(view["planner"]["model"], "haiku")

    def test_a_unit_is_done_only_when_its_state_says_passed(self):
        quiet = {"units": {"u1": {"status": "running", "at": "2026-01-01T00:00:00+00:00"}}}
        view = control.plan_view(PLAN, quiet, {}, [])
        self.assertEqual((view["done"], view["units"][0]["status"], view["finished"]), (0, "running", None))
        self.assertEqual(control.plan_view(PLAN, {"units": {"u1": {"status": "passed"}}}, {}, [])["done"], 1)

    def test_autopilot_reads_plans_and_state_from_the_home_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = orchestrate.home
            orchestrate.home = lambda: Path(tmp)
            try:
                orchestrate.write_json(Path(tmp) / "plans" / f"{PLAN['plan_id']}.json", PLAN)
                orchestrate.write_json(Path(tmp) / "executions" / f"{PLAN['plan_id']}.json",
                                       {"units": {"u1": {"status": "running", "at": orchestrate.now(), "model": "m"}}})
                data = control.autopilot()
            finally:
                orchestrate.home = original
        self.assertEqual([a["id"] for a in data["agents"]], ["u1"])
        self.assertEqual(data["limits"]["pools"], {"remote_free": 2, "local": 1})

    def test_page_has_the_autopilot_view_with_folded_logs(self):
        text = control.PAGE.read_text(encoding="utf-8")
        for word in ('"Autopilot"', "Pause new assignments", "Create plan", "<details><summary>Events"):
            self.assertIn(word, text)


class AutopilotJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "plan_autopilot.py").write_text("")
        (self.root / "plans").mkdir()
        self.plan = self.root / "plans" / f"{PLAN['plan_id']}.json"
        self.plan.write_text("{}")

    def test_commands_are_fixed_argv_and_auto_merge_is_never_offered(self):
        argv = control_jobs.autopilot_command("plan", self.root, instruction="Add a flag; rm -rf /", planner="haiku")
        self.assertEqual(argv[2:6], ["plan", "--instruction", "Add a flag; rm -rf /", "--planner"])
        run = control_jobs.autopilot_command("run", self.root, plan=self.plan, publish="pr")
        self.assertEqual(run[-2:], ["--publish", "pr"])
        for bad in ({"publish": "auto-merge"}, {"plan": self.root / "plans" / "other.json"}, {"plan": None}):
            with self.assertRaises(ValueError):
                control_jobs.autopilot_command("run", self.root, **{"plan": self.plan, "publish": "none", **bad})
        for bad in ({"instruction": ""}, {"instruction": "x" * 6001}, {"planner": "gpt"}):
            with self.assertRaises(ValueError):
                control_jobs.autopilot_command("plan", self.root, **{"instruction": "ok", "planner": "auto", **bad})

    def test_one_job_per_plan_and_the_exit_code_decides_the_state(self):
        class Proc:
            pid, code = 4242, None

            def poll(self):
                return self.code

        proc = Proc()
        manager = control_jobs.AutopilotManager(self.root, self.root / "jobs", self.root / "plans", popen=lambda *a, **k: proc)
        job = manager.start(PLAN["plan_id"])
        self.assertEqual((job["state"], job["kind"]), ("running", "run"))
        with self.assertRaises(RuntimeError):
            manager.start(PLAN["plan_id"])
        self.assertEqual(manager.snapshot()[0]["state"], "running")
        proc.code = 1
        self.assertEqual(manager.snapshot()[0]["state"], "failed")
        with self.assertRaises(ValueError):
            manager.start("../../etc")

    def test_handler_refuses_an_unknown_plan_and_a_start_without_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = orchestrate.home
            orchestrate.home = lambda: Path(tmp)
            handler = control.Handler.__new__(control.Handler)
            handler.autopilot = control_jobs.AutopilotManager(self.root, Path(tmp) / "jobs", Path(tmp) / "plans",
                                                             popen=lambda *a, **k: None)
            try:
                orchestrate.write_json(Path(tmp) / "plans" / f"{PLAN['plan_id']}.json", PLAN)
                for action, data in (("start", {"plan_id": "auto-" + "f" * 14, "confirmed": True}),
                                     ("start", {"plan_id": PLAN["plan_id"]}), ("pause", {"plan_id": "../x"}),
                                     ("cancel", {"plan_id": PLAN["plan_id"], "unit": "u9"}), ("merge", {"plan_id": PLAN["plan_id"]})):
                    with self.assertRaises(ValueError, msg=action):
                        handler.autopilot_action(action, data)
                self.assertTrue(handler.autopilot_action("pause", {"plan_id": PLAN["plan_id"]})["paused"])
                self.assertFalse(handler.autopilot_action("unpause", {"plan_id": PLAN["plan_id"]})["paused"])
                self.assertEqual(handler.autopilot_action("cancel", {"plan_id": PLAN["plan_id"], "unit": "u2"})["cancel"], ["u2"])
            finally:
                orchestrate.home = original


if __name__ == "__main__":
    unittest.main()
