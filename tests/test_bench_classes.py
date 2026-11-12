"""Graders of the bench classes review-diff and decompose. No model runs: each grader must pass the reference answer
and fail a wrong one."""
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


if __name__ == "__main__":
    unittest.main()
