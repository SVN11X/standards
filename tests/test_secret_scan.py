import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "secret_scan.py"


class SecretScanHook(unittest.TestCase):
    def run_hook(self, path: Path) -> str:
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)}}, ensure_ascii=False)
        ran = subprocess.run([sys.executable, str(HOOK)], input=payload.encode("utf-8"), capture_output=True, timeout=60)
        return ran.stdout.decode("utf-8")

    def test_a_credential_in_a_file_with_an_accented_name_is_found(self):
        folder = Path(tempfile.mkdtemp(prefix="std-scan-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        target = folder / "configuración.py"
        target.write_text("token = 'ghp_" + "a1B2c3D4e5" * 3 + "abcdef'\n", encoding="utf-8")
        self.assertIn('"block"', self.run_hook(target))

    def test_a_clean_file_passes(self):
        folder = Path(tempfile.mkdtemp(prefix="std-scan-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        target = folder / "señal.py"
        target.write_text("value = 1\n", encoding="utf-8")
        self.assertEqual(self.run_hook(target), "")


if __name__ == "__main__":
    unittest.main()
