"""What the hooks add to a session, and what they leave out because the session holds it."""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

import context_log  # noqa: E402
import route_prompt  # noqa: E402

SESSION = {"session_id": "abc", "transcript_path": "/t/abc.jsonl"}
ROUTER = "standards router: work request for repository web, folder . (the session is inside this folder)."
RECALL = "Read before planning (recalled, not the whole history):\n- 2026-11-20 the build needs node 22\n- the owner prefers small PRs"


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"STANDARDS_HOME": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def blocks(self, recall=RECALL):
        return [("style", "The owner asked for depth this turn.", "always"), ("router", ROUTER, "once"), ("recall", recall, "lines")]

    def test_the_first_message_gets_every_block(self):
        sent, row = context_log.select(SESSION, self.blocks())
        self.assertEqual(sent, ["The owner asked for depth this turn.", ROUTER, RECALL])
        self.assertEqual((row["skipped_chars"], row["blocks"]["router"]), (0, len(ROUTER)))

    def test_a_block_the_session_holds_becomes_one_short_line(self):
        _, first = context_log.select(SESSION, self.blocks())
        sent, row = context_log.select(SESSION, self.blocks())
        self.assertEqual(sent[0], "The owner asked for depth this turn.")
        self.assertIn("router: unchanged since an earlier message", sent[1])
        self.assertEqual(len(sent), 2)
        self.assertEqual(row["sent_chars"] + row["skipped_chars"], first["sent_chars"])

    def test_only_new_recalled_notes_are_sent(self):
        context_log.select(SESSION, self.blocks())
        sent, _ = context_log.select(SESSION, self.blocks(RECALL + "\n- a new note about the tests"))
        self.assertEqual(sent[-1], "Read before planning (recalled, not the whole history):\n- a new note about the tests")

    def test_a_compaction_sends_everything_again(self):
        context_log.select(SESSION, self.blocks())
        context_log.forget(SESSION)
        sent, row = context_log.select(SESSION, self.blocks())
        self.assertEqual((len(sent), row["skipped_chars"]), (3, 0))

    def test_another_transcript_or_no_session_starts_empty(self):
        context_log.select(SESSION, self.blocks())
        cleared, _ = context_log.select({**SESSION, "transcript_path": "/t/new.jsonl"}, self.blocks())
        anonymous, _ = context_log.select({}, self.blocks())
        again, _ = context_log.select({}, self.blocks())
        self.assertEqual((len(cleared), len(anonymous), len(again)), (3, 3, 3))
        self.assertIn(ROUTER, again)

    def test_an_old_entry_is_sent_again(self):
        context_log.select(SESSION, self.blocks())
        later = context_log.now() + dt.timedelta(hours=context_log.MAX_AGE_H + 1)
        with mock.patch.object(context_log, "now", return_value=later):
            sent, _ = context_log.select(SESSION, self.blocks())
        self.assertIn(ROUTER, sent)

    def test_the_summary_adds_up_the_log(self):
        for _ in range(2):
            _, row = context_log.select(SESSION, self.blocks())
            context_log.log(row)
        total = context_log.summary()
        self.assertEqual(total["injections"], 2)
        self.assertGreater(total["skipped_chars"], 0)
        self.assertEqual(total["blocks"]["router"]["count"], 2)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"STANDARDS_HOME": self.tmp.name, "STANDARDS_NO_PEERBOX": "1",
                                               "STANDARDS_NO_SUPERVISOR": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_hook(self) -> str:
        payload = json.dumps({**SESSION, "prompt": "Corrige el título", "cwd": self.tmp.name})
        out = io.StringIO()
        with mock.patch.object(route_prompt, "context_parts", return_value={"router": ROUTER, "recall": RECALL}), \
             mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode("utf-8")), encoding="utf-8")), \
             mock.patch.object(sys, "stdout", out):
            self.assertEqual(route_prompt.main(), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_the_second_prompt_leaves_out_what_the_first_added(self):
        first = self.run_hook()
        second = self.run_hook()
        self.assertIn(ROUTER, first)
        self.assertIn("2026-11-20 the build needs node 22", first)
        self.assertNotIn(ROUTER, second)
        self.assertNotIn("node 22", second)
        rows = [json.loads(line) for line in (Path(self.tmp.name) / "context.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertGreater(rows[1]["skipped_chars"], 0)


class CommandTests(unittest.TestCase):
    def test_usage_context_prints_the_summary(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import contextlib
        import usage
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"STANDARDS_HOME": tmp}):
            _, row = context_log.select(SESSION, [("router", ROUTER, "once")])
            context_log.log(row)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(usage.main(["context", "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["blocks"]["router"]["chars"], len(ROUTER))


if __name__ == "__main__":
    unittest.main()
