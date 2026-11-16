#!/usr/bin/env python3
"""Blocker records: one per stopped action, with the six facts the owner needs to answer "why can't you do it?".

A record names the smallest action a rule really covers, the evidence, what kind of obstacle it is, the approval that
already exists, the work done before stopping and the exact condition that unblocks it. A record with an empty field,
an unknown kind, or an evidence line that was completed from memory is refused, so a vague "blocked" cannot be saved.
Run: python scripts/blockers.py add|list|why|resolve
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrate  # noqa: E402

KINDS = ("owner-rule", "platform-restriction", "technical-requirement", "physical-intervention", "product-decision",
         "agent-precaution")
FIELDS = ("action", "evidence", "kinds", "authorization", "work_done", "unblock")
# A precaution the agent wrote itself carries no authority. It needs the effect it hides, and the isolated check tried first.
NOT_FOUND = "rule not located"


def path_for(plan_id: str) -> Path:
    return orchestrate.home() / "blockers" / f"{plan_id}.json"


def load(plan_id: str) -> list[dict]:
    try:
        return json.loads(path_for(plan_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def validate(row: dict) -> list[str]:
    problems = [f"missing {name}" for name in FIELDS if not row.get(name)]
    kinds = row.get("kinds") or []
    problems += [f"unknown kind {k}" for k in kinds if k not in KINDS]
    action = str(row.get("action") or "")
    if action and len(action.split()) < 4:
        problems.append("action is too general: name the operation, the repository and the object")
    evidence = row.get("evidence") or {}
    if isinstance(evidence, dict) and not (evidence.get("source") and evidence.get("text")) and NOT_FOUND not in str(evidence):
        problems.append("evidence needs a source (file:line, revision or tool answer) and its exact text, or 'rule not located'")
    if "agent-precaution" in kinds and not row.get("hidden_effect"):
        problems.append("an agent precaution must state the real effect it protects and the isolated check tried first")
    return problems


def add(plan_id: str, row: dict) -> dict:
    problems = validate(row)
    if problems:
        raise ValueError("; ".join(problems))
    rows = [r for r in load(plan_id) if r.get("action") != row["action"]]
    saved = {**row, "id": f"b{len(rows) + 1}", "state": "open", "at": orchestrate.now()}
    orchestrate.write_json(path_for(plan_id), [*rows, saved])
    return saved


def resolve(plan_id: str, blocker_id: str, how: str) -> dict:
    rows = load(plan_id)
    for row in rows:
        if row["id"] == blocker_id:
            row.update(state="resolved", resolved_by=how, resolved_at=orchestrate.now())
            orchestrate.write_json(path_for(plan_id), rows)
            return row
    raise KeyError(blocker_id)


def why(plan_id: str) -> str:
    """The answer to the owner's question, grouped so the human decisions come last."""
    rows = [r for r in load(plan_id) if r.get("state") == "open"]
    if not rows:
        return "Nothing is blocked."
    out = []
    for row in rows:
        evidence = row["evidence"]
        shown = evidence if isinstance(evidence, str) else f"{evidence.get('source')}: {evidence.get('text')}"
        out += [f"[{row['id']}] {row['action']}", f"  evidence: {shown}", f"  kind: {', '.join(row['kinds'])}",
                f"  authorization: {row['authorization']}", f"  done: {row['work_done']}", f"  unblocks when: {row['unblock']}"]
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["add", "list", "why", "resolve"])
    parser.add_argument("plan")
    parser.add_argument("--json", help="the record as a JSON object (add) or the blocker id (resolve)")
    parser.add_argument("--how", default="")
    args = parser.parse_args(argv)
    if args.command == "add":
        try:
            print(json.dumps(add(args.plan, json.loads(args.json or "{}")), ensure_ascii=False))
        except ValueError as error:
            print(f"refused: {error}")
            return 1
    elif args.command == "resolve":
        print(json.dumps(resolve(args.plan, args.json or "", args.how), ensure_ascii=False))
    elif args.command == "list":
        print(json.dumps(load(args.plan), ensure_ascii=False, indent=1))
    else:
        print(why(args.plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
