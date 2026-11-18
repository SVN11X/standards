#!/usr/bin/env python3
"""Regex search that shows each match inside the function or class that holds it.

Small-context delegates (OpenCode, Ollama) need the place of a match in the code, not whole files. Every match is
grouped under its enclosing definition chain ("class Store > def save") with line numbers. With --seen FILE, a
definition whose whole range was shown before collapses to one line, and the ranges just shown are recorded.
The idea comes from agentgrep in jcode (MIT, Jeremy Huang, https://github.com/1jehuang/jcode). This is own code.
Run: python scripts/agentgrep.py PATTERN [PATH ...] [--glob GLOB] [--ignore-case] [--seen FILE] [--max N] [--json]
"""
import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "standards/agentgrep/v1"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
MAX_BYTES = 1_000_000
TEXT_WIDTH = 200
NOT_METHODS = {"if", "for", "while", "switch", "catch", "function", "return", "else", "new", "throw", "using",
               "foreach", "lock", "do", "try", "await", "yield"}

MODS = (r"(?:(?:public|private|protected|internal|static|abstract|sealed|final|partial|override|virtual|async|"
        r"synchronized|readonly|unsafe|extern|get|set)\s+)*")
PY = [(re.compile(r"^(\s*)(async\s+def|def|class)\s+(\w+)"), None)]
JS = [
    (re.compile(r"^(\s*)(?:export\s+)?(?:default\s+)?(?:async\s+)?(function)\*?\s+(\w+)"), None),
    (re.compile(r"^(\s*)(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(class)\s+(\w+)"), None),
    (re.compile(r"^(\s*)(?:export\s+)?(const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?"
                r"(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"), None),
    (re.compile(r"^(\s*)()" + MODS + r"(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::\s*[^{]+)?\{\s*$"), "method"),
]
GO = [(re.compile(r"^()(func)\s+(?:\([^)]*\)\s*)?(\w+)"), None)]
RUST = [
    (re.compile(r"^(\s*)(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(fn|struct|enum|trait)\s+(\w+)"), None),
    (re.compile(r"^(\s*)(?:unsafe\s+)?(impl)\b([^{]*?)\s*(?:\{|where\b|$)"), None),
]
CLIKE = [
    (re.compile(r"^(\s*)" + MODS + r"(class|interface|struct|enum|record)\s+(\w+)"), None),
    (re.compile(r"^(\s*)" + MODS + r"[\w<>\[\],.?]+\s+()(\w+)\s*\([^;]*\)\s*(?:throws\s+[\w,.\s]+)?\{?\s*$"),
     "method"),
]
PS = [(re.compile(r"^(\s*)(function)\s+([\w-]+)", re.IGNORECASE), None)]
LANGS = {".py": PY, ".js": JS, ".jsx": JS, ".ts": JS, ".tsx": JS, ".mjs": JS, ".cjs": JS, ".go": GO,
         ".rs": RUST, ".cs": CLIKE, ".java": CLIKE, ".ps1": PS, ".psm1": PS}


def definitions(lines, ext):
    """Return (line, indent, label) for every definition line, in file order."""
    rules = LANGS.get(ext, [])
    found = []
    for number, text in enumerate(lines, 1):
        for rule, kind in rules:
            m = rule.match(text)
            if not m:
                continue
            first = text.split(None, 1)[0] if text.strip() else ""
            if kind == "method" and (first in NOT_METHODS or m.group(3) in NOT_METHODS):
                continue
            keyword, name = m.group(2), m.group(3).strip()
            label = f"{keyword} {name}".strip() if keyword else name
            found.append((number, len(m.group(1).expandtabs(4)), label))
            break
    return found


def indent_of(text):
    text = text.expandtabs(4)
    return len(text) - len(text.lstrip())


def locate(defs, lines, number):
    """Return the chain of definitions around a line, outermost first."""
    limit = indent_of(lines[number - 1])
    chain = []
    for entry in reversed([d for d in defs if d[0] < number]):
        if entry[1] < limit:
            chain.append(entry)
            limit = entry[1]
            if limit == 0:
                break
    return list(reversed(chain))


def def_end(defs, index, total):
    indent = defs[index][1]
    for later in defs[index + 1:]:
        if later[1] <= indent:
            return later[0] - 1
    return total


def is_binary(path):
    with open(path, "rb") as handle:
        return b"\0" in handle.read(4096)


def files_under(paths, glob):
    for base in paths:
        base = Path(base)
        if base.is_file():
            yield base
            continue
        for root, dirs, names in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(names):
                if glob and not fnmatch.fnmatch(name, glob):
                    continue
                yield Path(root) / name


def readable(path):
    try:
        return path.stat().st_size <= MAX_BYTES and not is_binary(path)
    except OSError:
        return False


def search(pattern, paths, glob):
    """Yield (path, lines, defs, [(line, chain)]) for each file with matches."""
    for path in files_under(paths, glob):
        if not readable(path):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = [n for n, text in enumerate(lines, 1) if pattern.search(text)]
        if not hits:
            continue
        defs = definitions(lines, path.suffix.lower())
        yield path.as_posix(), lines, defs, [(n, locate(defs, lines, n)) for n in hits]


def covered(ranges, start, end):
    return any(s <= start and end <= e for s, e in ranges)


def merge(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def load_seen(path):
    if not path or not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: [tuple(r) for r in v] for k, v in data.items()} if isinstance(data, dict) else {}


def collect(pattern, paths, glob, limit, seen):
    """Group the first `limit` matches by file and definition. Return (files, shown, left_out, new_ranges)."""
    files, shown, left, fresh = [], 0, 0, {}
    for path, lines, defs, hits in search(pattern, paths, glob):
        groups = {}
        for number, chain in hits:
            if shown >= limit:
                left += 1
                continue
            shown += 1
            key = chain[-1][0] if chain else 0
            if key not in groups:
                groups[key] = {"chain": [c[2] for c in chain], "line": key, "matches": [], "seen": False}
                if chain:
                    end = def_end(defs, defs.index(chain[-1]), len(lines))
                    groups[key]["range"] = (key, end)
                    groups[key]["seen"] = covered(seen.get(path, []), key, end)
            groups[key]["matches"].append({"line": number, "text": lines[number - 1].strip()[:TEXT_WIDTH]})
        if groups:
            files.append({"path": path, "definitions": list(groups.values())})
            for group in groups.values():
                if group["seen"]:
                    continue
                if "range" in group:
                    fresh.setdefault(path, []).append(group["range"])
                else:
                    fresh.setdefault(path, []).extend((m["line"], m["line"]) for m in group["matches"])
    return files, shown, left, fresh


def save_seen(path, seen, fresh):
    merged = {k: [list(r) for r in v] for k, v in seen.items()}
    for key, ranges in fresh.items():
        merged[key] = merge(merged.get(key, []) + ranges)
    Path(path).write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render(files, shown, left):
    out = []
    for entry in files:
        out.append(entry["path"])
        for group in entry["definitions"]:
            title = " > ".join(group["chain"]) if group["chain"] else "(top level)"
            count = len(group["matches"])
            if group["seen"]:
                noun = "match" if count == 1 else "matches"
                out.append(f"  L{group['line']} {title}: {count} {noun}, already seen")
                continue
            out.append(f"  L{group['line']} {title}" if group["chain"] else f"  {title}")
            out.extend(f"    L{m['line']}: {m['text']}" for m in group["matches"])
    out.append(f"{shown} matches" + (f", {left} left out" if left else ""))
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Search with each match shown inside its definition.")
    parser.add_argument("pattern")
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("--glob")
    parser.add_argument("--ignore-case", "-i", action="store_true")
    parser.add_argument("--seen")
    parser.add_argument("--max", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        pattern = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
    except re.error as error:
        print(f"bad pattern: {error}", file=sys.stderr)
        return 2
    seen = load_seen(args.seen)
    files, shown, left, fresh = collect(pattern, args.paths, args.glob, max(0, args.max), seen)
    if args.json:
        for entry in files:
            for group in entry["definitions"]:
                group.pop("range", None)
        print(json.dumps({"schema": SCHEMA, "files": files, "matches": shown, "left_out": left},
                         ensure_ascii=False, indent=2))
    else:
        print(render(files, shown, left))
    if args.seen:
        save_seen(args.seen, seen, fresh)
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
