import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import shift_notice  # noqa: E402


def git(cwd, *args):
    identity = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **identity})


class ShiftNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        env = mock.patch.dict(os.environ, {"STANDARDS_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        os.environ.pop("STANDARDS_SHIFT_NOTICE", None)

    def call(self, session, tool, path):
        time.sleep(0.03)
        event = {"session_id": session, "cwd": str(self.root), "tool_name": tool,
                 "tool_input": {"file_path": str(path)}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = shift_notice.main(json.dumps(event))
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_notice_once(self):
        f = self.root / "a.txt"
        self.call("bbbbbbbb-1", "Read", f)
        self.call("aaaaaaaa-1", "Edit", f)
        first = self.call("bbbbbbbb-1", "Read", self.root / "other.txt")
        context = json.loads(first)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("changed under you: session aaaaaaaa", context)
        self.assertEqual(self.call("bbbbbbbb-1", "Read", self.root / "other.txt"), "")

    def test_writing_a_file_that_changed_since_the_read_gets_the_notice(self):
        f = self.root / "a.txt"
        self.call("bbbbbbbb-1", "Read", f)
        self.call("aaaaaaaa-1", "Edit", f)
        context = json.loads(self.call("bbbbbbbb-1", "Write", f))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("changed under you: session aaaaaaaa", context)

    def test_reading_the_changed_file_again_needs_no_notice(self):
        f = self.root / "a.txt"
        self.call("bbbbbbbb-1", "Read", f)
        self.call("aaaaaaaa-1", "Edit", f)
        self.assertEqual(self.call("bbbbbbbb-1", "Read", f), "")
        self.assertEqual(self.call("bbbbbbbb-1", "Read", self.root / "other.txt"), "")

    def test_edit_before_read_is_silent(self):
        f = self.root / "a.txt"
        self.call("aaaaaaaa-1", "Write", f)
        self.assertEqual(self.call("bbbbbbbb-1", "Read", f), "")
        self.assertEqual(self.call("bbbbbbbb-1", "Read", f), "")

    def test_same_tree_message(self):
        f = self.root / "a.txt"
        self.call("bbbbbbbb-1", "Read", f)
        self.call("aaaaaaaa-1", "Edit", f)
        self.assertIn("in this working tree", self.call("bbbbbbbb-1", "Read", self.root / "z.txt"))

    def test_worktrees_share_key(self):
        repo = self.root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "a.txt").write_text("x")
        git(repo, "add", "a.txt")
        git(repo, "commit", "-q", "-m", "init")
        wt = self.root / "wt"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "other")
        self.assertEqual(shift_notice.file_key(repo / "a.txt")[0], shift_notice.file_key(wt / "a.txt")[0])
        self.call("bbbbbbbb-1", "Read", repo / "a.txt")
        self.call("aaaaaaaa-1", "Edit", wt / "a.txt")
        self.assertIn("another worktree", self.call("bbbbbbbb-1", "Read", repo / "b.txt"))

    def test_outside_checkout_uses_absolute_path(self):
        f = self.root / "loose.txt"
        key, root = shift_notice.file_key(f)
        self.assertIsNone(root)
        self.assertEqual(key.lower(), str(f).lower())
        self.call("bbbbbbbb-1", "Read", f)
        self.call("aaaaaaaa-1", "Write", f)
        self.assertIn("loose.txt", self.call("bbbbbbbb-1", "Read", self.root / "x.txt"))

    def test_off_and_malformed(self):
        with mock.patch.dict(os.environ, {"STANDARDS_SHIFT_NOTICE": "0"}):
            self.assertEqual(self.call("a", "Read", self.root / "a.txt"), "")
        for text in ("not json", "[]", '{"tool_name": "Read"}'):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(shift_notice.main(text), 0)
            self.assertEqual(out.getvalue(), "")

    def test_database_can_be_deleted(self):
        self.call("a", "Read", self.root / "a.txt")
        for leftover in self.home.glob("shift.db*"):
            leftover.unlink()


if __name__ == "__main__":
    unittest.main()
