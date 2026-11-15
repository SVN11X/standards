"""Planning agent: the tier comes from a score, Claude passes the cost and privacy gate, Opus needs a reason."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import orchestrate  # noqa: E402
import plan_autopilot as autopilot  # noqa: E402
import planner  # noqa: E402

CONF = orchestrate.policy()
SMALL = "Fix the typo in the README title"
MEDIUM = ("Add a retry option to scripts/providers.py and scripts/analyze.py, cover it in tests/test_providers.py "
          "and describe the new schema field in docs/006-model-analyzer.md and settings/providers.yml")
LARGE = ("Redesign the architecture of the orchestrator as a multi-agent pipeline. Migrate the protocol between "
         "scripts, settings, schemas, tests, docs and hooks.\n- scheduler\n- planner\n- executor\n- dashboard\n- security review\n"
         + "It must keep every permission and deploy rule. " * 12)
PATHS = ["scripts/providers.py", "scripts/analyze.py", "tests/test_providers.py", "docs/006-model-analyzer.md",
         "settings/providers.yml", "schemas/work-plan.schema.json", "hooks/guard.py", "README.md"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        os.environ["STANDARDS_HOME"] = str(self.repo / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)

    def local(self, cls="personal-public", **extra):
        return {"folders": [{"path": str(self.repo), "class": cls, **extra}]}

    def select(self, text, asked=None, cls="personal-public", **kw):
        return planner.select(text, self.repo, CONF, self.local(cls), asked, PATHS, cli="claude", **kw)


class TierTests(Base):
    def test_a_program_scores_the_request_into_three_tiers(self):
        self.assertEqual(planner.complexity(SMALL, PATHS, CONF)[0], "light")
        self.assertEqual(planner.complexity(MEDIUM, PATHS, CONF)[0], "medium")
        self.assertEqual(planner.complexity(LARGE, PATHS, CONF)[0], "advanced")

    def test_auto_picks_the_smallest_model_that_is_enough(self):
        self.assertEqual([self.select(t)["model"] for t in (SMALL, MEDIUM, LARGE)], ["haiku", "sonnet", "opus"])

    def test_opus_without_a_reason_falls_to_the_tier_of_the_score(self):
        choice = self.select(SMALL, "opus")
        self.assertEqual((choice["model"], choice["tier"]), ("haiku", "light"))
        self.assertTrue(any("Opus was asked" in r for r in choice["reasons"]))

    def test_opus_with_a_reason_is_the_owners_call_and_is_recorded(self):
        choice = self.select(SMALL, "opus", opus_reason="the last two plans missed the migration order")
        self.assertEqual(choice["model"], "opus")
        self.assertTrue(any("migration order" in r for r in choice["reasons"]))

    def test_the_owner_may_always_ask_for_a_smaller_model(self):
        self.assertEqual(self.select(LARGE, "haiku")["model"], "haiku")
        self.assertEqual(self.select(LARGE, "local")["backend"], "ollama")

    def test_a_structure_repair_never_runs_on_opus(self):
        self.assertEqual(planner.repairer(self.select(LARGE), CONF)["model"], "haiku")
        worse = {**CONF, "planning": {**CONF["planning"], "repair_tier": "advanced"}}
        self.assertEqual(planner.repairer(self.select(LARGE), worse)["model"], "haiku")

    def test_a_blocked_draft_climbs_one_tier_and_never_reaches_opus_on_its_own(self):
        light = self.select(SMALL)
        medium = planner.escalate(light, CONF, 0)
        self.assertEqual(medium["model"], "sonnet")
        self.assertIsNone(planner.escalate(light, CONF, 1))
        self.assertIsNone(planner.escalate(medium, CONF, 0))
        allowed = {**CONF, "planning": {**CONF["planning"], "opus_on_block": True}}
        self.assertEqual(planner.escalate(medium, allowed, 0)["model"], "opus")


class GateTests(Base):
    def test_restricted_and_work_code_never_reach_claude(self):
        for cls in ("restricted", "work"):
            choice = self.select(LARGE, "opus", cls=cls, opus_reason="insist")
            self.assertEqual(choice["backend"], "ollama", cls)
            self.assertTrue(any("Claude is not used" in r for r in choice["reasons"]))

    def test_work_code_reaches_claude_only_with_the_owners_consent_for_that_folder(self):
        choice = planner.select(MEDIUM, self.repo, CONF, self.local("work", allow_remote_claude=True), None, PATHS, cli="claude")
        self.assertEqual(choice["backend"], "claude")

    def test_a_free_or_local_cost_mode_keeps_the_subscription_out(self):
        for mode in ("local-only", "free-strict"):
            self.assertEqual(self.select(MEDIUM, mode=mode)["backend"], "ollama", mode)

    def test_no_cli_means_the_local_planner(self):
        choice = planner.select(SMALL, self.repo, CONF, self.local(), None, PATHS, cli="")
        self.assertEqual(choice["backend"], "ollama")


class CallTests(Base):
    def run_fake(self, reply, seen):
        def run(cmd, cwd=None, timeout=60, env=None, stdin=None, **kw):
            seen.append({"cmd": cmd, "env": env, "stdin": stdin, "cwd": cwd, "timeout": timeout})
            return {"exit": 0, "stdout": reply, "stderr": "", "seconds": 2.0, "timeout": False}
        return run

    def test_one_call_with_the_model_named_json_out_and_no_api_key(self):
        seen = []
        reply = json.dumps({"type": "result", "is_error": False, "result": '{"units": []}', "total_cost_usd": 0.01,
                            "usage": {"input_tokens": 900, "output_tokens": 100}})
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-not-a-real-key"}):
            out = planner.ask_claude([{"role": "user", "content": "plan this"}], "haiku", CONF,
                                     run=self.run_fake(reply, seen), flags=["--tools", "--no-session-persistence"])
        call = seen[0]
        self.assertEqual(call["cmd"][:6], ["claude", "-p", "--model", "haiku", "--output-format", "json"])
        self.assertIn("--no-session-persistence", call["cmd"])
        self.assertNotIn("--max-turns", call["cmd"])
        self.assertNotIn("ANTHROPIC_API_KEY", call["env"])
        self.assertEqual(call["stdin"], "plan this")
        self.assertNotEqual(Path(call["cwd"]).resolve(), Path.cwd().resolve())
        self.assertEqual((out["text"], out["input_tokens"], out["output_tokens"]), ('{"units": []}', 900, 100))
        row = json.loads((orchestrate.home() / "telemetry.jsonl").read_text().splitlines()[-1])
        self.assertEqual((row["provider"], row["model"], row["tokens_per_second"]), ("claude", "haiku", 50.0))

    def test_tokens_the_cli_did_not_report_stay_null(self):
        out = planner.ask_claude([{"role": "user", "content": "x"}], "haiku", CONF, run=self.run_fake("plain text", []), flags=[])
        self.assertEqual((out["text"], out["input_tokens"], out["reported_cost_usd"]), ("plain text", None, None))

    def test_a_failed_or_silent_call_is_an_error_not_an_empty_plan(self):
        def failing(cmd, **kw):
            return {"exit": 1, "stdout": "", "stderr": "not logged in", "seconds": 0.1, "timeout": False}

        def silent(cmd, **kw):
            return {"exit": None, "stdout": "", "stderr": "timed out", "seconds": 180, "timeout": True}
        for run in (failing, silent):
            with self.assertRaises(planner.PlannerError):
                planner.ask_claude([{"role": "user", "content": "x"}], "haiku", CONF, run=run, flags=[])

    def test_a_second_opus_call_at_the_same_time_is_refused(self):
        held = planner.opus_slot(CONF)
        try:
            with self.assertRaisesRegex(planner.PlannerError, "one at a time"):
                planner.ask_claude([{"role": "user", "content": "x"}], "opus", CONF, run=self.run_fake("{}", []), flags=[])
        finally:
            held.unlink()
        planner.ask_claude([{"role": "user", "content": "x"}], "opus", CONF, run=self.run_fake("{}", []), flags=[])
        self.assertFalse((orchestrate.home() / "planner-opus.lock").exists())

    def test_only_flags_the_installed_cli_lists_are_used(self):
        text = "Options:\n  --model <model>   Model\n  --max-turns <n>   Turns\n  -p, --print   Print\n"
        self.assertEqual(planner.cli_flags(lambda cmd, **kw: {"stdout": text, "stderr": ""}), ["--max-turns"])


class MakePlanTests(Base):
    POLICY = {**CONF, "tasks": {"edit-small": ["opencode"]}, "planner_tasks": ["plan"], "protected": []}
    TEST = "python -m unittest discover -s tests"

    def setUp(self):
        super().setUp()
        (self.repo / "a.py").write_text("x\n")
        for target, value in ((autopilot.workplan, ["a.py"]),):
            patch = mock.patch.object(target, "tracked_files", return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(autopilot.orchestrate, "git", return_value="a" * 40)
        patch.start()
        self.addCleanup(patch.stop)

    def unit(self, **change):
        return {"title": "t", "goal": "Change a.py", "task_type": "edit-small", "allowed": ["a.py"], "criteria": ["ok"],
                "risk": "green", "depends_on": [], **change}

    def make(self, replies, text=SMALL, asked=None):
        models = []

        def ask(messages, model, conf):
            models.append(model)
            return {"text": json.dumps(replies.pop(0)), "model": model, "seconds": 1.0, "input_tokens": 10,
                    "output_tokens": 5, "reported_cost_usd": None}
        plan = autopilot.make_plan(text, self.repo, self.TEST, asked=asked, policy=self.POLICY, local=self.local(), ask_claude=ask)
        return plan, models

    def test_a_small_request_is_one_haiku_call_and_the_plan_names_its_planner(self):
        plan, models = self.make([{"units": [self.unit()]}])
        self.assertEqual(models, ["haiku"])
        self.assertEqual((plan["planner"]["model"], plan["planner"]["repair_calls"]), ("haiku", 0))
        self.assertEqual(plan["planner"]["calls"][0]["output_tokens"], 5)

    def test_an_advanced_draft_is_repaired_by_haiku(self):
        plan, models = self.make([{"units": [self.unit(criteria=[])]}, {"units": [self.unit()]}], text=LARGE)
        self.assertEqual(models, ["opus", "haiku"])

    def test_a_draft_that_stays_invalid_moves_one_tier_up_once(self):
        bad = {"units": [self.unit(criteria=[])]}
        plan, models = self.make([bad, bad, {"units": [self.unit()]}])
        self.assertEqual(models, ["haiku", "haiku", "sonnet"])
        self.assertEqual(plan["planner"]["escalations"], 1)

    def test_a_refused_scope_is_not_retried_on_a_stronger_model(self):
        with self.assertRaises(autopilot.Blocked):
            self.make([{"units": [self.unit(allowed=["../x.py"])]}])


if __name__ == "__main__":
    unittest.main()
