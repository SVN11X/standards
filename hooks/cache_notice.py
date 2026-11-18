#!/usr/bin/env python3
"""Stop and UserPromptSubmit hook that names the likely reason of a prompt cache miss.

`stop` compares the cache use the provider reported for the last request with the prompt of the request before it.
When at least 1024 tokens were written again, it prints a systemMessage with the likely reason and appends one line
to cache-misses.jsonl in STANDARDS_HOME (default ~/.standards). `prompt` warns when the last answer is older than
the cache lifetime, so the next answer will write the prompt again. The lifetime is STANDARDS_CACHE_TTL_MIN minutes
when set, else one hour when recent answers wrote one hour cache entries, else 5 minutes.

The idea and the miss classes come from the KV cache monitor of jcode (MIT, Jeremy Huang,
https://github.com/1jehuang/jcode, crates/jcode-base/src/kv_cache_monitor.rs). This is own code.

It only reads the local transcript. Nothing leaves the machine. A miss is an estimate from the reported usage,
not a guarantee. Any error prints nothing and exits 0, so the hook never blocks a turn.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_MISSED_TOKENS = 1024
TAIL_BYTES = 2 * 1024 * 1024
DEFAULT_TTL_MIN = 5.0


ONE_HOUR_TTL_MIN = 60.0


def ttl_minutes() -> float | None:
    """The lifetime the owner set, or None to read it from the transcript."""
    try:
        value = float(os.environ.get("STANDARDS_CACHE_TTL_MIN", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def effective_ttl(requests: list[dict], ttl: float | None) -> float:
    """The owner's value, else 60 minutes when recent requests wrote one hour cache entries, else 5.

    Claude Code can ask for a one hour cache, and the usage says so in cache_creation.ephemeral_1h_input_tokens.
    A fixed 5 minutes would call such a cache cold while it is still warm."""
    if ttl:
        return ttl
    return ONE_HOUR_TTL_MIN if any(r.get("one_hour") for r in requests[-5:]) else DEFAULT_TTL_MIN


def read_tail(path: Path) -> list[str]:
    with open(path, "rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - TAIL_BYTES))
        raw = handle.read()
    return raw.decode("utf-8", errors="ignore").splitlines()


def parse_time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def token_count(usage: dict, key: str) -> int:
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def load_requests(path: Path) -> list[dict]:
    """One record per requestId, in order, with whether a compaction came right before it."""
    requests: list[dict] = []
    index: dict[str, int] = {}
    compacted = False
    for line in read_tail(path):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("isCompactSummary") is True or (
            entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"
        ):
            compacted = True
            continue
        message = entry.get("message")
        if entry.get("type") != "assistant" or entry.get("isSidechain") is True or not isinstance(message, dict):
            continue
        usage = message.get("usage")
        at = parse_time(entry.get("timestamp"))
        if not isinstance(usage, dict) or at is None:
            continue
        record = {
            "at": at,
            "model": message.get("model"),
            "input": token_count(usage, "input_tokens"),
            "created": token_count(usage, "cache_creation_input_tokens"),
            "read": token_count(usage, "cache_read_input_tokens"),
            "compacted": compacted,
            "one_hour": isinstance(usage.get("cache_creation"), dict)
            and token_count(usage["cache_creation"], "ephemeral_1h_input_tokens") > 0,
        }
        # Claude Code writes messages of its own, such as a usage limit notice, with the model "<synthetic>" and no
        # usage. They never reached the provider, so they are not requests.
        if record["model"] == "<synthetic>" or not (record["input"] or record["created"] or record["read"]):
            continue
        compacted = False
        request_id = entry.get("requestId")
        if isinstance(request_id, str) and request_id in index:
            old = requests[index[request_id]]
            record["compacted"] = record["compacted"] or old["compacted"]
            requests[index[request_id]] = record
            continue
        if isinstance(request_id, str):
            index[request_id] = len(requests)
        requests.append(record)
    return requests


def prompt_size(request: dict) -> int:
    return request["input"] + request["created"] + request["read"]


def reason_for(before: dict, last: dict, ttl: float) -> str:
    if before["model"] != last["model"]:
        return "the model changed"
    if last["compacted"]:
        return "a compaction rewrote the context"
    if before["at"].date() != last["at"].date():
        return "the UTC date changed, which drops Anthropic's cache"
    gap = (last["at"] - before["at"]).total_seconds() / 60
    if gap > ttl:
        return f"the cache expired after {int(gap)} minutes idle"
    return "unexplained: the start of the prompt changed"


def check_miss(requests: list[dict], ttl: float) -> dict | None:
    if len(requests) < 2:
        return None
    before, last = requests[-2], requests[-1]
    missed = prompt_size(before) - last["read"]
    if missed < MIN_MISSED_TOKENS:
        return None
    return {"missed": missed, "reason": reason_for(before, last, ttl), "model": last["model"], "at": last["at"]}


def log_path() -> Path:
    return Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards") / "cache-misses.jsonl"


def stop_message(path: Path, session: str, ttl: float | None) -> str | None:
    requests = load_requests(path)
    miss = check_miss(requests, effective_ttl(requests, ttl))
    if miss is None:
        return None
    row = {
        "at": miss["at"].isoformat(),
        "session": session,
        "missed": miss["missed"],
        "reason": miss["reason"],
        "model": miss["model"],
    }
    try:
        target = log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return f"Prompt cache miss: {miss['missed']:,} tokens written again, likely because {miss['reason']}."


def prompt_message(path: Path, ttl: float | None, now: datetime | None = None) -> str | None:
    requests = load_requests(path)
    if len(requests) < 2:
        return None
    last = requests[-1]
    idle = ((now or datetime.now(timezone.utc)) - last["at"]).total_seconds() / 60
    if idle <= effective_ttl(requests, ttl):
        return None
    return (
        f"The prompt cache is likely cold: {int(idle)} minutes since the last answer, "
        f"so the next answer writes about {prompt_size(last):,} tokens again."
    )


def main(argv: list[str]) -> int:
    try:
        mode = argv[1] if len(argv) > 1 else ""
        if hasattr(sys.stdin, "reconfigure"):  # UTF-8 from Claude Code. A Windows pipe reads cp1252 and PowerShell adds a BOM
            sys.stdin.reconfigure(encoding="utf-8-sig")
        data = json.load(sys.stdin)
        path = Path(data.get("transcript_path") or "")
        if mode not in ("stop", "prompt") or not path.is_file():
            return 0
        ttl = ttl_minutes()
        if mode == "stop":
            text = stop_message(path, str(data.get("session_id") or ""), ttl)
        else:
            text = prompt_message(path, ttl)
        if text:
            print(json.dumps({"systemMessage": text}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
