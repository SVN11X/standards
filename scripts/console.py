"""Text output that works in every Windows console and pipe."""
import sys


def safe_output() -> None:
    """Never fail on a character the output cannot hold.

    On Windows a pipe, which is what Claude Code and a PowerShell pipeline read, writes in the ANSI code page
    (cp1252). It has no check mark, arrow or emoji, so a report that quoted one raised UnicodeEncodeError half
    printed. A pipe now gets UTF-8, which those readers decode. A console keeps its own encoding and shows a
    replacement character for what it cannot draw."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if stream.isatty():
                reconfigure(errors="replace")
            else:
                reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
