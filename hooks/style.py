"""The direct answer style the hooks add: action first, numbered steps, one next action, visible progress.

It is on unless the owner set `style: off` in ~/.standards/local.yml or said "modo normal" in the session. That choice
is saved per session, so it survives a compaction. The rules never touch JSON, commands or other output a tool reads.
The rules follow i-have-adhd (MIT, https://github.com/ayghri/i-have-adhd), in our own words.
"""
import json
import os
import re
from pathlib import Path

RULES = ("Direct answer style (the owner's choice, off with \"modo normal\"): "
         "1. The first line is the result or the next action. "
         "2. Number steps that must be done in order. "
         "3. End with one concrete next action when there is one. "
         "4. Say what is done and what is left, so progress is visible. "
         "5. Give time in minutes or hours, never \"a bit\". "
         "6. At most 5 items in a list. "
         "7. No preamble, no recap, no closing offers. "
         "Break these rules when the owner asks to explain or for detail (then explain fully, with headings), "
         "before a destructive action (confirm first), and after three failed attempts at the same fix (name the "
         "assumption that may be wrong and ask one question). Never reshape JSON, commands or any output a tool reads.")
OFF = re.compile(r"\b(modo normal|normal mode|stop (?:adhd|direct) mode|desactiva el modo directo|sin modo directo)\b", re.I)
ON = re.compile(r"\b(modo directo|direct mode|activa el modo directo)\b", re.I)
DEEP = re.compile(r"^\s*(explícame|explicame|explica|explain|walk me through|cuéntame en detalle)\b|\b(en detalle|a fondo|in depth|in detail)\b", re.I)


def home() -> Path:
    return Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")


def session_file(session: str) -> Path:
    return home() / "style" / (re.sub(r"[^\w-]", "", session or "session") + ".json")


def owner_default() -> bool:
    path = home() / "local.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    found = re.search(r"^style:\s*(\w+)", text, re.M)
    return not (found and found.group(1).lower() in ("off", "normal", "none"))


def enabled(session: str) -> bool:
    try:
        return bool(json.loads(session_file(session).read_text(encoding="utf-8"))["on"])
    except (OSError, ValueError, KeyError):
        return owner_default()


def from_prompt(prompt: str, session: str) -> str | None:
    """A switch in the prompt is saved for the session. Returns the line the session should read, or None."""
    text = prompt or ""
    wish = False if OFF.search(text) else True if ON.search(text) else None
    if wish is not None:
        path = session_file(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"on": wish}), encoding="utf-8")
        return ("Direct answer style is on for this session. " + RULES) if wish else \
            "Direct answer style is off for this session: answer in your default style. Confirm it in one line."
    if enabled(session) and DEEP.search(text):
        return "The owner asked for depth: explain fully this turn, with headings, and still no preamble or closing offers."
    return None


def startup_lines(session: str) -> str | None:
    return RULES if enabled(session) else None
