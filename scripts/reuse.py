#!/usr/bin/env python3
"""Look for code to reuse before writing new code, keep a compact map of the symbols, and collect deferred shortcuts.

`similar` ranks the functions and classes of a repository by the words they share with a task, so an executor sees
`slugify` before it writes a second one. `symbols` is the compact map: one line per definition with its first doc
line. `debt` reads the comments that start with `shortcut:` and their `revisit when` condition into a ledger.
The idea comes from Ponytail (MIT, https://github.com/DietrichGebert/ponytail). The code here is our own.
Run: python scripts/reuse.py similar "TASK" [--repo .] | map [--repo .] | debt [--repo .]
"""
import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}
JS_DEF = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*([A-Za-z_$][\w$]*)|"
                    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)|"
                    r"class\s+([A-Za-z_$][\w$]*))")
SHORTCUT = re.compile(r"(?:#|//)\s*shortcut:\s*(.+?)(?:\s*[.,;]?\s*revisit when\s*(.+))?$", re.I)
STOP = {"a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "with", "from", "that", "this", "it", "is", "be",
        "add", "make", "new", "function", "un", "una", "el", "la", "de", "del", "que", "y", "en", "para", "con", "por"}
MAX_FILE = 400_000


def tracked(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=False)
    return [n for n in out.stdout.splitlines() if Path(n).suffix in CODE]


def words(text: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    found = {w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if len(w) > 2}
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in found} - STOP


def python_symbols(rel: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("__"):
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            rows.append({"file": rel, "line": node.lineno, "kind": kind, "name": node.name, "doc": doc[0] if doc else ""})
    return rows


def js_symbols(rel: str, text: str) -> list[dict]:
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        found = JS_DEF.match(line)
        if found:
            name = next(g for g in found.groups() if g)
            rows.append({"file": rel, "line": number, "kind": "class" if found.group(3) else "def", "name": name, "doc": ""})
    return rows


def symbols(repo: Path) -> list[dict]:
    rows = []
    for rel in tracked(repo):
        path = repo / rel
        try:
            if path.stat().st_size > MAX_FILE:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rows += python_symbols(rel, text) if rel.endswith(".py") else js_symbols(rel, text)
    return rows


def similar(repo: Path, task: str, top: int = 5) -> list[dict]:
    """Definitions that share words with the task, best first. Tests are left out: they are not code to reuse."""
    want = words(task)
    scored = []
    for row in symbols(repo):
        if re.search(r"(^|/)tests?/|test_|\.test\.|\.spec\.", row["file"]):
            continue
        name_words = words(row["name"])
        hits = len(want & name_words) * 2 + len(want & words(row["doc"]))
        if hits:
            scored.append((hits, -len(name_words), row))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]["file"], item[2]["line"]))
    return [row for _, _, row in scored[:top]]


def debt(repo: Path) -> list[dict]:
    rows = []
    for rel in tracked(repo):
        try:
            lines = (repo / rel).read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            found = SHORTCUT.search(line)
            if found:
                rows.append({"file": rel, "line": number, "shortcut": found.group(1).strip(),
                             "revisit_when": (found.group(2) or "").strip() or None})
    return rows


def packet_lines(repo: Path, task: str, top: int = 5) -> list[str]:
    """The lines the delegated task packet gets: reuse first, write new code only when nothing fits."""
    found = similar(repo, task, top)
    if not found:
        return []
    lines = ["", "## Existing code to reuse first",
             "Read these before writing new code. Call or extend one when it fits. Write new code only when none does, and say why."]
    lines += [f"- `{r['file']}:{r['line']}` {r['kind']} `{r['name']}`" + (f": {r['doc']}" if r["doc"] else "") for r in found]
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["similar", "map", "debt"])
    parser.add_argument("task", nargs="?", default="")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.command == "similar":
        rows = similar(repo, args.task, args.top)
    elif args.command == "map":
        for row in symbols(repo):
            print(f"{row['file']}:{row['line']} {row['kind']} {row['name']}" + (f"  {row['doc']}" if row["doc"] else ""))
        return 0
    else:
        rows = debt(repo)
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
