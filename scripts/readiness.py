#!/usr/bin/env python3
"""Compute whether a change is ready: link its spec, decisions, tasks and test evidence into one verdict.

The verdict is READY, NEEDS_DECISION or BLOCKED, and the worst signal wins. A critical requirement without a test that
names it blocks the change even when CI is green, because a green suite only says the tests that exist pass. Missing
evidence counts against the change, never for it.
A requirement in docs/specs/<change>/requirements.md is a line that starts with an id: `R1 (critical): WHEN ...`.
A test covers it when the test file contains `<change>/R1`. A decision is linked when plan.md names its record.
The idea comes from Interlock (MIT, https://github.com/renzrollon/interlock). The code here is our own.
Run: python scripts/readiness.py <change> [--repo .] [--ci green|red|unknown]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REQUIREMENT = re.compile(r"^\s*(?:[-*]\s*)?\**(R\d+)\**\s*(\((critical|crítico|critico)\))?\s*[:.]\s*(.+)$", re.I | re.M)
DECISION_LINK = re.compile(r"docs/decisions/(\d{4}-[\w.-]+\.md)")
OPEN_TASK = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+)$", re.M)
ORDER = {"READY": 0, "NEEDS_DECISION": 1, "BLOCKED": 2}


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def test_files(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=False)
    return [n for n in out.stdout.splitlines() if re.search(r"(^|/)tests?/|test_|_test\.|\.test\.|\.spec\.", n)]


def assess(repo: Path, change: str, ci: str = "unknown") -> dict:
    folder = repo / "docs" / "specs" / change
    signals = []

    def add(level: str, what: str) -> None:
        signals.append({"level": level, "what": what})

    requirements = [{"id": m.group(1).upper(), "critical": bool(m.group(2)), "text": m.group(4).strip()}
                    for m in REQUIREMENT.finditer(read(folder / "requirements.md"))]
    if not requirements:
        add("BLOCKED", f"docs/specs/{change}/requirements.md has no requirement with an id such as `R1:`")
    texts = {name: read(repo / name) for name in test_files(repo)}
    for req in requirements:
        tag = f"{change}/{req['id']}"
        covered = sorted(name for name, text in texts.items() if re.search(re.escape(tag) + r"\b", text))
        req["tests"] = covered
        if not covered:
            add("BLOCKED" if req["critical"] else "NEEDS_DECISION",
                f"{tag} {'(critical) ' if req['critical'] else ''}has no test that names it: {req['text'][:90]}")
    for name in sorted(set(DECISION_LINK.findall(read(folder / "plan.md")))):
        status = re.search(r"^-\s*Status:\s*(\w+)", read(repo / "docs" / "decisions" / name), re.I | re.M)
        state = status.group(1).lower() if status else "missing"
        if state != "accepted":
            add("NEEDS_DECISION", f"decision docs/decisions/{name} is {state}, not accepted")
    for task in OPEN_TASK.findall(read(folder / "tasks.md")):
        add("BLOCKED", f"open task: {task.strip()[:90]}")
    if ci == "red":
        add("BLOCKED", "CI is red")
    elif ci != "green":
        add("NEEDS_DECISION", "CI result is unknown")
    verdict = max((s["level"] for s in signals), key=ORDER.get, default="READY")
    return {"change": change, "verdict": verdict, "ci": ci, "requirements": requirements, "signals": signals}


def markdown(result: dict) -> str:
    lines = [f"Readiness of `{result['change']}`: **{result['verdict']}** (CI {result['ci']})."]
    lines += [f"- {s['level']}: {s['what']}" for s in result["signals"]]
    covered = [r for r in result["requirements"] if r.get("tests")]
    if covered:
        lines.append("Covered: " + ", ".join(f"{r['id']} by {', '.join(r['tests'])}" for r in covered))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("change")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--ci", choices=["green", "red", "unknown"], default="unknown")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = assess(args.repo.resolve(), args.change, args.ci)
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else markdown(result))
    return {"READY": 0, "NEEDS_DECISION": 3, "BLOCKED": 4}[result["verdict"]]


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
