"""The commit gate of the guard hook blocks a commit only for errors of the standard check about the files that commit
holds. A loose file the owner adds at the root meanwhile does not block an unrelated commit. Run: python -m unittest discover -s tests"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import guard  # noqa: E402
import standard  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


class CommitGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "site"
        standard.init_repo(cls.repo, {"profile": "software", "name": "site", "setup_done": True, "content_language": "en",
                                      "description": "Test repository."})
        standard.git_add_all(cls.repo)
        git(cls.repo, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "chore: init")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        os.environ["STANDARD_PY"] = str(ROOT / "scripts" / "standard.py")
        self.addCleanup(os.environ.pop, "STANDARD_PY", None)
        self.loose = self.repo / "owner-notes.txt"
        self.loose.write_text("the owner is writing this\n", encoding="utf-8")
        self.addCleanup(self.loose.unlink, missing_ok=True)
        (self.repo / "src").mkdir(exist_ok=True)
        self.mine = self.repo / "src" / "app.py"
        self.mine.write_text("print(1)\n", encoding="utf-8")
        self.addCleanup(self.mine.unlink, missing_ok=True)
        self.addCleanup(git, self.repo, "reset", "-q")

    def test_a_loose_file_of_the_owner_does_not_block_an_unrelated_commit(self):
        git(self.repo, "add", "src/app.py")
        self.assertIsNone(guard.commit_gate(self.repo, 'git commit -m "feat: app"'))
        self.assertIsNone(guard.commit_gate(self.repo, 'git add src/app.py && git commit -m "feat: app"'))

    def test_a_commit_that_takes_the_loose_file_is_blocked(self):
        reason = guard.commit_gate(self.repo, 'git add -A && git commit -m "feat: app"')
        self.assertIn("owner-notes.txt", reason)
        git(self.repo, "add", "owner-notes.txt")
        self.assertIn("owner-notes.txt", guard.commit_gate(self.repo, 'git commit -m "feat: notes"'))


class BranchDeletion(unittest.TestCase):
    def decision(self, command):
        out = guard.decide({"tool_input": {"command": command}, "cwd": tempfile.gettempdir()})
        return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")

    def test_a_merged_branch_is_deleted_without_the_owner_and_an_unmerged_one_asks(self):
        self.assertIsNone(self.decision("git branch -d feat/item-3"))
        self.assertIsNone(self.decision("git worktree remove .claude/worktrees/item-3"))
        for command in ("git branch -D feat/item-3", "git branch --delete --force feat/item-3", "git branch -d -f feat/item-3"):
            self.assertEqual(self.decision(command), "ask", command)


if __name__ == "__main__":
    unittest.main()
