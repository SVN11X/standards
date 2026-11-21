"""Guardrails of .standard.yml that the check enforces: forbidden patterns and module boundaries in Python and TypeScript.
Run: python -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import guardrails  # noqa: E402

FILES = {
    "src/features/signup/Form.tsx": 'import { total } from "../billing/total";\nimport { Button } from "@/shared/Button";\n'
                                    'import React from "react";\nuseEffect(() => {}, []);\n',
    "src/features/signup/legacy/Old.tsx": "useEffect(() => {}, []);\n",
    "src/features/billing/total.ts": "export const total = 1;\n",
    "src/shared/Button.tsx": "export const Button = () => null;\n",
    "app/signup/__init__.py": "",
    "app/signup/views.py": "from ..billing import prices\nfrom app.shared import text\nimport requests\nfrom . import forms\n",
    "app/signup/forms.py": "",
    "app/billing/__init__.py": "",
    "app/billing/prices.py": "",
    "app/shared/__init__.py": "",
    "app/shared/text.py": "",
}


class Guardrails(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        for rel, text in FILES.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")
        self.files = sorted(FILES)

    def check(self, block):
        return guardrails.check(self.repo, self.files, {"guardrails": block})

    def test_a_forbidden_pattern_is_blocked_with_its_line_and_its_reason(self):
        hits, broken = self.check({"forbidden": [{"id": "no-use-effect", "pattern": r"\buseEffect\(", "paths": ["src/*.tsx"],
                                                  "except": ["src/features/signup/legacy/*"], "why": "Derive the state."}]})
        self.assertEqual(broken, [])
        self.assertEqual(hits, [("src/features/signup/Form.tsx:4", "Guardrail no-use-effect: Derive the state.")])

    def test_a_typescript_import_across_a_boundary_is_blocked_and_an_allowed_one_passes(self):
        block = {"boundaries": [{"module": "src/features/signup", "may_import": ["src/shared"], "why": "Only through shared."}],
                 "aliases": {"@/": "src/"}}
        hits, _ = self.check(block)
        self.assertEqual(len(hits), 1)
        self.assertIn("it imports src/features/billing/total.ts", hits[0][1])
        block["boundaries"][0]["may_import"].append("src/features/billing")
        self.assertEqual(self.check(block)[0], [])

    def test_python_imports_are_resolved_and_other_packages_are_not_judged(self):
        hits, _ = self.check({"boundaries": [{"module": "app/signup", "may_import": ["app/shared"], "why": "Only through shared."}]})
        self.assertEqual([message.split(": it imports ")[1].split(",")[0] for _, message in hits], ["app/billing"])

    def test_a_broken_rule_is_reported_instead_of_passing_silently(self):
        _, broken = self.check({"forbidden": [{"pattern": "(", "paths": ["*"], "why": "x"}, {"pattern": "x"}],
                                "boundaries": [{"module": "src"}]})
        self.assertEqual(len(broken), 3)
        self.assertEqual(guardrails.check(self.repo, self.files, {})[0], [])


if __name__ == "__main__":
    unittest.main()
