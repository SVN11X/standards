#!/usr/bin/env python3
"""Notification hook: plays a short sound when Claude Code needs the owner, on any system."""
import subprocess
import sys


def main() -> int:
    sys.stdin.read()
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=5, check=False)
        else:
            sys.stderr.write("\a")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
