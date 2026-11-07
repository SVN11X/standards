#!/usr/bin/env python3
"""Read-only inventory of a web project. It never changes files and never uses the network."""
import argparse
import json
from pathlib import Path

SKIP = {".git", "node_modules", ".next", ".astro", ".venv", "venv", "dist", "build", ".cache", "coverage",
        ".svelte-kit", "out", ".standards"}
CONFIG = {"package.json", "astro.config.mjs", "astro.config.ts", "vite.config.ts", "vite.config.js",
          "next.config.js", "next.config.mjs", "svelte.config.js", "tailwind.config.js", "tailwind.config.ts",
          "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb", "CNAME", "robots.txt",
          "sitemap.xml", "AGENTS.md", "DESIGN.md", ".standard.yml"}
ASSETS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".mp4", ".webm", ".woff", ".woff2", ".glb", ".gltf"}
LOCKFILES = ["pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb"]


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
