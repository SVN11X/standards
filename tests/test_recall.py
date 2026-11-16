"""A new session gets the decision that fits its request, and a finished plan leaves a handoff for the next one."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import recall  # noqa: E402

DECISION = ("# 0004. Keep sessions in SQLite\n\n- Status: accepted\n- Date: 2026-11-10\n- Proposed by: Claude Code\n"
            "- Accepted by: owner, in PR 12\n\n## Context\n\nx\n\n## Decision\n\nStudy sessions live in one SQLite file, "
            "never in JSON files.\n\n## Consequences\n\ny\n")
OTHER = DECISION.replace("0004. Keep sessions in SQLite", "0005. Validate PDF files").replace(
    "Study sessions live in one SQLite file, never in JSON files.", "Validators read PDF and Markdown.")


class RecallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "tutor"
        (self.repo / "docs" / "decisions").mkdir(parents=True)
        (self.repo / "docs" / "decisions" / "0004-sessions-in-sqlite.md").write_text(DECISION, encoding="utf-8")
        (self.repo / "docs" / "decisions" / "0005-pdf.md").write_text(OTHER, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def test_only_the_decision_that_fits_comes_back(self):
        found = recall.lines(self.repo, "Save the study sessions in JSON files instead")
        self.assertEqual(len(found), 1)
        self.assertIn("0004-sessions-in-sqlite.md (accepted)", found[0])
        self.assertIn("never in JSON files", found[0])
        self.assertEqual(recall.lines(self.repo, "Change the color of the button"), [])

    def test_a_finished_plan_leaves_a_handoff_the_next_session_reads(self):
        plan = {"plan_id": "p9", "goal": "Move study sessions to the new schema"}
        state = {"units": {"u1": {"status": "passed"}, "u2": {"status": "blocked", "note": "no reviewer model"}}}
        recall.handoff(self.repo, plan, state)
        found = recall.lines(self.repo, "continue the study sessions schema work")
        memo = [line for line in found if line.startswith("Memory")]
        self.assertEqual(len(memo), 1)
        self.assertIn("fact, plan p9", memo[0])
        self.assertIn("u2 (no reviewer model)", memo[0])

    def test_the_prompt_hook_puts_the_decision_in_context(self):
        (self.repo / ".standard.yml").write_text("profile: software\n", encoding="utf-8")
        env = {**os.environ, "STANDARDS_NO_PEERBOX": "1"}
        payload = {"prompt": "Cambia las study sessions a JSON files", "cwd": str(self.repo), "session_id": "r1"}
        out = subprocess.run([sys.executable, str(ROOT / "hooks" / "route_prompt.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=60, check=True)
        context = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("recalled, not the whole history", context)
        self.assertIn("0004-sessions-in-sqlite.md", context)


if __name__ == "__main__":
    unittest.main()
