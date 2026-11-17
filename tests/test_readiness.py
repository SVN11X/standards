"""A change is ready only when every requirement has evidence. The worst signal wins."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import readiness  # noqa: E402

CHANGE = "2026-11-export"


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        spec = self.repo / "docs" / "specs" / CHANGE
        spec.mkdir(parents=True)
        (spec / "requirements.md").write_text(
            "# Requirements\n\n- R1 (critical): WHEN the export fails THE SYSTEM SHALL keep the original file.\n"
            "- R2: WHEN the export ends THE SYSTEM SHALL show its size.\n", encoding="utf-8")
        (spec / "tasks.md").write_text("- [x] T1 write the exporter\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        self.test = self.repo / "tests" / "test_export.py"
        self.test.write_text(f"def test_size():  # covers {CHANGE}/R2\n    pass\n", encoding="utf-8")
        self.commit()

    def commit(self):
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "c"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def test_an_uncovered_critical_requirement_blocks_even_with_green_ci(self):
        result = readiness.assess(self.repo, CHANGE, "green")
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertIn(f"{CHANGE}/R1 (critical) has no test", readiness.markdown(result))

    def test_every_requirement_covered_and_green_ci_is_ready(self):
        self.test.write_text(self.test.read_text() + f"def test_keep():  # covers {CHANGE}/R1\n    pass\n", encoding="utf-8")
        self.commit()
        self.assertEqual(readiness.assess(self.repo, CHANGE, "green")["verdict"], "READY")
        self.assertEqual(readiness.assess(self.repo, CHANGE, "unknown")["verdict"], "NEEDS_DECISION")
        self.assertEqual(readiness.assess(self.repo, CHANGE, "red")["verdict"], "BLOCKED")

    def test_a_linked_decision_that_is_not_accepted_needs_the_owner(self):
        self.test.write_text(self.test.read_text() + f"# covers {CHANGE}/R1\n", encoding="utf-8")
        (self.repo / "docs" / "decisions").mkdir()
        (self.repo / "docs" / "decisions" / "0003-format.md").write_text("# 0003\n\n- Status: proposed\n", encoding="utf-8")
        (self.repo / "docs" / "specs" / CHANGE / "plan.md").write_text("Uses docs/decisions/0003-format.md\n", encoding="utf-8")
        self.commit()
        result = readiness.assess(self.repo, CHANGE, "green")
        self.assertEqual(result["verdict"], "NEEDS_DECISION")
        self.assertIn("0003-format.md is proposed", readiness.markdown(result))

    def test_an_open_task_blocks(self):
        (self.repo / "docs" / "specs" / CHANGE / "tasks.md").write_text("- [ ] T2 handle disk full\n", encoding="utf-8")
        self.assertEqual(readiness.assess(self.repo, CHANGE, "green")["verdict"], "BLOCKED")

    def test_the_pull_request_of_a_plan_with_a_spec_carries_the_verdict(self):
        import plan_autopilot
        section = plan_autopilot.readiness_section({"repo": str(self.repo), "spec": CHANGE})
        self.assertIn("## Readiness", section)
        self.assertIn("**BLOCKED**", section)
        self.assertEqual(plan_autopilot.readiness_section({"repo": str(self.repo)}), "")


if __name__ == "__main__":
    unittest.main()
