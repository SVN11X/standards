"""The Promptline pack is valid and its control prompts are the ones the router understands."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import promptline_pack  # noqa: E402
import router  # noqa: E402


def text_of(title: str) -> str:
    return next(p["text"] for p in promptline_pack.PROMPTS if p["title"] == title)


class PackTests(unittest.TestCase):
    def test_pack_has_no_problems(self):
        self.assertEqual(promptline_pack.problems(promptline_pack.pack()), [])

    def test_control_prompts_classify_as_control(self):
        for title in ("Estado", "Pausa", "Reanuda", "Cancela el plan", "Por qué se detuvo"):
            with self.subTest(title=title):
                self.assertEqual(router.classify(text_of(title))[0], "control")

    def test_continue_is_work(self):
        self.assertEqual(router.classify(text_of("Continúa"))[0], "work")

    def test_problems_flags_each_defect(self):
        def one(**changes):
            item = {"title": "A", "tags": ["x"], "group": "G", "text": "hola"}
            return {"name": "n", "prompts": [{**item, **changes}]}

        dup = {"name": "n", "prompts": [one()["prompts"][0], one()["prompts"][0]]}
        self.assertTrue(any("duplicate" in p for p in promptline_pack.problems(dup)))
        self.assertTrue(any("lowercase" in p for p in promptline_pack.problems(one(tags=["Caps"]))))
        self.assertTrue(any("1 to 3" in p for p in promptline_pack.problems(one(tags=["a", "b", "c", "d"]))))
        self.assertTrue(any("{Bad}" in p for p in promptline_pack.problems(one(text="hola {Bad}"))))
        self.assertEqual(promptline_pack.problems(one(text="{a_b} {{c}} {clipboard} {date} {time}")), [])

    def test_main_writes_the_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack.json"
            self.assertEqual(promptline_pack.main(["--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), promptline_pack.pack())


if __name__ == "__main__":
    unittest.main()
