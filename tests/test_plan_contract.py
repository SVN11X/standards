"""Planner draft contract: parser, safe fixes, every problem at once, one repair call and its guard."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_autopilot as autopilot  # noqa: E402
import plan_contract as contract  # noqa: E402

POLICY = {"tasks": {"fix-test": ["opencode"], "edit-small": ["opencode"], "docs-small": ["opencode"], "test": ["tools"]},
          "planner_tasks": ["plan"], "protected": ["AGENTS.md"]}
TEST = "python -m unittest discover -s tests"
TRACKED = ["a.py", "b.py", "c.py", "docs/guide.md"]


def unit(**change):
    data = {"title": "Edit a", "goal": "Change a.py", "task_type": "edit-small", "allowed": ["a.py"],
            "new_files": [], "criteria": ["Tests pass"], "risk": "green", "depends_on": []}
    data.update(change)
    return data


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        for name in TRACKED:
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text("x\n", encoding="utf-8")
        patch = mock.patch.object(contract.workplan, "tracked_files", return_value=list(TRACKED))
        patch.start()
        self.addCleanup(patch.stop)

    def normalize(self, *units, instruction="Edit files"):
        return contract.normalize({"units": list(units)}, instruction, self.repo, POLICY)


class ParseTests(unittest.TestCase):
    def test_fence_prose_and_trailing_commas_are_syntax_fixes(self):
        text = 'Here is the plan:\n```json\n{"units": [{"title": "x",},],}\n```\nDone.'
        raw, fixes, problem = contract.parse(text)
        self.assertIsNone(problem)
        self.assertEqual(raw, {"units": [{"title": "x"}]})
        self.assertIn("removed trailing commas", fixes)

    def test_cut_off_json_is_a_problem_never_a_guess(self):
        raw, _, problem = contract.parse('{"units": [{"title": "x", "goal": "cha')
        self.assertIsNone(raw)
        self.assertIn("cut off", problem)

    def test_no_object_and_non_object(self):
        self.assertIn("no JSON object", contract.parse("I cannot plan this")[2])
        self.assertIsNotNone(contract.parse("[1, 2]")[2])


class NormalizeTests(Base):
    def test_invalid_risk_becomes_red_and_a_known_word_keeps_its_level(self):
        units, fixes, issues = self.normalize(unit(risk="banana"), unit(risk="LOW", allowed=["b.py"]),
                                              unit(risk=7, allowed=["c.py"]), unit(risk="medium", allowed=["docs/guide.md"]))
        self.assertEqual(issues, [])
        self.assertEqual([u["risk"] for u in units], ["red", "green", "red", "yellow"])
        self.assertTrue(any("'banana' became red" in f for f in fixes))

    def test_a_risky_request_is_red_whatever_the_draft_says(self):
        units, _, _ = self.normalize(unit(risk="low"), instruction="Change the login permissions")
        self.assertEqual(units[0]["risk"], "red")

    def test_many_structure_errors_are_fixed_here_with_no_model(self):
        draft = unit(title=None, task_type="Fix_Test", allowed="./a.py", criteria="Tests pass", risk="Critical",
                     new_files=None, depends_on=None)
        other = unit(allowed=["docs\\guide.md", "docs/guide.md"], new_files=["docs/new.md"], depends_on="1",
                     acceptance={"criteria": ["  ", "Guide names the command"]})
        del other["criteria"]
        units, fixes, issues = self.normalize(draft, other)
        self.assertEqual(issues, [])
        self.assertEqual(units[0]["task_type"], "fix-test")
        self.assertEqual(units[0]["allowed"], ["a.py"])
        self.assertEqual(units[0]["acceptance"]["criteria"], ["Tests pass"])
        self.assertEqual(units[0]["risk"], "red")
        self.assertEqual(units[0]["title"], "Change a.py")
        self.assertEqual(units[1]["allowed"], ["docs/guide.md", "docs/new.md"])
        self.assertEqual(units[1]["acceptance"]["criteria"], ["Guide names the command"])
        self.assertEqual(units[1]["depends_on"], ["u1"])
        self.assertGreaterEqual(len(fixes), 8)

    def test_every_problem_is_reported_in_one_pass(self):
        _, _, issues = self.normalize(unit(criteria=[]), unit(task_type="plan", allowed=["b.py"]),
                                      unit(goal="", allowed=["missing.py"]))
        self.assertEqual({(i["unit"], i["field"]) for i in issues},
                         {(1, "criteria"), (2, "task_type"), (3, "goal"), (3, "allowed")})
        self.assertFalse(any(i["fatal"] for i in issues))

    def test_unsafe_path_is_fatal_and_named_with_the_other_problems(self):
        _, _, issues = self.normalize(unit(allowed=["../outside.py"], criteria=[]))
        fields = {(i["field"], i["fatal"]) for i in issues}
        self.assertIn(("allowed", True), fields)
        self.assertIn(("criteria", False), fields)

    def test_cycle_loses_its_forward_edge_and_plan_order_wins(self):
        units, fixes, issues = self.normalize(unit(depends_on=[2]), unit(allowed=["b.py"], depends_on=[1]))
        self.assertEqual(issues, [])
        self.assertEqual([u["depends_on"] for u in units], [[], ["u1"]])
        self.assertTrue(any("break the cycle" in f for f in fixes))

    def test_missing_depends_on_waits_for_the_unit_before_and_an_empty_list_is_independent(self):
        chained = unit(allowed=["b.py"])
        del chained["depends_on"]
        units, _, _ = self.normalize(unit(), chained, unit(allowed=["c.py"], depends_on=[]))
        self.assertEqual([u["depends_on"] for u in units], [[], ["u1"], []])

    def test_unknown_or_self_dependency_is_dropped(self):
        units, _, issues = self.normalize(unit(depends_on=["u9", "u1", 1]))
        self.assertEqual((units[0]["depends_on"], issues), ([], []))

    def test_keys_the_contract_does_not_know_never_reach_the_plan(self):
        units, _, _ = self.normalize(unit(test="rm -rf .", budgets={"max_wall_s": 999999}, protect=[]))
        self.assertEqual(set(units[0]), {"id", "title", "goal", "task_type", "allowed", "new_files", "acceptance",
                                         "risk", "depends_on"})

    def test_prompt_and_validator_share_the_field_list(self):
        text = contract.prompt("Edit a.py", TRACKED, POLICY)
        for word in ("criteria", "depends_on", "new_files", "risk", "green, yellow, red", "edit-small"):
            self.assertIn(word, text)
        self.assertNotIn("plan,", text)


class GuardTests(unittest.TestCase):
    ISSUES = [{"unit": 1, "field": "criteria", "problem": "x", "fatal": False},
              {"unit": 1, "field": "allowed", "problem": "x", "fatal": False}]

    def test_a_listed_field_may_change_and_a_path_may_only_go(self):
        before = {"units": [unit(allowed=["a.py", "missing.py"], criteria=[])]}
        contract.guard(before, {"units": [unit(allowed=["a.py"], criteria=["ok"])]}, self.ISSUES)
        with self.assertRaisesRegex(contract.Blocked, "modified scope"):
            contract.guard(before, {"units": [unit(allowed=["a.py", "b.py"], criteria=["ok"])]}, self.ISSUES)

    def test_an_unlisted_field_must_come_back_equal(self):
        before = {"units": [unit(criteria=[])]}
        for change in ({"risk": "green", "goal": "Do more"}, {"task_type": "fix-test"}, {"new_files": ["x.py"]}):
            with self.assertRaisesRegex(contract.Blocked, "modified scope"):
                contract.guard(before, {"units": [unit(criteria=["ok"], **change)]}, self.ISSUES[:1])

    def test_unit_count_and_metadata_are_fixed(self):
        before = {"units": [unit(criteria=[])]}
        with self.assertRaisesRegex(contract.Blocked, "number of units"):
            contract.guard(before, {"units": [unit(), unit()]}, self.ISSUES)
        with self.assertRaisesRegex(contract.Blocked, "metadata"):
            contract.guard(before, {"units": [unit()], "budgets": {"max_wall_s": 9}}, self.ISSUES)


class BuildTests(Base):
    def build(self, replies, repair=None):
        calls = []

        def ask(messages):
            calls.append(messages)
            return replies.pop(0)

        plan, record = autopilot.build_plan("Edit files", self.repo, TEST, "a" * 40, POLICY, ask, repair)
        return plan, record, calls

    def test_problems_in_two_units_cost_one_repair_call_that_names_both(self):
        first = {"units": [unit(criteria=[]), unit(allowed=["b.py"], task_type="plan", risk="???")]}
        fixed = {"units": [unit(criteria=["a works"]), unit(allowed=["b.py"], task_type="fix-test", risk="???")]}
        plan, record, calls = self.build([json.dumps(first), json.dumps(fixed)])
        self.assertEqual(len(calls), 2)
        message = calls[1][-1]["content"]
        self.assertIn("unit 1, criteria", message)
        self.assertIn("unit 2, task_type", message)
        self.assertEqual(record["repair_calls"], 1)
        self.assertEqual([u["risk"] for u in plan["units"]], ["green", "red"])
        self.assertEqual(autopilot.workplan.validate(plan, POLICY), [])

    def test_a_valid_draft_costs_no_repair_call(self):
        plan, record, calls = self.build(["```json\n" + json.dumps({"units": [unit(risk="LOW")]}) + "\n```"])
        self.assertEqual((len(calls), record["repair_calls"]), (1, 0))
        self.assertEqual(plan["units"][0]["acceptance"]["test"], TEST)

    def test_cut_off_json_is_asked_again_once_and_then_fully_validated(self):
        plan, record, calls = self.build(['{"units": [{"title": "x"', json.dumps({"units": [unit()]})])
        self.assertEqual((len(calls), record["repair_calls"]), (2, 1))
        self.assertEqual(len(plan["units"]), 1)

    def test_a_repair_cannot_add_a_file_or_lower_a_risk(self):
        first = {"units": [unit(criteria=[], risk="red")]}
        for change in ({"allowed": ["a.py", "b.py"]}, {"risk": "green"}):
            with self.assertRaisesRegex(contract.Blocked, "modified scope"):
                self.build([json.dumps(first), json.dumps({"units": [unit(criteria=["ok"], **{"risk": "red", **change})]})])

    def test_an_unsafe_draft_is_refused_before_any_repair(self):
        with self.assertRaises(contract.Blocked) as caught:
            self.build([json.dumps({"units": [unit(allowed=["../../etc/passwd"], criteria=[])]})])
        self.assertNotIsInstance(caught.exception, contract.Unrepaired)

    def test_a_draft_still_invalid_after_its_repair_runs_nothing(self):
        bad = json.dumps({"units": [unit(criteria=[])]})
        with self.assertRaises(contract.Unrepaired):
            self.build([bad, bad])

    def test_the_repair_goes_to_the_repair_model_not_the_drafting_one(self):
        seen = []
        plan, _, calls = self.build([json.dumps({"units": [unit(criteria=[])]})],
                                    repair=lambda m: seen.append(m) or json.dumps({"units": [unit(criteria=["ok"])]}))
        self.assertEqual((len(calls), len(seen)), (1, 1))


if __name__ == "__main__":
    unittest.main()
