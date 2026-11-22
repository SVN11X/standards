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

FIXED = DIFF.replace("+x = eval(input())", "+x = int(input())")


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
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: calls.append(f) or FIXED)
        self.assertEqual((result["verdict"], result["rounds"], len(calls)), ("pass", 2, 1))

    def test_only_one_fix_round(self):
        fake = Fake({"verdict": "fail", "findings": [finding()]}, {"verdict": "fail", "findings": [finding()]})
        calls = []
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: calls.append(f) or FIXED)
        self.assertEqual((result["verdict"], result["rounds"], len(calls)), ("fail", 2, 1))
        self.assertEqual(len(fake.replies), 0)

    def test_a_fix_that_changes_nothing_keeps_the_verdict_without_a_new_call(self):
        fake = Fake({"verdict": "fail", "findings": [finding()]}, {"verdict": "pass", "findings": []})
        result = review.review(DIFF, "a", "b", fake, fixer=lambda f: DIFF)
        self.assertEqual((result["verdict"], result["calls"], result["reused"]), ("fail", 0, 1))
        self.assertEqual(len(fake.prompts), 1)

    def test_medium_warns_without_fix(self):
        result = review.review(DIFF, "a", "b", Fake({"verdict": "fail", "findings": [finding("medium")]}),
                               fixer=lambda f: self.fail("no fix expected"))
        self.assertEqual(result["verdict"], "warn")

    def test_reviewer_error_is_reported(self):
        def boom(prompt):
            raise ValueError("no json")
        self.assertEqual(review.review(DIFF, "a", "b", boom)["verdict"], "error")


def big_diff(files: int = 3, lines: int = 120) -> str:
    out = []
    for n in range(files):
        out += [f"diff --git a/f{n}.py b/f{n}.py", f"--- a/f{n}.py", f"+++ b/f{n}.py", f"@@ -1,1 +1,{lines + 1} @@", " keep = 0"]
        out += [f"+value_{i} = compute({i}, 'some text that makes the line long enough')" for i in range(lines)]
    return "\n".join(out) + "\n"


class PartTests(unittest.TestCase):
    def test_a_short_diff_is_one_part_with_the_same_prompt(self):
        self.assertEqual(review.parts(DIFF, 6000), [DIFF])
        self.assertNotIn("one part of a larger change", review.prompt_for(DIFF))

    def test_parts_stay_under_the_limit_and_keep_every_added_line(self):
        diff = big_diff()
        pieces = review.parts(diff, 3000)
        self.assertGreater(len(pieces), 3)
        self.assertTrue(all(len(p) <= 3000 for p in pieces))
        shown = review.diff_lines(diff)
        joined: dict = {}
        for piece in pieces:
            for name, numbers in review.diff_lines(piece).items():
                joined.setdefault(name, set()).update(numbers)
        self.assertEqual(joined, shown)

    def test_a_finding_in_a_later_part_keeps_its_file_line_number(self):
        diff = big_diff(files=1, lines=200)
        pieces = review.parts(diff, 3000)
        last = pieces[-1]
        number = max(review.diff_lines(last)["f0.py"])
        kept, _ = review.validate_findings([finding(file="f0.py", start=number, end=number)], review.diff_lines(last))
        self.assertEqual(len(kept), 1)
        self.assertEqual(number, 201)

    def test_every_part_is_reviewed_and_names_the_whole_change(self):
        diff = big_diff()
        fake = Fake(*[{"verdict": "pass", "findings": []}] * 20)
        result = review.review(diff, "a", "b", fake, part_chars=3000)
        self.assertEqual((result["verdict"], result["parts"], result["calls"]), ("pass", result["parts"], len(fake.prompts)))
        self.assertGreater(result["parts"], 1)
        self.assertTrue(all("f0.py, f1.py, f2.py" in prompt for prompt in fake.prompts))

    def test_a_high_finding_in_any_part_fails_the_review(self):
        diff = big_diff()
        count = len(review.parts(diff, 3000))
        replies = [{"verdict": "pass", "findings": []}] * (count - 1)
        last = max(review.diff_lines(review.parts(diff, 3000)[-1])["f2.py"])
        replies.append({"verdict": "fail", "findings": [finding(file="f2.py", start=last, end=last)]})
        result = review.review(diff, "a", "b", Fake(*replies), part_chars=3000)
        self.assertEqual(result["verdict"], "fail")

    def test_an_error_in_one_part_stops_the_review(self):
        calls = []

        def flaky(prompt):
            calls.append(prompt)
            if len(calls) == 2:
                raise ValueError("no json")
            return {"verdict": "pass", "findings": []}
        result = review.review(big_diff(), "a", "b", flaky, part_chars=3000)
        self.assertEqual((result["verdict"], len(calls)), ("error", 2))

    def test_a_diff_over_the_limit_is_refused_before_any_call(self):
        result = review.review(big_diff(), "a", "b", lambda p: self.fail("no call expected"), max_chars=1000)
        self.assertEqual(result["verdict"], "blocked")
        self.assertIn("over the review limit", result["reason"])

    def test_limits_come_from_the_policy(self):
        self.assertEqual(review.limits({"review": {"part_chars": 100, "max_diff_chars": 900}}),
                         {"part_chars": 100, "max_chars": 900})
        self.assertEqual(review.limits(None), {"part_chars": review.PART_CHARS, "max_chars": review.MAX_DIFF_CHARS})


if __name__ == "__main__":
    unittest.main()
