"""Standards AI Control: run summaries, telemetry totals and the page file."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import control  # noqa: E402
import orchestrate  # noqa: E402


class ControlTests(unittest.TestCase):
    def test_finished_run_is_complete_and_counts_its_checks(self):
        data = {"id": "x", "state": "failed", "task": "Fix it\nmore", "checks": {"a": "PASS", "b": "FAIL"},
                "history": [{"state": "planned", "at": "t0", "note": ""}, {"state": "failed", "at": "t1", "note": "tests failed"}]}
        row = control.run_summary(data)
        self.assertEqual((row["stage_progress"], row["checks_passed"], row["checks_total"]), (1.0, 1, 2))
        self.assertEqual(row["task"], "Fix it")

    def test_running_run_progress_comes_from_stages_reached(self):
        data = {"state": "running", "history": [{"state": "planned", "at": "t"}, {"state": "approved", "at": "t"}]}
        self.assertEqual(control.run_summary(data)["stage_progress"], 0.5)

    def test_telemetry_sums_tokens_per_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = orchestrate.home
            orchestrate.home = lambda: Path(tmp)
            try:
                for tokens in (3, 4):
                    orchestrate.append_telemetry({"provider": "colibri", "model": "m", "prompt_tokens": 10,
                                                  "completion_tokens": tokens, "seconds": 1.0})
                total = control.telemetry()["by_model"]["colibri/m"]
            finally:
                orchestrate.home = original
        self.assertEqual((total["requests"], total["input"], total["output"]), (2, 20, 7))

    def test_page_exists_and_names_unavailable_metrics(self):
        text = control.PAGE.read_text(encoding="utf-8")
        self.assertIn("Not available", text)
        self.assertNotIn("0.0.0.0", text)

    def test_bad_jsonl_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(json.dumps({"a": 1}) + "\nnot json\n", encoding="utf-8")
            self.assertEqual(control.read_jsonl(path), [{"a": 1}])


if __name__ == "__main__":
    unittest.main()
