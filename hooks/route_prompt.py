#!/usr/bin/env python3
"""UserPromptSubmit hook: tell the session what a work request is about before it starts.

It asks the router (scripts/router.py) for a decision: the repository and folder, the recipe, the provider of
each capability on this machine, how the result is verified, what leaves the machine and which permission
the request needs. A question gets no context, so asking stays as fast as before. The hook reads files and
writes one small task record under ~/.standards. It never edits the repository and never blocks a request:
on any error it prints nothing. It routes the owner's words, without the reminders and the wrapper a client
adds around the prompt. It starts one thing, a supervisor pass in the background when the owner says
continúa, sigue or retoma, and that pass only resumes plans already started. What it adds is logged by
context_log.py, and a routing or a recalled note the session already holds is not added again.
"""
import json
import os
import re
import sys
from pathlib import Path


def router_dir() -> Path | None:
    """The scripts folder that holds router.py: the standards checkout, or the copy the plugin ships."""
    candidates = [Path(__file__).resolve().parents[1] / "scripts"]
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / "skills" / "repo-setup" / "standard" / "scripts")
    return next((path for path in candidates if (path / "router.py").is_file()), None)


def own_words(prompt: str) -> str:
    """The owner's own words, without the reminders and the wrapper a client adds around the prompt."""
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", prompt, flags=re.DOTALL)
    lines = text.splitlines()
    background = next((i for i, line in enumerate(lines)
                       if line.strip().startswith("Background (from the session that started this one):")), None)
    if background is not None:
        task = next((i for i, line in enumerate(lines) if i > background and line.strip() == "Task:"), None)
        if task is not None:
            text = "\n".join(lines[task + 1:])
    paragraphs = re.split(r"\n\s*\n", text)
    if paragraphs and paragraphs[-1].strip().startswith("Shared notes folder for this group of sessions"):
        text = "\n\n".join(paragraphs[:-1])
    return text.strip()


def context(data: dict) -> str | None:
    parts = context_parts(data)
    return "\n".join(t for t in (parts.get("router"), parts.get("recall")) if t) or None


def context_parts(data: dict) -> dict:
    """The routing and the recalled notes apart, so each can be left out on its own when the session holds it."""
    prompt = str(data.get("prompt") or "")
    scripts = router_dir()
    if not prompt.strip() or scripts is None:
        return {}
    sys.path.insert(0, str(scripts))
    import repo_fingerprint
    import router
    cwd = Path(data.get("cwd") or os.getcwd())
    # A question needs no context, and a folder outside any repository has nothing to route.
    if router.classify(prompt)[0] == "query" or repo_fingerprint.git(cwd, "rev-parse", "--show-toplevel") is None:
        return {}
    decision = router.decide(prompt, cwd, "claude", session=data.get("session_id"), permission_mode=data.get("permission_mode"))
    limit = int(router.owner_limits(Path(decision["repository"]["root"])).get("max_context_chars", 1800))
    text = router.render(decision, limit) or ""
    if decision["intent"] == "message":
        name = peer_name(data)
        if name is not None:
            text += f" Your name on the peerbox: {name}."
        try:
            import peerbox
            groups = peerbox.groups(peerbox.connect())
            if groups:
                text += " Groups on this machine: " + ", ".join("@" + g for g in groups) + "."
        except Exception:  # noqa: BLE001 (the peerbox is a hint, the request goes on without it)
            pass
    if decision["intent"] in ("work", "review", "publish", "setup"):
        try:
            import recall
            found = recall.lines(Path(decision["repository"]["root"]), prompt)
        except Exception:  # noqa: BLE001 (recall is a hint, the request goes on without it)
            found = []
        if found:
            return {"router": text or None, "recall": "Read before planning (recalled, not the whole history):\n"
                    + "\n".join(found)[:900]}
    return {"router": text or None}


def folder_slug(data: dict) -> str:
    """The folder of this session as a peerbox name: also the name of the group its sessions share."""
    return re.sub(r"[^a-z0-9-]+", "-", Path(data.get("cwd") or os.getcwd()).name.lower()).strip("-")[:30] or "repo"


def peer_name(data: dict) -> str | None:
    """The peerbox name of this session, or None when the client gave no session id."""
    session = str(data.get("session_id") or "")
    if not session:
        return None
    return f"claude-{folder_slug(data)}-{re.sub(r'[^a-z0-9]', '', session.lower())[:6]}"


def inbox(data: dict) -> str | None:
    """Register this session on the peerbox and hand it the messages waiting for it. Never blocks a request."""
    scripts = router_dir()
    if scripts is None or os.environ.get("STANDARDS_NO_PEERBOX"):
        return None
    name = peer_name(data)
    if name is None:
        return None
    folder = folder_slug(data)
    sys.path.insert(0, str(scripts))
    import peerbox
    db = peerbox.connect()
    peerbox.register(db, name, "claude", str(data.get("session_id") or ""))
    peerbox.group(db, folder if len(folder) > 1 else "repo", [name])
    text = peerbox.render(peerbox.pull(db, name))
    return (text + f" Your name on the peerbox: {name}.") if text else None


def resume_plans(data: dict) -> str | None:
    """Start one supervisor pass in the background when the owner asks to go on with started work. Never blocks a request."""
    prompt = str(data.get("prompt") or "")
    scripts = router_dir()
    if scripts is None or not prompt.strip() or os.environ.get("STANDARDS_NO_SUPERVISOR"):
        return None
    sys.path.insert(0, str(scripts))
    import router
    if not router.resumes(prompt):
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import session_probe
    session_probe.recover(scripts / "orchestrate.py")
    return ("A supervisor pass started in the background. It resumes every started plan that has pending work, "
            "no live process and no owner pause, so do not start a second executor for those plans. "
            "Anything new in this message still goes through the session. "
            "`python <standards>/scripts/execute.py status PLAN.json` shows each plan.")


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):  # UTF-8 from Claude Code. A Windows pipe reads cp1252 and PowerShell adds a BOM
        sys.stdin.reconfigure(encoding="utf-8-sig")
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    try:
        data["prompt"] = own_words(str(data.get("prompt") or ""))
    except Exception:  # noqa: BLE001 (fail open, the request must go through)
        pass
    try:
        parts = context_parts(data)
    except Exception:  # noqa: BLE001 (fail open, the request must go through)
        parts = {}
    try:
        messages = inbox(data)
    except Exception:  # noqa: BLE001 (a message never blocks a request)
        messages = None
    try:
        resumed = resume_plans(data)
    except Exception:  # noqa: BLE001 (the supervisor never blocks a request)
        resumed = None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import style
        styled = style.from_prompt(str(data.get("prompt") or ""), str(data.get("session_id") or ""))
    except Exception:  # noqa: BLE001
        styled = None
    blocks = [("style", styled, "always"), ("peerbox", messages, "always"), ("supervisor", resumed, "always"),
              ("router", parts.get("router"), "once"), ("recall", parts.get("recall"), "lines")]
    try:
        import context_log
        sent, row = context_log.select(data, blocks)
        context_log.log(row)
    except Exception:  # noqa: BLE001 (the log never changes what the session gets)
        sent = [text for _, text, _ in blocks if text]
    text = "\n\n".join(t for t in sent if t) or None
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
