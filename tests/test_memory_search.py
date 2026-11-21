"""Word and meaning search of the local memory with a fake embedding model. The fake maps Spanish and English words of
the same idea to the same axis, so it proves the mechanism (fusion, filters, versions, recovery), not the quality of a model.
Run: python -m unittest discover -s tests"""
import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import memory  # noqa: E402
import recall  # noqa: E402

IDEAS = [
    {"tardó", "tarda", "tanto", "lento", "slow", "prefill", "timeout", "timed", "seconds", "segundos", "177"},
    {"corregir", "corrige", "error", "bug", "fix", "fix-bug", "fixed"},
    {"color", "botón", "button", "colour"},
    {"sesiones", "sessions", "sqlite", "json"},
]


class FakeEmbedder:
    def __init__(self, revision="r1", model="fake-embed", fail_after=None):
        self.model, self.revision, self.calls, self.fail_after = model, revision, 0, fail_after
        self.settings = {**memory.SEARCH, "batch": 1, "min_similarity": 0.5, "query_prefix": ""}

    def __call__(self, texts):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise OSError("interrupted")
        out = []
        for text in texts:
            words = {w.strip("¿?.,()").lower() for w in text.split()}
            out.append([float(len(words & idea)) for idea in IDEAS] + [0.01])
        return out


COLIBRI = "Colibri prefill took 177 seconds for 1009 tokens and fix-bug timed out at 600 s on the RTX 2060"


class MemorySearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["STANDARDS_HOME"] = str(Path(self.tmp.name) / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.repo = Path(self.tmp.name) / "standards"
        (self.repo / "docs" / "decisions").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.db = memory.connect()
        self.addCleanup(self.db.close)
        self.colibri = memory.add(self.db, "test", COLIBRI, repo="standards", ref="docs/007-autonomous-execution.md", source="tool")
        self.hint = memory.add(self.db, "note", "The button color comes from the theme file", repo="standards", source="agent")
        memory.add(self.db, "test", COLIBRI, repo="other", ref="other/report.md", source="tool")

    def index(self, embed, repo="standards"):
        root = self.repo if repo == "standards" else None
        return memory.index(self.db, memory.fragments(self.db, repo, root), embed, repo)

    def test_a_spanish_question_finds_the_english_measurement_and_its_source(self):
        embed = FakeEmbedder()
        self.index(embed)
        question = "¿por qué tardó tanto en corregir el error?"
        words = memory.hybrid(self.db, question, "standards", self.repo, None)
        self.assertEqual(words["results"], [])
        found = memory.hybrid(self.db, question, "standards", self.repo, embed)
        first = found["results"][0]
        self.assertEqual((first["key"], first["ref"], first["via"]), (f"entry:{self.colibri}", "docs/007-autonomous-execution.md", ["meaning"]))
        self.assertEqual(found["mode"], "words and meaning")

    def test_a_question_in_one_project_never_returns_another_project(self):
        embed = FakeEmbedder()
        self.index(embed)
        self.index(embed, "other")
        for engine in (None, embed):
            found = memory.hybrid(self.db, "Colibri prefill timeout", "standards", self.repo, engine, top=10)["candidates"]
            self.assertTrue(found)
            self.assertEqual({item["repo"] for item in found}, {"standards"})

    def test_an_agent_note_keeps_its_label_in_the_recalled_lines(self):
        embed = FakeEmbedder()
        self.index(embed)
        found = recall.lines(self.repo, "¿De qué color es el botón?", embed=embed)
        self.assertTrue(any("agent hint, check it before acting" in line for line in found))
        self.assertFalse(any("RTX 2060" in line for line in found))

    def test_only_new_or_changed_fragments_are_embedded_again(self):
        self.assertEqual(self.index(FakeEmbedder())["embedded"], 2)
        self.assertEqual(self.index(FakeEmbedder())["embedded"], 0)
        self.db.execute("DELETE FROM entries WHERE id = ?", (self.hint,))
        memory.add(self.db, "note", "The button colour is set in the theme", repo="standards", source="agent")
        self.assertEqual(self.index(FakeEmbedder()), {"embedded": 1, "kept": 1, "removed": 1})
        self.assertEqual(self.index(FakeEmbedder(revision="r2"))["embedded"], 2)

    def test_vectors_of_another_model_version_are_ignored_and_words_still_answer(self):
        self.index(FakeEmbedder(revision="r1"))
        found = memory.hybrid(self.db, "Colibri prefill timeout", "standards", self.repo, FakeEmbedder(revision="r2"))
        self.assertEqual(found["results"][0]["via"], ["words"])
        self.assertIn("no vector of this model and revision", found["note"])

    def test_an_interrupted_index_keeps_what_it_finished(self):
        with self.assertRaises(OSError):
            self.index(FakeEmbedder(fail_after=1))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 1)
        self.assertEqual(self.index(FakeEmbedder())["embedded"], 1)

    def test_an_old_database_opens_and_searches_by_words(self):
        path = Path(self.tmp.name) / "old.db"
        with contextlib.closing(sqlite3.connect(path)) as old:
            old.executescript(memory.SCHEMA.split("CREATE TABLE IF NOT EXISTS vectors")[0])
            old.execute("INSERT INTO entries(kind, repo, ref, source, text) VALUES ('test', 'standards', 'r', 'tool', ?)", (COLIBRI,))
            old.commit()
        with contextlib.closing(memory.connect(path)) as db:
            self.assertEqual(len(memory.hybrid(db, "prefill timeout", "standards")["results"]), 1)

    def test_the_embedder_refuses_an_address_off_this_machine(self):
        with self.assertRaises(ValueError):
            memory.Embedder({**memory.SEARCH, "url": "http://example.com:11434"})
        embed, why = memory.local_embedder({**memory.SEARCH, "url": "http://127.0.0.1:9", "timeout_s": 0.5})
        self.assertIsNone(embed)
        self.assertTrue(why)

    def test_the_evaluation_counts_hits_per_language_and_kind(self):
        embed = FakeEmbedder()
        self.index(embed)
        cases = [{"query": "Colibri prefill timeout", "lang": "en", "type": "exact", "expect": ["docs/007-autonomous-execution.md"]},
                 {"query": "¿por qué tardó tanto en corregir el error?", "lang": "es", "type": "paraphrase",
                  "expect": [f"entry:{self.colibri}"]},
                 {"query": "receta de tortilla", "lang": "es", "type": "unanswerable", "expect": []}]
        report = memory.evaluate(self.db, cases, "standards", self.repo, embed)
        self.assertEqual(report["words"]["es/paraphrase"]["top3"], 0)
        self.assertEqual(report["words and meaning"]["es/paraphrase"]["top3"], 1)
        self.assertEqual(report["words and meaning"]["en/exact"]["top3"], 1)
        self.assertEqual(report["words and meaning"]["es/unanswerable"]["empty_ok"], 1)
        text = "\n".join(memory.eval_lines(report))
        self.assertIn("es/paraphrase: top 3 1 of 1", text)
        self.assertIn("no answer returned for 1 of 1", text)


if __name__ == "__main__":
    unittest.main()
