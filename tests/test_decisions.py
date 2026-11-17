"""A decision record names who accepted it only once it is accepted."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import standard  # noqa: E402


def record(status, by):
    return f"# 0001. T\n\n- Status: {status}\n- Date: 2026-11-16\n- Proposed by: Claude Code\n- Accepted by: {by}\n\n## Context\nx\n"


class DecisionTests(unittest.TestCase):
    def messages(self, status, by):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "docs" / "decisions"
            folder.mkdir(parents=True)
            (folder / "0001-t.md").write_text(record(status, by), encoding="utf-8")
            (folder / "0000-template.md").write_text(record("proposed", "owner"), encoding="utf-8")
            report = standard.Report()
            standard.check_decisions(Path(tmp), report)
            return [str(item) for item in report.errors]

    def test_proposed_with_a_named_acceptance_is_an_error(self):
        self.assertEqual(len(self.messages("proposed", "owner")), 1)

    def test_proposed_pending_and_accepted_with_a_name_pass(self):
        self.assertEqual(self.messages("proposed", "pending"), [])
        self.assertEqual(self.messages("accepted", "owner, in the pull request of 2026-11-16"), [])

    def test_accepted_without_a_name_is_an_error(self):
        self.assertEqual(len(self.messages("accepted", "")), 1)

    def test_the_template_itself_is_not_checked_and_says_pending(self):
        root = Path(standard.__file__).resolve().parents[1] / "base" / "files" / "docs" / "decisions" / "0000-template.md"
        self.assertIn("Accepted by: pending", root.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
