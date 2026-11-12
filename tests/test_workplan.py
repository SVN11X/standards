"""Work plan contract. Run: python -m unittest discover -s tests"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import workplan  # noqa: E402

POLICY = {
    "tasks": {"edit-small": ["opencode"], "lint": ["tools"]},
    "planner_tasks": ["plan"],
    "protected": ["AGENTS.md", ".github/workflows/*"],
}
FILES = ["a/x.py", "a/y.py", "b/z.py", "package.json", "AGENTS.md"]


def unit(uid, allowed, deps=(), kind="edit-small", test="python -m unittest", **extra):
    data = {"id": uid, "title": uid, "task_type": kind, "goal": "g", "allowed": list(allowed),
            "depends_on": list(deps), "acceptance": {"test": test} if test else {}}
    data.update(extra)
    return data


def plan(*units):
    return {"plan_id": "p", "goal": "g", "units": list(units)}


class Validate(unittest.TestCase):
    def check(self, p):
        return workplan.validate(p, POLICY)

    def test_valid(self):
        self.assertEqual(self.check(plan(unit("u1", ["a/*.py"]), unit("u2", ["b/z.py"], ["u1"]))), [])

    def test_schema_errors(self):
        self.assertTrue(any("allowed" in e for e in self.check(plan(unit("u1", [])))))
        self.assertTrue(any("missing goal" in e for e in self.check({"plan_id": "p", "units": []})))

    def test_duplicate_unknown_planner(self):
        errors = self.check(plan(unit("u1", ["a/x.py"]), unit("u1", ["a/y.py"], kind="plan"),
                                 unit("u3", ["b/z.py"], ["nope"], kind="mystery")))
        text = " ".join(errors)
        for needle in ("duplicate unit id u1", "planner type", "unknown task_type mystery", "unknown dependency nope"):
            self.assertIn(needle, text)

    def test_protected_and_acceptance(self):
        errors = self.check(plan(unit("u1", ["AGENTS.md"]), unit("u2", ["a/x.py"], test=None),
                                 unit("u3", ["a/y.py"], kind="lint", test=None)))
        text = " ".join(errors)
        self.assertIn("u1: protected file AGENTS.md", text)
        self.assertIn("u2: acceptance.test is required", text)
        self.assertNotIn("u3", text)

    def test_cycle(self):
        errors = self.check(plan(unit("u1", ["a/x.py"], ["u2"]), unit("u2", ["a/y.py"], ["u1"])))
        self.assertTrue(any("cycle" in e for e in errors))
        with self.assertRaises(ValueError):
            workplan.topo_order(plan(unit("u1", ["a"], ["u2"]), unit("u2", ["b"], ["u1"]))["units"])


class Graph(unittest.TestCase):
    def test_topo_order(self):
        units = plan(unit("c", ["a"], ["b"]), unit("b", ["b"], ["a"]), unit("a", ["c"]))["units"]
        self.assertEqual(workplan.topo_order(units), ["a", "b", "c"])

    def test_expand_globs_and_new_files(self):
        got = workplan.expand(unit("u", ["a/*.py"], new_files=["a/new.py"]), FILES)
        self.assertEqual(got, {"a/x.py", "a/y.py", "a/new.py"})

    def test_conflicts_and_batches(self):
        p = plan(unit("u1", ["a/x.py"]), unit("u2", ["a/*.py"]), unit("u3", ["b/z.py"]),
                 unit("u4", ["b/z.py"], ["u3"]))
        self.assertEqual([c[:2] for c in workplan.conflicts(p, FILES)], [("u1", "u2")])
        self.assertEqual(workplan.batches(p, FILES), [["u1", "u3"], ["u2", "u4"]])

    def test_serial_files_never_parallel(self):
        p = plan(unit("u1", ["a/x.py"], new_files=["pyproject.toml"]),
                 unit("u2", ["a/y.py"], new_files=["requirements-dev.txt"]))
        self.assertEqual(workplan.conflicts(p, FILES)[0][2], "both touch serial files")
        self.assertEqual(workplan.batches(p, FILES), [["u1"], ["u2"]])

    def test_one_serial_file_is_fine(self):
        p = plan(unit("u1", ["package.json"]), unit("u2", ["a/y.py"]))
        self.assertEqual(workplan.conflicts(p, FILES), [])

    def test_max_parallel(self):
        p = plan(unit("u1", ["a/x.py"]), unit("u2", ["a/y.py"]), unit("u3", ["b/z.py"]))
        self.assertEqual(workplan.batches(p, FILES, max_parallel=2), [["u1", "u2"], ["u3"]])

    def test_input_not_mutated(self):
        p = plan(unit("u1", ["a/x.py"]))
        before = copy.deepcopy(p)
        workplan.batches(p, FILES)
        self.assertEqual(p, before)


if __name__ == "__main__":
    unittest.main()
