#!/usr/bin/env python3
"""SessionStart hook after compaction: puts the repository's key rules and plan status back in context."""
import json
import os
import re
import sys
from pathlib import Path

SECTIONS = ("How to work", "Traffic light", "When sources disagree (highest first)")


def repository_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def sections(text: str, wanted: tuple[str, ...]) -> list[str]:
    found, current = [], None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1) if heading.group(1) in wanted else None
            if current:
                found.append(line)
            continue
        if current and line.strip():
            found.append(line)
    return found


def context(cwd: Path) -> str | None:
    root = repository_root(cwd)
    if root is None or not (root / "AGENTS.md").exists():
        return None
    agents = (root / "AGENTS.md").read_text(encoding="utf-8", errors="ignore")
    lines = ["The conversation was compacted. These rules from AGENTS.md still apply. Read the whole file again before the next change."]
    lines += sections(agents, SECTIONS)
    plan = root / "docs" / "improvement-plan.md"
    if plan.exists():
        text = plan.read_text(encoding="utf-8", errors="ignore")
        pending = re.findall(r"^\s*[-*]\s+\[ \]\s+(?!BLOCKED)(.+)$", text, re.MULTILINE)
        lines.append(f"Improvement plan: {len(pending)} pending items." + (f" Next: {pending[0][:200]}" if pending else ""))
    if (root / ".git" / "standard-autopilot").exists():
        lines.append("Autopilot is on. Keep working through the plan.")
    return "\n".join(lines)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    text = context(Path(data.get("cwd") or os.getcwd()))
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
