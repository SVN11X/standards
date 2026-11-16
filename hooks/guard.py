#!/usr/bin/env python3
"""PreToolUse hook for Bash commands.

Asks the owner before actions that cannot be undone or that leave the machine (merge, deploy,
force push, mass deletion, publishing secrets), and blocks a git commit while the standard check
of the repository fails. When the owner allowed merges (`orchestrate.py consent --merge when-green`),
a direct `gh pr merge` is turned to scripts/merge_when_green.py, which merges only after every check
passed. The rules live in hooks, so they hold even when the agent forgets them.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
ASK = [
    (r"\bgit\s+push\b[^\n]*\s(--force\b|--force-with-lease\b|-f\b)", "a force push"),
    (r"\bgit\s+reset\s+--hard\b", "discarding local changes with git reset --hard"),
    (r"\bgit\s+clean\s+-[a-z]*f", "deleting untracked files with git clean"),
    (r"\bgit\s+branch\s+-D\b", "deleting a branch that may not be merged"),
    (r"\bgit\s+(filter-branch|filter-repo)\b", "rewriting history"),
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", "a recursive deletion"),
    (r"\bRemove-Item\b[^\n]*-Recurse", "a recursive deletion"),
    (r"\b(rmdir|rd)\s+/s\b|\bdel\s+/s\b", "a recursive deletion"),
    (r"\bwrangler\s+(deploy|publish|secret)\b", "deploying or changing secrets in Cloudflare"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b", "publishing a package"),
    (r"\bgh\s+(repo|release)\s+delete\b", "deleting a repository or release"),
    (r"\bgh\s+secret\s+set\b", "changing a GitHub secret"),
    (r"\b(terraform|tofu)\s+(apply|destroy)\b|\bpulumi\s+(up|destroy)\b", "changing cloud infrastructure"),
    (r"\b(kubectl|helm)\s+(delete|uninstall)\b", "deleting cluster resources"),
    (r"\b(aws|gcloud|az)\b[^\n]*\b(delete|remove|destroy)\b", "deleting cloud resources"),
    (r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", "deleting database data"),
    (r"\bgit\s+push\b[^\n]*\s\+\S", "a force push with a + refspec"),
    (r"\bollama\s+(pull|rm|push|create|cp)\b", "downloading, deleting or publishing a local model"),
    (r"\borchestrate\.py\b[^\n]*\b(consent|merge-opencode)\b", "changing what may leave the machine or the global OpenCode config"),
    (r"\b(npm|pnpm|yarn)\s+(i|install|add)\b[^\n]*\s(-g|--global)\b", "a global package install"),
    (r"\b(winget|choco|scoop)\s+install\b", "installing software on the machine"),
]
COMMIT = re.compile(r"\bgit\s+commit\b")


def find_standard_script() -> Path | None:
    override = os.environ.get("STANDARD_PY")
    candidates = [Path(override)] if override else []
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / "skills" / "repo-setup" / "standard" / "scripts" / "standard.py")
    return next((path for path in candidates if path.is_file()), None)


def repository_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def commit_gate(cwd: Path) -> str | None:
    """Return the reason to block a commit, or None to let it through."""
    root = repository_root(cwd)
    script = find_standard_script()
    if root is None or script is None or not (root / ".standard.yml").exists():
        return None
    try:
        result = subprocess.run([sys.executable, str(script), "check", str(root)], capture_output=True,
                                text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0:
        return None
    if "PyYAML is required" in (result.stdout + result.stderr):
        return None
    errors = [line for line in result.stdout.splitlines() if line.startswith("ERROR")][:10]
    return ("The standard check fails, so this commit is blocked. Fix these first:\n" + "\n".join(errors))


def merge_script() -> Path | None:
    """merge_when_green.py from the standards checkout or from the copy the plugin ships."""
    candidates = [Path(__file__).resolve().parents[1] / "scripts"]
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        candidates.append(Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "skills" / "repo-setup" / "standard" / "scripts")
    return next((c / "merge_when_green.py" for c in candidates if (c / "merge_when_green.py").is_file()), None)


def merge_decision(command: str) -> dict:
    """A direct merge asks the owner. With the owner's setting when-green it goes through the checked merge instead."""
    script = merge_script()
    setting = "ask"
    if script is not None:
        sys.path.insert(0, str(script.parent))
        try:
            import merge_when_green
            setting = merge_when_green.owner_setting()
        except Exception:  # noqa: BLE001 (a broken tool keeps the merge with the owner)
            setting = "ask"
    if setting == "when-green" and not re.search(r"--admin\b", command):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": (
                                           "The owner allows merges once every check passed. Merge with "
                                           f'python "{script}" <PR> --wait 1800, which checks that first and never bypasses the rules.')}}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                   "permissionDecisionReason": "This is merging a pull request. The owner decides."}}


def decide(data: dict) -> dict | None:
    command = (data.get("tool_input") or {}).get("command") or ""
    if MERGE.search(command):
        return merge_decision(command)
    for pattern, what in ASK:
        if re.search(pattern, command, re.IGNORECASE):
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                           "permissionDecisionReason": f"This is {what}. The owner decides."}}
    if COMMIT.search(command):
        reason = commit_gate(Path(data.get("cwd") or os.getcwd()))
        if reason:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
    return None


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
