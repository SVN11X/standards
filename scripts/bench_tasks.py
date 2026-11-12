#!/usr/bin/env python3
"""Synthetic bench tasks and the code that grades them. A program decides every result here, never a model.

Chat tasks send short prompts and check the reply: classify, extract, summarize, web-subprofile, tool-call,
vision and design-judge. Agent tasks give a coding agent a small repository and check it with acceptance
tests the agent never saw: fix-bug, fix-multi, docs-small and refactor-module (its hidden tests include an `ast` check). scripts/orchestrate.py runs them.
"""
from __future__ import annotations

import base64
import os
import re
import struct
import zlib
from pathlib import Path

import yaml

STANDARD_ROOT = Path(__file__).resolve().parents[1]
SUBPROFILES = STANDARD_ROOT / "profiles" / "web" / "subprofiles.yml"
PASS_ACCURACY = 0.75
# What a model must be able to do for a chat task. Tasks with a baseline also run on a program without AI.
CHAT_TASKS = {"classify": [], "extract": [], "summarize": [], "web-subprofile": [], "tool-call": ["tools"],
              "vision": ["vision"], "design-judge": ["vision"],
              "review-diff": [], "decompose": []}
BASELINES = {"classify", "extract", "web-subprofile"}
# Version of the rule that grades each task. Raise it when a grader changes what it accepts: runs graded by an older
# rule stay in the history and stop counting. A task that is not listed is at version 1.
GRADERS = {"summarize": 3, "tool-call": 2, "refactor-module": 1, "review-diff": 1, "decompose": 1}


def grader_version(task: str | None) -> int:
    return GRADERS.get(str(task), 1)


class OutOfTime(Exception):
    """The time limit of one bench run is used up. The items left count as failures."""


# classify

CLASSIFY = [("The app crashes when I upload a PNG", "bug"), ("Add a dark mode toggle", "feature"),
            ("Fix the typo in the install guide", "docs"), ("Login fails with a 500 error", "bug"),
            ("Support exporting to CSV", "feature"), ("Explain the config options in the README", "docs"),
            ("Search returns duplicate results", "bug"), ("Allow sorting the table by date", "feature"),
            ("Document the API rate limits", "docs"), ("The page is blank on Safari", "bug"),
            ("Add keyboard shortcuts", "feature"), ("Update the screenshots in the tutorial", "docs")]
KEYWORDS = {"bug": ("crash", "fail", "error", "blank", "duplicate", "broken"),
            "docs": ("readme", "guide", "document", "typo", "tutorial", "explain"),
            "feature": ("add", "support", "allow")}


def keyword_label(text: str) -> str:
    low = text.lower()
    for label in ("bug", "docs", "feature"):
        if any(word in low for word in KEYWORDS[label]):
            return label
    return "feature"


# extract

EXTRACT = [("2026-03-14 09:12:55 ERROR payment-api Timeout after 30s calling ledger",
            {"date": "2026-03-14", "level": "ERROR", "service": "payment-api", "seconds": 30}),
           ("2026-03-14 09:13:02 WARN auth-gateway Retry 2 took 4s",
            {"date": "2026-03-14", "level": "WARN", "service": "auth-gateway", "seconds": 4}),
           ("2025-12-01 23:59:59 INFO report-builder Finished in 187s",
            {"date": "2025-12-01", "level": "INFO", "service": "report-builder", "seconds": 187}),
           ("2026-01-09 07:00:11 ERROR image-resizer Gave up after 12s waiting for storage",
            {"date": "2026-01-09", "level": "ERROR", "service": "image-resizer", "seconds": 12}),
           ("2026-07-22 16:45:30 WARN search-indexer Slow batch of 5000 documents, 61s",
            {"date": "2026-07-22", "level": "WARN", "service": "search-indexer", "seconds": 61}),
           ("2026-02-28 03:03:03 INFO backup-runner Completed 3 volumes in 240s",
            {"date": "2026-02-28", "level": "INFO", "service": "backup-runner", "seconds": 240})]
EXTRACT_PROMPT = ('Extract a JSON object from this log line with exactly these keys: "date" (YYYY-MM-DD), "level", '
                  '"service" and "seconds" (the duration, as a number).\nLine: ')


def extract_baseline(line: str) -> dict:
    parts = line.split()
    seconds = re.findall(r"\b(\d+)s\b", line)
    return {"date": parts[0], "level": parts[2], "service": parts[3], "seconds": int(seconds[-1]) if seconds else None}


def extract_ok(expected: dict, parsed) -> bool:
    if not isinstance(parsed, dict):
        return False
    try:
        seconds = int(float(parsed.get("seconds")))
    except (TypeError, ValueError):
        return False
    return (str(parsed.get("date")) == expected["date"] and str(parsed.get("level", "")).upper() == expected["level"]
            and str(parsed.get("service")) == expected["service"] and seconds == expected["seconds"])


# summarize

SUMMARIZE = [
    {"text": "To work on two branches at once without stashing, add a linked worktree: `git worktree add ../hotfix -b hotfix main` "
             "creates the folder ../hotfix on a new branch hotfix from main. List them with `git worktree list`. When the work "
             "is merged, delete the folder with `git worktree remove ../hotfix` and clean stale records with `git worktree prune`. "
             "A branch can be checked out in only one worktree at a time.",
     "facts": [["worktree"]]},
    {"text": "Ollama keeps a model in memory for five minutes after the last request. `ollama ps` shows the loaded models and how "
             "much of each runs on the GPU. A model that does not fit in VRAM is split with the CPU and answers several times "
             "slower. `ollama stop qwen3.5:9b` unloads a model at once. Nothing here downloads a model: that is `ollama pull`, "
             "which needs the owner's approval.",
     "facts": [["gpu", "vram", "memory", "loaded"]]},
    {"text": "Create an isolated environment with `python -m venv .venv`, activate it, then install the pinned dependencies with "
             "`pip install -r requirements.txt`. Run the tests with `python -m unittest discover -s tests`. Never install "
             "packages globally with sudo.",
     "facts": [["environment", "venv", "dependenc"]]},
]
SUMMARIZE_PROMPT = ("Summarize the text for a teammate in at most three sentences. Mention only commands that appear in the text, "
                    'exactly as written. Answer JSON {"summary": "...", "commands": ["..."]}.\nText: ')
COMMAND_SHAPE = re.compile(r"\b(?:git|ollama|pip|npm|docker)\s+[a-z][\w-]*\s+(?:--?[\w-]+|\.\.?/\S+)")


def squeeze(text: str) -> str:
    """One spacing and no quoting marks, so a command a model wrapped in quotes or backticks still matches the text."""
    return " ".join(re.sub(r"[`\"'\u201c\u201d\u2018\u2019]", " ", str(text)).split())


def summarize_ok(item: dict, parsed) -> tuple[bool, str]:
    """A summary passes when it has the right shape, names no command that is not in the text and stays on the subject.

    The subject check is one word group per text on purpose. A short summary may leave a detail out, and asking for
    several exact words failed correct summaries in a real run.
    """
    if not isinstance(parsed, dict) or not isinstance(parsed.get("summary"), str) or not parsed["summary"].strip():
        return False, "no summary"
    summary = parsed["summary"]
    listed = parsed.get("commands") or []
    if not isinstance(listed, list) or len(summary) > 700:
        return False, "wrong shape or too long"
    source = squeeze(item["text"])
    found = [str(c) for c in listed] + re.findall(r"`([^`]+)`", summary) + COMMAND_SHAPE.findall(squeeze(summary))
    invented = [c for c in found if squeeze(c) and squeeze(c).rstrip(".,") not in source]
    if invented:
        return False, f"command not in the text: {invented[0][:60]}"
    low = summary.lower()
    missing = [group[0] for group in item["facts"] if not any(word in low for word in group)]
    return (not missing), (f"does not mention {missing[0]}" if missing else "")


# web-subprofile


def subprofiles() -> dict:
    return (yaml.safe_load(SUBPROFILES.read_text(encoding="utf-8")) or {}).get("subprofiles") or {}


def subprofile_items() -> list[tuple[str, str]]:
    return [(text, name) for name, spec in subprofiles().items() for text in spec.get("examples") or []]


def subprofile_prompt(text: str) -> str:
    lines = [f"- {name}: {spec['choose_when']}" for name, spec in subprofiles().items()]
    return ("Choose the web sub-profile that fits this request.\n" + "\n".join(lines)
            + '\nAnswer JSON {"subprofile": "<one of the names above>"}.\nRequest: ' + text)


def suggest_subprofile(text: str) -> tuple[str | None, list[str]]:
    """Keyword baseline: the sub-profile with the most signals in the request, or None on a tie or no signal."""
    low = " " + re.sub(r"[^\w\sáéíóúñ]", " ", text.lower()) + " "
    hits = {name: [s for s in spec.get("signals") or [] if f" {s} " in low] for name, spec in subprofiles().items()}
    best = sorted(hits.items(), key=lambda kv: -len(kv[1]))
    if not best or not best[0][1] or (len(best) > 1 and len(best[0][1]) == len(best[1][1])):
        return None, []
    return best[0][0], best[0][1]


# tool-call

TOOLS = [{"type": "function", "function": {
              "name": "read_file", "description": "Read a text file of the repository.",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
         {"type": "function", "function": {
              "name": "run_tests", "description": "Run the tests of one file and return the result.",
              "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}}}]
TOOL_CASES = [
    {"prompt": "The test in tests/test_calc.py fails. First read calc.py with read_file. Then run the tests with run_tests on "
               "tests/test_calc.py. Then say in one sentence what you found.",
     "results": {"read_file": "def sum_even(numbers):\n    return sum(n for n in numbers if n % 2 != 0)\n",
                 "run_tests": "FAILED test_mixed: 4 != 6"},
     "order": ["read_file", "run_tests"], "final": None},
    {"prompt": "Read config.yml with read_file and tell me which port it sets. If the file cannot be read, say so. Do not guess.",
     "results": {"read_file": '{"error": "file not found: config.yml"}', "run_tests": "no tests ran"},
     "order": ["read_file"], "final": ["not found", "cannot", "can't", "could not", "couldn't", "unable", "does not exist",
                                       "doesn't exist", "missing", "error", "no such"]},
]


def tool_case_ok(case: dict, chat) -> tuple[bool, str]:
    """Drive one conversation: the model must call the right tools in order, with valid arguments, then answer in text."""
    messages = [{"role": "user", "content": case["prompt"]}]
    called = []
    known = {tool["function"]["name"]: tool["function"]["parameters"]["required"][0] for tool in TOOLS}
    for _ in range(5):
        reply = chat(messages, TOOLS)
        if not isinstance(reply, dict):
            return False, "no reply"
        calls = reply.get("tool_calls") or []
        if not calls:
            text = str(reply.get("content") or "").strip()
            first = [called.index(name) if name in called else -1 for name in case["order"]]
            if -1 in first or first != sorted(first):
                return False, f"called {called or 'nothing'}, expected {' before '.join(case['order'])}"
            if not text:
                return False, "no final answer"
            if case["final"] and not any(word in text.lower() for word in case["final"]):
                return False, "answered as if the file had been read"
            return True, ""
        messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name, arguments = function.get("name"), function.get("arguments")
            if name not in known:
                return False, f"called a tool that does not exist: {name}"
            if not isinstance(arguments, dict) or not isinstance(arguments.get(known[name]), str) or not arguments[known[name]]:
                return False, f"{name} called without a valid {known[name]}"
            called.append(name)
            messages.append({"role": "tool", "tool_name": name, "tool_call_id": call.get("id"), "content": case["results"][name]})
    return False, "kept calling tools without answering"


# vision and design-judge: images are drawn here so every run sees the same pixels and nothing is copied from a project

COLORS = {"red": (220, 40, 40), "green": (40, 170, 70), "blue": (40, 90, 220), "orange": (245, 140, 20)}
GRAY, DARK, PAPER = (205, 205, 210), (40, 40, 48), (245, 245, 245)
VISION = [(3, 2, "orange"), (4, 4, "blue"), (2, 1, "green"), (5, 3, "red")]
VISION_PROMPT = ("This image is a screenshot of a toolbar with rectangular buttons in one row. One button is colored and the "
                 'rest are gray. Answer JSON {"buttons": <how many buttons>, "highlighted": <position of the colored button '
                 'counting from the left, starting at 1>, "color": "red" | "green" | "blue" | "orange"}.')
JUDGE_PROMPT = ("Two versions of the same screen: the first image is version A and the second image is version B. Which version "
                'makes the main action easier to find? Answer JSON {"choice": "a" or "b", "reason": "<one short sentence>"}.')


def png(width: int, height: int, rects: list[tuple], background: tuple = PAPER) -> bytes:
    """A PNG from filled rectangles (x0, y0, x1, y1, color), written with the standard library only."""
    rows = [bytearray(bytes(background) * width) for _ in range(height)]
    for x0, y0, x1, y1, color in rects:
        fill = bytes(color) * (x1 - x0)
        for y in range(max(0, y0), min(height, y1)):
            rows[y][x0 * 3:x1 * 3] = fill

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def toolbar(colors: list[tuple], page: tuple = PAPER) -> bytes:
    rects = [(0, 0, 640, 40, DARK)]
    step = 600 // len(colors)
    for index, color in enumerate(colors):
        left = 20 + index * step
        rects.append((left, 100, left + step - 20, 160, color))
    return png(640, 240, rects, page)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def vision_items() -> list[dict]:
    items = []
    for count, position, color in VISION:
        colors = [COLORS[color] if i + 1 == position else GRAY for i in range(count)]
        items.append({"image": b64(toolbar(colors)), "expected": {"buttons": count, "highlighted": position, "color": color}})
    return items


def vision_ok(expected: dict, parsed) -> bool:
    if not isinstance(parsed, dict):
        return False
    try:
        return (int(parsed.get("buttons")) == expected["buttons"] and int(parsed.get("highlighted")) == expected["highlighted"]
                and str(parsed.get("color", "")).strip().lower() == expected["color"])
    except (TypeError, ValueError):
        return False


def sample_pairs() -> list[dict]:
    """Two made-up pairs that only prove the mechanism works. They are nobody's taste and never count for routing."""
    loud = toolbar([COLORS["red"], COLORS["green"], COLORS["blue"], COLORS["orange"]])
    calm = toolbar([COLORS["blue"], GRAY, GRAY, GRAY])
    faint = toolbar([(232, 232, 236), (238, 238, 240), (238, 238, 240)])
    clear = toolbar([DARK, GRAY, GRAY])
    return [{"id": "sample-one-primary", "a": b64(loud), "b": b64(calm), "choice": "b"},
            {"id": "sample-contrast", "a": b64(clear), "b": b64(faint), "choice": "a"}]


def design_pairs(home: Path | None = None) -> tuple[list[dict], bool]:
    """The owner's pairs from STANDARDS_HOME/design-pairs/pairs.yml, or the sample pairs. The flag says which."""
    folder = (home or Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")) / "design-pairs"
    listing = folder / "pairs.yml"
    pairs = []
    if listing.exists():
        for pair in (yaml.safe_load(listing.read_text(encoding="utf-8")) or {}).get("pairs") or []:
            a, b = folder / str(pair.get("a")), folder / str(pair.get("b"))
            if pair.get("choice") in {"a", "b"} and a.is_file() and b.is_file():
                pairs.append({"id": str(pair.get("id") or a.stem), "a": b64(a.read_bytes()), "b": b64(b.read_bytes()),
                              "choice": pair["choice"]})
    return (pairs, False) if pairs else (sample_pairs(), True)


def judge_ok(pair: dict, ask) -> bool:
    """A pair counts only when the model agrees with the choice in both orders, so a habit of answering 'a' never passes."""
    flipped = {"a": "b", "b": "a"}
    first = ask(JUDGE_PROMPT, [pair["a"], pair["b"]])
    second = ask(JUDGE_PROMPT, [pair["b"], pair["a"]])
    answers = [str((reply or {}).get("choice", "")).strip().lower() if isinstance(reply, dict) else "" for reply in (first, second)]
    return answers == [pair["choice"], flipped[pair["choice"]]]


def request_estimate(task: str) -> int:
    """About how many requests one run of a chat task sends, to plan against a provider's daily limit."""
    return {"classify": len(CLASSIFY), "extract": len(EXTRACT), "summarize": len(SUMMARIZE), "web-subprofile": len(subprofile_items()),
            "tool-call": 3 * len(TOOL_CASES), "vision": len(VISION), "design-judge": 2 * len(design_pairs()[0]),
            "review-diff": len(REVIEW_CASES),
            "decompose": len(DECOMPOSE_SPECS)}.get(task, 1)


# review-diff

# Each case is a new file added in one diff with one seeded defect. `defect` is the line range of the new file where it sits.
REVIEW_CASES = [
    {"id": "sql-injection", "file": "app/db.py", "defect": (6, 7), "lines": [
        "import sqlite3", "", "", "def find_user(conn, name):", "    cursor = conn.cursor()",
        "    query = f\"SELECT id, email FROM users WHERE name = '{name}'\"", "    cursor.execute(query)",
        "    return cursor.fetchall()"]},
    {"id": "off-by-one", "file": "app/pages.py", "defect": (3, 3), "lines": [
        "def page_slice(items, page, size):", "    \"\"\"Return the items of a 1-based page.\"\"\"", "    start = page * size",
        "    return items[start:start + size]"]},
    {"id": "mutable-default", "file": "app/tags.py", "defect": (1, 3), "lines": [
        "def add_tag(item, tags=[]):", "    tags.append(item)", "    return tags"]},
    {"id": "hardcoded-credential", "file": "app/settings.py", "defect": (3, 3), "lines": [
        "import os", "", "DB_PASSWORD = \"hunter2-prod\"", "DB_HOST = os.environ.get(\"DB_HOST\", \"localhost\")"]},
    {"id": "inverted-permission", "file": "app/perms.py", "defect": (2, 2), "lines": [
        "def can_delete(user, post):", "    return user.is_admin or post.author_id != user.id"]},
    {"id": "divide-by-zero", "file": "app/stats.py", "defect": (3, 3), "lines": [
        "def average(values):", "    \"\"\"Mean of a list of numbers.\"\"\"", "    return sum(values) / len(values)"]},
]
REVIEW_PROMPT = ("Review this diff. Report real defects only. Answer JSON "
                 '{"findings": [{"file": "path", "line_start": 1, "line_end": 1, "severity": "high|medium|low", "note": "..."}]} '
                 "with line numbers of the new file. Use high only for a defect that must be fixed before merge.\nDiff:\n")
MAX_FINDING_LINES = 10


def review_diff_text(case: dict) -> str:
    """The unified diff of a new file, so the line numbers in the diff are the line numbers of the new file."""
    name, lines = case["file"], case["lines"]
    head = f"diff --git a/{name} b/{name}\nnew file mode 100644\n--- /dev/null\n+++ b/{name}\n@@ -0,0 +1,{len(lines)} @@\n"
    return head + "".join(f"+{line}\n" for line in lines)


def review_reference(case: dict) -> dict:
    start, end = case["defect"]
    return {"findings": [{"file": case["file"], "line_start": start, "line_end": end, "severity": "high",
                          "note": "seeded defect"}]}


def finding_span(finding) -> tuple[str, int, int, str] | None:
    """(file, first line, last line, severity) of a well formed finding, else None."""
    if not isinstance(finding, dict) or not isinstance(finding.get("file"), str):
        return None
    try:
        start = int(finding.get("line_start", finding.get("line")))
        end = int(finding.get("line_end", start))
    except (TypeError, ValueError):
        return None
    name = finding["file"].strip()
    name = name[2:] if name[:2] in ("a/", "b/") else name
    return name, start, max(start, end), str(finding.get("severity", "")).strip().lower()


def review_ok(case: dict, parsed) -> tuple[bool, str]:
    """A diff passes when a finding names its file and overlaps the defect lines and no high finding sits elsewhere.

    A finding that spans more than MAX_FINDING_LINES lines does not count as a hit, so flagging the whole file never passes.
    """
    findings = parsed.get("findings") if isinstance(parsed, dict) else None
    if not isinstance(findings, list):
        return False, "no findings list"
    start, end = case["defect"]
    hit, false_high = False, None
    for raw in findings:
        span = finding_span(raw)
        if span is None:
            continue
        name, first, last, severity = span
        on_defect = name == case["file"] and first <= end and last >= start and last - first < MAX_FINDING_LINES
        hit = hit or on_defect
        if severity == "high" and not on_defect and false_high is None:
            false_high = f"{name}:{first}"
    if false_high:
        return False, f"false high finding at {false_high} in {case['id']}"
    return hit, "" if hit else f"missed {case['id']} at {case['file']}:{start}-{end}"


# decompose

def _unit(uid: str, title: str, files: list[str], deps: list[str] | None = None) -> dict:
    return {"id": uid, "title": title, "task_type": "edit-small", "goal": title, "allowed": files,
            "acceptance": {"test": "python -m unittest"}, "depends_on": deps or []}


DECOMPOSE_SPECS = [
    {"id": "tax", "task": "Add tax support: pricing computes the tax, the cart total includes it, the receipt prints it and the README documents it.",
     "files": ["shop/pricing.py", "shop/cart.py", "shop/receipt.py", "tests/test_shop.py", "README.md"],
     "must_touch": ["shop/pricing.py", "shop/cart.py", "shop/receipt.py", "README.md"], "min_units": 3,
     "reference": [_unit("u1", "Tax in pricing", ["shop/pricing.py"]), _unit("u2", "Tax in the cart", ["shop/cart.py"], ["u1"]),
                   _unit("u3", "Tax on the receipt", ["shop/receipt.py"], ["u2"]), _unit("u4", "Document tax", ["README.md"])]},
    {"id": "verbose", "task": "Add a --verbose flag: the argument parser reads it, the logger gets debug levels, the config sets a default, "
                              "main wires all three and docs/usage.md describes it.",
     "files": ["cli/args.py", "cli/config.py", "cli/log.py", "cli/main.py", "docs/usage.md", "tests/test_cli.py"],
     "must_touch": ["cli/args.py", "cli/config.py", "cli/log.py", "cli/main.py", "docs/usage.md"], "min_units": 4,
     "reference": [_unit("u1", "Parse the flag", ["cli/args.py"]), _unit("u2", "Debug levels", ["cli/log.py"]),
                   _unit("u3", "Config default", ["cli/config.py"]),
                   _unit("u4", "Wire it in main", ["cli/main.py"], ["u1", "u2", "u3"]), _unit("u5", "Document the flag", ["docs/usage.md"])]},
    {"id": "rename", "task": "Rename parse to parse_text in lib/a.py. lib/b.py and lib/c.py import it and must follow. Bump the version in "
                             "pyproject.toml and add a line to CHANGELOG.md.",
     "files": ["lib/a.py", "lib/b.py", "lib/c.py", "pyproject.toml", "CHANGELOG.md", "tests/test_lib.py"],
     "must_touch": ["lib/a.py", "lib/b.py", "lib/c.py", "pyproject.toml", "CHANGELOG.md"], "min_units": 4,
     "reference": [_unit("u1", "Rename in a", ["lib/a.py"]), _unit("u2", "Follow in b", ["lib/b.py"], ["u1"]),
                   _unit("u3", "Follow in c", ["lib/c.py"], ["u1"]), _unit("u4", "Bump the version", ["pyproject.toml"]),
                   _unit("u5", "Changelog line", ["CHANGELOG.md"], ["u4"])]},
]
DECOMPOSE_PROMPT = ("Split this task into work units for coding agents. Answer JSON "
                    '{"units": [{"id": "u1", "title": "...", "task_type": "edit-small", "goal": "...", "allowed": ["path"], '
                    '"acceptance": {"test": "python -m unittest"}, "depends_on": []}]}. Use only files from the list. Every file under '
                    "Must change must be in the allowed list of some unit. Units that do not depend on each other, directly or "
                    "through others, must not share a file.\n")


def decompose_prompt(spec: dict) -> str:
    return (DECOMPOSE_PROMPT + f"Task: {spec['task']}\nFiles: {', '.join(spec['files'])}\n"
            f"Must change: {', '.join(spec['must_touch'])}")


def decompose_ok(spec: dict, parsed) -> tuple[bool, str]:
    """A split passes when workplan.validate accepts it, it has enough units, every file to change is in some unit and
    units that may run together share no file. validate also rejects a cycle in depends_on."""
    import workplan
    units = parsed.get("units") if isinstance(parsed, dict) else None
    if not isinstance(units, list) or not units:
        return False, "no units"
    plan = {"plan_id": spec["id"], "goal": spec["task"], "units": units}
    errors = workplan.validate(plan)
    if errors:
        return False, f"invalid plan: {errors[0]}"
    if len(units) < spec["min_units"]:
        return False, f"{len(units)} units, at least {spec['min_units']} needed"
    covered = set().union(*(workplan.expand(unit, spec["files"]) for unit in units))
    missing = sorted(set(spec["must_touch"]) - covered)
    if missing:
        return False, f"not covered: {missing[0]}"
    clash = workplan.conflicts(plan, spec["files"])
    if clash:
        return False, f"parallel units {clash[0][0]} and {clash[0][1]}: {clash[0][2]}"
    return True, ""


# Running a chat task


def run_chat(task: str, ask=None, chat=None, baseline: bool = False, home: Path | None = None) -> dict:
    """Run one chat task. ask(prompt, images) returns the parsed JSON reply or None. chat(messages, tools) returns a message.

    Returns the task name to record, the accuracy, the item count and the first reasons for failure.
    """
    name, passed, notes, total = task, 0, [], 0

    def attempt(check) -> None:
        nonlocal passed, total
        total += 1
        try:
            ok, note = check()
        except OutOfTime:
            ok, note = False, "time limit of the run reached"
        passed += bool(ok)
        if not ok and note and len(notes) < 3:
            notes.append(note)

    if task == "classify":
        for text, label in CLASSIFY:
            attempt(lambda: ((keyword_label(text) if baseline else str((ask(
                f'Classify this issue as bug, feature or docs. Answer JSON {{"label": "..."}}.\nIssue: {text}', None) or {}
            ).get("label", "")).strip().lower()) == label, f"wrong label for: {text[:40]}"))
    elif task == "extract":
        for line, expected in EXTRACT:
            attempt(lambda: (extract_ok(expected, extract_baseline(line) if baseline else ask(EXTRACT_PROMPT + line, None)),
                             f"wrong fields for: {line[:40]}"))
    elif task == "summarize":
        for item in SUMMARIZE:
            attempt(lambda: summarize_ok(item, ask(SUMMARIZE_PROMPT + item["text"], None)))
    elif task == "web-subprofile":
        for text, label in subprofile_items():
            attempt(lambda: ((suggest_subprofile(text)[0] if baseline else str((ask(subprofile_prompt(text), None) or {}
                             ).get("subprofile", "")).strip().lower()) == label, f"wrong sub-profile for: {text[:40]}"))
    elif task == "tool-call":
        for case in TOOL_CASES:
            attempt(lambda: tool_case_ok(case, chat))
    elif task == "vision":
        for item in vision_items():
            attempt(lambda: (vision_ok(item["expected"], ask(VISION_PROMPT, [item["image"]])), f"misread {item['expected']}"))
    elif task == "design-judge":
        pairs, sample = design_pairs(home)
        name = "design-judge-sample" if sample else "design-judge"
        for pair in pairs:
            attempt(lambda: (judge_ok(pair, ask), f"disagreed on {pair['id']}"))
    elif task == "review-diff":
        for case in REVIEW_CASES:
            attempt(lambda: review_ok(case, ask(REVIEW_PROMPT + review_diff_text(case), None)))
    elif task == "decompose":
        for spec in DECOMPOSE_SPECS:
            attempt(lambda: decompose_ok(spec, ask(decompose_prompt(spec), None)))
    else:
        raise ValueError(f"unknown chat task {task}")
    return {"task": name, "accuracy": round(passed / total, 2) if total else 0.0, "items": total, "notes": notes}


# Agent tasks: a small repository, a task, and acceptance tests the agent never sees

BUGGY = '''def sum_even(numbers):
    """Return the sum of the even numbers."""
    return sum(n for n in numbers if n % 2 != 0)


def count_words(text):
    return len(text.split())
'''
VISIBLE_TESTS = '''import unittest

from calc import sum_even


class SumEven(unittest.TestCase):
    def test_mixed(self):
        self.assertEqual(sum_even([1, 2, 3, 4]), 6)

    def test_empty(self):
        self.assertEqual(sum_even([]), 0)

    def test_odd_only(self):
        self.assertEqual(sum_even([1, 3, 5]), 0)


if __name__ == "__main__":
    unittest.main()
'''
HIDDEN_TESTS = '''import unittest

from calc import count_words, sum_even


class Hidden(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(sum_even([-2, -3, 4]), 2)

    def test_other_function_kept(self):
        self.assertEqual(count_words("a b  c"), 3)


if __name__ == "__main__":
    unittest.main()
'''
PRICING = '''def line_total(price_cents, quantity, discount_percent=0):
    """Total in cents for one line, after a discount given in percent."""
    total = price_cents * quantity
    return total - total * discount_percent // 10
'''
CART = '''from shop.pricing import line_total


def cart_total(lines):
    """Total in cents for lines of (price_cents, quantity, discount_percent)."""
    return sum(line_total(price, quantity) for price, quantity, discount in lines)


def count_items(lines):
    return sum(quantity for _, quantity, _ in lines)
'''
RECEIPT = '''from shop.cart import cart_total


def receipt(lines):
    """One line of text such as 'TOTAL 18.05'."""
    total = cart_total(lines)
    return f"TOTAL {total // 100}.{total % 100}"
'''
SHOP_TESTS = '''import unittest

from shop.cart import cart_total
from shop.pricing import line_total
from shop.receipt import receipt


class Shop(unittest.TestCase):
    def test_line_discount(self):
        self.assertEqual(line_total(1000, 2, 10), 1800)

    def test_cart_uses_discount(self):
        self.assertEqual(cart_total([(1000, 2, 10), (250, 1, 0)]), 2050)

    def test_receipt(self):
        self.assertEqual(receipt([(1000, 2, 10), (5, 1, 0)]), "TOTAL 18.05")


if __name__ == "__main__":
    unittest.main()
'''
SHOP_HIDDEN = '''import unittest

from shop.cart import cart_total, count_items
from shop.pricing import line_total
from shop.receipt import receipt


class Hidden(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(line_total(999, 3), 2997)

    def test_half_discount(self):
        self.assertEqual(cart_total([(1001, 1, 50)]), 501)

    def test_whole_amount_keeps_two_decimals(self):
        self.assertEqual(receipt([(100, 1, 0)]), "TOTAL 1.00")

    def test_other_function_kept(self):
        self.assertEqual(count_items([(1, 2, 0), (1, 3, 0)]), 5)


if __name__ == "__main__":
    unittest.main()
'''
DOCS_HIDDEN = '''import unittest
from pathlib import Path


class Hidden(unittest.TestCase):
    def test_usage_section(self):
        text = Path("README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# calc"))
        self.assertIn("## Usage", text)
        usage = text.split("## Usage", 1)[1]
        self.assertIn("sum_even(", usage)
        self.assertIn("count_words(", usage)
        self.assertLess(len(text), 3000)


if __name__ == "__main__":
    unittest.main()
'''
SLUG = """def slugify(text):
    words = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return "-".join(words)
"""
POSTS = SLUG + '''

def post_url(title):
    return "/posts/" + slugify(title)
'''
USERS = SLUG + '''

def profile_url(name):
    return "/u/" + slugify(name)
'''
TAGS = SLUG + '''

def tag_url(tag):
    return "/tags/" + slugify(tag)
'''
APP_TESTS = """import unittest
from app.posts import post_url
from app.tags import tag_url
from app.users import profile_url


class App(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(post_url("Hello, World!"), "/posts/hello-world")
        self.assertEqual(profile_url("Ada  Lovelace"), "/u/ada-lovelace")
        self.assertEqual(tag_url("C++ tips"), "/tags/c-tips")


if __name__ == "__main__":
    unittest.main()
"""
APP_HIDDEN = """import ast
import unittest
from pathlib import Path


def tree(name):
    return ast.parse(Path("app", name).read_text(encoding="utf-8"))


class Hidden(unittest.TestCase):
    def test_behavior_kept(self):
        from app.posts import post_url
        from app.tags import tag_url
        from app.text import slugify
        from app.users import profile_url
        self.assertEqual(slugify("  Mixed CASE--text 42 "), "mixed-case-text-42")
        self.assertEqual(slugify("***"), "")
        self.assertEqual(post_url("A b"), "/posts/a-b")
        self.assertEqual(profile_url("Zoe_Q"), "/u/zoe-q")
        self.assertEqual(tag_url("x/y"), "/tags/x-y")

    def test_defined_once_in_text(self):
        defined = [name for name in ("posts.py", "users.py", "tags.py", "text.py", "__init__.py")
                   if any(isinstance(n, ast.FunctionDef) and n.name == "slugify" for n in ast.walk(tree(name)))]
        self.assertEqual(defined, ["text.py"])

    def test_modules_import_it(self):
        for name in ("posts.py", "users.py", "tags.py"):
            imports = [n for n in ast.walk(tree(name)) if isinstance(n, ast.ImportFrom) and n.module == "app.text"
                       and any(a.name == "slugify" for a in n.names)]
            self.assertTrue(imports, name)

    def test_public_functions_kept(self):
        for name, func in (("posts.py", "post_url"), ("users.py", "profile_url"), ("tags.py", "tag_url")):
            self.assertIn(func, [n.name for n in tree(name).body if isinstance(n, ast.FunctionDef)])


if __name__ == "__main__":
    unittest.main()
"""
IGNORE = "__pycache__/\n*.pyc\n"
README = "# calc\n\nSmall helpers.\n"
AGENT_TASKS = {
    "fix-bug": {
        "files": {"calc.py": BUGGY, "test_calc.py": VISIBLE_TESTS, "README.md": README, ".gitignore": IGNORE},
        "task": "Fix sum_even in calc.py so it sums the even numbers. Keep count_words.",
        "allowed": ["calc.py"], "test": "test_calc", "hidden": HIDDEN_TESTS},
    "fix-multi": {
        "files": {"shop/__init__.py": "", "shop/pricing.py": PRICING, "shop/cart.py": CART, "shop/receipt.py": RECEIPT,
                  "test_shop.py": SHOP_TESTS, "README.md": "# shop\n\nPrices in cents.\n", ".gitignore": IGNORE},
        "task": "The tests in test_shop.py fail. Fix the code in shop/ so discounts are applied in percent and the receipt "
                "always shows two decimals. Keep every public function. Do not change the tests.",
        "allowed": ["shop/*.py"], "test": "test_shop", "hidden": SHOP_HIDDEN},
    "docs-small": {
        "files": {"calc.py": BUGGY.replace("% 2 != 0", "% 2 == 0"), "test_calc.py": VISIBLE_TESTS, "README.md": README,
                  ".gitignore": IGNORE},
        "task": "Add a '## Usage' section to README.md that documents sum_even and count_words with one example call each. "
                "Change only README.md.",
        "allowed": ["README.md"], "test": "test_calc", "hidden": DOCS_HIDDEN},
    "refactor-module": {
        "files": {"app/__init__.py": "", "app/posts.py": POSTS, "app/users.py": USERS, "app/tags.py": TAGS,
                  "test_app.py": APP_TESTS, "README.md": "# app\n\nURL helpers.\n", ".gitignore": IGNORE},
        "task": "The function slugify is copied into app/posts.py, app/users.py and app/tags.py. Move it into a new module "
                "app/text.py and import it from the three modules with `from app.text import slugify`. Keep every public "
                "function and its behavior. Do not change the tests.",
        "allowed": ["app/*.py"], "test": "test_app", "hidden": APP_HIDDEN},
}
