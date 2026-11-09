#!/usr/bin/env python3
"""SessionStart hook: tell the session which executors this machine has, in about a second.

It only looks: is OpenCode on the PATH, does the local Ollama answer, which free models the owner
checked, and the privacy class of this folder. It installs nothing, connects to nothing remote and
never blocks the session. Detection is not delegation: the session still runs orchestrate.py route
and orchestrate.py delegate, which do the work and verify it.
"""
import json
import os
import shutil
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autopilot  # noqa: E402


def orchestrate_path() -> Path | None:
    candidates = []
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / "skills" / "repo-setup" / "standard" / "scripts" / "orchestrate.py")
    candidates.append(Path(__file__).resolve().parents[1] / "scripts" / "orchestrate.py")
    return next((path for path in candidates if path.is_file()), None)


def ollama_up(host: str = "127.0.0.1", port: int = 11434) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def owner_facts(repo: Path) -> tuple[str, int]:
    path = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards") / "local.yml"
    if not path.exists():
        return "not set (default personal-private)", 0
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 (the hook never breaks a session)
        return "unknown", 0
    target = str(repo).replace("\\", "/").lower()
    best = ""
    for entry in data.get("folders") or []:
        pattern = str(entry.get("path", "")).replace("\\", "/").lower().rstrip("/*")
        if target.startswith(pattern) and len(pattern) > len(best):
            best = pattern
            cls = entry.get("class")
    return (cls if best else "not set (default personal-private)"), len(data.get("free_models") or [])


def context(cwd: Path) -> str | None:
    root = autopilot.repository_root(cwd)
    if root is None or not (root / ".standard.yml").exists():
        return None
    script = orchestrate_path()
    privacy, free = owner_facts(root)
    parts = [f"OpenCode {'found' if shutil.which('opencode') else 'not installed'}",
             f"Ollama {'answering' if ollama_up() else 'off'}",
             f"free models checked by the owner: {free}", f"privacy of this folder: {privacy}"]
    command = f'python "{script}"' if script else "python <standard>/scripts/orchestrate.py"
    return ("Executors on this machine: " + ", ".join(parts) + ". "
            "Use a program without AI first for search, lint, tests and hashes. Before handing a task to another model, run "
            f"`{command} route <task-type> --repo . --files <n> --risk <green|yellow|red>` and, when it names opencode or "
            f"ollama, `{command} delegate ...`. That command checks the diff, the protected files and the tests itself. "
            "Never treat an executor's own summary as evidence.")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    try:
        text = context(Path(data.get("cwd") or os.getcwd()))
    except Exception:  # noqa: BLE001 (fail open, the session must start)
        text = None
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
