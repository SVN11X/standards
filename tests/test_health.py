"""Failure codes, cooldowns and fallbacks in route(). Uses a temporary home, never ~/.standards."""
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402

TODAY = dt.date.today().isoformat()


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="std-health-"))
        self.old = os.environ.get("STANDARDS_HOME")
        os.environ["STANDARDS_HOME"] = str(self.tmp / "home")
        self.conf = orchestrate.policy()
        self.local = {"folders": [{"path": str(self.tmp), "class": "personal-public"}],
                      "free_models": [{"id": "opencode/a-free", "checked": TODAY, "data_use": "none"},
                                      {"id": "opencode/b-free", "checked": TODAY, "data_use": "none"}]}
        self.caps = {"opencode": {"path": "opencode"}, "colibri": {"up": True, "models": ["fake-coder"]}}

    def tearDown(self):
        if self.old is None:
            os.environ.pop("STANDARDS_HOME", None)
        else:
            os.environ["STANDARDS_HOME"] = self.old

    def route(self):
        return orchestrate.route("edit-small", self.tmp, conf=self.conf, local=self.local, caps=self.caps, catalog={})

    def test_failure_codes(self):
        code = orchestrate.failure_code
        self.assertEqual(code(1, True, ""), "timeout")
        self.assertEqual(code(1, False, "HTTP 429 too many requests"), "rate_limit")
        self.assertEqual(code(1, False, "401 Unauthorized"), "auth")
        self.assertEqual(code(1, False, "connection refused"), "unavailable")
        self.assertIsNone(code(1, False, "tests failed"))
        self.assertIsNone(code(0, False, "429 in a log line"))

    def test_cooldown_is_written_to_the_temp_home_and_expires(self):
        at = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        orchestrate.record_health("opencode", "m", "rate_limit", self.conf, at)
        self.assertTrue((self.tmp / "home" / "health.json").exists())
        self.assertIn(("opencode", "m"), orchestrate.cooling_set(at + dt.timedelta(seconds=10)))
        self.assertNotIn(("opencode", "m"), orchestrate.cooling_set(at + dt.timedelta(days=1)))
        orchestrate.record_health("opencode", "m", None, self.conf)
        self.assertEqual(orchestrate.load_health(), {})

    def test_failing_model_is_skipped_and_the_next_one_is_chosen(self):
        first = self.route()
        self.assertEqual(first["executor"], "opencode")
        orchestrate.record_health("opencode", first["model"], "rate_limit", self.conf)
        second = self.route()
        self.assertEqual(second["executor"], "opencode")
        self.assertNotEqual(second["model"], first["model"])

    def test_colibri_is_never_a_fallback_and_is_not_replaced(self):
        self.assertEqual(self.route()["fallbacks"], [])
        for model in ("opencode/a-free", "opencode/b-free"):
            orchestrate.record_health("opencode", model, "auth", self.conf)
        decision = self.route()
        self.assertEqual(decision["executor"], "colibri")
        self.assertEqual(decision["fallbacks"], [])

    def test_colibri_cooldown_blocks_it(self):
        orchestrate.record_health("colibri", "colibri/fake-coder", "timeout", self.conf)
        ok, why, _ = orchestrate.eligible("colibri", "edit-small", self.tmp, 0, self.conf, self.local, self.caps,
                                          {}, None, False, {}, orchestrate.cooling_set())
        self.assertFalse(ok)
        self.assertIn("timeout", why)


if __name__ == "__main__":
    unittest.main()
