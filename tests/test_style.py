"""The direct style starts with the session, survives a compaction, yields to a request for depth and turns off on request."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
import style  # noqa: E402


def hook(name, payload, env):
    out = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(payload), capture_output=True,
                         text=True, env=env, timeout=60, check=True)
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if out.stdout.strip() else ""


class StyleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {**os.environ, "STANDARDS_HOME": self.tmp.name, "STANDARDS_NO_SUPERVISOR": "1", "STANDARDS_NO_PEERBOX": "1"}
        os.environ["STANDARDS_HOME"] = self.tmp.name
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "AGENTS.md").write_text("# AGENTS.md\n\n## How to work\n1. Read the task.\n", encoding="utf-8")
        (self.repo / ".standard.yml").write_text("profile: software\n", encoding="utf-8")

    def payload(self, **extra):
        return {"cwd": str(self.repo), "session_id": "s1", **extra}

    def test_on_at_startup_and_after_compaction(self):
        self.assertIn("Direct answer style", hook("session_probe.py", self.payload(), self.env))
        self.assertIn("Direct answer style", hook("reinject.py", self.payload(), self.env))

    def test_modo_normal_turns_it_off_for_the_session_and_compaction_keeps_that(self):
        said = hook("route_prompt.py", self.payload(prompt="modo normal, por favor"), self.env)
        self.assertIn("Direct answer style is off", said)
        after = hook("reinject.py", self.payload(), self.env)
        self.assertIn("How to work", after)
        self.assertNotIn("Direct answer style", after)
        self.assertIn("Direct answer style is on", hook("route_prompt.py", self.payload(prompt="vuelve al modo directo"), self.env))

    def test_a_request_for_depth_is_answered_in_full(self):
        self.assertIn("explain fully", style.from_prompt("Explícame cómo funciona el supervisor", "s2"))
        self.assertIsNone(style.from_prompt("corrige el test", "s2"))

    def test_the_owner_can_turn_it_off_for_every_session(self):
        Path(self.tmp.name, "local.yml").write_text("style: off\n", encoding="utf-8")
        self.assertFalse(style.enabled("any"))
        self.assertIsNone(style.startup_lines("any"))

    def test_the_rules_keep_machine_output_untouched(self):
        self.assertIn("Never reshape JSON, commands or any output a tool reads", style.RULES)


if __name__ == "__main__":
    unittest.main()
