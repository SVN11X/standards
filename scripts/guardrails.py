#!/usr/bin/env python3
"""Rules a repository makes its environment enforce, declared in .standard.yml under `guardrails`.

A written instruction can be missed. A guardrail is checked by `standard.py check` on every push and pull request,
so a change that breaks it is blocked before it is integrated, whoever wrote it.

    guardrails:
      forbidden:
        - {id: no-use-effect, pattern: "\\buseEffect\\(", paths: ["src/*.tsx"], why: "derive state or use a handler"}
      boundaries:
        - {module: src/features/signup, may_import: [src/shared], why: "a feature reaches another only through shared"}
      aliases: {"@/": "src/"}

`forbidden` lists regular expressions that may not appear in the files of `paths` (globs, `*` also crosses folders),
except in the files of `except`. `boundaries` lists modules: a file inside a module may import, inside this
repository, only its own module and the paths of `may_import`. Imports of other packages are not judged. Python
imports are read with `ast`, JavaScript and TypeScript imports with a pattern for import, export from, require and
import(). `aliases` maps an import prefix to a folder of the repository.
"""
from __future__ import annotations

import ast
import fnmatch
import posixpath
import re
from pathlib import Path

JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte")
JS_IMPORT = re.compile(r"""(?:\bimport\s+(?:[^'"]*?\sfrom\s+)?|\bexport\s+[^'"]*?\sfrom\s+|\brequire\(\s*|\bimport\(\s*)['"]([^'"]+)['"]""")


def problems(config: dict) -> list[str]:
    """What is wrong in the guardrails block itself, so a broken rule never passes silently."""
    found = []
    block = config.get("guardrails") or {}
    if not isinstance(block, dict):
        return ["guardrails must be a mapping with forbidden, boundaries and aliases"]
    for index, rule in enumerate(block.get("forbidden") or []):
        where = f"guardrails.forbidden[{rule.get('id', index)}]"
        if not rule.get("pattern") or not rule.get("paths") or not rule.get("why"):
            found.append(f"{where} needs pattern, paths and why")
            continue
        try:
            re.compile(rule["pattern"])
        except re.error as error:
            found.append(f"{where}: the pattern does not compile ({error})")
    for index, rule in enumerate(block.get("boundaries") or []):
        if not rule.get("module") or not rule.get("why"):
            found.append(f"guardrails.boundaries[{index}] needs module and why")
    return found


def matches(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, glob) for glob in globs or [])


def forbidden_hits(repo: Path, files: list[str], rules: list[dict]) -> list[tuple[str, str]]:
    """(where, message) for every line that holds a forbidden pattern."""
    hits = []
    for rule in rules or []:
        pattern = re.compile(rule["pattern"])
        for rel in files:
            if not matches(rel, rule["paths"]) or matches(rel, rule.get("except") or []):
                continue
            try:
                text = (repo / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    label = rule.get("id") or rule["pattern"]
                    hits.append((f"{rel}:{number}", f"Guardrail {label}: {rule['why']}"))
    return hits


def python_imports(text: str, rel: str) -> list[str]:
    """Imported modules as paths without suffix, relative imports resolved against the file's package."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    package = posixpath.dirname(rel)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name.replace(".", "/") for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = posixpath.dirname(base)
                target = posixpath.join(base, (node.module or "").replace(".", "/")) if node.module else base
                found.append(target)
                found += [posixpath.join(target, alias.name) for alias in node.names if not node.module]
            elif node.module:
                found.append(node.module.replace(".", "/"))
    return found


def js_imports(text: str, rel: str, aliases: dict) -> list[str]:
    found = []
    for spec in JS_IMPORT.findall(text):
        if spec.startswith("."):
            found.append(posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec)))
            continue
        for prefix, folder in (aliases or {}).items():
            if spec.startswith(prefix):
                found.append(posixpath.normpath(posixpath.join(folder, spec[len(prefix):])))
                break
    return found


def in_repo(target: str, tracked: set[str], folders: set[str]) -> str | None:
    """The tracked file or folder an import names, or None when it is another package."""
    for candidate in (target, f"src/{target}"):
        if candidate in folders:
            return candidate
        for suffix in ("", ".py", "/__init__.py", *JS_SUFFIXES, *(f"/index{s}" for s in JS_SUFFIXES)):
            if candidate + suffix in tracked:
                return candidate + suffix
    return None


def inside(path: str, folder: str) -> bool:
    folder = folder.rstrip("/")
    return path == folder or path.startswith(folder + "/")


def boundary_hits(repo: Path, files: list[str], rules: list[dict], aliases: dict | None = None) -> list[tuple[str, str]]:
    """(where, message) for every import that leaves its module for a path the module may not import."""
    tracked = set(files)
    folders = {posixpath.dirname(rel) for rel in files}
    folders |= {"/".join(rel.split("/")[:depth]) for rel in files for depth in range(1, rel.count("/") + 1)}
    hits = []
    for rule in rules or []:
        module = rule["module"].rstrip("/")
        allowed = [module, *(rule.get("may_import") or [])]
        for rel in files:
            if not inside(rel, module) or not rel.endswith((".py", *JS_SUFFIXES)):
                continue
            try:
                text = (repo / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            targets = python_imports(text, rel) if rel.endswith(".py") else js_imports(text, rel, aliases or {})
            for target in targets:
                path = in_repo(target, tracked, folders)
                if path and not any(inside(path, folder) for folder in allowed):
                    hits.append((rel, f"Guardrail boundary of {module}: it imports {path}, which is outside "
                                      f"{', '.join(allowed)}. {rule['why']}"))
    return hits


def check(repo: Path, files: list[str], config: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """(hits, problems of the block). Every hit is an error of the standard check."""
    found = problems(config)
    if found:
        return [], found
    block = config.get("guardrails") or {}
    return (forbidden_hits(repo, files, block.get("forbidden") or [])
            + boundary_hits(repo, files, block.get("boundaries") or [], block.get("aliases") or {})), []
