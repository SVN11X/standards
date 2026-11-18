#!/usr/bin/env python3
"""UserPromptSubmit hook: tell the session what a work request is about before it starts.

It asks the router (scripts/router.py) for a decision: the repository and folder, the recipe, the provider of
each capability on this machine, how the result is verified, what leaves the machine and which permission
the request needs. A question gets no context, so asking stays as fast as before. The hook reads files and
writes one small task record under ~/.standards. It never edits the repository and never blocks a request:
on any error it prints nothing. It starts one thing, a supervisor pass in the background when the owner says
continúa, sigue or retoma, and that pass only resumes plans already started.
"""
import json
import os
import sys
from pathlib import Path


def router_dir() -> Path | None:
    """The scripts folder that holds router.py: the standards checkout, or the copy the plugin ships."""
    candidates = [Path(__file__).resolve().parents[1] / "scripts"]
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / "skills" / "repo-setup" / "standard" / "scripts")
    return next((path for path in candidates if (path / "router.py").is_file()), None)


def context(data: dict) -> str | None:
    prompt = str(data.get("prompt") or "")
    scripts = router_dir()
    if not prompt.strip() or scripts is None:
        return None
    sys.path.insert(0, str(scripts))
    import repo_fingerprint
    import router
    cwd = Path(data.get("cwd") or os.getcwd())
    # A question needs no context, and a folder outside any repository has nothing to route.
    if router.classify(prompt)[0] == "query" or repo_fingerprint.git(cwd, "rev-parse", "--show-toplevel") is None:
        return None
    decision = router.decide(prompt, cwd, "claude", session=data.get("session_id"), permission_mode=data.get("permission_mode"))
    limit = int(router.owner_limits(Path(decision["repository"]["root"])).get("max_context_chars", 1800))
    text = router.render(decision, limit) or ""
    if decision["intent"] in ("work", "review", "publish", "setup"):
        try:
            import recall
            found = recall.lines(Path(decision["repository"]["root"]), prompt)
        except Exception:  # noqa: BLE001 (recall is a hint, the request goes on without it)
            found = []
        if found:
            text += "\nRead before planning (recalled, not the whole history):\n" + "\n".join(found)[:900]
    return text or None


def inbox(data: dict) -> str | None:
    """Register this session on the peerbox and hand it the messages waiting for it. Never blocks a request."""
    scripts = router_dir()
    session = str(data.get("session_id") or "")
    if scripts is None or not session or os.environ.get("STANDARDS_NO_PEERBOX"):
        return None
    sys.path.insert(0, str(scripts))
    import re
    import peerbox
    folder = re.sub(r"[^a-z0-9-]+", "-", Path(data.get("cwd") or os.getcwd()).name.lower()).strip("-")[:30] or "repo"
    name = f"claude-{folder}-{re.sub(r'[^a-z0-9]', '', session.lower())[:6]}"
    db = peerbox.connect()
    peerbox.register(db, name, "claude", session)
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
    if hasattr(sys.stdin, "reconfigure"):  # Claude Code sends UTF-8, a Windows pipe would read it as cp1252
        sys.stdin.reconfigure(encoding="utf-8")
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    try:
        text = context(data)
    except Exception:  # noqa: BLE001 (fail open, the request must go through)
        text = None
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
    text = "\n\n".join(t for t in (styled, messages, resumed, text) if t) or None
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
