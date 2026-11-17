import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
import cache_notice  # noqa: E402

BASE = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)


def assistant(minutes, read, created=0, model="m1", request="r", side=False, inp=10):
    return {
        "type": "assistant",
        "timestamp": (BASE + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "isSidechain": side,
        "requestId": request,
        "message": {
            "model": model,
            "usage": {"input_tokens": inp, "cache_creation_input_tokens": created, "cache_read_input_tokens": read},
        },
    }


class CacheNoticeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        old = os.environ.get("STANDARDS_HOME")
        os.environ["STANDARDS_HOME"] = str(self.home)
        self.addCleanup(self.restore, old)

    @staticmethod
    def restore(old):
        if old is None:
            os.environ.pop("STANDARDS_HOME", None)
        else:
            os.environ["STANDARDS_HOME"] = old

    def transcript(self, entries, raw=()):
        path = self.dir / "t.jsonl"
        lines = list(raw) + [json.dumps(e) for e in entries]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def stop(self, entries, raw=()):
        return cache_notice.stop_message(self.transcript(entries, raw), "s1", 5.0)

    def test_full_read_gives_no_notice(self):
        first = assistant(0, 0, created=50000, request="a")
        second = assistant(1, 50010, request="b")
        self.assertIsNone(self.stop([first, second]))
        self.assertFalse((self.home / "cache-misses.jsonl").exists())

    def test_a_synthetic_message_of_the_client_is_not_a_request(self):
        # Found on a real transcript: a usage limit notice, model "<synthetic>" with no usage, read as a model change.
        first = assistant(0, 0, created=50000, request="a")
        notice = assistant(1, 0, model="<synthetic>", request="n", inp=0)
        second = assistant(2, 50010, request="b")
        self.assertIsNone(self.stop([first, notice, second]))
        self.assertIsNone(self.stop([first, second, notice]))

    def test_a_one_hour_cache_is_not_called_cold_after_ten_minutes(self):
        hour = [assistant(0, 0, 48000, request="a"), assistant(1, 48010, request="b")]
        hour[0]["message"]["usage"]["cache_creation"] = {"ephemeral_1h_input_tokens": 48000, "ephemeral_5m_input_tokens": 0}
        later = BASE + timedelta(minutes=11)
        self.assertIsNone(cache_notice.prompt_message(self.transcript(hour), None, now=later))
        five = [assistant(0, 0, 48000, request="a"), assistant(1, 48010, request="b")]
        self.assertIn("likely cold", cache_notice.prompt_message(self.transcript(five), None, now=later))

    def test_model_changed(self):
        text = self.stop([assistant(0, 0, 48000, request="a"), assistant(1, 0, 48000, model="m2", request="b")])
        self.assertIn("48,010 tokens written again", text)
        self.assertIn("the model changed", text)

    def test_compaction_between(self):
        for marker in ({"isCompactSummary": True, "type": "user"}, {"type": "system", "subtype": "compact_boundary"}):
            text = self.stop([assistant(0, 0, 48000, request="a"), marker, assistant(1, 0, 9000, request="b")])
            self.assertIn("a compaction rewrote the context", text)

    def test_utc_date_changed(self):
        text = self.stop([assistant(0, 0, 48000, request="a"), assistant(840, 0, 48000, request="b")])
        self.assertIn("the UTC date changed", text)

    def test_gap_above_ttl(self):
        text = self.stop([assistant(0, 0, 48000, request="a"), assistant(12, 0, 48000, request="b")])
        self.assertIn("the cache expired after 12 minutes idle", text)

    def test_unexplained_and_log_line(self):
        text = self.stop([assistant(0, 0, 48000, request="a"), assistant(1, 100, 47910, request="b")])
        self.assertIn("unexplained: the start of the prompt changed", text)
        rows = (self.home / "cache-misses.jsonl").read_text(encoding="utf-8").splitlines()
        row = json.loads(rows[0])
        self.assertEqual(sorted(row), ["at", "missed", "model", "reason", "session"])
        self.assertEqual(row["session"], "s1")

    def test_small_miss_is_ignored(self):
        self.assertIsNone(self.stop([assistant(0, 0, 2000, request="a"), assistant(1, 1500, request="b")]))

    def test_same_request_counts_once_and_sidechain_is_ignored(self):
        entries = [
            assistant(0, 0, 48000, request="a"),
            assistant(0, 0, 48000, request="a"),
            assistant(1, 48010, request="b"),
            assistant(1, 48010, request="b"),
            assistant(2, 0, 90000, request="c", side=True),
        ]
        requests = cache_notice.load_requests(self.transcript(entries))
        self.assertEqual(len(requests), 2)
        self.assertIsNone(self.stop(entries))

    def test_prompt_mode(self):
        path = self.transcript([assistant(0, 0, 48000, request="a"), assistant(1, 48010, request="b")])
        text = cache_notice.prompt_message(path, 5.0, now=BASE + timedelta(minutes=21))
        self.assertIn("20 minutes since the last answer", text)
        self.assertIn("48,020 tokens", text)
        self.assertIsNone(cache_notice.prompt_message(path, 5.0, now=BASE + timedelta(minutes=3)))

    def test_malformed_lines_and_missing_transcript(self):
        entries = [assistant(0, 0, 48000, request="a"), assistant(1, 0, 48000, model="m2", request="b")]
        text = self.stop(entries, raw=["{not json", "[1, 2]", ""])
        self.assertIn("the model changed", text)
        # main reads the hook input from stdin: give it one, or the test waits on an open terminal.
        missing = json.dumps({"session_id": "s1", "transcript_path": str(self.home / "missing.jsonl")})
        with mock.patch.object(cache_notice.sys, "stdin", io.StringIO(missing)):
            self.assertEqual(cache_notice.main(["cache_notice.py", "stop"]), 0)


if __name__ == "__main__":
    unittest.main()
