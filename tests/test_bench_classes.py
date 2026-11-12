"""Graders of the bench classes review-diff and decompose. No model runs: each grader must pass the reference answer
and fail a wrong one."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bench_tasks  # noqa: E402


class ReviewDiff(unittest.TestCase):
    def test_six_cases_in_the_bench(self):
        self.assertEqual(len(bench_tasks.REVIEW_CASES), 6)
        self.assertIn("review-diff", bench_tasks.CHAT_TASKS)
        self.assertEqual(bench_tasks.grader_version("review-diff"), 1)

    def test_diff_line_numbers_match_the_new_file(self):
        for case in bench_tasks.REVIEW_CASES:
            text = bench_tasks.review_diff_text(case)
            body = [line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]
            self.assertEqual(body, case["lines"])
            self.assertIn(f"@@ -0,0 +1,{len(case['lines'])} @@", text)
            start, end = case["defect"]
            self.assertTrue(1 <= start <= end <= len(case["lines"]), case["id"])

    def test_reference_passes(self):
        for case in bench_tasks.REVIEW_CASES:
            self.assertTrue(bench_tasks.review_ok(case, bench_tasks.review_reference(case))[0], case["id"])

    def test_wrong_answers_fail(self):
        case = bench_tasks.REVIEW_CASES[0]
        ref = bench_tasks.review_reference(case)["findings"][0]
        wrong = {
            "empty": {"findings": []},
            "not json": None,
            "wrong file": {"findings": [{**ref, "file": "app/other.py"}]},
            "wrong lines": {"findings": [{**ref, "line_start": 1, "line_end": 1}]},
            "whole file": {"findings": [{**ref, "line_start": 1, "line_end": 40}]},
            "false high": {"findings": [ref, {**ref, "line_start": 1, "line_end": 1, "severity": "high"}]},
            "bad shape": {"findings": ["line 6"]},
        }
        for name, answer in wrong.items():
            self.assertFalse(bench_tasks.review_ok(case, answer)[0], name)

    def test_low_finding_elsewhere_and_b_prefix_are_tolerated(self):
        case = bench_tasks.REVIEW_CASES[0]
        ref = bench_tasks.review_reference(case)["findings"][0]
        answer = {"findings": [{**ref, "file": "b/" + ref["file"], "line_start": "6", "line_end": "6"},
                               {**ref, "line_start": 1, "line_end": 1, "severity": "low"}]}
        self.assertTrue(bench_tasks.review_ok(case, answer)[0])

    def test_run_chat_scores_reference_and_wrong_model(self):
        def good(prompt, images):
            case = next(c for c in bench_tasks.REVIEW_CASES if f"+++ b/{c['file']}" in prompt)
            return bench_tasks.review_reference(case)
        self.assertEqual(bench_tasks.run_chat("review-diff", ask=good)["accuracy"], 1.0)
        self.assertEqual(bench_tasks.run_chat("review-diff", ask=lambda p, i: {"findings": []})["accuracy"], 0.0)


class Decompose(unittest.TestCase):
    def setUp(self):
        self.spec = bench_tasks.DECOMPOSE_SPECS[2]
        self.ref = {"units": copy.deepcopy(self.spec["reference"])}

    def grade(self, answer):
        return bench_tasks.decompose_ok(self.spec, answer)

    def test_three_specs_registered(self):
        self.assertEqual(len(bench_tasks.DECOMPOSE_SPECS), 3)
        self.assertIn("decompose", bench_tasks.CHAT_TASKS)
        self.assertEqual(bench_tasks.grader_version("decompose"), 1)

    def test_reference_passes(self):
        for spec in bench_tasks.DECOMPOSE_SPECS:
            self.assertEqual(bench_tasks.decompose_ok(spec, {"units": spec["reference"]}), (True, ""), spec["id"])

    def test_reference_has_parallel_units(self):
        import workplan
        for spec in bench_tasks.DECOMPOSE_SPECS:
            plan = {"plan_id": "p", "goal": "g", "units": spec["reference"]}
            self.assertTrue(any(len(batch) > 1 for batch in workplan.batches(plan, spec["files"])), spec["id"])

    def test_not_json_and_no_units_fail(self):
        self.assertFalse(self.grade(None)[0])
        self.assertFalse(self.grade({"units": []})[0])

    def test_cycle_fails(self):
        self.ref["units"][0]["depends_on"] = ["u2"]
        ok, note = self.grade(self.ref)
        self.assertFalse(ok)
        self.assertIn("cycle", note)

    def test_missing_coverage_fails(self):
        self.ref["units"] = [u for u in self.ref["units"] if u["id"] != "u5"]
        ok, note = self.grade(self.ref)
        self.assertFalse(ok)
        self.assertIn("not covered: CHANGELOG.md", note)

    def test_parallel_units_sharing_a_file_fail(self):
        self.ref["units"][2]["allowed"] = ["lib/b.py"]
        self.ref["units"].append({**self.ref["units"][3], "id": "u6", "allowed": ["lib/c.py"], "depends_on": ["u1"]})
        ok, note = self.grade(self.ref)
        self.assertFalse(ok)
        self.assertIn("shared file", note)

    def test_one_big_unit_fails(self):
        big = {**self.spec["reference"][0], "allowed": self.spec["must_touch"]}
        self.assertIn("units, at least", self.grade({"units": [big]})[1])

    def test_invalid_unit_fails_validate(self):
        self.ref["units"][0]["task_type"] = "no-such-type"
        self.assertIn("invalid plan", self.grade(self.ref)[1])
        del self.ref["units"][0]["acceptance"]
        self.assertFalse(self.grade(self.ref)[0])

    def test_run_chat_scores_reference_and_wrong_model(self):
        def good(prompt, images):
            spec = next(s for s in bench_tasks.DECOMPOSE_SPECS if f"Task: {s['task']}" in prompt)
            return {"units": spec["reference"]}
        self.assertEqual(bench_tasks.run_chat("decompose", ask=good)["accuracy"], 1.0)
        self.assertEqual(bench_tasks.run_chat("decompose", ask=lambda p, i: {"units": []})["accuracy"], 0.0)


if __name__ == "__main__":
    unittest.main()
