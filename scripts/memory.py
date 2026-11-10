#!/usr/bin/env python3
"""Local technical memory: decisions, test results and summaries, searchable with SQLite FTS5.

Commands:
  add      store one entry (kind, text, repository, reference, source)
  search   full-text search, newest first
  list     the latest entries of one repository
  forget   delete one entry by id. To correct an entry, forget it and add the right one
  export   print every entry as JSON lines, to keep or move the memory
  expire   delete agent hints older than a number of days. Facts from the owner and from tools stay

Each entry says where it came from. owner and tool entries are facts with a reference. agent entries
are hints: check them against the files and tests before acting on them. An entry older than 90 days
is marked old, because the code may have changed since. Secrets are refused.
The database lives in STANDARDS_HOME (default ~/.standards/memory.db), outside every repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
try:
    from secret_scan import scan
except ImportError:  # pragma: no cover
    def scan(text: str) -> list[str]:
        return []

KINDS = ("decision", "test", "summary", "capability", "note")
SOURCES = ("owner", "tool", "agent")
SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, repo TEXT, ref TEXT, source TEXT NOT NULL,
  text TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')));
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(text, content='entries', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
"""


def db_path() -> Path:
    root = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")
    root.mkdir(parents=True, exist_ok=True)
    return root / "memory.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or db_path())
    db.executescript(SCHEMA)
    return db


def add(db, kind: str, text: str, repo: str | None = None, ref: str | None = None, source: str = "agent") -> int:
    if kind not in KINDS or source not in SOURCES:
        raise ValueError(f"kind must be one of {KINDS} and source one of {SOURCES}")
    found = scan(text)
    if found:
        raise ValueError(f"refused: the text looks like it holds {', '.join(found)}")
    if source != "agent" and not ref:
        raise ValueError("owner and tool entries need a reference: a file, a commit or a report")
    cursor = db.execute("INSERT INTO entries(kind, repo, ref, source, text) VALUES (?, ?, ?, ?, ?)",
                        (kind, repo, ref, source, text.strip()))
    db.commit()
    return cursor.lastrowid


def search(db, query: str, repo: str | None = None, limit: int = 10) -> list[tuple]:
    terms = " ".join(f'"{word}"' for word in re.findall(r"\w+", query))
    if not terms:
        return []
    sql = ("SELECT e.id, e.kind, e.source, e.repo, e.ref, e.created, e.text FROM entries_fts f "
           "JOIN entries e ON e.id = f.rowid WHERE entries_fts MATCH ?")
    params: list = [terms]
    if repo:
        sql += " AND e.repo = ?"
        params.append(repo)
    sql += " ORDER BY e.id DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


OLD_DAYS = 90


def age_days(created: str) -> int:
    try:
        return (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.datetime.fromisoformat(created)).days
    except ValueError:
        return 0


def expire(db, days: int) -> int:
    """Delete agent hints older than the given days. A hint is never promoted to a fact by staying in the database."""
    cursor = db.execute("DELETE FROM entries WHERE source = 'agent' AND created < datetime('now', ?)", (f"-{int(days)} days",))
    db.commit()
    return cursor.rowcount


def export(db) -> list[dict]:
    names = ("id", "kind", "source", "repo", "ref", "created", "text")
    return [dict(zip(names, row)) for row in db.execute("SELECT id, kind, source, repo, ref, created, text FROM entries ORDER BY id")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("text")
    p.add_argument("--repo")
    p.add_argument("--ref")
    p.add_argument("--source", choices=SOURCES, default="agent")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--repo")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("list")
    p.add_argument("--repo")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("forget")
    p.add_argument("id", type=int)
    sub.add_parser("export")
    p = sub.add_parser("expire")
    p.add_argument("--days", type=int, default=180)
    args = parser.parse_args(argv)
    db = connect()
    if args.command == "add":
        try:
            print(f"stored entry {add(db, args.kind, args.text, args.repo, args.ref, args.source)}")
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        return 0
    if args.command == "forget":
        db.execute("DELETE FROM entries WHERE id = ?", (args.id,))
        db.commit()
        return 0
    if args.command == "export":
        for entry in export(db):
            print(json.dumps(entry, ensure_ascii=False))
        return 0
    if args.command == "expire":
        print(f"deleted {expire(db, args.days)} agent hints older than {args.days} days")
        return 0
    rows = (search(db, args.query, args.repo, args.limit) if args.command == "search" else
            db.execute("SELECT id, kind, source, repo, ref, created, text FROM entries WHERE (? IS NULL OR repo = ?) "
                       "ORDER BY id DESC LIMIT ?", (args.repo, args.repo, args.limit)).fetchall())
    for row in rows:
        label = ("hint" if row[2] == "agent" else row[2]) + (", old: check it against the files" if age_days(row[5]) > OLD_DAYS else "")
        print(f"#{row[0]} {row[1]} [{label}] {row[3] or '-'} {row[4] or '-'} {row[5]}: {row[6][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
