#!/usr/bin/env python3
"""Repository fingerprint: what a folder is, read from its own files, with the file behind every claim.

The router asks it before choosing tools. It reads `.standard.yml` first, then the manifests and file
names under the folder. It runs no build, installs nothing and sends nothing anywhere. A signal always
names the file that shows it, so a decision can say why a tool was chosen.

The result is cached in ~/.standards/fingerprints, keyed by the commit and by the manifests on disk, so one
request does not read a repository twice.

Usage: python scripts/repo_fingerprint.py [PATH] [--no-cache]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "standards/repo-fingerprint/v1"
SKIP_DIRS = {".git", "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__", ".next", ".astro",
             ".svelte-kit", "vendor", ".pytest_cache", ".ruff_cache", "coverage", ".turbo"}
MAX_FILES = 20000
MAX_READ = 262144
# A package of package.json and the signal it gives.
NODE_PACKAGES = {
    "react": "react", "react-dom": "react", "vue": "vue", "svelte": "svelte", "astro": "astro", "next": "next",
    "vite": "vite", "three": "three", "gsap": "gsap", "leaflet": "leaflet", "zod": "zod", "i18next": "i18next",
    "typescript": "typescript", "vitest": "vitest", "jest": "jest", "@playwright/test": "playwright",
    "playwright": "playwright", "@axe-core/playwright": "axe", "axe-core": "axe", "storybook": "storybook",
    "@storybook/react": "storybook", "@tauri-apps/api": "tauri", "@tauri-apps/cli": "tauri", "electron": "electron",
    "wrangler": "cloudflare-worker", "eslint": "eslint", "tailwindcss": "tailwind",
    "hyperframes": "hyperframes", "remotion": "remotion", "@motion-canvas/core": "motion-canvas", "@mermaid-js/mermaid-cli": "mermaid",
    "mermaid": "mermaid", "sharp": "image-processing", "react-native": "react-native", "expo": "expo", "@lhci/cli": "lighthouse",
    "msw": "msw", "@pact-foundation/pact": "pact", "@redocly/cli": "openapi",
}
PYTHON_PACKAGES = {"pytest": "pytest", "httpx": "http-client", "requests": "http-client", "beautifulsoup4": "scraper",
                   "bs4": "scraper", "playwright": "playwright", "ruff": "ruff", "pyright": "pyright", "pandas": "dataframe",
                   "pywinauto": "pywinauto", "nbval": "nbval", "manim": "manim", "pillow": "image-processing",
                   "pandera": "data-validation", "duckdb": "duckdb", "dvc": "dvc", "dbt-core": "dbt", "sqlfluff": "sql",
                   "pytesseract": "ocr", "matplotlib": "charts", "plotly": "charts"}
# A file name pattern and the signal it gives. The first tracked file that matches is the evidence.
NAME_SIGNALS = [
    (r"(^|/)package\.json$", "node"), (r"(^|/)pnpm-workspace\.yaml$", "monorepo"), (r"(^|/)tsconfig[^/]*\.json$", "typescript"),
    (r"\.tsx?$", "typescript"), (r"(^|/)(pyproject\.toml|setup\.py|requirements[^/]*\.txt)$", "python"), (r"\.py$", "python"),
    (r"(^|/)go\.mod$", "go"), (r"(^|/)Cargo\.toml$", "rust"), (r"(^|/)src-tauri/", "tauri"), (r"\.(csproj|sln)$", "dotnet"),
    (r"\.ps1$", "powershell"), (r"\.tex$", "latex"), (r"\.bib$", "bibliography"),
    (r"\.kicad_(pcb|sch|pro)$", "kicad"), (r"(^|/)platformio\.ini$", "firmware"), (r"\.tf$", "terraform"),
    (r"(^|/)(Dockerfile|docker-compose\.ya?ml|compose\.ya?ml)$", "docker"), (r"(^|/)wrangler\.(toml|jsonc?)$", "cloudflare-worker"),
    (r"(^|/)\.github/workflows/[^/]+\.ya?ml$", "ci"), (r"(^|/)(manifest\.webmanifest|sw\.js|service-worker\.js)$", "pwa"),
    (r"\.ipynb$", "notebook"), (r"\.(sqlite3?|db)$", "sqlite"), (r"_windows\.go$", "windows"), (r"\.(rc|manifest)$", "windows"),
    (r"(^|/)(tests?|__tests__|e2e)/", "tests"), (r"(\.test\.[cm]?[jt]sx?|\.spec\.[cm]?[jt]sx?|_test\.go|(^|/)test_[^/]+\.py)$", "tests"),
    (r"(^|/)index\.html$", "html"), (r"\.svelte$", "svelte"), (r"\.astro$", "astro"), (r"\.vue$", "vue"),
    # Learning content: question banks, lessons and flashcards kept as data.
    (r"(^|/)[^/]*(question|quiz|exam|lesson|flashcard|pregunta|leccion|lección|curated|imported_q)[^/]*\.(json|ya?ml)$", "learning-content"),
    # Media and the sources diagrams are drawn from.
    (r"\.(png|jpe?g|webp|avif|gif)$", "images"), (r"\.svg$", "images"), (r"\.(mp4|webm|mov|m4v)$", "video"), (r"\.vtt$", "captions"),
    (r"\.(mmd|mermaid)$", "mermaid"), (r"\.d2$", "d2"), (r"\.drawio$", "drawio"), (r"\.(dot|gv)$", "graphviz"),
    (r"\.excalidraw$", "excalidraw"),
    # Kinds of project the owner's guide of 2026-11-15 names.
    (r"(^|/)(openapi|swagger)[^/]*\.(ya?ml|json)$", "openapi"), (r"(^|/)AndroidManifest\.xml$", "android"),
    (r"(^|/)build\.gradle(\.kts)?$", "android"), (r"\.xcodeproj/", "ios"), (r"(^|/)Podfile$", "ios"),
    (r"(^|/)project\.godot$", "godot"), (r"(^|/)ProjectSettings/ProjectVersion\.txt$", "unity"),
    (r"(^|/)dbt_project\.ya?ml$", "dbt"), (r"\.sql$", "sql"), (r"(^|/)(Chart\.ya?ml|kustomization\.ya?ml)$", "kubernetes"),
    (r"\.Tests\.ps1$", "pester"), (r"(^|/)(lighthouserc|\.lighthouserc)[^/]*$", "lighthouse"),
    (r"(^|/)_quarto\.ya?ml$|\.qmd$", "quarto"), (r"(^|/)mkdocs\.ya?ml$", "markdown-docs"), (r"(^|/)\.vale\.ini$", "vale"),
    (r"(^|/)REUSE\.toml$|(^|/)\.reuse/dep5$", "reuse"),
]
# Text inside Go or Python source that only makes sense on Windows.
WINDOWS_CODE = re.compile(r"golang\.org/x/sys/windows|syscall\.NewLazyDLL|ctypes\.windll|\bimport winreg\b|\bimport win32\w+|"
                          r"\bfrom win32\w+ import|\bimport tkinter\b|\bfrom tkinter import")
MANIFESTS = re.compile(r"(^|/)(package\.json|pyproject\.toml|go\.mod|Cargo\.toml|requirements[^/]*\.txt|\.standard\.yml|"
                       r"pnpm-workspace\.yaml|platformio\.ini|wrangler\.(toml|jsonc?))$")
PROJECT_FILES = re.compile(r"(^|/)(package\.json|pyproject\.toml|go\.mod|Cargo\.toml)$")


def home() -> Path:
    path = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")
    path.mkdir(parents=True, exist_ok=True)
    return path


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_root(path: Path) -> Path:
    """The git root that holds the path, or the path itself when it is in no repository."""
    path = path if path.is_dir() else path.parent
    top = git(path, "rev-parse", "--show-toplevel")
    return Path(top) if top else path.resolve()


def list_files(root: Path) -> list[str]:
    """Tracked and untracked files that git does not ignore. Without git, a bounded walk."""
    out = git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if out is not None:
        return [line for line in out.splitlines() if line][:MAX_FILES]
    found: list[str] = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            found.append((Path(folder) / name).relative_to(root).as_posix())
            if len(found) >= MAX_FILES:
                return found
    return found


def read(root: Path, name: str) -> str:
    try:
        with (root / name).open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(MAX_READ)
    except OSError:
        return ""


def read_standard(root: Path) -> dict:
    """The owner's declaration in .standard.yml. Declared values count before anything the files suggest."""
    path = root / ".standard.yml"
    if not path.is_file():
        return {"present": False, "profile": None, "experience": None, "privacy": None, "parts": []}
    text = read(root, ".standard.yml")
    try:
        import yaml
        data = yaml.safe_load(text) or {}
    except Exception:  # noqa: BLE001 (no PyYAML, or a file being edited: read the plain top-level keys)
        data = {m.group(1): m.group(2).strip().strip("'\"") for m in re.finditer(r"(?m)^(\w+):[ \t]*([^\n#]+)", text)}
    options = data.get("options") if isinstance(data.get("options"), dict) else {}
    parts = data.get("parts") if isinstance(data.get("parts"), list) else []
    return {"present": True, "profile": data.get("profile"), "experience": options.get("experience"),
            "privacy": data.get("privacy"),
            "parts": [{"path": str(p.get("path")), "profile": p.get("profile")} for p in parts if isinstance(p, dict)]}


def node_facts(root: Path, name: str) -> tuple[list[str], dict]:
    try:
        data = json.loads(read(root, name) or "{}")
    except ValueError:
        return [], {}
    if not isinstance(data, dict):
        return [], {}
    packages = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    signals = sorted({NODE_PACKAGES[p] for p in packages if p in NODE_PACKAGES})
    if data.get("workspaces"):
        signals.append("monorepo")
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    runner = "pnpm" if (root / Path(name).parent / "pnpm-lock.yaml").exists() or (root / "pnpm-lock.yaml").exists() else "npm"
    commands = {key: f"{runner} run {key}" if key != "test" else f"{runner} test"
                for key in ("test", "build", "lint", "check", "typecheck") if scripts.get(key)}
    return signals, commands


def python_facts(root: Path, name: str) -> list[str]:
    text = read(root, name).lower()
    return sorted({signal for package, signal in PYTHON_PACKAGES.items()
                   if re.search(r"(?m)(^|[\"'\s\[,])" + re.escape(package) + r"\b", text)})


def collect(root: Path, files: list[str], prefix: str = "") -> tuple[list[dict], dict]:
    """Signals and commands of the files under a folder. `prefix` is that folder, relative to the root."""
    scoped = [f for f in files if f.startswith(prefix)] if prefix else files
    found: dict[str, str] = {}

    def add(signal: str, evidence: str) -> None:
        found.setdefault(signal, evidence)

    commands: dict[str, str] = {}
    for name in scoped:
        for pattern, signal in NAME_SIGNALS:
            if signal not in found and re.search(pattern, name):
                add(signal, name)
    here = prefix.rstrip("/")
    for name in scoped:
        folder = name.rsplit("/", 1)[0] if "/" in name else ""
        base = name.rsplit("/", 1)[-1]
        if base == "package.json":
            signals, scripts = node_facts(root, name)
            for signal in signals:
                add(signal, name)
            if folder == here:
                commands.update(scripts)
        elif base == "pyproject.toml" or base.startswith("requirements"):
            for signal in python_facts(root, name):
                add(signal, name)
    # What to install before the test command can run, read from the lockfiles and requirement files of this folder.
    here_files = {n.rsplit("/", 1)[-1] for n in scoped if (n.rsplit("/", 1)[0] if "/" in n else "") == here}
    install = []
    if "pnpm-lock.yaml" in here_files:
        install.append("pnpm install --frozen-lockfile")
    elif "package-lock.json" in here_files:
        install.append("npm ci")
    elif "package.json" in here_files and not prefix:
        # A package below the root without its own lockfile is installed by the root, as in a workspace.
        install.append("npm install")
    install += [f"python -m pip install -r {(here + '/') if here else ''}{n}" for n in sorted(here_files)
                if re.fullmatch(r"requirements[^/]*\.txt", n)]
    src_layout = any(n.startswith((here + "/src/") if here else "src/") for n in scoped)
    if "pyproject.toml" in here_files and (src_layout or not any("requirements" in i for i in install)):
        # A package under src/ is importable by its tests only once it is installed.
        install.append("python -m pip install -e " + (here or "."))
    if install:
        commands["install"] = " && ".join(install) if len(install) == 1 else install
    if "python" in found and "pytest" in found and "test" not in commands:
        commands["test"] = "python -m pytest -q"
    if "python" in found and "test" not in commands:
        # Tests written with unittest need no runner in the requirements, so the test files themselves are the evidence.
        for name in scoped:
            folder = name.rsplit("/", 1)[0] if "/" in name else ""
            if re.search(r"(^|/)test_[^/]+\.py$", name) and re.search(r"(?m)^\s*(import unittest|from unittest\b)", read(root, name)[:8192]):
                start = folder[len(prefix):] if prefix and folder.startswith(prefix) else folder
                commands["test"] = f"python -m unittest discover -s {start or '.'}"
                add("unittest", name)
                break
    if "go" in found:
        commands.setdefault("test", "go test ./...")
    if "rust" in found and "node" not in found:
        commands.setdefault("test", "cargo test --quiet")
    checked = 0
    for name in scoped:
        if "windows" in found or checked >= 200:
            break
        if name.endswith((".go", ".py")):
            checked += 1
            if WINDOWS_CODE.search(read(root, name)[:65536]):
                add("windows", name)
    # A page with no build step: HTML without a package manifest beside it.
    if "html" in found and "node" not in found:
        add("static-web", found["html"])
    if found.keys() & {"react", "vue", "svelte", "astro", "next", "vite", "static-web", "pwa", "html"}:
        add("web", next(found[s] for s in ("react", "vue", "svelte", "astro", "next", "vite", "static-web", "pwa", "html") if s in found))
    if found.keys() & {"tauri", "electron", "dotnet"} or ("windows" in found and "web" not in found):
        add("desktop", next(found[s] for s in ("tauri", "electron", "dotnet", "windows") if s in found))
    return [{"id": signal, "evidence": evidence} for signal, evidence in sorted(found.items())], commands


def subprojects(root: Path, files: list[str]) -> list[dict]:
    """Folders below the root that are projects of their own: they hold a manifest, or a page without one.

    A page counts only where no manifest above it builds it: the src/index.html of a site with a package.json
    at its root is that site, not a second project."""
    folders = sorted({f.rsplit("/", 1)[0] for f in files if "/" in f and PROJECT_FILES.search(f)})
    if any(PROJECT_FILES.search(f) and "/" not in f for f in files):
        pages = []
    else:
        pages = sorted({f.rsplit("/", 1)[0] for f in files if f.endswith("/index.html")})
    folders += [p for p in pages if not any(p == f or p.startswith(f + "/") for f in folders)]
    # A project inside another project is part of it, so only the outermost folders count.
    top = [f for f in sorted(set(folders)) if not any(f.startswith(o + "/") for o in folders if o != f)]
    out = []
    for folder in top[:40]:
        signals, commands = collect(root, files, folder + "/")
        out.append({"path": folder, "signals": signals, "commands": commands})
    return out


def cache_key(root: Path, revision: str | None, files: list[str]) -> str:
    digest = hashlib.sha256((revision or "no-git").encode())
    for name in sorted(f for f in files if MANIFESTS.search(f)):
        try:
            stat = (root / name).stat()
            digest.update(f"{name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        except OSError:
            digest.update(f"{name}:gone".encode())
    digest.update(str(len(files)).encode())
    return digest.hexdigest()[:20]


def fingerprint(path: Path, use_cache: bool = True) -> dict:
    """What the repository that holds `path` is. Every signal names the file that shows it."""
    root = repo_root(Path(path).resolve())
    files = list_files(root)
    revision = git(root, "rev-parse", "HEAD")
    key = cache_key(root, revision, files)
    saved = home() / "fingerprints" / (hashlib.sha256(str(root).encode()).hexdigest()[:16] + ".json")
    if use_cache and saved.is_file():
        try:
            old = json.loads(saved.read_text(encoding="utf-8"))
            if old.get("key") == key and old.get("schema") == SCHEMA:
                return {**old, "cached": True}
        except (OSError, ValueError):
            pass
    signals, commands = collect(root, files)
    data = {"schema": SCHEMA, "key": key, "root": str(root), "name": root.name, "revision": revision,
            "standard": read_standard(root), "signals": signals, "commands": commands,
            "subprojects": subprojects(root, files), "readme": any(f.lower() == "readme.md" for f in files),
            "files": len(files), "cached": False}
    try:
        saved.parent.mkdir(parents=True, exist_ok=True)
        tmp = saved.with_name(f"{saved.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, saved)
    except OSError:
        pass
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(fingerprint(Path(args.path), use_cache=not args.no_cache), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
