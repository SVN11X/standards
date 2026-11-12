"""Cross-model review with a fake reviewer. Run: python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import review  # noqa: E402

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 import os
+x = eval(input())
 print(1)
 print(2)
"""


def finding(severity="high", file="app.py", start=2, end=2, message="eval on input"):
    return {"severity": severity, "file": file, "line_start": start, "line_end": end, "message": message}


class Fake:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


class ReviewTests(unittest.TestCase):
    def test_diff_lines(self):
        self.assertEqual(review.diff_lines(DIFF), {"app.py": {1, 2, 3, 4}})

    def test_invented_lines_and_files_dropped(self):
        kept, dropped = review.validate_findings(
            [finding(), finding(start=40, end=41), finding(file="other.py"), finding(severity="critical"),
             finding(start=3, end=2)], review.diff_lines(DIFF))
        self.assertEqual(len(kept), 1)
        self.assertEqual([d["reason"] for d in dropped],
                         ["lines not in diff", "file not in diff", "unknown severity", "bad line range"])

    def test_same_model_blocked_without_call(self):
        fake = Fake()
        result = review.review(DIFF, "qwen3.5-9b", "qwen3.5-9b:latest", fake)
        self.assertEqual(result["verdict"], "blocked")
        self.assertEqual(fake.prompts, [])

    def test_pass(self):
        result = review.review(DIFF, "a", "b", Fake({"verdict": "pass", "findings": []}))
        self.assertEqual((result["verdict"], result["rounds"]), ("pass", 1))

    def test_invented_high_does_not_fail(self):
        fake = Fake({"verdict": "fail", "findings": [finding(start=99, end=99)]})
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: self.fail("no fix expected"))
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(len(result["dropped"]), 1)

    def test_one_fix_round_then_pass(self):
        fake = Fake({"verdict": "fail", "findings": [finding()]}, {"verdict": "pass", "findings": []})
        calls = []
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: calls.append(f) or DIFF)
        self.assertEqual((result["verdict"], result["rounds"], len(calls)), ("pass", 2, 1))

    def test_only_one_fix_round(self):
        fake = Fake({"verdict": "fail", "findings": [finding()]}, {"verdict": "fail", "findings": [finding()]})
        calls = []
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: calls.append(f) or DIFF)
        self.assertEqual((result["verdict"], result["rounds"], len(calls)), ("fail", 2, 1))
        self.assertEqual(len(fake.replies), 0)

    def test_medium_warns_without_fix(self):
        result = review.review(DIFF, "a", "b", Fake({"verdict": "fail", "findings": [finding("medium")]}),
                               fixer=lambda f: self.fail("no fix expected"))
        self.assertEqual(result["verdict"], "warn")

    def test_reviewer_error_is_reported(self):
        def boom(prompt):
            raise ValueError("no json")
        self.assertEqual(review.review(DIFF, "a", "b", boom)["verdict"], "error")


if __name__ == "__main__":
    unittest.main()
