"""Cleaning a delegation: the run's worktree and branch go, a commit not integrated stays, and the guard lets it through."""
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
sys.path.insert(0, str(ROOT / "hooks"))

import guard  # noqa: E402
import orchestrate  # noqa: E402

RUN = "20261116-080051-f8e859"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class Clean(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        patcher = mock.patch.dict(os.environ, {"STANDARDS_HOME": str(self.root / "home")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-q", "-m", "init")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.worktree = orchestrate.home() / "worktrees" / RUN
        git(self.repo, "worktree", "add", "-q", "-b", f"delegate/{RUN}", str(self.worktree), self.base)

    def run_record(self, state, commit=None):
        orchestrate.record({"id": RUN, "executor": "opencode", "state": state, "repo": str(self.repo), "task": "x",
                            "branch": f"delegate/{RUN}", "worktree": str(self.worktree), "base": self.base, "commit": commit})

    def commit_in_worktree(self):
        (self.worktree / "b.txt").write_text("b\n", encoding="utf-8")
        git(self.worktree, "add", "b.txt")
        git(self.worktree, "commit", "-q", "-m", "chore(delegate): b")
        return git(self.worktree, "rev-parse", "HEAD")

    def test_a_failed_run_loses_its_worktree_and_branch(self):
        self.run_record("failed")
        out = orchestrate.clean_run(RUN)
        self.assertFalse(self.worktree.exists())
        self.assertEqual(git(self.repo, "branch", "--list", f"delegate/{RUN}"), "")
        self.assertIn(f"delegate/{RUN}", out["removed"])
        self.assertTrue(json.loads((orchestrate.home() / "runs" / f"{RUN}.json").read_text())["cleaned"])

    def test_a_verified_commit_stays_until_it_is_integrated(self):
        commit = self.commit_in_worktree()
        self.run_record("verified", commit)
        with self.assertRaisesRegex(RuntimeError, "not in the current branch yet"):
            orchestrate.clean_run(RUN)
        self.assertTrue(self.worktree.exists())
        git(self.repo, "cherry-pick", commit)
        orchestrate.clean_run(RUN)
        self.assertEqual(git(self.repo, "branch", "--list", f"delegate/{RUN}"), "")

    def test_force_drops_a_commit_not_integrated_and_a_running_run_is_left_alone(self):
        self.run_record("running")
        with self.assertRaisesRegex(RuntimeError, "still running"):
            orchestrate.clean_run(RUN)
        self.run_record("verified", self.commit_in_worktree())
        orchestrate.clean_run(RUN, force=True)
        self.assertFalse(self.worktree.exists())


class Guard(unittest.TestCase):
    def decide(self, command, record=True):
        with tempfile.TemporaryDirectory() as tmp:
            if record:
                (Path(tmp) / "runs").mkdir()
                (Path(tmp) / "runs" / f"{RUN}.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {"STANDARDS_HOME": tmp}):
                out = guard.decide({"tool_input": {"command": command}, "cwd": tmp})
        return (out or {}).get("hookSpecificOutput", {}).get("permissionDecision")

    def test_deleting_a_branch_the_standard_made_does_not_ask(self):
        seen = ("cd /c/repo; git worktree remove --force C:/x && git branch -D delegate/20261116-080051-f8e859 >/dev/null; "
                "grep -n x a.py")
        self.assertIsNone(self.decide(seen))
        self.assertIsNone(self.decide(f"git branch -D delegate/{RUN}"))

    def test_any_other_branch_deletion_still_asks(self):
        self.assertEqual(self.decide(f"git branch -D delegate/{RUN}", record=False), "ask")
        self.assertEqual(self.decide("git branch -D feat/settings"), "ask")
        self.assertEqual(self.decide(f"git branch -D delegate/{RUN} main"), "ask")
        self.assertEqual(self.decide(f"git branch -D delegate/{RUN}; git branch -D main"), "ask")


    def test_a_recursive_deletion_inside_a_temporary_folder_does_not_ask(self):
        import tempfile as tf
        temp = tf.gettempdir().replace("\\", "/")
        seen = (f'cd /c/repo; SP="{temp}/claude/f8d9/585d/scratchpad"; rm -rf "$SP/appdata2"; mkdir -p "$SP/appdata2"; '
                'LOCALAPPDATA="$SP/appdata2" python -c "print(1)"')
        self.assertIsNone(self.decide(seen))
        self.assertIsNone(self.decide(f"rm -rf {temp}/build-1 2>/dev/null"))
        self.assertIsNone(self.decide("rm -rf /tmp/x /tmp/y"))

    def test_a_recursive_deletion_anywhere_else_still_asks(self):
        import tempfile as tf
        temp = tf.gettempdir().replace("\\", "/")
        for command in ("rm -rf src", f"rm -rf {temp}", f"rm -rf {temp}/../home", "rm -rf /tmp/x src",
                        'rm -rf "$UNKNOWN/x"', "rm -rf /tmp/*", f'SP="{temp}/a"; rm -rf "$SP/x"; rm -rf docs',
                        'SP="$HOME/x"; rm -rf "$SP/y"'):
            with self.subTest(command):
                self.assertEqual(self.decide(command), "ask")

    def test_windows_paths_are_compared_in_one_spelling(self):
        roots = [guard.plain_path("C:\\Users\\valde\\AppData\\Local\\Temp")]
        self.assertTrue(guard.is_scratch("C:/Users/valde/AppData/Local/Temp/claude/f8d9/scratchpad/appdata2", roots))
        self.assertTrue(guard.is_scratch("/c/users/valde/appdata/local/temp/x", roots))
        self.assertFalse(guard.is_scratch("C:/Users/valde/AppData/Local/TempX/y", roots))
        self.assertFalse(guard.is_scratch("C:/my_drive/Portafolio/OpenTutor/src", roots))

if __name__ == "__main__":
    unittest.main()
