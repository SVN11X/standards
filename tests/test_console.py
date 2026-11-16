"""Output on Windows: a report with a check mark or an arrow never stops half printed in a cp1252 pipe."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import console  # noqa: E402


class Console(unittest.TestCase):
    def test_a_pipe_in_the_ansi_code_page_gets_utf8(self):
        raw = io.BytesIO()
        pipe = io.TextIOWrapper(raw, encoding="cp1252")
        with mock.patch.object(sys, "stdout", pipe), mock.patch.object(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")):
            console.safe_output()
            print("listo ✓ → ok")
            sys.stdout.flush()
        self.assertEqual(raw.getvalue().decode("utf-8").strip(), "listo ✓ → ok")

    def test_the_report_of_runs_prints_through_a_cp1252_pipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "runs").mkdir()
            record = {"id": "20261116-080051-f8e859", "executor": "opencode", "state": "failed", "model": "m",
                      "task": "probar ✓ → ok", "history": [{"state": "failed", "note": "tests ✗ 🚫"}]}
            (Path(tmp) / "runs" / "20261116-080051-f8e859.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            env = {**os.environ, "STANDARDS_HOME": tmp, "PYTHONIOENCODING": "cp1252"}
            ran = subprocess.run([sys.executable, str(ROOT / "scripts" / "orchestrate.py"), "runs"], capture_output=True, env=env,
                                 timeout=60)
        self.assertEqual(ran.returncode, 0, ran.stderr.decode("utf-8", "replace"))
        self.assertIn("probar ✓ → ok", ran.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
