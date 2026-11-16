#!/usr/bin/env python3
"""Visual assets: find open-licensed images, attach them with their credit and alt text, and audit a site's media.

search   asks Openverse and Wikimedia Commons, which both return the license and the author of every file.
         Only licenses that allow commercial use and changes are kept unless the owner allows more.
attach   downloads one result into the repository, writes its credit to a credits file and refuses an image
         with no alt text (or no --decorative), no license or a license the owner did not allow.
audit    reads the HTML and Markdown of a repository: images without alt text or size, heavy files, files no
         credit covers, SVG with scripts, and video without captions or poster.

The search sends the query words to Openverse (WordPress) or Wikimedia. Nothing else leaves the machine.

Usage: python scripts/media.py search "QUERY" [--source openverse|commons|all] [--limit N] [--allow nc,nd] [--json]
       python scripts/media.py attach URL_OR_RESULT_JSON --to PATH --alt "TEXT" [--credits FILE]
       python scripts/media.py audit [DIR] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "standards/media/v1"
USER_AGENT = "standards-media/1 (https://github.com/SVN11X/standards)"
OPENVERSE = "https://api.openverse.org/v1/images/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
CREDITS = Path("assets") / "CREDITS.json"
# Openverse license codes (api/api/constants/licenses.py). Kept by default: commercial use and changes allowed.
DEFAULT_LICENSES = ("cc0", "pdm", "by", "by-sa")
EXTRA = {"nc": ("by-nc", "by-nc-sa"), "nd": ("by-nd",), "nc-nd": ("by-nc-nd",)}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".m4v"}
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "coverage", "vendor", ".astro", ".next"}
HEAVY_IMAGE = 300_000
HEAVY_VIDEO = 5_000_000


class MediaError(RuntimeError):
    """The request is refused: no license, a license the owner did not allow, or no alt text."""


def http_json(url: str, timeout: float = 20.0) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed hosts above)
        return json.loads(response.read().decode("utf-8"))


def http_bytes(url: str, timeout: float = 60.0, limit: int = 25_000_000) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (only result URLs)
        data = response.read(limit + 1)
    if len(data) > limit:
        raise MediaError(f"the file is larger than {limit // 1_000_000} MB")
    return data


def allowed_licenses(extra: list[str] | None) -> set[str]:
    out = set(DEFAULT_LICENSES)
    for key in extra or []:
        out |= set(EXTRA.get(key.strip(), ()))
    return out


def license_code(short: str) -> str | None:
    """A Commons license name such as "CC BY-SA 4.0" or "Public domain" as an Openverse code."""
    text = (short or "").strip().lower()
    if not text:
        return None
    if text.startswith("cc0"):
        return "cc0"
    if "public domain" in text or text in ("pd", "pdm"):
        return "pdm"
    found = re.match(r"cc[ -](by(?:-nc)?(?:-sa|-nd)?)\b", text)
    return found.group(1) if found else None


def credit_line(item: dict) -> str:
    """The attribution the license asks for: title, author, license and where to find them."""
    who = item.get("creator") or "unknown author"
    name = item.get("license_name") or item.get("license", "").upper()
    return f"\"{item.get('title') or 'Untitled'}\" by {who}, {name}, {item.get('landing_url') or item.get('url')}"


def openverse(query: str, licenses: set[str], limit: int, fetch=http_json) -> list[dict]:
    params = {"q": query, "page_size": min(limit, 20), "license": ",".join(sorted(licenses)), "mature": "false"}
    data = fetch(OPENVERSE + "?" + urllib.parse.urlencode(params))
    out = []
    for row in data.get("results") or []:
        code = str(row.get("license") or "").lower()
        if code not in licenses or not row.get("url"):
            continue
        version = row.get("license_version") or ""
        out.append({"source": "openverse", "id": row.get("id"), "title": row.get("title"), "url": row["url"],
                    "landing_url": row.get("foreign_landing_url"), "creator": row.get("creator"), "creator_url": row.get("creator_url"),
                    "license": code, "license_name": ("CC0" if code == "cc0" else "Public Domain Mark" if code == "pdm"
                                                      else f"CC {code.upper()} {version}".strip()),
                    "license_url": row.get("license_url"), "provider": row.get("provider") or row.get("source"),
                    "width": row.get("width"), "height": row.get("height"), "filetype": row.get("filetype"),
                    "attribution": row.get("attribution")})
    return out


def commons(query: str, licenses: set[str], limit: int, fetch=http_json) -> list[dict]:
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6,
              "gsrlimit": min(limit, 20), "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600}
    data = fetch(COMMONS + "?" + urllib.parse.urlencode(params))
    out = []
    for page in sorted(((data.get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = {k: (v or {}).get("value") for k, v in (info.get("extmetadata") or {}).items()}
        code = license_code(meta.get("LicenseShortName") or "")
        if code not in licenses or not info.get("url"):
            continue
        creator = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist") or "")).strip() or None
        out.append({"source": "commons", "id": page.get("pageid"), "title": re.sub(r"^File:", "", page.get("title") or ""),
                    "url": info.get("thumburl") or info["url"], "original_url": info["url"], "landing_url": info.get("descriptionurl"),
                    "creator": creator, "creator_url": None, "license": code, "license_name": meta.get("LicenseShortName"),
                    "license_url": meta.get("LicenseUrl"), "provider": "wikimedia", "width": info.get("width"),
                    "height": info.get("height"), "filetype": (info.get("mime") or "").split("/")[-1] or None,
                    "attribution": None, "attribution_required": meta.get("AttributionRequired")})
    return out


def search(query: str, source: str = "all", limit: int = 10, extra: list[str] | None = None, fetch=http_json) -> dict:
    licenses = allowed_licenses(extra)
    results, problems = [], []
    for name, finder in (("openverse", openverse), ("commons", commons)):
        if source not in ("all", name):
            continue
        try:
            results += finder(query, licenses, limit, fetch)
        except Exception as error:  # noqa: BLE001 (one source down leaves the other)
            problems.append(f"{name}: {type(error).__name__}: {str(error)[:160]}")
    for item in results:
        item["credit"] = credit_line(item)
    return {"schema": SCHEMA, "query": query, "licenses": sorted(licenses), "results": results[: limit * 2], "problems": problems,
            "leaves_machine": "the query words, sent to Openverse and Wikimedia"}


def read_credits(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("assets") if isinstance(data, dict) and isinstance(data.get("assets"), list) else []


def write_credits(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema": "standards/credits/v1",
            "note": "One entry per file that was not made for this repository. Show the credit wherever the file is shown.",
            "assets": sorted(rows, key=lambda r: r["path"])}
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def attach(item: dict, target: Path, alt: str | None, root: Path, credits: Path | None = None, decorative: bool = False,
           extra: list[str] | None = None, download=http_bytes) -> dict:
    """Save one search result as a repository file with its credit. Refuses what the license or the reader would miss."""
    licenses = allowed_licenses(extra)
    if not item.get("license") or item["license"] not in licenses:
        raise MediaError(f"license {item.get('license')!r} is not allowed. Allowed: {', '.join(sorted(licenses))}")
    if not decorative and not (alt or "").strip():
        raise MediaError("an image needs alt text that says what it shows, or --decorative when it adds nothing")
    if alt and len(alt) > 250:
        raise MediaError("alt text over 250 characters belongs in a caption or the page text")
    if item["license"] not in ("cc0", "pdm") and not item.get("creator"):
        raise MediaError("the license asks for the author and the result names none. Pick another result")
    target = (root / target).resolve() if not target.is_absolute() else target.resolve()
    if not target.is_relative_to(root.resolve()):
        raise MediaError("the file must be saved inside the repository")
    data = download(item["url"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    credits = credits or root / CREDITS
    rel = target.relative_to(root.resolve()).as_posix()
    rows = [r for r in read_credits(credits) if r.get("path") != rel]
    entry = {"path": rel, "title": item.get("title"), "creator": item.get("creator"), "creator_url": item.get("creator_url"),
             "license": item["license"], "license_name": item.get("license_name"), "license_url": item.get("license_url"),
             "source": item.get("source"), "landing_url": item.get("landing_url"), "credit": credit_line(item),
             "alt": None if decorative else alt.strip(), "decorative": decorative, "sha256": hashlib.sha256(data).hexdigest(),
             "retrieved": dt.date.today().isoformat()}
    rows.append(entry)
    write_credits(credits, rows)
    return {"saved": rel, "bytes": len(data), "credits": str(credits), "entry": entry,
            "markup": (f'<img src="{rel}" alt="{html.escape(entry["alt"] or "")}" width="{item.get("width") or ""}" '
                       f'height="{item.get("height") or ""}" loading="lazy">')}


# Audit


def text_files(root: Path) -> list[Path]:
    return [f for f in sorted(root.rglob("*")) if f.suffix.lower() in (".html", ".htm", ".md", ".mdx", ".astro", ".svelte", ".vue", ".jsx", ".tsx")
            and f.is_file() and not any(part in SKIP_DIRS for part in f.relative_to(root).parts) and f.stat().st_size < 3_000_000]


def media_files(root: Path) -> list[Path]:
    return [f for f in sorted(root.rglob("*")) if f.suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES and f.is_file()
            and not any(part in SKIP_DIRS for part in f.relative_to(root).parts)]


def attr(tag: str, name: str) -> str | None:
    found = re.search(r"\b" + name + r"\s*=\s*(\"([^\"]*)\"|'([^']*)'|\{[^}]*\}|([^\s>]+))", tag, re.I)
    if not found:
        return None
    return next((g for g in found.groups()[1:] if g is not None), found.group(1))


CREDIT_FILES = re.compile(r"(^|/)(credits|attribution|attributions|notice|third[-_]party[-_]notices|acknowledg\w*)(\.[\w.]+)?$", re.I)


def credit_sources(root: Path, credits: Path) -> tuple[set[str], list[str], list[str]]:
    """(paths credited in the credits file, text of credit pages, globs of REUSE annotations)."""
    known = {r.get("path") for r in read_credits(credits) if r.get("path")}
    pages = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and CREDIT_FILES.search(rel) and not any(part in SKIP_DIRS for part in path.relative_to(root).parts) \
                and path.suffix.lower() in ("", ".md", ".txt", ".html", ".htm", ".json") and path != credits:
            pages.append(path.read_text(encoding="utf-8", errors="ignore"))
    globs = []
    reuse = root / "REUSE.toml"
    if reuse.is_file():
        globs += re.findall(r'path\s*=\s*\[?\s*"([^"]+)"', reuse.read_text(encoding="utf-8", errors="ignore"))
    dep5 = root / ".reuse" / "dep5"
    if dep5.is_file():
        globs += [g for line in dep5.read_text(encoding="utf-8", errors="ignore").splitlines() if line.startswith("Files:")
                  for g in line[6:].split()]
    return known, pages, globs


def code_free(text: str, suffix: str) -> str:
    """Markdown without its code, so an <img> written as an example in a code span is not read as an image."""
    if suffix not in (".md", ".mdx"):
        return text
    text = re.sub(r"```.*?```|~~~.*?~~~", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "``", text)


def audit(root: Path, credits: Path | None = None) -> dict:
    """What a reader or a license would miss in the media of a repository."""
    root = root.resolve()
    issues: dict[str, list[dict]] = {k: [] for k in ("no-alt", "no-size", "vague-alt", "video-no-captions", "video-no-poster",
                                                     "video-autoplay-sound", "heavy", "svg-script", "no-credit")}
    for path in text_files(root):
        text = code_free(path.read_text(encoding="utf-8", errors="ignore"), path.suffix.lower())
        rel = path.relative_to(root).as_posix()
        for match in re.finditer(r"<img\b[^>]*>", text, re.I):
            tag = match.group(0)
            alt = attr(tag, "alt")
            line = text.count("\n", 0, match.start()) + 1
            where = {"file": rel, "line": line, "src": (attr(tag, "src") or "")[:120]}
            if alt is None and not re.search(r'aria-hidden\s*=\s*["\']?true|role\s*=\s*["\']?presentation', tag, re.I):
                issues["no-alt"].append(where)
            elif alt is not None and re.fullmatch(r"\s*(image|imagen|foto|photo|picture|img|icon|icono|logo|graphic|[\w-]+\.(png|jpe?g|webp|svg|gif))\s*", alt, re.I):
                issues["vague-alt"].append({**where, "alt": alt})
            if not (attr(tag, "width") and attr(tag, "height")) and not re.search(r"aspect-ratio", tag, re.I):
                issues["no-size"].append(where)
        for match in re.finditer(r"!\[([^\]]*)\]\(([^)\s]+)", text):
            where = {"file": rel, "line": text.count("\n", 0, match.start()) + 1, "src": match.group(2)[:120]}
            if not match.group(1).strip():
                issues["no-alt"].append(where)
        for match in re.finditer(r"<video\b[^>]*>(.*?)</video>", text, re.I | re.S):
            tag = match.group(0)
            where = {"file": rel, "line": text.count("\n", 0, match.start()) + 1}
            if not re.search(r"<track\b[^>]*kind\s*=\s*[\"']?(captions|subtitles)", tag, re.I) and not re.search(r"\bmuted\b", tag, re.I):
                issues["video-no-captions"].append(where)
            if not attr(tag.split(">")[0], "poster"):
                issues["video-no-poster"].append(where)
            if re.search(r"\bautoplay\b", tag.split(">")[0], re.I) and not re.search(r"\bmuted\b", tag.split(">")[0], re.I):
                issues["video-autoplay-sound"].append(where)
    import fnmatch
    credits = credits or root / CREDITS
    known, pages, globs = credit_sources(root, credits)
    # A credits page that names a folder, such as `assets/icons/`, credits every file in it.
    folders = {m for page in pages for m in re.findall(r"(?<![\w/.:-])((?:[\w.-]+/)+)", page) if not m.startswith(("http", "www."))}
    own = [p for p in known if p and p.endswith("/")] + sorted(folders)
    files = media_files(root)
    uncredited = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        video = path.suffix.lower() in VIDEO_SUFFIXES
        if size > (HEAVY_VIDEO if video else HEAVY_IMAGE) and path.suffix.lower() != ".svg":
            issues["heavy"].append({"file": rel, "bytes": size})
        if path.suffix.lower() == ".svg" and re.search(r"<script\b|\son\w+\s*=", path.read_text(encoding="utf-8", errors="ignore"), re.I):
            issues["svg-script"].append({"file": rel})
        credited = (rel in known or any(rel.startswith(prefix) for prefix in own) or any(fnmatch.fnmatch(rel, g) for g in globs)
                    or any(rel in page or path.name in page for page in pages))
        if not credited:
            uncredited.append({"file": rel})
    if uncredited and not (known or pages or globs):
        issues["no-credits-at-all"] = [{"file": ".", "files": len(uncredited),
                                        "detail": "no credits file, credits page or REUSE annotation in the repository"}]
    else:
        issues["no-credit"] = uncredited
    return {"schema": SCHEMA, "root": str(root), "media_files": len(files), "credits_file": str(credits),
            "credited": len(files) - len(uncredited), "credit_sources": {"file_entries": len(known), "pages": len(pages), "reuse_globs": len(globs)},
            "issues": {k: v for k, v in issues.items() if v},
            "notes": {"no-credit": "a file made for the repository is credited with one entry whose path ends in / for its folder, "
                                   "or license 'own-work'. Third-party files need their real credit",
                      "heavy": f"images over {HEAVY_IMAGE // 1000} KB, videos over {HEAVY_VIDEO // 1_000_000} MB"}}


def summary(report: dict) -> str:
    src = report["credit_sources"]
    lines = [f"{report['media_files']} media files, {report['credited']} credited by {src['file_entries']} credits file entries, "
             f"{src['pages']} credits pages and {src['reuse_globs']} REUSE annotations."]
    for name, rows in report["issues"].items():
        sample = ", ".join(f"{r['file']}:{r['line']}" if "line" in r else r["file"] for r in rows[:4])
        lines.append(f"- {name}: {len(rows)} ({sample})")
    if not report["issues"]:
        lines.append("No finding.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--source", choices=("all", "openverse", "commons"), default="all")
    find.add_argument("--limit", type=int, default=8)
    find.add_argument("--allow", default="", help="also allow nc, nd or nc-nd licenses, comma separated")
    find.add_argument("--json", action="store_true")
    keep = sub.add_parser("attach")
    keep.add_argument("result", help="a search result as JSON, or a file that holds one")
    keep.add_argument("--to", type=Path, required=True)
    keep.add_argument("--alt")
    keep.add_argument("--decorative", action="store_true")
    keep.add_argument("--credits", type=Path)
    keep.add_argument("--allow", default="")
    keep.add_argument("--repo", type=Path, default=Path("."))
    look = sub.add_parser("audit")
    look.add_argument("root", nargs="?", type=Path, default=Path("."))
    look.add_argument("--credits", type=Path)
    look.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "search":
        report = search(args.query, args.source, args.limit, [a for a in args.allow.split(",") if a])
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            for n, item in enumerate(report["results"], 1):
                print(f"{n}. [{item['license_name']}] {item['title']} ({item.get('width')}x{item.get('height')}) {item['landing_url']}")
            for problem in report["problems"]:
                print("unreachable: " + problem)
        return 0 if report["results"] or not report["problems"] else 1
    if args.command == "attach":
        raw = Path(args.result).read_text(encoding="utf-8") if Path(args.result).is_file() else args.result
        try:
            print(json.dumps(attach(json.loads(raw), args.to, args.alt, args.repo.resolve(), args.credits, args.decorative,
                                    [a for a in args.allow.split(",") if a]), indent=2, ensure_ascii=False))
        except (MediaError, ValueError, OSError) as error:
            print(f"refused: {error}")
            return 1
        return 0
    report = audit(args.root, args.credits)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else summary(report))
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
