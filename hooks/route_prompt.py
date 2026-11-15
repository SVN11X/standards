#!/usr/bin/env python3
"""UserPromptSubmit hook: tell the session what a work request is about before it starts.

It asks the router (scripts/router.py) for a decision: the repository and folder, the recipe, the provider of
each capability on this machine, how the result is verified, what leaves the machine and which permission
the request needs. A question gets no context, so asking stays as fast as before. The hook reads files and
writes one small task record under ~/.standards. It never edits the repository, never starts a tool and
never blocks a request: on any error it prints nothing.
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
    return router.render(decision, limit) or None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    try:
        text = context(data if isinstance(data, dict) else {})
    except Exception:  # noqa: BLE001 (fail open, the request must go through)
        text = None
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
