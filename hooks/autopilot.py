#!/usr/bin/env python3
"""Stop hook: while autopilot is on, keep the session working through docs/improvement-plan.md.

Autopilot is on when the file standard-autopilot exists in the git folder of the worktree, the path
that `git rev-parse --git-path standard-autopilot` prints (.git/standard-autopilot in a normal clone).
Pending items are "- [ ]" lines that are not marked BLOCKED. The hook lets the session stop when nothing is pending, or when two stops in a row
happen without any change to the plan, so a stuck session never loops forever.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PENDING = re.compile(r"^\s*[-*]\s+\[ \]\s+(?!BLOCKED)", re.IGNORECASE | re.MULTILINE)
MAX_STALLS = 2


def git_paths(start: Path) -> tuple[Path, Path] | None:
    """The worktree root and its own git folder. In a linked worktree .git is a file, not a folder."""
    try:
        out = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel", "--absolute-git-dir"],
                             capture_output=True, text=True, timeout=5, check=False)
        lines = out.stdout.splitlines()
        if out.returncode == 0 and len(lines) == 2:
            return Path(lines[0]), Path(lines[1])
    except (OSError, subprocess.TimeoutExpired):
        pass
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            return candidate, marker
        if marker.is_file():
            text = marker.read_text(encoding="utf-8", errors="ignore").strip()
            if text.startswith("gitdir:"):
                gitdir = Path(text[len("gitdir:"):].strip())
                return candidate, (gitdir if gitdir.is_absolute() else candidate / gitdir).resolve()
    return None


def repository_root(start: Path) -> Path | None:
    paths = git_paths(start)
    return paths[0] if paths else None


def marker_path(start: Path) -> Path | None:
    """Where the autopilot switch lives: `git rev-parse --git-path standard-autopilot`."""
    paths = git_paths(start)
    return paths[1] / "standard-autopilot" if paths else None


def decide(data: dict) -> dict | None:
    paths = git_paths(Path(data.get("cwd") or os.getcwd()))
    if paths is None:
        return None
    root, gitdir = paths
    plan = root / "docs" / "improvement-plan.md"
    if not (gitdir / "standard-autopilot").exists() or not plan.exists():
        return None
    text = plan.read_text(encoding="utf-8", errors="ignore")
    pending = len(PENDING.findall(text))
    if pending == 0:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    session = re.sub(r"[^\w-]", "", str(data.get("session_id") or "session"))
    state_file = Path(tempfile.gettempdir()) / f"standard-autopilot-{session}.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    stalls = state.get("stalls", 0) + 1 if state.get("digest") == digest else 0
    state_file.write_text(json.dumps({"digest": digest, "stalls": stalls}), encoding="utf-8")
    if stalls >= MAX_STALLS:
        return None
    return {"decision": "block",
            "reason": (f"Autopilot is on and docs/improvement-plan.md has {pending} pending items. "
                       "Continue with the next one: change it, run the check, commit, push and update the plan. "
                       "If an item needs the owner, mark it '- [ ] BLOCKED: <question>' and move on. "
                       f'When nothing is pending, delete {gitdir / "standard-autopilot"} and give one final summary '
                       "with every BLOCKED question.")}


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    decision = decide(data)
    if decision:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
