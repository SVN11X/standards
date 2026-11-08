#!/usr/bin/env python3
"""PostToolUse hook for file writes: stops the agent when a written file contains a credential."""
import json
import re
import sys
from pathlib import Path

PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "an AWS access key"),
    (r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}", "a GitHub token"),
    (r"sk-ant-[A-Za-z0-9_-]{20,}", "an Anthropic API key"),
    (r"sk-(proj-)?[A-Za-z0-9]{32,}", "an OpenAI API key"),
    (r"gsk_[A-Za-z0-9]{40,}", "a Groq API key"),
    (r"AIza[0-9A-Za-z_-]{35}", "a Google API key"),
    (r"xox[abprs]-[A-Za-z0-9-]{10,}", "a Slack token"),
    (r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "a private key"),
    (r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]", "a hard-coded secret"),
]
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".woff", ".woff2", ".ico", ".lock"}


def scan(text: str) -> list[str]:
    return sorted({label for pattern, label in PATTERNS if re.search(pattern, text)})


def decide(data: dict) -> dict | None:
    path = Path((data.get("tool_input") or {}).get("file_path") or "")
    if not path.name or path.suffix.lower() in SKIP_SUFFIXES or path.name == ".env.example":
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    found = scan(text)
    if not found:
        return None
    return {"decision": "block",
            "reason": (f"{path.name} now contains {', '.join(found)}. Remove it from the file and read it from "
                       "an environment variable or a secret store instead. If it was a real credential, "
                       "tell the owner to rotate it.")}


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
