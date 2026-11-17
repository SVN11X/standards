#!/usr/bin/env python3
"""PostToolUse hook: tells a Claude Code session when another session changed a file it has read.

Every Read, Write, Edit, MultiEdit and NotebookEdit is recorded in a small SQLite database under
$STANDARDS_HOME (default ~/.standards). After each tool call the hook looks for edits by other sessions on files
this session read earlier and adds one line per file to the context. Files are matched across git worktrees of one
repository by their path inside the checkout.

The idea comes from the swarm of jcode (MIT, https://github.com/1jehuang/jcode): when one agent edits a file that
another agent has read, the other agent is notified. This is own code, written for sessions on one machine.
Nothing leaves the machine. STANDARDS_SHIFT_NOTICE=0 turns the hook off. On any error it prints nothing.
"""
import contextlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

READ_TOOLS = {"Read"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
MAX_AGE = 24 * 3600
MAX_LINES = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS reads(session TEXT, key TEXT, path TEXT, at REAL, PRIMARY KEY(session, key));
CREATE TABLE IF NOT EXISTS changes(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, path TEXT, session TEXT,
                                   worktree TEXT, at REAL);
CREATE TABLE IF NOT EXISTS delivered(session TEXT, change_id INTEGER, PRIMARY KEY(session, change_id));
"""


def db_path() -> Path:
    home = os.environ.get("STANDARDS_HOME")
    return (Path(home) if home else Path.home() / ".standards") / "shift.db"


def find_checkout(path: Path) -> tuple[Path, Path] | None:
    for folder in path.parents:
        marker = folder / ".git"
        if marker.is_dir():
            return folder, marker
        if marker.is_file():
            first = marker.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[:1]
            if first and first[0].startswith("gitdir:"):
                gitdir = Path(first[0][len("gitdir:"):].strip())
                if not gitdir.is_absolute():
                    gitdir = folder / gitdir
                for candidate in (gitdir, *gitdir.parents):
                    if candidate.parent.name == "worktrees":
                        return folder, candidate.parent.parent
                return folder, gitdir
    return None


def file_key(path: Path) -> tuple[str, str | None]:
    found = find_checkout(path)
    if found is None:
        key, root = str(path), None
    else:
        root, common = found
        key, root = f"{common}|{path.relative_to(root).as_posix()}", str(root)
    return (key.lower() if os.name == "nt" else key), root


def target(event: dict) -> Path | None:
    tool_input = event.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(event.get("cwd") or ".") / path
    return path.resolve()


def same_tree(a: str | None, b: str | None) -> bool:
    return a == b or (a is not None and b is not None and os.path.normcase(a) == os.path.normcase(b))


def notices(db: sqlite3.Connection, session: str) -> list[str]:
    rows = db.execute(
        "SELECT c.id, r.path, c.session, c.worktree, c.at FROM changes c JOIN reads r ON r.key = c.key "
        "WHERE r.session = ? AND c.session != ? AND c.at > r.at "
        "AND NOT EXISTS (SELECT 1 FROM delivered d WHERE d.session = ? AND d.change_id = c.id) "
        "ORDER BY c.at", (session, session, session)).fetchall()
    latest = {}
    for row in rows:
        latest[row[1], row[2]] = row
    lines = []
    for _, path, other, worktree, at in latest.values():
        _, mine = file_key(Path(path))
        where = ("in this working tree" if same_tree(mine, worktree) else
                 "in another worktree of this repository, expect a conflict when both are integrated")
        lines.append(f"File {path} changed under you: session {other[:8]} edited it at "
                     f"{datetime.fromtimestamp(at):%H:%M} {where}. Read its diff before relying on what you read.")
    db.executemany("INSERT OR IGNORE INTO delivered VALUES (?, ?)", [(session, row[0]) for row in rows])
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"and {len(lines) - MAX_LINES} more"]
    return lines


def handle(event: dict) -> dict | None:
    tool = event.get("tool_name")
    session = str(event.get("session_id") or "")
    if not session or tool not in READ_TOOLS | WRITE_TOOLS:
        return None
    path = target(event)
    if path is None:
        return None
    now = time.time()
    key, root = file_key(path)
    path_db = db_path()
    path_db.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path_db, timeout=5)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        db.execute("DELETE FROM reads WHERE at < ?", (now - MAX_AGE,))
        db.execute("DELETE FROM changes WHERE at < ?", (now - MAX_AGE,))
        db.execute("DELETE FROM delivered WHERE change_id NOT IN (SELECT id FROM changes)")
        if tool in WRITE_TOOLS:
            db.execute("INSERT INTO changes(key, path, session, worktree, at) VALUES (?, ?, ?, ?, ?)",
                       (key, str(path), session, root, now))
        db.execute("INSERT OR REPLACE INTO reads VALUES (?, ?, ?, ?)", (session, key, str(path), now))
        lines = notices(db, session)
        db.commit()
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(lines)}}


def main(stdin_text: str | None = None) -> int:
    if os.environ.get("STANDARDS_SHIFT_NOTICE") == "0":
        return 0
    try:
        event = json.loads(sys.stdin.read() if stdin_text is None else stdin_text)
        output = handle(event) if isinstance(event, dict) else None
        if output:
            print(json.dumps(output))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
