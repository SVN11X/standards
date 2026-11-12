#!/usr/bin/env python3
"""Work plan contract: validate a plan, order its units, expand globs, find conflicts and group parallel batches.

Usage: python scripts/workplan.py validate PLAN.json
       python scripts/workplan.py batches PLAN.json [--repo DIR]
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402

SCHEMA = ROOT / "schemas" / "work-plan.schema.json"
SERIAL_FILES = ["package.json", "package-lock.json", "pyproject.toml", "requirements*.txt", ".standard.yml"]
TYPES = {"object": dict, "array": list, "string": str, "integer": int}


def check_schema(value, schema: dict, where: str = "plan") -> list[str]:
    """Minimal JSON Schema subset: type, required, properties, items, enum, minItems, minLength, minimum."""
    kind = schema.get("type")
    if kind:
        ok = isinstance(value, TYPES[kind]) and not (kind == "integer" and isinstance(value, bool))
        if not ok:
            return [f"{where}: expected {kind}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: must be one of {schema['enum']}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: must not be empty")
    if isinstance(value, int) and not isinstance(value, bool) and value < schema.get("minimum", value):
        errors.append(f"{where}: must be at least {schema['minimum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing {key}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += check_schema(value[key], sub, f"{where}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: needs at least {schema['minItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors += check_schema(item, schema["items"], f"{where}[{index}]")
    return errors


def matches(path: str, pattern: str) -> bool:
    return path == pattern or fnmatch.fnmatchcase(path, pattern)


def find_cycle(units: list[dict]) -> list[str]:
    """Return the ids of one cycle in depends_on, or an empty list."""
    known = {u["id"] for u in units}
    graph = {u["id"]: [d for d in u.get("depends_on", []) if d in known] for u in units}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        stack.append(node)
        for nxt in graph[node]:
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return []

    for node in graph:
        if node not in state:
            found = visit(node)
            if found:
                return found
    return []


def topo_order(units: list[dict]) -> list[str]:
    """Topological order, ties kept in plan order. Raises ValueError on a cycle."""
    ids = [u["id"] for u in units]
    deps = {u["id"]: set(u.get("depends_on", [])) & set(ids) for u in units}
    done: list[str] = []
    while len(done) < len(ids):
        ready = [i for i in ids if i not in done and deps[i] <= set(done)]
        if not ready:
            raise ValueError("cycle in depends_on: " + " -> ".join(find_cycle(units)))
        done.append(ready[0])
    return done


def ancestors(units: list[dict]) -> dict[str, set[str]]:
    deps = {u["id"]: set(u.get("depends_on", [])) for u in units}

    def walk(node: str, seen: set[str]) -> set[str]:
        for dep in deps.get(node, ()):
            if dep in deps and dep not in seen:
                seen.add(dep)
                walk(dep, seen)
        return seen

    return {node: walk(node, set()) for node in deps}


def tracked_files(repo: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in out.stdout.splitlines() if line]


def expand(unit: dict, files: list[str]) -> set[str]:
    """Files a unit may touch: allowed patterns against the tracked files, plus the declared new files."""
    found = {f for f in files for pattern in unit.get("allowed", []) if matches(f, pattern)}
    return found | set(unit.get("new_files", []))


def is_serial(path: str, serial: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(matches(path, p) or matches(name, p) for p in serial)


def validate(plan: dict, pol: dict | None = None) -> list[str]:
    """Return a list of problems. An empty list means the plan is valid."""
    pol = pol if pol is not None else orchestrate.policy()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = check_schema(plan, schema)
    if errors:
        return errors
    units = plan["units"]
    ids = [u["id"] for u in units]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate unit id {dup}")
    planner = set(pol.get("planner_tasks", []))
    known = set(pol.get("tasks", {}))
    tools = {t for t, c in pol.get("tasks", {}).items() if c == ["tools"]}
    protected = pol.get("protected", [])
    for unit in units:
        uid = unit["id"]
        kind = unit["task_type"]
        if kind in planner:
            errors.append(f"{uid}: task_type {kind} is a planner type")
        elif kind not in known:
            errors.append(f"{uid}: unknown task_type {kind}")
        for dep in unit.get("depends_on", []):
            if dep == uid:
                errors.append(f"{uid}: depends on itself")
            elif dep not in ids:
                errors.append(f"{uid}: unknown dependency {dep}")
        for path in unit["allowed"] + unit.get("new_files", []):
            if any(matches(path, p) for p in protected):
                errors.append(f"{uid}: protected file {path} in allowed or new_files")
        if kind not in tools and not unit["acceptance"].get("test") and not plan.get("defaults", {}).get("test"):
            errors.append(f"{uid}: acceptance.test is required for task_type {kind}")
    cycle = find_cycle(units)
    if cycle:
        errors.append("cycle in depends_on: " + " -> ".join(cycle))
    return errors


def conflicts(plan: dict, files: list[str] | None = None, serial: list[str] | None = None) -> list[tuple[str, str, str]]:
    """Pairs of independent units that share a file or both touch a serial file: (a, b, reason)."""
    units = plan["units"]
    files = files or []
    serial = SERIAL_FILES if serial is None else serial
    anc = ancestors(units)
    sets = {u["id"]: expand(u, files) for u in units}
    out = []
    for i, a in enumerate(units):
        for b in units[i + 1:]:
            if a["id"] in anc[b["id"]] or b["id"] in anc[a["id"]]:
                continue
            shared = sets[a["id"]] & sets[b["id"]]
            if shared:
                out.append((a["id"], b["id"], "shared file " + sorted(shared)[0]))
            elif any(is_serial(f, serial) for f in sets[a["id"]]) and any(is_serial(f, serial) for f in sets[b["id"]]):
                out.append((a["id"], b["id"], "both touch serial files"))
    return out


def batches(plan: dict, files: list[str] | None = None, serial: list[str] | None = None,
            max_parallel: int | None = None) -> list[list[str]]:
    """Layers of unit ids that may run together. Each layer is ordered, disjoint and free of dependency paths."""
    units = plan["units"]
    order = topo_order(units)
    clash = {frozenset(c[:2]) for c in conflicts(plan, files, serial)}
    deps = {u["id"]: set(u.get("depends_on", [])) for u in units}
    done: set[str] = set()
    result: list[list[str]] = []
    while len(done) < len(order):
        batch: list[str] = []
        for uid in order:
            if uid in done or not deps[uid] <= done:
                continue
            if max_parallel and len(batch) >= max_parallel:
                break
            if all(frozenset((uid, other)) not in clash for other in batch):
                batch.append(uid)
        result.append(batch)
        done.update(batch)
    return result


def child(unit: dict, suffix: str, **change) -> dict:
    """A smaller unit derived from a parent. Ids are `<parent>.<suffix>`."""
    data = copy.deepcopy(unit)
    data["id"] = f"{unit['id']}.{suffix}"
    data["title"] = f"{unit['title']} ({suffix})"
    data["depends_on"] = list(unit.get("depends_on", []))
    data.update(change)
    return data


def split_by_files(unit: dict, files: list[str]) -> list[dict]:
    """One unit per file the parent may touch. Empty when the parent covers fewer than two files."""
    touched = sorted(expand(unit, files))
    if len(touched) < 2:
        return []
    return [child(unit, str(n), allowed=[f], new_files=[] if f in files else [f],
                  acceptance=copy.deepcopy(unit["acceptance"])) for n, f in enumerate(touched, 1)]


def split_by_criteria(unit: dict) -> list[dict]:
    """One unit per acceptance criterion, chained in order because they share files."""
    criteria = unit["acceptance"].get("criteria", [])
    if len(criteria) < 2:
        return []
    out: list[dict] = []
    for n, text in enumerate(criteria, 1):
        acceptance = copy.deepcopy(unit["acceptance"])
        acceptance["criteria"] = [text]
        deps = list(unit.get("depends_on", [])) + ([out[-1]["id"]] if out else [])
        out.append(child(unit, str(n), goal=f"{unit['goal']} Only this criterion: {text}", acceptance=acceptance,
                         depends_on=deps))
    return out


def check_split(unit: dict, parts: list, files: list[str], pol: dict | None = None) -> list[str]:
    """Problems with a proposed split. Empty means every part is valid and stays inside the parent."""
    if not isinstance(parts, list) or len(parts) < 2:
        return ["a split needs at least two units"]
    if not all(isinstance(p, dict) for p in parts):
        return ["every part must be an object"]
    errors = validate({"plan_id": "split", "goal": unit["goal"], "units": parts}, pol)
    if errors:
        return errors
    parent = expand(unit, files)
    for part in parts:
        if not expand(part, files) <= parent:
            errors.append(f"{part['id']}: touches files outside {unit['id']}")
        if part["id"] == unit["id"]:
            errors.append(f"{part['id']}: reuses the parent id")
    return errors


def split_unit(unit: dict, files: list[str], propose=None, pol: dict | None = None) -> tuple[str, list[dict]]:
    """Split one unit. Tries files, then criteria, then `propose(unit, files)` (the model, injected).

    Returns (method, units). Each candidate is validated and the first valid one wins.
    Returns ("none", []) when nothing valid exists. The input unit is not changed.
    """
    steps = [("files", lambda: split_by_files(unit, files)), ("criteria", lambda: split_by_criteria(unit))]
    if propose is not None:
        steps.append(("model", lambda: propose(copy.deepcopy(unit), list(files))))
    for method, make in steps:
        try:
            parts = make()
        except Exception:
            continue
        if parts and not check_split(unit, parts, files, pol):
            return method, parts
    return "none", []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["validate", "batches"])
    parser.add_argument("plan")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    errors = validate(plan)
    if errors:
        print("\n".join(errors))
        return 1
    if args.command == "batches":
        for number, batch in enumerate(batches(plan, tracked_files(Path(args.repo))), 1):
            print(f"{number}: {' '.join(batch)}")
    else:
        print("valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
