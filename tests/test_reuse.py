"""Reuse first: the executor's packet names existing code that fits the task, and shortcuts become a ledger."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import orchestrate  # noqa: E402
import reuse  # noqa: E402

TODAY = orchestrate.dt.date.today().isoformat()


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "text_utils.py").write_text(
            'def slugify(title):\n    """Turn a title into a URL slug."""\n    return title.lower().replace(" ", "-")\n\n\n'
            "def word_count(text):\n    return len(text.split())  # shortcut: no unicode spaces. revisit when users paste PDFs\n",
            encoding="utf-8")
        (self.repo / "web.js").write_text("export function formatPrice(cents) { return cents / 100 }\n", encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")

    def test_similar_finds_the_existing_function_first(self):
        found = reuse.similar(self.repo, "Add a slug for each post title in the URL")
        self.assertEqual((found[0]["file"], found[0]["name"]), ("src/text_utils.py", "slugify"))
        self.assertEqual(reuse.similar(self.repo, "format the price in cents")[0]["name"], "formatPrice")

    def test_debt_reads_shortcuts_and_their_condition(self):
        rows = reuse.debt(self.repo)
        self.assertEqual(rows, [{"file": "src/text_utils.py", "line": 7, "shortcut": "no unicode spaces",
                                 "revisit_when": "users paste PDFs"}])

    def test_the_executor_packet_names_the_function_to_reuse(self):
        seen = []
        real = orchestrate.run

        def fake(cmd, *a, **k):
            if cmd and cmd[0] == "fake":
                seen.append((Path(k["cwd"]) / orchestrate.TASK_FILE).read_text(encoding="utf-8"))
                return {"exit": 1, "seconds": 0, "timeout": False, "stdout": "", "stderr": "stop"}
            return real(cmd, *a, **k)

        local = {"folders": [{"path": str(self.repo), "class": "personal-public"}],
                 "free_models": [{"id": "opencode/a-free", "checked": TODAY, "data_use": "none"}]}
        with mock.patch.object(orchestrate, "run", side_effect=fake):
            orchestrate.delegate_opencode(self.repo, "Add a slug for each post title", ["src/*"], None, model="opencode/a-free",
                                          conf=orchestrate.policy(), local=local, command=["fake"], catalog={})
        self.assertIn("## Existing code to reuse first", seen[0])
        self.assertIn("`src/text_utils.py:1` def `slugify`: Turn a title into a URL slug.", seen[0])


if __name__ == "__main__":
    unittest.main()
