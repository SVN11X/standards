"""Token use in one shape for every executor, joined per task. Run: python -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import orchestrate  # noqa: E402
import usage  # noqa: E402

# Two steps of `opencode run --format json`: a tool call and the final answer, with reasoning and cache.
OPENCODE_EVENTS = "\n".join([
    json.dumps({"type": "step_start", "sessionID": "ses_1", "part": {"type": "step-start"}}),
    json.dumps({"type": "text", "sessionID": "ses_1", "part": {"type": "text", "text": "editing"}}),
    json.dumps({"type": "step_finish", "sessionID": "ses_1", "part": {"type": "step-finish", "reason": "tool-calls", "cost": 0,
                "tokens": {"input": 1200, "output": 80, "reasoning": 20, "cache": {"read": 0, "write": 5000}}}}),
    "not json at all",
    json.dumps({"type": "step_finish", "sessionID": "ses_1", "part": {"type": "step-finish", "reason": "stop", "cost": 0.001,
                "tokens": {"input": 300, "output": 40, "reasoning": 0, "cache": {"read": 21415, "write": 0}}}}),
])


class ParseTests(unittest.TestCase):
    def test_opencode_steps_add_up_and_reasoning_counts_as_output(self):
        out = usage.from_opencode(OPENCODE_EVENTS)
        self.assertEqual(out["usage"], {"input_tokens": 1500, "output_tokens": 140, "reasoning_tokens": 20,
                                        "cache_read_tokens": 21415, "cache_write_tokens": 5000})
        self.assertEqual((out["reported_cost_usd"], out["session_id"], out["steps"]), (0.001, "ses_1", 2))

    def test_opencode_text_output_reports_nothing(self):
        out = usage.from_opencode("Done. All tests pass.")
        self.assertEqual(out["usage"], usage.empty())
        self.assertEqual((out["reported_cost_usd"], out["steps"]), (None, 0))

    def test_claude_model_usage_counts_every_model(self):
        reply = {"usage": {"input_tokens": 5, "output_tokens": 10, "cache_read_input_tokens": 100},
                 "modelUsage": {"claude-haiku-5-5": {"inputTokens": 5, "outputTokens": 10, "cacheReadInputTokens": 100,
                                                      "cacheCreationInputTokens": 0, "costUSD": 0.01},
                                "claude-sonnet-5-5": {"inputTokens": 50, "outputTokens": 7, "cacheReadInputTokens": 0,
                                                       "cacheCreationInputTokens": 900, "costUSD": 0.02}}}
        self.assertEqual(usage.from_claude(reply), {"input_tokens": 55, "output_tokens": 17, "reasoning_tokens": None,
                                                    "cache_read_tokens": 100, "cache_write_tokens": 900})

    def test_claude_without_model_usage_reads_usage(self):
        reply = {"usage": {"input_tokens": 2, "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 500,
                           "output_tokens": 10}}
        counted = usage.from_claude(reply)
        self.assertEqual((counted["input_tokens"], counted["cache_write_tokens"], counted["cache_read_tokens"]), (2, 3000, 500))
        self.assertEqual(usage.prompt_tokens(counted), 3502)

    def test_openai_cached_tokens_leave_the_new_input(self):
        counted = usage.from_openai({"prompt_tokens": 1000, "completion_tokens": 50,
                                     "prompt_tokens_details": {"cached_tokens": 800},
                                     "completion_tokens_details": {"reasoning_tokens": 30}})
        self.assertEqual(counted, {"input_tokens": 200, "output_tokens": 50, "reasoning_tokens": 30,
                                   "cache_read_tokens": 800, "cache_write_tokens": None})

    def test_ollama_reports_no_cache(self):
        counted = usage.from_ollama({"prompt_eval_count": 40, "eval_count": 9})
        self.assertEqual((counted["input_tokens"], counted["output_tokens"], counted["cache_read_tokens"]), (40, 9, None))

    def test_a_count_that_is_not_a_count_is_null(self):
        self.assertEqual(usage.from_openai({"prompt_tokens": "12", "completion_tokens": -1}), usage.empty())


class RowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = self.tmp.name
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)

    def test_scope_names_the_task_and_inner_scopes_add_to_it(self):
        with usage.scope(task_id="p/u1", plan_id="p", kind="execute"):
            with usage.scope(kind="review", attempt=2):
                row = usage.call_row("ollama", "m", usage.from_ollama({"eval_count": 4}), "ollama", 2.0)
            outer = usage.current()
        self.assertEqual((row["task_id"], row["plan_id"], row["kind"], row["attempt"]), ("p/u1", "p", "review", 2))
        self.assertEqual(outer["kind"], "execute")
        self.assertEqual(usage.current(), {})

    def test_a_scope_stays_in_its_thread(self):
        seen = []
        with usage.scope(task_id="main"):
            worker = threading.Thread(target=lambda: seen.append(usage.current()))
            worker.start()
            worker.join()
        self.assertEqual(seen, [{}])

    def test_reported_cost_and_extra_charge_stay_apart(self):
        claude = usage.call_row("claude", "haiku", {}, "claude-json", reported_cost_usd=0.04)
        agent = usage.call_row("opencode", "opencode/a-free", {}, "opencode-events", reported_cost_usd=0.0)
        api = usage.call_row("api", "openrouter/x", {}, "openai-usage", charged_usd=0.0123)
        self.assertEqual((claude["reported_cost_usd"], claude["extra_charge_usd"], claude["cost_basis"]), (0.04, 0.0, "subscription"))
        self.assertEqual((agent["extra_charge_usd"], agent["usage_source"]), (None, "none"))
        self.assertEqual(api["extra_charge_usd"], 0.0123)

    def test_a_task_counts_failed_attempts_and_reviews(self):
        rows = []
        with usage.scope(task_id="p/u1", plan_id="p", kind="execute"):
            for attempt, tokens in ((1, 900), (2, 400)):
                with usage.scope(attempt=attempt):
                    rows.append(usage.call_row("opencode", "m", {"input_tokens": tokens, "output_tokens": 10,
                                                                 "cache_read_tokens": 1000}, "opencode-events"))
            with usage.scope(kind="review"):
                rows.append(usage.call_row("ollama", "r", {"input_tokens": 300, "output_tokens": 20}, "ollama"))
                rows.append(usage.call_row("ollama", "r", {}, "ollama"))
        rows.append(usage.outcome_row("p/u1", plan_id="p", accepted=True, attempts=2, tests_passed=True,
                                      review_passed=True, duration_seconds=31.5, executor="opencode", model="m"))
        with usage.scope(plan_id="p", kind="plan"):
            rows.append(usage.call_row("claude", "haiku", {"input_tokens": 50, "output_tokens": 500}, "claude-json",
                                       reported_cost_usd=0.02))
        found = {t["task_id"]: t for t in usage.tasks(rows)}
        task = found["p/u1"]
        self.assertEqual(task["usage"], {"input_tokens": 1600, "output_tokens": 40, "reasoning_tokens": None,
                                         "cache_read_tokens": 2000, "cache_write_tokens": None})
        self.assertEqual((task["calls"], task["kinds"], task["unreported_calls"]), (4, {"execute": 2, "review": 2}, 1))
        self.assertEqual(task["execution"], {"duration_seconds": 31.5, "attempts": 2, "tests_passed": True, "review_passed": True})
        self.assertTrue(task["result"]["accepted"])
        self.assertEqual(found["p/plan"]["result"]["reported_cost_usd"], 0.02)
        self.assertIsNone(found["p/plan"]["result"]["accepted"])

    def test_rows_before_schema_2_still_read(self):
        orchestrate.append_telemetry({"provider": "claude", "model": "haiku", "kind": "plan", "prompt_tokens": 3502,
                                      "completion_tokens": 10, "seconds": 1.0, "reported_cost_usd": 0.01})
        usage.record("ollama", "m", {"input_tokens": 7, "output_tokens": 3}, "ollama", 1.0)
        models = usage.by_model(usage.read_rows())
        self.assertEqual((models["claude/haiku"]["input"], models["claude/haiku"]["cache_read"]), (3502, None))
        self.assertEqual(models["ollama/m"]["output"], 3)

    def test_read_rows_keeps_the_last_lines_only_when_asked(self):
        for n in range(5):
            usage.record("ollama", "m", {"input_tokens": n}, "ollama")
        self.assertEqual([r["usage"]["input_tokens"] for r in usage.read_rows(limit=2)], [3, 4])

    def test_cli_prints_tasks_as_json(self):
        with usage.scope(task_id="p/u1", plan_id="p", kind="execute"):
            usage.record("opencode", "m", {"input_tokens": 10}, "opencode-events")
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(usage.main(["tasks", "--plan", "p", "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())[0]["usage"]["input_tokens"], 10)


def arm_rows(plans: int, tokens: int, lose=(), reviewer_cost=None) -> list[dict]:
    rows = []
    for n in range(plans):
        plan = f"auto-{n:014d}"
        with usage.scope(plan_id=plan, kind="plan"):
            rows.append(usage.call_row("claude", "haiku", {"input_tokens": 100, "cache_read_tokens": 4000, "output_tokens": 300},
                                       "claude-json", reported_cost_usd=0.01))
        with usage.scope(task_id=f"{plan}/u1", plan_id=plan, kind="execute"):
            rows.append(usage.call_row("opencode", "m", {"input_tokens": tokens, "output_tokens": 200}, "opencode-events",
                                       reported_cost_usd=0.0))
            with usage.scope(kind="review"):
                rows.append(usage.call_row("ollama", "r", {"input_tokens": 500, "output_tokens": 50}, "ollama",
                                           reported_cost_usd=reviewer_cost))
        accepted = n not in lose
        rows.append(usage.outcome_row(f"{plan}/u1", plan_id=plan, accepted=accepted, attempts=1, tests_passed=accepted,
                                      review_passed=accepted))
        rows.append(usage.outcome_row(plan, plan_id=plan, accepted=accepted, attempts=1, tests_passed=accepted,
                                      review_passed=accepted, duration_seconds=60 + n))
    return rows


class CompareTests(unittest.TestCase):
    def test_a_cheaper_candidate_that_loses_nothing_passes_the_pilot(self):
        result = usage.compare(arm_rows(30, 4000), arm_rows(30, 2400))
        self.assertEqual((result["metric"], result["pairs"], result["regressions"]), ("new-tokens", 30, []))
        self.assertEqual(result["baseline"]["per_accepted"], 5150)
        self.assertGreaterEqual(result["saving"], 0.15)
        self.assertTrue(result["passes_pilot"], result["why_not"])
        self.assertEqual(result["baseline"]["p90_seconds"], 86)

    def test_a_plan_the_baseline_delivered_and_the_candidate_lost_fails_it(self):
        result = usage.compare(arm_rows(30, 4000), arm_rows(30, 1000, lose=[7]))
        self.assertEqual(result["regressions"], ["auto-00000000000007"])
        self.assertFalse(result["passes_pilot"])
        self.assertIn("the candidate did not", " ".join(result["why_not"]))

    def test_too_few_pairs_or_too_little_saving_is_named(self):
        result = usage.compare(arm_rows(10, 4000), arm_rows(12, 3900))
        self.assertEqual(result["pairs"], 10)
        self.assertEqual(result["only_in_candidate"], ["auto-00000000000010", "auto-00000000000011"])
        why = " ".join(result["why_not"])
        self.assertIn("10 paired plans, 30 needed", why)
        self.assertIn("needed", why.split(";")[-1])

    def test_cost_is_compared_only_when_every_call_reported_one(self):
        self.assertEqual(usage.compare(arm_rows(3, 10, reviewer_cost=0.0), arm_rows(3, 10, reviewer_cost=0.0))["metric"], "cost")
        self.assertEqual(usage.compare(arm_rows(3, 10), arm_rows(3, 10))["metric"], "new-tokens")

    def test_the_command_reads_two_homes(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            for name, tokens in (("a", 4000), ("b", 2000)):
                folder = Path(tmp) / name
                folder.mkdir()
                (folder / "telemetry.jsonl").write_text("".join(json.dumps(r) + "\n" for r in arm_rows(30, tokens)))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = usage.main(["compare", str(Path(tmp) / "a"), str(Path(tmp) / "b")])
        self.assertEqual(code, 0)
        self.assertIn("passes the pilot", out.getvalue())


class FlagTests(unittest.TestCase):
    CONF = {"executors": {"opencode": {"command": ["opencode", "run", "--model", "{model}", "{message}"],
                                       "usage_flags": ["--format", "json"]}}}

    def setUp(self):
        orchestrate.help_text.cache_clear()
        self.addCleanup(orchestrate.help_text.cache_clear)

    def help(self, text):
        return mock.patch.object(orchestrate, "run", return_value={"exit": 0, "stdout": text, "stderr": ""})

    def test_flags_are_added_only_when_the_help_lists_them(self):
        with self.help("Options:\n  --model  model to use\n  --format  format: default or json\n"):
            self.assertEqual(orchestrate.usage_flags("opencode", self.CONF, None), ["--format", "json"])
        orchestrate.help_text.cache_clear()
        with self.help("Options:\n  --model  model to use\n"):
            self.assertEqual(orchestrate.usage_flags("opencode", self.CONF, None), [])

    def test_a_command_from_the_caller_is_used_as_given(self):
        with self.help("  --format  json\n"):
            self.assertEqual(orchestrate.usage_flags("opencode", self.CONF, ["fake"]), [])

    def test_an_executor_without_usage_flags_gets_none(self):
        self.assertEqual(orchestrate.usage_flags("claude", {"executors": {"claude": {"command": ["claude"]}}}, None), [])


class ExecutorTests(unittest.TestCase):
    def test_each_ended_unit_leaves_an_outcome_next_to_its_review(self):
        import test_execute
        case = test_execute.Base()
        case.setUp()
        self.addCleanup(case.doCleanups)

        def reviewer(prompt):
            usage.record("ollama", "rev:1b", {"input_tokens": 120, "output_tokens": 8}, "ollama")
            return test_execute.DIFF_OK

        run = case.executor(test_execute.plan(test_execute.unit("u1", ["a.txt"])), test_execute.FakeAgent(), reviewer)
        run.run()
        rows = usage.read_rows()
        review = [r for r in rows if r["kind"] == "review"]
        self.assertEqual([(r["task_id"], r["plan_id"]) for r in review], [("plan1/u1", "plan1")])
        found = {t["task_id"]: t for t in usage.tasks(rows, "plan1")}
        task = found["plan1/u1"]
        self.assertEqual((task["result"]["accepted"], task["execution"]["review_passed"]), (True, True))
        self.assertEqual(task["usage"]["input_tokens"], 120)
        self.assertTrue(found["plan1"]["result"]["accepted"])
        self.assertEqual(usage.plan_results(rows)["plan1"]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
