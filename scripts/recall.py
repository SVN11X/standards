#!/usr/bin/env python3
"""Hand a new session the decisions and notes that fit its request, so it never needs the whole history.

`lines` ranks the decision records of the repository and the entries of the local memory by the words they share with
the request, and returns at most two of each with where they came from. Once `memory.py index` stored meaning vectors
for the repository and the local embedding model answers, it ranks by words and by meaning together, so a question in
Spanish finds a note written in English. The lines stay inside a budget of characters. `handoff` stores what a finished plan left:
what passed, what is blocked and why, so the next phase starts from it. The idea follows ProjectArchitect, whose
license forbids redistributing it or a similar version: nothing of it is copied here. https://github.com/Druthulu/ProjectArchitect
Run: python scripts/recall.py "REQUEST" [--repo .]
"""
import argparse
import contextlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory  # noqa: E402
import reuse  # noqa: E402

MIN_SHARED = 2


def decision_records(root: Path) -> list[dict]:
    rows = []
    for path in sorted((root / "docs" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")):
        if path.name.startswith("0000-"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = re.search(r"^#\s+(.+)$", text, re.M)
        status = re.search(r"^-\s*Status:\s*(\w+)", text, re.I | re.M)
        decision = re.search(r"^##\s+Decision\s*\n+(.+?)(?:\n\n|\n##|\Z)", text, re.M | re.S)
        rows.append({"path": path.relative_to(root).as_posix(), "title": title.group(1).strip() if title else path.stem,
                     "status": status.group(1).lower() if status else "unknown",
                     "decision": " ".join((decision.group(1) if decision else "").split())})
    return rows


def ranked_decisions(root: Path, request: str, top: int = 2) -> list[dict]:
    want = reuse.words(request)
    scored = []
    for row in decision_records(root):
        in_title = want & reuse.words(row["title"])
        shared = in_title | (want & reuse.words(row["decision"]))
        # Two different words in common, so one generic word such as "files" never recalls an unrelated decision.
        if len(shared) >= MIN_SHARED:
            scored.append(((len(shared), len(in_title)), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:top]]


def ranked_memories(request: str, repo: str, top: int = 2) -> list[tuple]:
    terms = sorted(w for w in reuse.words(request) if len(w) >= 4)[:8]
    if not terms:
        return []
    sql = ("SELECT e.id, e.kind, e.source, e.ref, e.created, e.text FROM entries_fts f JOIN entries e ON e.id = f.rowid "
           "WHERE entries_fts MATCH ? AND e.repo = ? ORDER BY e.id DESC LIMIT ?")
    # Closed at once: on Windows an open database keeps its folder from being removed.
    with contextlib.closing(memory.connect()) as db:
        return db.execute(sql, (" OR ".join(f'"{t}"' for t in terms), repo, top)).fetchall()


def memory_line(_id, kind: str, source: str, ref: str | None, created: str | None, text: str) -> str:
    label = "fact" if source in ("owner", "tool") else "agent hint, check it before acting"
    old = " It is older than 90 days." if created and memory.age_days(created) > memory.OLD_DAYS else ""
    return f"Memory {_id} ({kind}, {label}{', ' + ref if ref else ''}): {' '.join(text.split())[:220]}{old}"


def within(found: list[str], budget_chars: int) -> list[str]:
    kept, used = [], 0
    for line in found:
        if used + len(line) > budget_chars:
            break
        kept.append(line)
        used += len(line) + 1
    return kept


def meaning_lines(root: Path, request: str, embed=None) -> list[str] | None:
    """Lines ranked by words and meaning, or None when the repository has no vectors or the local model cannot answer."""
    with contextlib.closing(memory.connect()) as db:
        if not db.execute("SELECT 1 FROM vectors WHERE repo = ? LIMIT 1", (root.name,)).fetchone():
            return None
        embed = embed or memory.local_embedder()[0]
        if embed is None:
            return None
        found = memory.hybrid(db, request, root.name, root, embed, top=4)
    out = []
    for item in found["results"]:
        if item["source"] == "file":
            out.append(f"Relevant decision {item['ref']} ({item.get('status', 'unknown')}): {item['text'][:260]}")
        else:
            out.append(memory_line(item["key"].split(":", 1)[1], item["kind"], item["source"], item.get("ref"), item.get("created"),
                                   item["text"]))
    return out


def lines(root: Path, request: str, embed=None, budget_chars: int = 900) -> list[str]:
    meaning = meaning_lines(root, request, embed)
    if meaning is not None:
        return within(meaning, budget_chars)
    out = []
    for row in ranked_decisions(root, request):
        out.append(f"Relevant decision {row['path']} ({row['status']}): {row['title']}. {row['decision'][:220]}")
    for _id, kind, source, ref, created, text in ranked_memories(request, root.name):
        out.append(memory_line(_id, kind, source, ref, created, text))
    return within(out, budget_chars)


def handoff(repo: Path, plan: dict, state: dict) -> int | None:
    """What a finished or paused plan leaves for the next session. Returns the memory id, or None when nothing ran."""
    units = state.get("units") or {}
    if not units:
        return None
    done = sorted(u for u, e in units.items() if e.get("status") == "passed")
    stuck = [f"{u} ({(e.get('note') or e['status'])[:100]})" for u, e in sorted(units.items())
             if e.get("status") in ("blocked", "failed")]
    text = (f"Plan {plan['plan_id']}: {plan.get('goal', '').splitlines()[0][:160]}. Passed: {', '.join(done) or 'none'}. "
            f"Stopped: {', '.join(stuck) or 'none'}.")
    with contextlib.closing(memory.connect()) as db:
        return memory.add(db, "summary", text, repo=Path(repo).name, ref=f"plan {plan['plan_id']}", source="tool")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("request")
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    print("\n".join(lines(args.repo.resolve(), args.request)) or "Nothing recorded fits this request.")
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
