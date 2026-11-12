"""Classification is advisory: never marks a blocker resolved."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import next_actions  # noqa: E402


class NextActionTests(unittest.TestCase):
    def test_technical_is_not_a_human_decision(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "docs" / "improvement-plan.md"
            file.parent.mkdir()
            file.write_text("- BLOCKED: run `analyze.py` on owner's machine\n"
                            "- BLOCKED: owner decides whether a free model may plan\n"
                            "- BLOCKED: some newly discovered step\n", encoding="utf-8")
            result = next_actions.snapshot(Path(root))
            self.assertEqual(result["counts"]["technical"], 1)
            self.assertEqual(result["counts"]["human"], 1)
            self.assertEqual(result["counts"]["review"], 1)
            self.assertEqual(len(result["items"]), 3)

    def test_missing_source_is_not_success(self):
        with tempfile.TemporaryDirectory() as root:
            result = next_actions.snapshot(Path(root))
            self.assertIn("error", result)
            self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
