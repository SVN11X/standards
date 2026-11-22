#!/usr/bin/env python3
"""What the hooks add to a session's context, block by block, and what the session already holds.

A block the session received unchanged earlier is replaced by one short line until the conversation is compacted,
because the earlier copy is still in the context. Recalled notes are sent line by line, so a follow-up adds only
the notes the session has not seen. A compaction drops the earlier copies, so reinject.py forgets the session, and
an entry older than MAX_AGE_H is sent again whatever happened. A session is told apart by its id and its
transcript, so a cleared conversation starts empty.

Every injection appends one line to context.jsonl under STANDARDS_HOME: the hook, each block's size, and the
characters left out because the session held them. Characters are counted, not tokens.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

MAX_AGE_H = 6


def home() -> Path:
    return Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def session_key(data: dict) -> str | None:
    session = str(data.get("session_id") or "")
    if not session:
        return None
    transcript = str(data.get("transcript_path") or "")
    return re.sub(r"[^\w-]", "", session)[:40] + "-" + hashlib.sha256(transcript.encode()).hexdigest()[:8]


def state_path(key: str) -> Path:
    return home() / "context" / f"{key}.json"


def digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def held(key: str | None) -> dict:
    if not key:
        return {}
    try:
        data = json.loads(state_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    limit = now() - dt.timedelta(hours=MAX_AGE_H)
    fresh = {}
    for name, stamp in (data.get("held") or {}).items():
        try:
            if dt.datetime.fromisoformat(stamp) >= limit:
                fresh[name] = stamp
        except (TypeError, ValueError):
            continue
    return fresh


def save(key: str | None, entries: dict) -> None:
    if not key:
        return
    path = state_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"held": entries}), encoding="utf-8")


def forget(data: dict) -> None:
    """After a compaction the earlier copies are gone, so everything is sent again."""
    key = session_key(data)
    if key:
        state_path(key).unlink(missing_ok=True)


def select(data: dict, blocks: list[tuple[str, str | None, str]]) -> tuple[list[str], dict]:
    """`blocks` are (name, text, mode). Mode `always` is sent every time, `once` is replaced by a short line when
    the session holds it, and `lines` sends only the lines the session has not seen. Returns the texts to send
    and the log row."""
    key = session_key(data)
    entries = held(key)
    stamp = now().replace(microsecond=0).isoformat()
    out, sizes, skipped = [], {}, 0
    for name, text, mode in blocks:
        if not text:
            continue
        if mode == "once" and key:
            mark = f"{name}:{digest(text)}"
            if mark in entries:
                note = f"({name}: unchanged since an earlier message of this session, still above.)"
                out.append(note)
                sizes[name] = len(note)
                skipped += len(text) - len(note)
                continue
            entries[mark] = stamp
        elif mode == "lines" and key:
            # A line ending in a colon is a heading: it is sent with new lines under it and never on its own.
            kept = []
            for line in text.splitlines():
                mark = f"{name}:{digest(line)}"
                if line.strip() and not line.rstrip().endswith(":") and mark in entries:
                    continue
                entries.setdefault(mark, stamp)
                kept.append(line)
            new = "\n".join(kept) if any(line.strip() and not line.rstrip().endswith(":") for line in kept) else ""
            skipped += len(text) - len(new)
            text = new
            if not text:
                continue
        out.append(text)
        sizes[name] = len(text)
    try:
        save(key, entries)
    except OSError:
        pass
    row = {"date": stamp, "session": key, "hook": data.get("hook_event_name") or "UserPromptSubmit",
           "blocks": sizes, "sent_chars": sum(sizes.values()), "skipped_chars": max(skipped, 0)}
    return out, row


def log(row: dict) -> None:
    try:
        path = home() / "context.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass


def summary(path: Path | None = None) -> dict:
    """Injections, characters sent and characters left out, in total and per block."""
    path = path or home() / "context.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    total = {"injections": 0, "sent_chars": 0, "skipped_chars": 0, "blocks": {}}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        total["injections"] += 1
        total["sent_chars"] += int(row.get("sent_chars") or 0)
        total["skipped_chars"] += int(row.get("skipped_chars") or 0)
        for name, size in (row.get("blocks") or {}).items():
            item = total["blocks"].setdefault(name, {"count": 0, "chars": 0})
            item["count"] += 1
            item["chars"] += int(size or 0)
    return total
