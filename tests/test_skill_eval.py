"""Skill evals: several runs of one case, each on a fresh fixture, graded by a program. A step half the runs miss is
flagged as a gap of the skill. The agent here is a fake script. Run: python -m unittest discover -s tests"""
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import skill_eval  # noqa: E402

GOOD = "Read AGENTS.md first.\nShould fix: app.py:1 adds leftpad, which is not in the radar and has no decision record.\n" \
       "Should fix: app.py:5 has a comment that restates the code.\n"
LAZY = "Should fix: app.py:5 has a comment that restates the code. Great job otherwise.\n"


class SkillEval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.spec = skill_eval.load("code-review")

    def test_the_shipped_evals_are_valid(self):
        self.assertEqual(skill_eval.check_all(), [])

    def test_a_step_most_runs_skip_is_flagged_as_a_gap_of_the_skill(self):
        report = skill_eval.grade(self.spec, {"new-dependency-and-slop": [GOOD, LAZY, LAZY]})
        case = report["new-dependency-and-slop"]
        self.assertEqual(case["scores"], ["6 of 6", "3 of 6", "3 of 6"])
        rows = {item["id"]: item for item in case["criteria"]}
        self.assertEqual((rows["dependency"]["met"], rows["dependency"]["skill_gap"]), (1, True))
        self.assertEqual((rows["slop"]["met"], rows["slop"]["skill_gap"]), (3, False))
        self.assertIn("revise SKILL.md", "\n".join(skill_eval.lines(report)))

    def test_a_broken_case_is_reported(self):
        found = skill_eval.problems({"cases": [{"id": "x", "task": "t", "criteria": [{"id": "c", "why": "w"},
                                                                                     {"id": "p", "why": "w", "pattern": "("}]}]}, "e")
        self.assertEqual(len(found), 2)

    def test_each_run_starts_from_a_fresh_fixture_and_the_answers_are_kept(self):
        agent = Path(self.tmp.name) / "agent.py"
        agent.write_text(textwrap.dedent(f"""
            import pathlib, subprocess
            task = pathlib.Path(".skill-task.md").read_text(encoding="utf-8")
            assert "# code-review" in task and "Review the last commit" in task
            log = subprocess.run(["git", "log", "--format=%s"], capture_output=True, text=True).stdout.split()
            pathlib.Path("scratch.txt").write_text("left by the agent")
            print({GOOD!r} if log[0] == "the" else "wrong history")
        """), encoding="utf-8")
        report, out = skill_eval.run("code-review", "claude", runs=2, command=[sys.executable, str(agent), "{message}"],
                                     say=lambda line: None)
        self.assertEqual(report["new-dependency-and-slop"]["scores"], ["6 of 6", "6 of 6"])
        self.assertEqual(sorted(p.name for p in out.glob("*.txt")), ["new-dependency-and-slop-1.txt", "new-dependency-and-slop-2.txt"])
        again = skill_eval.grade(self.spec, skill_eval.saved(out))
        self.assertEqual(again["new-dependency-and-slop"]["scores"], ["6 of 6", "6 of 6"])

    def test_local_only_never_sends_the_skill_to_claude(self):
        with self.assertRaises(PermissionError):
            skill_eval.run("code-review", "claude", runs=1, command=[sys.executable, "-c", "print(1)"], mode="local-only",
                           say=lambda line: None)


if __name__ == "__main__":
    unittest.main()
