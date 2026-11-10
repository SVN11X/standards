#!/usr/bin/env python3
"""Read-only inventory of a web project, with static design measures. It never changes files and never uses the network."""
import argparse
import json
import re
from pathlib import Path

SKIP = {".git", "node_modules", ".next", ".astro", ".venv", "venv", "dist", "build", ".cache", "coverage",
        ".svelte-kit", "out", ".standards"}
CONFIG = {"package.json", "astro.config.mjs", "astro.config.ts", "vite.config.ts", "vite.config.js",
          "next.config.js", "next.config.mjs", "svelte.config.js", "tailwind.config.js", "tailwind.config.ts",
          "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb", "CNAME", "robots.txt",
          "sitemap.xml", "AGENTS.md", "DESIGN.md", ".standard.yml"}
ASSETS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".mp4", ".webm", ".woff", ".woff2", ".glb", ".gltf"}
LOCKFILES = ["pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb"]


GENERIC_FONTS = {"serif", "sans-serif", "monospace", "system-ui", "cursive", "fantasy", "ui-sans-serif", "ui-serif", "ui-monospace",
                 "inherit", "initial", "unset", "-apple-system", "blinkmacsystemfont", "emoji", "math"}
FONT = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
COLOR = re.compile(r"#[0-9a-f]{3,8}\b|(?:rgba?|hsla?|oklch|oklab|lab|lch)\([^)]*\)", re.I)
DURATION = re.compile(r"(?:transition|animation)(?:-duration)?\s*:[^;}{]*?\b(\d*\.?\d+m?s)\b", re.I)
TOKEN_TIME = re.compile(r"\b(\d*\.?\d+m?s)\b")


def milliseconds(value: str) -> float:
    return float(value[:-2]) if value.endswith("ms") else float(value[:-1]) * 1000


def design_measures(root: Path) -> dict:
    """Layer 1 of the design judgment that needs no browser. Every finding carries the file, the value and the limit."""
    findings, fonts, colors = [], set(), set()
    add = lambda check, file, value, limit: findings.append({"check": check, "layer": "measured", "file": file, "value": value, "limit": limit})  # noqa: E731
    design = root / "DESIGN.md"
    tokens = {milliseconds(t) for t in TOKEN_TIME.findall(design.read_text(encoding="utf-8", errors="ignore"))} if design.is_file() else set()
    reduced_in_css = False
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or any(part in SKIP for part in rel.parts) or path.suffix.lower() not in {".css", ".scss", ".html", ".htm", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
            continue
        if path.stat().st_size > 1_000_000 or ".min." in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        name, suffix = str(rel).replace("\\", "/"), path.suffix.lower()
        for declared in FONT.findall(text):
            first = declared.split(",")[0].strip().strip("\"'").lower()
            if first and first not in GENERIC_FONTS and not first.startswith("var("):
                fonts.add(first)
        colors.update(c.lower().replace(" ", "") for c in COLOR.findall(text) if suffix in {".css", ".scss", ".html", ".htm", ".vue", ".svelte"})
        if "prefers-reduced-motion" in text and suffix in {".css", ".scss", ".html", ".htm", ".vue", ".svelte"}:
            reduced_in_css = True
        if tokens:
            off = sorted({d for d in DURATION.findall(text) if milliseconds(d) not in tokens and milliseconds(d) > 1})
            if off:
                add("duration-outside-tokens", name, ", ".join(off), "the durations in DESIGN.md")
        if "requestAnimationFrame" in text and "prefers-reduced-motion" not in text:
            add("script-ignores-reduced-motion", name, "requestAnimationFrame without reading prefers-reduced-motion", "read the setting in the loop")
        if suffix in {".html", ".htm"}:
            if re.search(r"<html\b", text, re.I) and not re.search(r"<html\b[^>]*\blang=", text, re.I):
                add("missing-lang", name, "html without lang", "a lang attribute")
            images = re.findall(r"<img\b[^>]*>", text, re.I)
            no_alt = sum(1 for tag in images if not re.search(r"\balt=", tag, re.I))
            no_size = sum(1 for tag in images if not (re.search(r"\bwidth=", tag, re.I) and re.search(r"\bheight=", tag, re.I)))
            if no_alt:
                add("image-without-alt", name, f"{no_alt} of {len(images)} images", "alt on every image")
            if no_size:
                add("image-without-size", name, f"{no_size} of {len(images)} images", "width and height on every image")
            levels = [int(level) for level in re.findall(r"<h([1-6])\b", text, re.I)]
            jumps = [f"h{a} to h{b}" for a, b in zip(levels, levels[1:]) if b > a + 1]
            if jumps:
                add("heading-order", name, ", ".join(jumps[:3]), "no skipped heading level")
    if len(fonts) > 2:
        add("font-families", "(all files)", ", ".join(sorted(fonts)), "2 families")
    if fonts or colors:
        if not reduced_in_css:
            add("no-reduced-motion-rule", "(all files)", "no prefers-reduced-motion in the styles", "one rule that turns motion off")
    return {"font_families": sorted(fonts), "distinct_colors": len(colors), "findings": findings}


def analyze(folder: Path) -> dict:
    root = folder.resolve()
    result = {"folder": str(root), "config_files": [], "dependencies": {}, "scripts": {},
              "top_folders": [], "large_assets": [], "files_by_extension": {}, "notes": []}
    result["top_folders"] = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name not in SKIP)
    result["config_files"] = sorted(name for name in CONFIG if (root / name).is_file())
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.relative_to(root).parts):
            continue
        suffix = path.suffix.lower() or "(none)"
        result["files_by_extension"][suffix] = result["files_by_extension"].get(suffix, 0) + 1
        if suffix in ASSETS:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size >= 500_000:
                result["large_assets"].append({"path": str(path.relative_to(root)), "MiB": round(size / 1048576, 2)})
    result["large_assets"] = sorted(result["large_assets"], key=lambda item: -item["MiB"])[:30]
    package = root / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            result["dependencies"] = dict(sorted({**data.get("dependencies", {}), **data.get("devDependencies", {})}.items()))
            result["scripts"] = data.get("scripts", {})
        except (OSError, ValueError) as error:
            result["notes"].append(f"Could not read package.json: {error}")
    if (root / "next.config.js").exists() or (root / "next.config.mjs").exists():
        result["notes"].append("Next.js: check static export. Server rendering does not run on GitHub Pages.")
    if package.is_file() and not any((root / name).exists() for name in LOCKFILES):
        result["notes"].append("No lockfile at the root. Confirm the package manager.")
    if not (root / ".github" / "workflows").exists():
        result["notes"].append("No .github/workflows folder. Confirm how the site is deployed.")
    if not (root / "DESIGN.md").exists():
        result["notes"].append("No DESIGN.md. Ask the owner for visual direction or label visual work as a draft.")
    result["design"] = design_measures(root)
    result["notes"].append("The design findings are measured from the files. measure_page.mjs measures contrast, touch targets and overflow in a browser.")
    result["notes"].append("This inventory does not replace functional tests, Lighthouse, security or visual review.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", default=".", help="Root of the web project (read only)")
    args = parser.parse_args()
    root = Path(args.folder)
    if not root.is_dir():
        parser.error("The folder does not exist.")
    print(json.dumps(analyze(root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
