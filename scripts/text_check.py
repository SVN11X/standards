#!/usr/bin/env python3
"""Text check: is a page written so its reader can understand it and act on it.

Two kinds of evidence, kept apart on purpose:

- measures a program can take (`check`): sentence length, long sentences and paragraphs, a readability score
  in the language of the text (Szigriszt-Pazos with the INFLESZ scale for Spanish, Flesch for English), acronyms
  used before they are defined, vague link text and passive voice. They are proxies. A text can score well and
  still not help, and a precise technical text can score low.
- what people did (`protocol` and `evidence`): a comprehension test with real readers of the audience. A page
  is proven to help only by this: people do the task the page is for and answer its questions.

Usage: python scripts/text_check.py check PATH [PATH...] [--lang es|en] [--audience general|expert] [--json]
       python scripts/text_check.py protocol PAGE --task "TEXT" [--out DIR]
       python scripts/text_check.py evidence [DIR] [--pages PAGE...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA = "standards/text-check/v1"
EVIDENCE_DIR = Path("docs") / "evidence" / "comprehension"
TEXT_SUFFIXES = {".md", ".mdx", ".markdown", ".txt", ".html", ".htm", ".json"}
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "coverage", "vendor", ".astro"}
STOP = {"es": set("de la que el en y a los se del las un por con no una su para es al lo como más pero sus le ya o este sí "
                  "porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante".split()),
        "en": set("the of and to in is that for it as with was on be at by this are or from an which you can not have "
                  "but they his her she we will your has more if their its do when there".split())}
# Score bands. Spanish: INFLESZ (Barrio-Cantalejo et al. 2008). English: Flesch (1948).
BANDS = {"es": [(40, "muy difícil"), (55, "algo difícil"), (65, "normal"), (80, "bastante fácil"), (999, "muy fácil")],
         "en": [(30, "very difficult"), (50, "difficult"), (60, "fairly difficult"), (70, "plain English"), (80, "fairly easy"),
                (90, "easy"), (999, "very easy")]}
# Below these scores the text is reported as hard for its audience.
FLOOR = {("es", "general"): 55, ("es", "expert"): 40, ("en", "general"): 50, ("en", "expert"): 30}
LONG_SENTENCE = 25
VERY_LONG_SENTENCE = 40
LONG_PARAGRAPH = 120
VAGUE_LINKS = re.compile(r"^(click here|here|read more|more|link|this link|aquí|aqui|haz clic aquí|pincha aquí|clic aquí|más|"
                         r"más información|leer más|ver más|enlace|este enlace)$", re.I)
PASSIVE = {"en": re.compile(r"\b(is|are|was|were|be|been|being)\s+(\w+ed|\w+en|made|built|done|given|known|seen|shown|written)\b", re.I),
           "es": re.compile(r"\b(es|son|fue|fueron|era|eran|ser|sido|será|serán|sea|sean)\s+\w+(ado|ada|ados|adas|ido|ida|idos|idas)\b", re.I)}
COMMON_ACRONYMS = {"OK", "PDF", "URL", "ID", "FAQ", "USB", "PC", "TV", "UTC", "AM", "PM", "EU", "UE", "UK", "US", "EE", "UU", "N/A",
                   "HTML", "CSS", "JSON", "CSV", "PNG", "JPG", "SVG", "MP4", "GIF", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI"}
SOURCES = {
    "sentences": "GOV.UK content design, https://www.gov.uk/guidance/content-design/writing-for-gov-uk",
    "readability-es": "Barrio-Cantalejo et al. 2008, INFLESZ, Anales del Sistema Sanitario de Navarra 31(2):135-152",
    "readability-en": "Flesch 1948, https://doi.org/10.1037/h0057532",
    "plain-language": "ISO 24495-1:2023, https://www.iso.org/standard/78907.html",
    "links": "WCAG 2.2, Link Purpose (In Context), https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html",
    "abbreviations": "WCAG 2.2, Abbreviations, https://www.w3.org/WAI/WCAG22/Understanding/abbreviations.html",
    "people": "Nielsen 2000, https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/",
}


# Reading text out of files


def strip_markdown(text: str) -> str:
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    # Inline code reads as one word. It is capitalized so a sentence that starts with it is still split.
    text = re.sub(r"`[^`\n]*`", " Code ", text)
    return re.sub(r"(?<![(\w])https?://[^\s)>\]]+", " ", text)


def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style|svg|code|pre|noscript)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"</(p|div|li|h[1-6]|section|article|tr|br|header|footer|blockquote|figcaption|dd|dt)>|<br\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n\n" + "#" * int(m.group(1)) + " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return text


def json_text(data, out: list[str]) -> None:
    """Strings of a content file that read as prose: six words or more, not a URL or an id."""
    if isinstance(data, str):
        if len(data.split()) >= 6 and not re.match(r"^\s*(https?://|[\w.-]+/[\w./-]+$)", data):
            out.append(strip_html(strip_markdown(data)))
    elif isinstance(data, dict):
        for value in data.values():
            json_text(value, out)
    elif isinstance(data, list):
        for value in data:
            json_text(value, out)


def links(raw: str) -> list[str]:
    found = [m.group(1) for m in re.finditer(r"(?<!!)\[([^\]]+)\]\([^)]+\)", raw)]
    found += [re.sub(r"<[^>]+>", "", m.group(1)).strip() for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", raw, flags=re.S | re.I)]
    return [t.strip() for t in found if t.strip()]


def read(path: Path) -> tuple[str, list[str]]:
    """(text, link texts). Headings stay as lines that start with #."""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".json":
        try:
            parts: list[str] = []
            json_text(json.loads(raw), parts)
            return "\n\n".join(parts), []
        except ValueError:
            return "", []
    texts = links(raw)
    if path.suffix in (".html", ".htm"):
        return strip_html(raw), texts
    text = strip_markdown(raw)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = strip_html(text) if "<" in text else text
    return text, texts


def collect(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files += [f for f in sorted(path.rglob("*")) if f.suffix in TEXT_SUFFIXES and f.is_file()
                      and not any(part in SKIP_DIRS for part in f.parts) and f.stat().st_size < 3_000_000]
    return files


# Counting


def words_of(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", text)


def language(text: str) -> str:
    tokens = [w.lower() for w in words_of(text)]
    es = sum(1 for w in tokens if w in STOP["es"]) + 2 * len(re.findall(r"[ñáéíóú¿¡]", text.lower()))
    en = sum(1 for w in tokens if w in STOP["en"])
    return "es" if es > en else "en"


def syllables_es(word: str) -> int:
    """Syllables of a Spanish word: vowel groups, split where two strong vowels meet or a weak vowel carries the accent."""
    w = word.lower()
    w = re.sub(r"(?<=[qg])u(?=[eiéí])", "", w)
    w = re.sub(r"y$", "i", w)
    strong, accented_weak, vowels = set("aeoáéóàèò"), set("íú"), set("aeiouáéíóúüàèìòù")
    count, previous = 0, None
    for char in w:
        if char in vowels:
            if previous is None:
                count += 1
            elif (char in strong and previous in strong) or char in accented_weak or previous in accented_weak:
                count += 1
            previous = char
        else:
            previous = None
    return max(1, count)


def syllables_en(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|[^laeiouy]ed|[^laeiouy]e)$", lambda m: m.group(0)[0], w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def blocks(text: str) -> list[tuple[str, str]]:
    """(kind, text) for every block: heading, item (a list line) or paragraph."""
    out = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in chunk.strip().splitlines() if line.strip()]
        if not lines:
            continue
        if all(re.match(r"^([-*+]|\d+[.)])\s", line) for line in lines):
            out += [("item", re.sub(r"^([-*+]|\d+[.)])\s+", "", line)) for line in lines]
        elif len(lines) == 1 and re.match(r"^#{1,6}\s", lines[0]):
            out.append(("heading", lines[0].lstrip("# ").strip()))
        elif all(line.startswith("|") for line in lines):
            continue
        else:
            out.append(("paragraph", " ".join(re.sub(r"^#{1,6}\s+", "", line) for line in lines)))
    return out


def sentences_of(paragraph: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+(?=[\"'«¿¡(]?[A-ZÁÉÍÓÚÑ0-9])", paragraph.strip())
    return [p for p in parts if words_of(p)]


def band(lang: str, score: float) -> str:
    return next(label for top, label in BANDS[lang] if score < top)


def acronyms(text: str) -> list[str]:
    """Acronyms whose first use comes with no expansion: neither "Full Name (ACR)" nor "ACR (full name)"."""
    seen, missing = set(), []
    for match in re.finditer(r"\b[A-Z][A-Z0-9]{1,5}s?\b", text):
        token = match.group(0).rstrip("s") if match.group(0).endswith("s") and match.group(0)[:-1].isupper() else match.group(0)
        if token in seen or token in COMMON_ACRONYMS or re.search(r"\d", token) or not re.search(r"[A-Z].*[A-Z]", token):
            continue
        seen.add(token)
        after = text[match.end():match.end() + 3]
        before = text[max(0, match.start() - 2):match.start()]
        if after.lstrip().startswith("(") or before.endswith("("):
            continue
        missing.append(token)
    return missing


def measure(text: str, link_texts: list[str], lang: str | None = None, audience: str = "general", structured: bool = False) -> dict:
    """Measures of one text. `structured` is content an application lays out, such as a JSON lesson file, where
    headings are not part of the text."""
    lang = lang or language(text)
    parts = blocks(text)
    paragraphs = [t for kind, t in parts if kind == "paragraph"]
    units = [s for t in paragraphs for s in sentences_of(t)]
    units += [s for kind, t in parts if kind == "item" and len(words_of(t)) >= 4 for s in sentences_of(t)]
    counts = [len(words_of(s)) for s in units]
    words = [w for s in units for w in words_of(s)]
    out = {"language": lang, "audience": audience, "words": len(words), "sentences": len(units), "headings": sum(1 for k, _ in parts if k == "heading")}
    if not words:
        return {**out, "score": None, "band": None, "findings": []}
    count = syllables_es if lang == "es" else syllables_en
    syllables = sum(count(w) for w in words)
    per_word, per_sentence = syllables / len(words), len(words) / max(1, len(units))
    score = (206.835 - 62.3 * per_word - per_sentence) if lang == "es" else (206.835 - 1.015 * per_sentence - 84.6 * per_word)
    long = [s for s, n in zip(units, counts) if n > LONG_SENTENCE]
    very_long = [s for s, n in zip(units, counts) if n > VERY_LONG_SENTENCE]
    wide = [t for t in paragraphs if len(words_of(t)) > LONG_PARAGRAPH]
    passive = [s for s in units if PASSIVE[lang].search(s)]
    vague = [t for t in link_texts if VAGUE_LINKS.match(t)]
    undefined = acronyms(text)
    out.update(score=round(score, 1), band=band(lang, score), method="Szigriszt-Pazos (INFLESZ scale)" if lang == "es" else "Flesch reading ease",
               words_per_sentence=round(per_sentence, 1), syllables_per_word=round(per_word, 2),
               long_sentences=len(long), very_long_sentences=len(very_long), long_paragraphs=len(wide),
               passive_share=round(len(passive) / len(units), 2), vague_links=vague, undefined_acronyms=undefined[:30])
    findings = []
    floor = FLOOR[(lang, audience)]
    if len(words) >= 100 and score < floor:
        findings.append({"rule": "readability", "detail": f"score {score:.0f} ({band(lang, score)}), below {floor} for a {audience} audience",
                         "source": SOURCES["readability-es" if lang == "es" else "readability-en"]})
    if units and len(long) / len(units) > 0.2:
        findings.append({"rule": "long-sentences", "detail": f"{len(long)} of {len(units)} sentences have more than {LONG_SENTENCE} words",
                         "examples": [s[:160] for s in sorted(long, key=lambda s: -len(words_of(s)))[:3]], "source": SOURCES["sentences"]})
    elif very_long:
        findings.append({"rule": "very-long-sentences", "detail": f"{len(very_long)} sentences have more than {VERY_LONG_SENTENCE} words",
                         "examples": [s[:160] for s in very_long[:3]], "source": SOURCES["sentences"]})
    if wide:
        findings.append({"rule": "long-paragraphs", "detail": f"{len(wide)} paragraphs have more than {LONG_PARAGRAPH} words",
                         "examples": [p[:120] for p in wide[:3]], "source": SOURCES["plain-language"]})
    if len(words) > 400 and not out["headings"] and not structured:
        findings.append({"rule": "no-headings", "detail": f"{len(words)} words with no heading to scan by", "source": SOURCES["plain-language"]})
    if vague:
        findings.append({"rule": "vague-links", "detail": f"{len(vague)} links say only {', '.join(sorted(set(vague))[:4])}", "source": SOURCES["links"]})
    if undefined:
        findings.append({"rule": "acronyms", "detail": f"{len(undefined)} acronyms appear with no expansion at first use: "
                         + ", ".join(undefined[:10]), "source": SOURCES["abbreviations"]})
    if units and len(passive) / len(units) > 0.25:
        findings.append({"rule": "passive", "detail": f"{len(passive)} of {len(units)} sentences read as passive voice (a pattern match, not a parse)",
                         "examples": [s[:140] for s in passive[:2]], "source": SOURCES["plain-language"]})
    out["findings"] = findings
    return out


def check(paths: list[Path], lang: str | None = None, audience: str = "general") -> dict:
    files = []
    for path in collect(paths):
        text, link_texts = read(path)
        result = measure(text, link_texts, lang, audience, structured=path.suffix == ".json")
        if result["words"]:
            files.append({"file": str(path), **result})
    return {"schema": SCHEMA, "files": files,
            "note": "These are proxies. Only a comprehension test with readers of the audience shows that a page helps."}


# People


def slug(path: str) -> str:
    text = unicodedata.normalize("NFKD", path).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "page"


def protocol(page: str, task: str, out: Path) -> Path:
    """A comprehension test card for one page, to fill in with real readers. It holds no result until people do it."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slug(page)}.yml"
    if path.exists():
        raise FileExistsError(f"{path} exists. Add the new readers to it instead of starting over.")
    today = dt.date.today().isoformat()
    path.write_text(f"""# Comprehension test of {page}. Created {today} by scripts/text_check.py protocol.
# Ask five readers of the audience, one at a time, who did not write the page (Nielsen 2000).
# 1. Five seconds: show the page for five seconds, hide it, ask what it is for and what to do first.
# 2. Task: give the task below, say nothing more, watch and note where the reader hesitates.
# 3. Questions: ask the questions below without the page in front of the reader.
# Write what happened, not what the reader said they would do. Change the page, then test again in a new round.
page: {page}
task: {json.dumps(task, ensure_ascii=False)}
# Two to five questions whose answer is on the page, with the answer that counts as right.
questions:
  - ask: ""
    right: ""
rounds:
  - date: ""
    page_version: ""
    readers:
      # One entry per reader. completed: did the reader finish the task without help.
      - who: ""            # role or level only, never a name
        five_seconds: ""   # what the reader said the page is for
        completed: null
        seconds: null
        right_answers: null
        hesitated_at: ""
    decision: ""           # what changes on the page because of this round
""", encoding="utf-8")
    return path


def evidence(folder: Path, pages: list[str] | None = None) -> dict:
    """What the comprehension tests in a folder show. A page counts as tested once five readers finished a round."""
    import yaml
    tests = []
    for path in sorted(folder.glob("*.yml")) if folder.is_dir() else []:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            tests.append({"file": str(path), "problem": f"not valid YAML: {str(error).splitlines()[0]}"})
            continue
        rounds = [r for r in data.get("rounds") or [] if isinstance(r, dict)]
        last = rounds[-1] if rounds else {}
        readers = [r for r in last.get("readers") or [] if isinstance(r, dict) and r.get("completed") is not None]
        questions = [q for q in data.get("questions") or [] if isinstance(q, dict) and str(q.get("ask") or "").strip()]
        done = sum(1 for r in readers if r.get("completed") is True)
        right = [r["right_answers"] / len(questions) for r in readers if isinstance(r.get("right_answers"), (int, float)) and questions]
        state = "not run" if not readers else "too few readers" if len(readers) < 5 else "tested"
        tests.append({"file": str(path), "page": data.get("page"), "task": data.get("task"), "rounds": len(rounds), "readers": len(readers),
                      "completed": done, "completion_rate": round(done / len(readers), 2) if readers else None,
                      "right_answer_rate": round(sum(right) / len(right), 2) if right else None, "state": state,
                      "decision": last.get("decision") or None})
    tested = {t.get("page") for t in tests if t.get("state") == "tested"}
    untested = [p for p in pages or [] if p not in tested]
    return {"schema": SCHEMA, "tests": tests, "untested_pages": untested, "source": SOURCES["people"]}


def summary(report: dict) -> str:
    lines = []
    for item in report["files"]:
        head = (f"{item['file']}: {item['words']} words, {item['language']}, score {item['score']} ({item['band']}), "
                f"{item['words_per_sentence']} words per sentence, {item['long_sentences']} sentences over {LONG_SENTENCE} words")
        lines.append(head)
        lines += [f"  - {f['rule']}: {f['detail']}." for f in item["findings"]]
    lines.append(report["note"])
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("check")
    run.add_argument("paths", nargs="+", type=Path)
    run.add_argument("--lang", choices=("es", "en"))
    run.add_argument("--audience", choices=("general", "expert"), default="general")
    run.add_argument("--json", action="store_true")
    card = sub.add_parser("protocol")
    card.add_argument("page")
    card.add_argument("--task", required=True)
    card.add_argument("--out", type=Path, default=EVIDENCE_DIR)
    seen = sub.add_parser("evidence")
    seen.add_argument("folder", nargs="?", type=Path, default=EVIDENCE_DIR)
    seen.add_argument("--pages", nargs="*")
    args = parser.parse_args(argv)
    if args.command == "protocol":
        try:
            print(protocol(args.page, args.task, args.out))
        except FileExistsError as error:
            print(error)
            return 1
        return 0
    if args.command == "evidence":
        report = evidence(args.folder, args.pages)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    report = check(args.paths, args.lang, args.audience)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
