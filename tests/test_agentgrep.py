"""agentgrep groups matches by enclosing definition, collapses seen ones and skips junk files."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import agentgrep  # noqa: E402

PY = """import os


class Store:
    def save(self, item):
        data = item
        return data

    def load(self):
        return None


NEEDLE = 1
"""
TS = """export class Repo {
  find(id: number): string {
    return String(id);
  }
}

const make = (n: number) => {
  return n;
};
"""
GO = "package main\n\nfunc Run(x int) int {\n\treturn x\n}\n"
PS = """function Get-Thing {
    param($a)
    return $a
}
"""


def run(*args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = agentgrep.main([str(a) for a in args])
    return code, buffer.getvalue()


class AgentGrepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        for name, text in {"store.py": PY, "repo.ts": TS, "main.go": GO, "thing.ps1": PS}.items():
            (self.dir / name).write_text(text, encoding="utf-8")

    def test_method_match_shows_class_chain_and_lines(self):
        _, out = run("data = item", self.dir / "store.py")
        self.assertIn("  L5 class Store > def save", out)
        self.assertIn("    L6: data = item", out)

    def test_other_languages_find_their_definition(self):
        self.assertIn("class Repo > find", run("String", self.dir / "repo.ts")[1])
        self.assertIn("const make", run("return n", self.dir / "repo.ts")[1])
        self.assertIn("  L3 func Run", run("return x", self.dir / "main.go")[1])
        self.assertIn("  L1 function Get-Thing", run("return", self.dir / "thing.ps1")[1])

    def test_top_level_match(self):
        _, out = run("NEEDLE", self.dir / "store.py")
        self.assertIn("  (top level)", out)
        self.assertIn("    L13: NEEDLE = 1", out)

    def test_seen_collapses_and_records(self):
        seen = self.dir / "seen.json"
        target = self.dir / "store.py"
        _, first = run("data", target, "--seen", seen)
        self.assertIn("L6: data = item", first)
        recorded = json.loads(seen.read_text(encoding="utf-8"))
        self.assertEqual(recorded[target.as_posix()], [[5, 8]])
        _, second = run("data", target, "--seen", seen)
        self.assertIn("  L5 class Store > def save: 2 matches, already seen", second)
        self.assertNotIn("L6:", second)

    def test_max_reports_left_out(self):
        _, out = run("e", self.dir / "store.py", "--max", "2")
        self.assertIn("2 matches, ", out)
        self.assertRegex(out, r"\d+ left out")

    def test_skips_binary_and_node_modules(self):
        (self.dir / "blob.bin").write_bytes(b"\0\0needle")
        (self.dir / "node_modules").mkdir()
        (self.dir / "node_modules" / "dep.js").write_text("needle\n", encoding="utf-8")
        (self.dir / "ok.txt").write_text("needle\n", encoding="utf-8")
        _, out = run("needle", self.dir)
        self.assertIn("ok.txt", out)
        self.assertNotIn("blob.bin", out)
        self.assertNotIn("node_modules", out)

    def test_glob_and_ignore_case(self):
        _, out = run("CLASS", self.dir, "--glob", "*.py", "--ignore-case")
        self.assertIn("store.py", out)
        self.assertNotIn("repo.ts", out)

    def test_json_schema(self):
        _, out = run("data = item", self.dir / "store.py", "--json")
        data = json.loads(out)
        self.assertEqual(data["schema"], "standards/agentgrep/v1")
        self.assertEqual((data["matches"], data["left_out"]), (1, 0))
        group = data["files"][0]["definitions"][0]
        self.assertEqual(group["chain"], ["class Store", "def save"])
        self.assertEqual(group["line"], 5)
        self.assertEqual(group["matches"], [{"line": 6, "text": "data = item"}])
        self.assertFalse(group["seen"])


if __name__ == "__main__":
    unittest.main()
