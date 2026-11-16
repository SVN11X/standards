"""Desktop UX: the rules on plain numbers, the usability card and SUS, and a real tkinter window when one can open."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import desktop_ux as ux  # noqa: E402


def rules(findings):
    return sorted({(f["rule"], f["severity"]) for f in findings})


class Rules(unittest.TestCase):
    def test_contrast_follows_wcag(self):
        self.assertEqual(ux.contrast((0, 0, 0), (1, 1, 1)), 21.0)
        grey = tuple(0xBB / 255 for _ in range(3))
        self.assertLess(ux.contrast(grey, (1, 1, 1)), 4.5)
        self.assertTrue(ux.large_text(18, False))
        self.assertTrue(ux.large_text(14, True))
        self.assertFalse(ux.large_text(14, False))

    def test_a_small_target_passes_only_with_room_around_it(self):
        alone = [{"where": "a", "rect": (0, 0, 16, 16)}, {"where": "b", "rect": (60, 0, 100, 30)}]
        self.assertEqual(ux.target_findings(alone, 1), [])
        crowded = [{"where": "a", "rect": (0, 0, 16, 16)}, {"where": "b", "rect": (18, 0, 34, 16)}]
        found = ux.target_findings(crowded, 1)
        self.assertEqual([f["where"] for f in found if f["rule"] == "target"], ["a", "b"])
        self.assertIn(("spacing", "warning"), rules(found))

    def test_targets_that_touch_or_keep_five_pixels_apart_are_spaced_well(self):
        touching = [{"where": "a", "rect": (0, 0, 40, 30)}, {"where": "b", "rect": (40, 0, 80, 30)}]
        apart = [{"where": "a", "rect": (0, 0, 40, 30)}, {"where": "b", "rect": (45, 0, 85, 30)}]
        close = [{"where": "a", "rect": (0, 0, 40, 30)}, {"where": "b", "rect": (43, 0, 83, 30)}]
        self.assertEqual(ux.target_findings(touching, 1), [])
        self.assertEqual(ux.target_findings(apart, 1), [])
        self.assertEqual(rules(ux.target_findings(close, 1)), [("spacing", "warning")])
        spacing = [f for f in ux.target_findings(close, 2) if f["rule"] == "spacing"]
        self.assertEqual(spacing[0]["detail"].split()[0], "1.5")

    def test_uia_rules(self):
        window = (0, 0, 400, 300)
        items = [
            {"name": "", "type": "Button", "rect": (10, 10, 60, 40), "focusable": True},
            {"name": "Guardar", "type": "Button", "rect": (100, 10, 160, 40), "focusable": False},
            {"name": "Guardar", "type": "Button", "rect": (200, 10, 260, 40), "focusable": True},
            {"name": "Uno", "type": "ListItem", "rect": (10, 100, 200, 130), "focusable": False},
            {"name": "Fuera", "type": "Button", "rect": (360, 250, 440, 290), "focusable": True},
            {"name": "", "type": "Button", "rect": (10, 200, 60, 230), "focusable": False, "offscreen": True},
            {"name": "Texto", "type": "Text", "rect": (10, 150, 60, 160)},
        ]
        found = ux.uia_findings(items, window, 1)
        self.assertEqual(sorted(f["rule"] for f in found), ["clipped", "keyboard", "labels", "name"])

    def test_sus_score(self):
        self.assertEqual(ux.sus_score([3] * 10), 50.0)
        self.assertEqual(ux.sus_score([5, 1] * 5), 100.0)
        self.assertEqual(ux.sus_score([1, 5] * 5), 0.0)
        self.assertIsNone(ux.sus_score([3] * 9))
        self.assertIsNone(ux.sus_score([3] * 9 + [6]))

    def test_sizes(self):
        self.assertEqual(ux.sizes_of("1024x700, 800x600"), [(1024, 700), (800, 600)])
        with self.assertRaises(Exception):
            ux.sizes_of("big")


class People(unittest.TestCase):
    def test_the_card_holds_no_result_until_people_fill_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = ux.protocol("OpenTutor", ["Inicia una sesión de una hora", "Elige la carpeta del banco"], Path(tmp), "2026-11-16")
            data = yaml.safe_load(card.read_text(encoding="utf-8"))
            self.assertEqual((data["kind"], len(data["tasks"])), ("usability", 2))
            self.assertEqual(len(data["rounds"][0]["participants"][0]["tasks"]), 2)
            self.assertIn("Creo que me gustaría usar este sistema con frecuencia.", card.read_text(encoding="utf-8"))
            self.assertEqual(ux.evidence(Path(tmp))["tests"][0]["state"], "not run")
            with self.assertRaises(FileExistsError):
                ux.protocol("OpenTutor", ["x"], Path(tmp))

    def test_evidence_reads_five_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = ux.protocol("OpenTutor", ["Inicia una sesión", "Elige la carpeta"], Path(tmp), "2026-11-16")
            data = yaml.safe_load(card.read_text(encoding="utf-8"))
            people = []
            for done, sus in ((True, [5, 1] * 5), (True, [4, 2] * 5), ("partial", [3] * 10), (False, [2, 4] * 5), (True, [4, 2] * 5)):
                people.append({"who": "student", "tasks": [{"done": done, "seconds": 30, "errors": 1, "hesitated_at": "Ajustes"},
                                                           {"done": True, "seconds": 12, "errors": 0, "hesitated_at": ""}], "sus": sus})
            data["rounds"][0]["participants"] = people
            card.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
            test = ux.evidence(Path(tmp))["tests"][0]
            self.assertEqual((test["state"], test["people"]), ("tested", 5))
            self.assertEqual(test["tasks"][0]["success_rate"], 0.7)
            self.assertEqual((test["tasks"][1]["success_rate"], test["tasks"][1]["median_seconds"]), (1.0, 12))
            self.assertEqual(test["sus_mean"], 65.0)
            self.assertEqual(test["sus_vs_average"], "at or below")
            self.assertIn("70% done", ux.evidence_summary(ux.evidence(Path(tmp))))


def tk_runner():
    """A command that opens a tkinter window here, or None when this machine cannot."""
    if subprocess.run([sys.executable, "-c", "import tkinter"], capture_output=True).returncode != 0:
        return None
    if os.environ.get("DISPLAY") or os.name == "nt":
        return [sys.executable]
    return ["xvfb-run", "-a", sys.executable] if shutil.which("xvfb-run") else None


@unittest.skipIf(tk_runner() is None, "no tkinter or no display on this machine")
class Tk(unittest.TestCase):
    def test_a_real_window_shows_one_problem_of_each_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            ran = subprocess.run([*tk_runner(), str(ROOT / "scripts" / "desktop_ux.py"), "tk", "tk_demo_app:build",
                                  "--src", str(ROOT / "tests" / "fixtures"), "--sizes", "640x480,200x120", "--json",
                                  "--shots", tmp], capture_output=True, text=True, timeout=120)
            self.assertEqual(ran.returncode, 0, ran.stderr)
            result = json.loads(ran.stdout)
            found = {(f["rule"], f["where"].split(" ")[0] if f["where"] != "the window" else "the window") for f in result["findings"]}
            for expected in [("contrast", "Label"), ("keyboard", "Button"), ("keyboard", "Label"), ("target", "Button"),
                             ("font", "Label"), ("spacing", "Button"), ("clipped", "Label"), ("clipped", "the window")]:
                self.assertIn(expected, found)
            self.assertEqual(len(result["screenshots"]) + sum("screenshot" in n for n in result["notes"]), 4)
            self.assertTrue(all(Path(p).stat().st_size > 0 for p in result["screenshots"]))


if __name__ == "__main__":
    unittest.main()
