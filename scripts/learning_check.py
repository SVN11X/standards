#!/usr/bin/env python3
"""Question bank audit: does a set of practice questions help people learn, by rules with a published source.

It finds the questions in JSON files by their shape (a stem, options and a key), whatever the field names,
and reports two kinds of findings:

- integrity errors: a key that names no option, an item with no key, a repeated id or option. They make an
  item wrong for every learner, so they set the exit code.
- learning findings: what the research on practice tests and on writing multiple-choice items says weakens an
  item. Each finding names its rule and its source in RULES. They are evidence for a person to judge.

Usage: python scripts/learning_check.py PATH [PATH...] [--json] [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

SCHEMA = "standards/learning-check/v1"
STEM_KEYS = ("question", "prompt", "stem", "text")
OPTION_KEYS = ("options", "choices", "answers", "alternatives")
KEY_KEYS = ("answer", "correct", "correctAnswer", "correct_answer", "answers_correct", "solution", "key")
EXPLAIN_KEYS = ("explanation", "rationale", "feedback", "why", "solution_explanation")
TOPIC_KEYS = ("category", "domain", "domainId", "topic", "tags", "lesson", "lessonId", "objective", "objectiveIds", "section")
SOURCE_KEYS = ("sources", "references", "sourceIds", "source", "reference")
OPTION_TEXT = ("text", "label", "value", "content", "html")
OPTION_ID = ("id", "letter", "key", "value")
OPTION_WHY = ("explanation", "why", "feedback", "rationale")
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "coverage"}
NAMES = re.compile(r"(question|quiz|exam|bank|pregunta|test|flashcard|lesson|leccion|lección|curated|imported|qa)", re.I)
ALL_ABOVE = re.compile(r"\b(all of the above|todas las anteriores|todas las opciones anteriores)\b", re.I)
NONE_ABOVE = re.compile(r"\b(none of the above|ninguna de las anteriores|ninguna de las opciones anteriores)\b", re.I)
NEGATIVE = re.compile(r"\b(NOT|EXCEPT|NO|EXCEPTO|SALVO|INCORRECTA|FALSE|FALSA)\b")
ASKS_NEGATIVE = re.compile(r"\b(which|what|cuál|cual|cuáles|qué)\b[^?.]{0,90}?\b(not|except|excepto|salvo|no es|no son|no está|"
                           r"no debe|no corresponde|incorrect\w*|false|falsa|falso)\b", re.I)
# Rules with the source that supports them. A finding always names one of these ids.
RULES = {
    "explanation": ("Every item explains why the key is right. Feedback that explains improves learning more than "
                    "feedback that only marks right or wrong.", "Hattie and Timperley 2007, https://doi.org/10.3102/003465430298487"),
    "short-explanation": ("An explanation of fewer than eight words rarely says why. It restates the answer.",
                          "Hattie and Timperley 2007, https://doi.org/10.3102/003465430298487"),
    "distractor-feedback": ("Each wrong option says why it is wrong, so a learner who picked it learns from the mistake.",
                            "Butler and Roediger 2008, https://doi.org/10.3758/MC.36.3.604"),
    "key-position": ("The position of the key is balanced across items. A skewed position lets people answer by pattern.",
                     "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "longest-key": ("Options are similar in length. When the key is often the longest option, length gives it away.",
                    "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "all-of-the-above": ("Avoid 'all of the above'. Recognizing two right options is enough to answer it.",
                         "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "none-of-the-above": ("Use 'none of the above' sparingly. It measures knowing what is wrong, not what is right.",
                          "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "negative-stem": ("Avoid negative stems. When one is needed, the negative word is emphasized in capitals.",
                      "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "few-options": ("A multiple-choice item has three or more plausible options, unless it is a true or false item.",
                    "Haladyna, Downing and Rodriguez 2002, https://doi.org/10.1207/S15324818AME1503_5"),
    "duplicate-stem": ("The same question asked twice under two ids splits the learner's history and the topic counts.",
                       "Roediger and Karpicke 2006, https://doi.org/10.1111/j.1467-9280.2006.01693.x"),
    "topic": ("Every item names its topic, so practice can be spaced over time and mixed across topics.",
              "Cepeda et al. 2006, https://doi.org/10.1037/0033-2909.132.3.354 and Rohrer and Taylor 2007, "
              "https://doi.org/10.1007/s11251-007-9015-8"),
    "thin-topic": ("A topic with fewer than five items gives too little retrieval practice to space or mix.",
                   "Dunlosky et al. 2013, https://doi.org/10.1177/1529100612453266"),
    "source": ("Every item names where its answer can be checked, so a learner can verify it and an editor can fix it.",
               "ISO 24495-1:2023 plain language, https://www.iso.org/standard/78907.html"),
}


def normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", re.sub(r"<[^>]+>", " ", str(text))).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def exact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def question_sentence(stem: str) -> str:
    """The sentence that asks: the last one with a question mark, else the last sentence. A scenario before it
    often says "does not" without asking in the negative."""
    parts = [p.strip() for p in re.split(r"(?<=[.?!:])\s+", stem) if p.strip()]
    asked = [p for p in parts if "?" in p]
    return (asked or parts or [""])[-1]


def plain(value) -> str:
    """Text of a field that may be a string, a dict of languages, or a dict with a text field."""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
    if isinstance(value, dict):
        for key in (*OPTION_TEXT, "en", "es"):
            if isinstance(value.get(key), str):
                return plain(value[key])
        strings = [v for v in value.values() if isinstance(v, str)]
        return plain(strings[0]) if strings else ""
    if isinstance(value, list):
        return " ".join(plain(v) for v in value)
    return "" if value is None else str(value)


def first(item: dict, keys) -> tuple[str | None, object]:
    for key in keys:
        if key in item and item[key] not in (None, "", []):
            return key, item[key]
    return None, None


def is_question(item) -> bool:
    if not isinstance(item, dict):
        return False
    stem = first(item, STEM_KEYS)[1]
    options = first(item, OPTION_KEYS)[1]
    return bool(stem) and isinstance(options, list) and len(options) >= 2


def find_lists(data, where: str = "$") -> list[tuple[str, list]]:
    """Every list in a JSON document whose items are mostly questions."""
    found = []
    if isinstance(data, list):
        if data and sum(is_question(x) for x in data) >= max(1, len(data) // 2):
            return [(where, data)]
        for index, value in enumerate(data[:2000]):
            found += find_lists(value, f"{where}[{index}]")
    elif isinstance(data, dict):
        for key, value in data.items():
            found += find_lists(value, f"{where}.{key}")
    return found


def option_view(options: list) -> list[dict]:
    out = []
    for index, option in enumerate(options):
        if isinstance(option, dict):
            ident = next((option[k] for k in OPTION_ID if isinstance(option.get(k), (str, int)) and k != "value"), None)
            why = next((option[k] for k in OPTION_WHY if option.get(k)), None)
            out.append({"index": index, "id": ident, "text": plain(option), "why": plain(why) if why else ""})
        else:
            out.append({"index": index, "id": None, "text": plain(option), "why": ""})
    return out


def key_indexes(raw, options: list[dict]) -> list[int] | None:
    """Indexes of the keyed options, or None when the key names no option."""
    values = raw if isinstance(raw, list) else [raw]
    found = []
    for value in values:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            if not 0 <= value < len(options):
                return None
            found.append(value)
            continue
        text = str(value).strip()
        match = next((o["index"] for o in options if o["id"] is not None and str(o["id"]).strip().lower() == text.lower()), None)
        if match is None and re.fullmatch(r"[A-Za-z]", text):
            match = ord(text.upper()) - 65 if ord(text.upper()) - 65 < len(options) else None
        if match is None and text.isdigit() and int(text) < len(options):
            match = int(text)
        if match is None:
            match = next((o["index"] for o in options if normal(o["text"]) == normal(text) and o["text"]), None)
        if match is None:
            return None
        found.append(match)
    return sorted(set(found)) or None


def read_items(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    items = []
    for where, rows in find_lists(data):
        for index, row in enumerate(rows):
            if not is_question(row):
                continue
            stem_key, stem = first(row, STEM_KEYS)
            options = option_view(first(row, OPTION_KEYS)[1])
            key_name, key_raw = first(row, KEY_KEYS)
            topic = first(row, TOPIC_KEYS)
            items.append({
                "file": str(path), "where": f"{where}[{index}]", "id": row.get("id"), "type": row.get("type"),
                "stem": plain(stem), "options": options,
                "key": key_indexes(key_raw, options) if key_name else None, "has_key": key_name is not None,
                "explanation": plain(first(row, EXPLAIN_KEYS)[1] or ""),
                "topic": plain(topic[1]) if topic[0] else "", "topic_field": topic[0],
                "sources": bool(first(row, SOURCE_KEYS)[1]),
            })
    return items


def collect(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_file():
            files.append(path)
            continue
        for found in sorted(path.rglob("*.json")):
            if not any(part in SKIP_DIRS for part in found.parts) and NAMES.search(found.name) and found.stat().st_size < 20_000_000:
                files.append(found)
    return files


def finding(rule: str, items: list[dict], detail: str, limit: int = 8) -> dict:
    return {"rule": rule, "count": len(items), "detail": detail, "advice": RULES[rule][0], "source": RULES[rule][1],
            "examples": [{"id": i["id"], "file": i["file"], "where": i["where"], "stem": i["stem"][:120]} for i in items[:limit]]}


def audit(items: list[dict]) -> dict:
    errors, findings = [], []
    if not items:
        return {"schema": SCHEMA, "items": 0, "errors": [], "findings": [], "metrics": {}}
    no_key = [i for i in items if not i["has_key"]]
    bad_key = [i for i in items if i["has_key"] and i["key"] is None]
    if no_key:
        errors.append({"error": "no-key", "count": len(no_key), "detail": "items with no field that names the right option",
                       "examples": [{"id": i["id"], "where": i["where"], "file": i["file"]} for i in no_key[:8]]})
    if bad_key:
        errors.append({"error": "key-names-no-option", "count": len(bad_key), "detail": "items whose key matches none of their options",
                       "examples": [{"id": i["id"], "where": i["where"], "file": i["file"]} for i in bad_key[:8]]})
    ids = Counter(str(i["id"]) for i in items if i["id"] is not None)
    repeated = {k: v for k, v in ids.items() if v > 1}
    if repeated:
        errors.append({"error": "repeated-id", "count": len(repeated), "detail": "ids used by more than one item",
                       "examples": [{"id": k, "times": v} for k, v in list(repeated.items())[:8]]})
    # Case and spaces only: in code options a quote or an asterisk is the whole difference.
    same_options = [i for i in items if len({exact(o["text"]) for o in i["options"] if o["text"]}) < len([o for o in i["options"] if o["text"]])]
    if same_options:
        errors.append({"error": "repeated-option", "count": len(same_options), "detail": "items with two options of the same text",
                       "examples": [{"id": i["id"], "where": i["where"], "file": i["file"]} for i in same_options[:8]]})
    keyed = [i for i in items if i["key"]]
    no_explain = [i for i in items if not i["explanation"] and not all(o["why"] for o in i["options"])]
    if no_explain:
        findings.append(finding("explanation", no_explain, f"{len(no_explain)} of {len(items)} items explain nothing"))
    short = [i for i in items if i["explanation"] and len(i["explanation"].split()) < 8]
    if short:
        findings.append(finding("short-explanation", short, f"{len(short)} explanations have fewer than eight words"))
    with_option_why = [i for i in keyed if any(o["why"] for o in i["options"])]
    missing_why = [i for i in keyed if not all(o["why"] for idx, o in enumerate(i["options"]) if idx not in i["key"])]
    single = [i for i in keyed if len(i["key"]) == 1 and len(i["options"]) >= 3 and i["type"] in (None, "single", "mcq", "multiple-choice")]
    metrics = {"items": len(items), "files": len({i["file"] for i in items}), "with_explanation": len(items) - len(no_explain),
               "with_distractor_feedback": len(keyed) - len(missing_why), "with_topic": sum(1 for i in items if i["topic"]),
               "with_sources": sum(1 for i in items if i["sources"])}
    if with_option_why and missing_why:
        findings.append(finding("distractor-feedback", missing_why, f"{len(missing_why)} items leave a wrong option unexplained"))
    elif not with_option_why and len(keyed) >= 20:
        findings.append({**finding("distractor-feedback", [], "no item says why a wrong option is wrong"), "count": len(keyed)})
    shuffled_by = shuffles_options(items)
    if shuffled_by:
        metrics["options_shuffled_by"] = shuffled_by
    if len(single) >= 20:
        by_count = Counter(len(i["options"]) for i in single)
        k = by_count.most_common(1)[0][0]
        same = [i for i in single if len(i["options"]) == k]
        positions = Counter(i["key"][0] for i in same)
        expected = len(same) / k
        chi = sum((positions.get(p, 0) - expected) ** 2 / expected for p in range(k))
        share = {chr(65 + p): round(positions.get(p, 0) / len(same), 3) for p in range(k)}
        metrics["key_position"] = {"options": k, "items": len(same), "share": share, "chi_square": round(chi, 2),
                                   "critical_0_01": CHI_CRITICAL.get(k - 1)}
        if CHI_CRITICAL.get(k - 1) and chi > CHI_CRITICAL[k - 1] and shuffled_by:
            metrics["key_position"]["note"] = (f"skewed in the data, but {shuffled_by} shuffles the options before showing them, "
                                               "so the learner never sees the stored position")
        elif CHI_CRITICAL.get(k - 1) and chi > CHI_CRITICAL[k - 1]:
            top = max(share, key=share.get)
            findings.append(finding("key-position", [i for i in same if chr(65 + i["key"][0]) == top],
                                    f"in {len(same)} items with {k} options the key is {top} in {share[top]:.0%}, "
                                    f"where {1 / k:.0%} is expected (chi-square {chi:.1f}, p < 0.01)"))
        longest = [i for i in same if max(range(k), key=lambda p: len(i["options"][p]["text"])) == i["key"][0]
                   and sorted(len(o["text"]) for o in i["options"])[-1] > 1.2 * sorted(len(o["text"]) for o in i["options"])[-2]]
        metrics["longest_is_key"] = round(len(longest) / len(same), 3)
        if len(longest) / len(same) > 1.5 / k:
            findings.append(finding("longest-key", longest, f"the key is clearly the longest option in {len(longest)} of {len(same)} "
                                                             f"items ({len(longest) / len(same):.0%}, chance is {1 / k:.0%})"))
    for rule, pattern in (("all-of-the-above", ALL_ABOVE), ("none-of-the-above", NONE_ABOVE)):
        hits = [i for i in items if any(pattern.search(o["text"]) for o in i["options"])]
        if hits:
            findings.append(finding(rule, hits, f"{len(hits)} items offer it"))
    negative = []
    for item in items:
        asked = question_sentence(item["stem"])
        # The negative must be what is asked: "which ... is not", "cuál ... no es". A scenario that "does not" is fine.
        asks = ASKS_NEGATIVE.search(asked)
        if asks and not NEGATIVE.search(asks.group(0)) and not re.search(r"\bnot only\b|\bno solo\b", asked, re.I):
            negative.append(item)
    if negative:
        findings.append(finding("negative-stem", negative, f"{len(negative)} stems ask in the negative without emphasis"))
    few = [i for i in items if len(i["options"]) == 2 and not boolean(i)]
    if few:
        findings.append(finding("few-options", few, f"{len(few)} multiple-choice items have only two options"))
    stems: dict[str, list[dict]] = {}
    for item in items:
        stems.setdefault(normal(item["stem"]), []).append(item)
    twice = [group[0] for key, group in stems.items() if key and len(group) > 1]
    if twice:
        findings.append(finding("duplicate-stem", twice, f"{len(twice)} questions appear more than once "
                                                          f"({sum(len(g) for g in stems.values() if len(g) > 1)} items)"))
    no_topic = [i for i in items if not i["topic"]]
    if no_topic:
        findings.append(finding("topic", no_topic, f"{len(no_topic)} of {len(items)} items name no topic"))
    topics = Counter(i["topic"] for i in items if i["topic"])
    thin = {t: n for t, n in topics.items() if n < 5}
    metrics["topics"] = len(topics)
    if topics and thin and len(topics) <= 200:
        findings.append({**finding("thin-topic", [i for i in items if i["topic"] in thin],
                                   f"{len(thin)} of {len(topics)} topics have fewer than five items: "
                                   + ", ".join(f"{t[:40]} ({n})" for t, n in sorted(thin.items(), key=lambda kv: kv[1])[:6]))})
    no_source = [i for i in items if not i["sources"]]
    if no_source:
        findings.append(finding("source", no_source, f"{len(no_source)} of {len(items)} items name no source"))
    return {"schema": SCHEMA, "items": len(items), "errors": errors, "findings": findings, "metrics": metrics}


SHUFFLE = re.compile(r"shuffle\w*\s*\(\s*[\w.$?]*\b(options|choices|answers|alternatives|opciones)\b"
                     r"|\b(options|choices|answers|opciones)\b[\w.?]*\s*\.\s*sort\(\s*\(\)\s*=>\s*Math\.random"
                     r"|random\.shuffle\(\s*[\w.]*\b(options|choices|answers)\b")
CODE = {".js", ".mjs", ".ts", ".tsx", ".jsx", ".svelte", ".vue", ".html", ".py", ".astro"}


def repo_of(path: Path) -> Path:
    for folder in (path if path.is_dir() else path.parent, *path.resolve().parents):
        if (folder / ".git").exists():
            return folder
    return path if path.is_dir() else path.parent


def shuffles_options(items: list[dict]) -> str | None:
    """The source file that shuffles the options before a learner sees them, if the repository has one."""
    roots = {repo_of(Path(i["file"])) for i in items}
    for root in sorted(roots):
        seen = 0
        for found in root.rglob("*"):
            if seen > 3000:
                break
            if found.suffix not in CODE or any(part in SKIP_DIRS for part in found.parts) or not found.is_file():
                continue
            seen += 1
            try:
                if found.stat().st_size < 2_000_000 and SHUFFLE.search(found.read_text(encoding="utf-8", errors="ignore")):
                    return found.relative_to(root).as_posix()
            except OSError:
                continue
    return None


def boolean(item: dict) -> bool:
    texts = {normal(o["text"]) for o in item["options"]}
    return item["type"] in ("boolean", "true-false", "truefalse") or texts <= {"true", "false", "verdadero", "falso", "si", "no", "yes"}


# Chi-square critical values at p = 0.01 for 1 to 7 degrees of freedom.
CHI_CRITICAL = {1: 6.63, 2: 9.21, 3: 11.34, 4: 13.28, 5: 15.09, 6: 16.81, 7: 18.48}


def summary(report: dict) -> str:
    lines = [f"{report['items']} items in {report['metrics'].get('files', 0)} files."]
    if not report["items"]:
        return "No question bank found. A question is an object with a stem, two or more options and a key."
    m = report["metrics"]
    lines.append(f"Explained: {m['with_explanation']}. Wrong options explained: {m['with_distractor_feedback']}. "
                 f"With topic: {m['with_topic']} ({m.get('topics', 0)} topics). With source: {m['with_sources']}.")
    for error in report["errors"]:
        lines.append(f"ERROR {error['error']}: {error['count']}. {error['detail']}.")
    for item in report["findings"]:
        lines.append(f"- {item['rule']}: {item['detail']}. {item['advice']} ({item['source']})")
    if not report["errors"] and not report["findings"]:
        lines.append("No finding.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit 1 on learning findings too, not only on integrity errors")
    args = parser.parse_args(argv)
    items = [item for path in collect(args.paths) for item in read_items(path)]
    report = audit(items)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else summary(report))
    return 1 if report["errors"] or (args.strict and report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
