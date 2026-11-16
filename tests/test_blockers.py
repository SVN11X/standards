"""Blocker records are refused when vague and answer the owner's question with the six facts."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import blockers  # noqa: E402

GOOD = {"action": "merge PR 19 of OpenTutor at its current HEAD", "evidence": {"source": "AGENTS.md:12", "text": "never merge"},
        "kinds": ["owner-rule"], "authorization": "none for this PR", "work_done": "diff and checks reviewed",
        "unblock": "the owner approves the merge of PR 19"}


class BlockerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = self.tmp.name
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)

    def test_complete_record_is_saved_and_explained(self):
        blockers.add("p", GOOD)
        text = blockers.why("p")
        for part in ("merge PR 19", "AGENTS.md:12", "owner-rule", "diff and checks reviewed", "approves the merge"):
            self.assertIn(part, text)

    def test_general_action_and_missing_fields_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            blockers.add("p", {**GOOD, "action": "gallery blocked", "unblock": ""})
        self.assertIn("too general", str(caught.exception))
        self.assertIn("missing unblock", str(caught.exception))

    def test_evidence_without_source_text_is_refused_unless_rule_not_located(self):
        with self.assertRaises(ValueError):
            blockers.add("p", {**GOOD, "evidence": {"source": "AGENTS.md"}})
        blockers.add("p", {**GOOD, "evidence": "rule not located"})

    def test_agent_precaution_must_name_its_hidden_effect(self):
        with self.assertRaises(ValueError):
            blockers.add("p", {**GOOD, "kinds": ["agent-precaution"]})
        blockers.add("p", {**GOOD, "kinds": ["agent-precaution"], "hidden_effect": "closes the app in use"})

    def test_resolved_blocker_leaves_the_answer(self):
        saved = blockers.add("p", GOOD)
        blockers.resolve("p", saved["id"], "owner approved")
        self.assertEqual(blockers.why("p"), "Nothing is blocked.")


if __name__ == "__main__":
    unittest.main()
