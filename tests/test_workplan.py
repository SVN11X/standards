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


class Split(unittest.TestCase):
    def split(self, u, propose=None):
        return workplan.split_unit(u, FILES, propose, POLICY)

    def test_by_files(self):
        u = unit("u", ["a/*.py"], new_files=["a/new.py"])
        method, parts = self.split(u)
        self.assertEqual(method, "files")
        self.assertEqual([p["id"] for p in parts], ["u.1", "u.2", "u.3"])
        self.assertEqual(sorted(sum((p["allowed"] + p["new_files"] for p in parts), [])), ["a/new.py", "a/new.py", "a/x.py", "a/y.py"])

    def test_by_criteria_chained(self):
        u = unit("u", ["b/z.py"], acceptance={"test": "t", "criteria": ["one", "two"]})
        method, parts = self.split(u)
        self.assertEqual(method, "criteria")
        self.assertEqual(parts[1]["depends_on"], ["u.1"])
        self.assertEqual(parts[0]["acceptance"]["criteria"], ["one"])

    def test_model_used_last_and_validated(self):
        u = unit("u", ["b/z.py"])
        good = [unit("u.a", ["b/z.py"]), unit("u.b", ["b/z.py"], ["u.a"])]
        calls = []

        def fake(unit_, files_):
            calls.append(unit_["id"])
            return good

        self.assertEqual(self.split(u, fake), ("model", good))
        self.assertEqual(calls, ["u"])

    def test_model_not_called_when_deterministic_works(self):
        def boom(*_):
            raise AssertionError("model called")

        self.assertEqual(self.split(unit("u", ["a/*.py"]), boom)[0], "files")

    def test_invalid_model_proposals_rejected(self):
        u = unit("u", ["b/z.py"])
        outside = [unit("u.a", ["a/x.py"]), unit("u.b", ["b/z.py"])]
        for bad in (outside, [unit("u.a", ["b/z.py"])], "junk", [unit("u.a", ["b/z.py"], kind="mystery"), unit("u.b", ["b/z.py"])],
                    [unit("u", ["b/z.py"]), unit("u.b", ["b/z.py"])]):
            self.assertEqual(self.split(u, lambda *_: bad), ("none", []))

    def test_model_error_and_no_model(self):
        def fail(*_):
            raise RuntimeError("down")

        u = unit("u", ["b/z.py"])
        self.assertEqual(self.split(u, fail), ("none", []))
        self.assertEqual(self.split(u), ("none", []))

    def test_unit_not_mutated(self):
        u = unit("u", ["a/*.py"])
        before = copy.deepcopy(u)
        self.split(u)
        self.assertEqual(u, before)


if __name__ == "__main__":
    unittest.main()
