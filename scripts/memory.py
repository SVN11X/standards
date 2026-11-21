#!/usr/bin/env python3
"""Local technical memory: decisions, test results and summaries, searchable with SQLite FTS5.

Commands:
  add      store one entry (kind, text, repository, reference, source)
  search   full-text search, newest first
  list     the latest entries of one repository
  forget   delete one entry by id. To correct an entry, forget it and add the right one
  export   print every entry as JSON lines, to keep or move the memory
  expire   delete agent hints older than a number of days. Facts from the owner and from tools stay
  index    store meaning vectors of the new or changed entries and decisions of one repository (local Ollama only)
  find     search one repository by words and by meaning, with the reference of every result
  eval     compare word search with word and meaning search on the owner's questions with known answers

Each entry says where it came from. owner and tool entries are facts with a reference. agent entries
are hints: check them against the files and tests before acting on them. An entry older than 90 days
is marked old, because the code may have changed since. Secrets are refused.
The database lives in STANDARDS_HOME (default ~/.standards/memory.db), outside every repository.

Meaning search is an addition, never a replacement: the vectors come from the embedding model of the local Ollama,
each one records its repository, key, source, content hash, model, model revision and dimensions, and a vector of
another model, revision or size is ignored until `index` rebuilds it. Without Ollama or without vectors, the word
search answers alone. Results are filtered to the repository before they are ranked, so a question asked in one
project never returns a fragment of another.
"""
from __future__ import annotations

import argparse
import array
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
try:
    from secret_scan import scan
except ImportError:  # pragma: no cover
    def scan(text: str) -> list[str]:
        return []

KINDS = ("decision", "test", "summary", "capability", "note")
SOURCES = ("owner", "tool", "agent")
SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, repo TEXT, ref TEXT, source TEXT NOT NULL,
  text TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')));
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(text, content='entries', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
CREATE TABLE IF NOT EXISTS vectors (
  key TEXT PRIMARY KEY, repo TEXT, source TEXT, ref TEXT, content_hash TEXT NOT NULL, model TEXT NOT NULL,
  revision TEXT, dims INTEGER NOT NULL, vector BLOB NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')));
"""
# Settings of the meaning search. The model is the local embedding model of settings/orchestration.yml.
SEARCH = {"model": "qwen3-embedding:0.6b", "url": "http://127.0.0.1:11434", "timeout_s": 3, "batch": 16, "rrf_k": 60,
          "candidates": 10, "min_similarity": 0.5,
          "query_prefix": "Instruct: Given a question, retrieve the notes and decisions that answer it\nQuery: "}


def db_path() -> Path:
    root = Path(os.environ.get("STANDARDS_HOME") or Path.home() / ".standards")
    root.mkdir(parents=True, exist_ok=True)
    return root / "memory.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or db_path())
    db.executescript(SCHEMA)
    return db


def add(db, kind: str, text: str, repo: str | None = None, ref: str | None = None, source: str = "agent") -> int:
    if kind not in KINDS or source not in SOURCES:
        raise ValueError(f"kind must be one of {KINDS} and source one of {SOURCES}")
    found = scan(text)
    if found:
        raise ValueError(f"refused: the text looks like it holds {', '.join(found)}")
    if source != "agent" and not ref:
        raise ValueError("owner and tool entries need a reference: a file, a commit or a report")
    cursor = db.execute("INSERT INTO entries(kind, repo, ref, source, text) VALUES (?, ?, ?, ?, ?)",
                        (kind, repo, ref, source, text.strip()))
    db.commit()
    return cursor.lastrowid


def search(db, query: str, repo: str | None = None, limit: int = 10) -> list[tuple]:
    terms = " ".join(f'"{word}"' for word in re.findall(r"\w+", query))
    if not terms:
        return []
    sql = ("SELECT e.id, e.kind, e.source, e.repo, e.ref, e.created, e.text FROM entries_fts f "
           "JOIN entries e ON e.id = f.rowid WHERE entries_fts MATCH ?")
    params: list = [terms]
    if repo:
        sql += " AND e.repo = ?"
        params.append(repo)
    sql += " ORDER BY e.id DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


OLD_DAYS = 90


def age_days(created: str) -> int:
    try:
        return (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.datetime.fromisoformat(created)).days
    except ValueError:
        return 0


def expire(db, days: int) -> int:
    """Delete agent hints older than the given days. A hint is never promoted to a fact by staying in the database."""
    cursor = db.execute("DELETE FROM entries WHERE source = 'agent' AND created < datetime('now', ?)", (f"-{int(days)} days",))
    db.commit()
    return cursor.rowcount


def export(db) -> list[dict]:
    names = ("id", "kind", "source", "repo", "ref", "created", "text")
    return [dict(zip(names, row)) for row in db.execute("SELECT id, kind, source, repo, ref, created, text FROM entries ORDER BY id")]


# Meaning search


def search_settings() -> dict:
    """SEARCH with the `memory` block and the Ollama address of settings/orchestration.yml, when they can be read."""
    found = dict(SEARCH)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import orchestrate
        conf = orchestrate.policy()
        found["url"] = conf["executors"]["ollama"].get("url", found["url"])
        found.update(conf.get("memory") or {})
    except Exception:  # noqa: BLE001 (the defaults above are safe: local address, word search always works)
        pass
    return found


def is_local(url: str) -> bool:
    return (urllib.parse.urlparse(url).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}


class Embedder:
    """Meaning vectors from the local Ollama. Notes and decisions may be private, so any other address is refused."""

    def __init__(self, settings: dict | None = None):
        self.settings = settings or search_settings()
        self.url = str(self.settings["url"]).rstrip("/")
        self.model = self.settings["model"]
        if not is_local(self.url) or re.search(r"(^|[:-])cloud$", self.model):
            raise ValueError(f"refused: meaning vectors are made on this machine only, not at {self.url} with {self.model}")
        self.revision = self._revision()

    def _post(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        # No proxy: the address is this machine, and a proxy would carry private text elsewhere.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=self.settings["timeout_s"] if payload is None else max(30, self.settings["timeout_s"])) as reply:
            return json.loads(reply.read().decode("utf-8"))

    def _revision(self) -> str:
        for model in self._post("/api/tags").get("models", []):
            if model.get("name") in (self.model, f"{self.model}:latest"):
                return str(model.get("digest") or "")[:12] or "unknown"
        raise ValueError(f"{self.model} is not installed in the local Ollama")

    def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors = self._post("/api/embed", {"model": self.model, "input": texts}).get("embeddings") or []
        if len(vectors) != len(texts):
            raise ValueError(f"Ollama returned {len(vectors)} vectors for {len(texts)} texts")
        return vectors


def local_embedder(settings: dict | None = None) -> tuple[Embedder | None, str]:
    """(embedder, why). None with the reason when the local model cannot answer: the word search then works alone."""
    try:
        return Embedder(settings), "ok"
    except (OSError, ValueError, urllib.error.URLError) as error:
        return None, str(error)[:200]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack(vector: list[float]) -> bytes:
    return array.array("f", vector).tobytes()


def unpack(blob: bytes) -> list[float]:
    values = array.array("f")
    values.frombytes(blob)
    return list(values)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / size if size else 0.0


def fragments(db, repo: str, root: Path | None = None) -> list[dict]:
    """What one repository can recall: its memory entries and, with its folder, its decision records. Nothing of another repository."""
    found = [{"key": f"entry:{row[0]}", "kind": row[1], "source": row[2], "repo": row[3], "ref": row[4], "created": row[5],
              "text": row[6]} for row in db.execute("SELECT id, kind, source, repo, ref, created, text FROM entries WHERE repo = ?", (repo,))]
    if root is not None:
        import recall
        for record in recall.decision_records(root):
            found.append({"key": f"file:{record['path']}", "kind": "decision", "source": "file", "repo": repo, "ref": record["path"],
                          "created": None, "status": record["status"], "title": record["title"],
                          "text": f"{record['title']}. {record['decision']}".strip()})
    return found


def index(db, items: list[dict], embed, repo: str) -> dict:
    """Vectors for the fragments that are new or changed, or whose vector came from another model or revision.
    Each batch is committed, so an interrupted run keeps what it finished and the next one does only the rest."""
    stored = {row[0]: row[1:] for row in db.execute("SELECT key, content_hash, model, revision FROM vectors WHERE repo = ?", (repo,))}
    wanted = {item["key"] for item in items}
    gone = [key for key in stored if key not in wanted]
    db.executemany("DELETE FROM vectors WHERE key = ?", [(key,) for key in gone])
    todo = [item for item in items if stored.get(item["key"]) != (content_hash(item["text"]), embed.model, embed.revision)]
    size = int(getattr(embed, "settings", SEARCH).get("batch", SEARCH["batch"]))
    for start in range(0, len(todo), size):
        batch = todo[start:start + size]
        vectors = embed([item["text"] for item in batch])
        db.executemany("INSERT OR REPLACE INTO vectors(key, repo, source, ref, content_hash, model, revision, dims, vector) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [(item["key"], repo, item["source"], item.get("ref"), content_hash(item["text"]), embed.model, embed.revision,
                         len(vector), pack(vector)) for item, vector in zip(batch, vectors)])
        db.commit()
    db.commit()
    return {"embedded": len(todo), "kept": len(items) - len(todo), "removed": len(gone)}


def lexical_ranking(db, query: str, items: list[dict]) -> list[str]:
    """Keys in word order: FTS5 rank for entries, shared words for decision records. Accents do not matter to FTS5."""
    terms = sorted({w.lower() for w in re.findall(r"\w+", query) if len(w) >= 3})[:12]
    allowed = {item["key"] for item in items}
    ranked = []
    if terms:
        rows = db.execute("SELECT e.id FROM entries_fts f JOIN entries e ON e.id = f.rowid WHERE entries_fts MATCH ? "
                          "ORDER BY bm25(entries_fts)", (" OR ".join(f'"{t}"' for t in terms),)).fetchall()
        ranked = [f"entry:{row[0]}" for row in rows if f"entry:{row[0]}" in allowed]
    want = set(terms)
    scored = []
    for item in items:
        if item["key"].startswith("file:"):
            shared = want & {w.lower() for w in re.findall(r"\w+", item["text"])}
            if len(shared) >= 2:
                scored.append((len(shared), item["key"]))
    return ranked + [key for _, key in sorted(scored, reverse=True)]


def semantic_ranking(db, query: str, items: list[dict], embed, repo: str) -> list[tuple[str, float]]:
    """(key, similarity) of the fragments whose vector came from this exact model, revision and size, best first."""
    allowed = {item["key"] for item in items}
    rows = db.execute("SELECT key, vector, dims FROM vectors WHERE repo = ? AND model = ? AND revision = ?",
                      (repo, embed.model, embed.revision)).fetchall()
    rows = [row for row in rows if row[0] in allowed]
    if not rows:
        return []
    asked = embed([getattr(embed, "settings", SEARCH).get("query_prefix", "") + query])[0]
    scored = [(key, cosine(asked, unpack(blob))) for key, blob, dims in rows if dims == len(asked)]
    return sorted(scored, key=lambda item: item[1], reverse=True)


def hybrid(db, query: str, repo: str, root: Path | None = None, embed=None, top: int = 3, settings: dict | None = None) -> dict:
    """The best fragments of one repository for a question, by words and by meaning, fused by key with reciprocal rank.

    The repository filter comes first. A meaning match counts only above `min_similarity`. Each result keeps its key,
    reference and source, so an agent hint stays a hint. `mode` says what answered: words, or words and meaning."""
    settings = settings or getattr(embed, "settings", None) or search_settings()
    items = fragments(db, repo, root)
    by_key = {item["key"]: item for item in items}
    lists = {"words": lexical_ranking(db, query, items)[: settings["candidates"]]}
    note = None
    if embed is not None:
        try:
            meaning = semantic_ranking(db, query, items, embed, repo)
            lists["meaning"] = [key for key, score in meaning if score >= settings["min_similarity"]][: settings["candidates"]]
            similarity = dict(meaning)
            if not meaning:
                note = "no vector of this model and revision yet: python scripts/memory.py index --repo <folder>"
        except (OSError, ValueError, urllib.error.URLError) as error:
            note, similarity = f"meaning search failed, words only: {str(error)[:120]}", {}
    else:
        similarity = {}
    score: dict[str, float] = {}
    via: dict[str, list[str]] = {}
    for name, keys in lists.items():
        for rank, key in enumerate(keys):
            score[key] = score.get(key, 0.0) + 1.0 / (settings["rrf_k"] + rank + 1)
            via.setdefault(key, []).append(name)
    ranked = sorted(score, key=lambda key: score[key], reverse=True)
    results = [{**by_key[key], "score": round(score[key], 5), "via": via[key], "similarity": round(similarity[key], 3)
                if key in similarity else None} for key in ranked if key in by_key]
    return {"mode": "words and meaning" if "meaning" in lists else "words", "note": note, "results": results[:top],
            "candidates": results}


def evaluate(db, cases: list[dict], repo: str, root: Path | None = None, embed=None, settings: dict | None = None) -> dict:
    """Hits among the first 3 and the first 10 per language and kind of question, for words alone and for words and
    meaning. A question with no answer passes when nothing comes back. Numerators and denominators, never a bare rate."""
    modes = {"words": None, **({"words and meaning": embed} if embed is not None else {})}
    report: dict = {}
    for name, engine in modes.items():
        groups: dict[str, dict] = {}
        for case in cases:
            found = hybrid(db, case["query"], case.get("repo") or repo, root, engine, top=10, settings=settings)["candidates"][:10]
            keys = [{item["key"], str(item.get("ref") or "")} for item in found]
            expect = set(case.get("expect") or [])
            group = groups.setdefault(f"{case.get('lang', '?')}/{case.get('type', '?')}",
                                      {"cases": 0, "top3": 0, "top10": 0, "only_after_3": 0, "empty_ok": 0, "unanswerable": 0})
            group["cases"] += 1
            if not expect:
                group["unanswerable"] += 1
                group["empty_ok"] += int(not found)
                continue
            position = next((i for i, names in enumerate(keys) if names & expect), None)
            group["top3"] += int(position is not None and position < 3)
            group["top10"] += int(position is not None)
            group["only_after_3"] += int(position is not None and position >= 3)
        report[name] = groups
    return report


def eval_lines(report: dict) -> list[str]:
    lines = []
    for mode, groups in report.items():
        lines.append(f"{mode}:")
        for name, g in sorted(groups.items()):
            answerable = g["cases"] - g["unanswerable"]
            parts = [f"top 3 {g['top3']} of {answerable}", f"top 10 {g['top10']} of {answerable}"] if answerable else []
            if g["only_after_3"]:
                parts.append(f"{g['only_after_3']} found only after the third place, where a reranker could help")
            if g["unanswerable"]:
                parts.append(f"no answer returned for {g['empty_ok']} of {g['unanswerable']} questions without one")
            lines.append(f"  {name}: " + ", ".join(parts))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("text")
    p.add_argument("--repo")
    p.add_argument("--ref")
    p.add_argument("--source", choices=SOURCES, default="agent")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--repo")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("list")
    p.add_argument("--repo")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("forget")
    p.add_argument("id", type=int)
    sub.add_parser("export")
    p = sub.add_parser("expire")
    p.add_argument("--days", type=int, default=180)
    for name in ("index", "find", "eval"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, default=Path("."), help="the repository folder. Its name is the repository of the entries")
        if name == "find":
            p.add_argument("query")
            p.add_argument("--top", type=int, default=3)
            p.add_argument("--words-only", action="store_true")
        if name == "eval":
            p.add_argument("cases", type=Path, help="YAML with queries: [{query, lang, type, expect: [key or ref]}]")
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    db = connect()
    if args.command in ("index", "find", "eval"):
        root = args.repo.resolve()
        embed, why = (None, "words only, as asked") if getattr(args, "words_only", False) else local_embedder()
        if args.command == "index":
            if embed is None:
                print(f"not indexed: {why}. Word search still works", file=sys.stderr)
                return 1
            counts = index(db, fragments(db, root.name, root), embed, root.name)
            print(f"{root.name}: {counts['embedded']} embedded, {counts['kept']} unchanged, {counts['removed']} removed "
                  f"({embed.model}, revision {embed.revision})")
            return 0
        if args.command == "find":
            found = hybrid(db, args.query, root.name, root, embed, args.top)
            print(f"search by {found['mode']}" + (f". {found['note']}" if found["note"] else "") + ("" if embed else f". Meaning: {why}"))
            for item in found["results"]:
                label = {"agent": "agent hint, check it before acting", "file": "decision record"}.get(item["source"], "fact")
                print(f"{item['key']} [{label}] {item.get('ref') or '-'} ({', '.join(item['via'])}): {' '.join(item['text'].split())[:200]}")
            return 0
        import yaml
        cases = (yaml.safe_load(args.cases.read_text(encoding="utf-8")) or {}).get("queries") or []
        report = evaluate(db, cases, root.name, root, embed)
        print(json.dumps(report, indent=2) if args.json else "\n".join(eval_lines(report) + ([] if embed else [f"meaning: {why}"])))
        return 0
    if args.command == "add":
        try:
            print(f"stored entry {add(db, args.kind, args.text, args.repo, args.ref, args.source)}")
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        return 0
    if args.command == "forget":
        db.execute("DELETE FROM entries WHERE id = ?", (args.id,))
        db.commit()
        return 0
    if args.command == "export":
        for entry in export(db):
            print(json.dumps(entry, ensure_ascii=False))
        return 0
    if args.command == "expire":
        print(f"deleted {expire(db, args.days)} agent hints older than {args.days} days")
        return 0
    rows = (search(db, args.query, args.repo, args.limit) if args.command == "search" else
            db.execute("SELECT id, kind, source, repo, ref, created, text FROM entries WHERE (? IS NULL OR repo = ?) "
                       "ORDER BY id DESC LIMIT ?", (args.repo, args.repo, args.limit)).fetchall())
    for row in rows:
        label = ("hint" if row[2] == "agent" else row[2]) + (", old: check it against the files" if age_days(row[5]) > OLD_DAYS else "")
        print(f"#{row[0]} {row[1]} [{label}] {row[3] or '-'} {row[4] or '-'} {row[5]}: {row[6][:200]}")
    return 0


if __name__ == "__main__":
    import console
    console.safe_output()
    sys.exit(main())
