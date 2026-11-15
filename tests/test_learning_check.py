"""Question bank audit: field detection in three real shapes, integrity errors and findings with their sources."""
import contextlib
import io
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import learning_check as lc  # noqa: E402


def flat(n, **change):
    """The shape of test_dk_data_analyst: options are strings and the key is an index."""
    item = {"question": f"Which tool reads partitioned table {n} fastest?", "options": ["Alpha", "Beta", "Gamma", "Delta"],
            "answer": n % 4, "category": f"topic-{n % 3}", "sources": ["https://example.org/docs"],
            "explanation": "Partition pruning reads only the files that hold the requested dates, so less data is scanned."}
    item.update(change)
    return item


def lettered(n, **change):
    """The shape of GCP_Data_Engineer_Fieldnotes: choices with letters and a why, the key is a list of letters."""
    item = {"id": f"lab-{n}", "text": f"Which design follows least privilege for job {n}?", "domain": 1, "references": ["iam"],
            "choices": [{"letter": L, "text": f"Option {L} for {n}", "why": f"Because {L} grants what job {n} needs and nothing else."}
                        for L in "ABCD"],
            "answer": ["ABCD"[n % 4]], "explanation": "A dedicated identity limits the permissions and the impact of this job."}
    item.update(change)
    return item


def keyed(n, **change):
    """The shape of nexocert: options with ids and their own explanation, the key is a list of option ids."""
    item = {"id": f"q{n}", "prompt": f"¿Qué arquitectura conviene en el caso {n}?", "type": "single", "domainId": "plan",
            "sourceIds": ["guide"], "explanation": "La recuperación incorpora documentos actualizados en el momento de la consulta.",
            "options": [{"id": f"o{k}", "text": f"Opción {k} del caso {n}", "explanation": f"Explica por qué la opción {k} cumple o no."}
                        for k in range(4)], "correct": [f"o{n % 4}"]}
    item.update(change)
    return item


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def check(self, data, name="questions.json"):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return lc.audit([i for f in lc.collect([self.root]) for i in lc.read_items(f)])

    def rules(self, report):
        return {f["rule"]: f for f in report["findings"]}


class ShapeTests(Base):
    def test_three_real_shapes_are_read_with_their_keys(self):
        for maker, wrap in ((flat, lambda x: x), (lettered, lambda x: x), (keyed, lambda x: {"exam": {"questions": x}})):
            with self.subTest(maker.__name__):
                for old in self.root.glob("*.json"):
                    old.unlink()
                report = self.check(wrap([maker(n) for n in range(24)]))
                self.assertEqual((report["items"], report["errors"]), (24, []))
                self.assertEqual(report["metrics"]["with_explanation"], 24)
                self.assertEqual(report["metrics"]["with_topic"], 24)
                self.assertNotIn("key-position", self.rules(report))

    def test_a_file_without_questions_and_unrelated_json_are_ignored(self):
        (self.root / "package.json").write_text(json.dumps({"options": [1, 2], "question": "x"}))
        report = self.check({"settings": {"theme": "dark"}}, "quiz-config.json")
        self.assertEqual(report["items"], 0)
        self.assertIn("No question bank found", lc.summary(report))

    def test_a_language_map_is_read_as_text(self):
        item = lettered(1, text={"en": "Which design follows least privilege?", "es": "¿Qué diseño sigue el menor privilegio?"})
        self.assertEqual(lc.plain(item["text"]), "Which design follows least privilege?")


class IntegrityTests(Base):
    def test_a_missing_or_wrong_key_a_repeated_id_and_a_repeated_option_are_errors(self):
        items = [lettered(n) for n in range(6)]
        del items[0]["answer"]
        items[1]["answer"] = ["Z"]
        items[2]["id"] = items[3]["id"]
        items[4]["choices"][1]["text"] = items[4]["choices"][0]["text"].upper()
        errors = {e["error"]: e["count"] for e in self.check(items)["errors"]}
        self.assertEqual(errors, {"no-key": 1, "key-names-no-option": 1, "repeated-id": 1, "repeated-option": 1})

    def test_options_that_differ_only_in_punctuation_are_different(self):
        """Found on GCP_Data_Engineer_Fieldnotes: code options that differ by a quote or an asterisk were reported as equal."""
        item = lettered(1)
        for choice, text in zip(item["choices"], ["'project.table'", "project.table*", "'project.table'*", "project.table"]):
            choice["text"] = text
        self.assertEqual(self.check([item])["errors"], [])

    def test_the_exit_code_follows_errors_and_strict_mode(self):
        path = self.root / "questions.json"
        path.write_text(json.dumps([lettered(n) for n in range(3)]))
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.assertEqual(lc.main([str(path)]), 0)
        broken = [lettered(n) for n in range(3)]
        broken[0]["answer"] = ["Z"]
        path.write_text(json.dumps(broken))
        self.assertEqual(lc.main([str(path)]), 1)
        path.write_text(json.dumps([lettered(n, explanation="") for n in range(3)]))
        self.assertEqual((lc.main([str(path)]), lc.main([str(path), "--strict"])), (0, 1))


class FindingTests(Base):
    def test_items_without_explanation_and_short_explanations(self):
        items = [flat(n) for n in range(10)]
        for item in items[:3]:
            item["explanation"] = ""
        items[3]["explanation"] = "Beta is right."
        rules = self.rules(self.check(items))
        self.assertEqual((rules["explanation"]["count"], rules["short-explanation"]["count"]), (3, 1))
        self.assertIn("Hattie and Timperley 2007", rules["explanation"]["source"])

    def test_a_skewed_key_position_is_found_and_a_shuffling_page_clears_it(self):
        items = [flat(n, answer=1 if n % 2 else n % 4) for n in range(80)]
        rules = self.rules(self.check(items))
        self.assertIn("key-position", rules)
        self.assertIn("the key is B", rules["key-position"]["detail"])
        (self.root / ".git").mkdir()
        (self.root / "quiz.js").write_text("const shown = shuffle(question.options);\n")
        report = self.check(items)
        self.assertNotIn("key-position", self.rules(report))
        self.assertIn("quiz.js shuffles the options", report["metrics"]["key_position"]["note"])

    def test_a_balanced_key_position_passes(self):
        rng = random.Random(7)
        report = self.check([flat(n, answer=rng.randrange(4)) for n in range(200)])
        self.assertNotIn("key-position", self.rules(report))
        self.assertLess(report["metrics"]["key_position"]["chi_square"], 11.34)

    def test_the_longest_option_as_key_is_found(self):
        items = []
        for n in range(40):
            options = ["Short", "Brief", "Tiny", "Small"]
            options[n % 4] = "A much longer and more qualified option that sounds complete"
            items.append(flat(n, options=options, answer=n % 4))
        self.assertIn("longest-key", self.rules(self.check(items)))

    def test_all_and_none_of_the_above_and_negative_questions(self):
        items = [flat(n) for n in range(6)]
        items[0]["options"][3] = "All of the above"
        items[1]["options"][3] = "Ninguna de las anteriores"
        items[2]["question"] = "Delta Lake supports schema evolution. Which of the following is not supported?"
        items[3]["question"] = "Which of the following is NOT supported?"
        items[4]["question"] = "The team does not want to manage servers. Which service fits?"
        rules = self.rules(self.check(items))
        self.assertEqual(rules["all-of-the-above"]["count"], 1)
        self.assertEqual(rules["none-of-the-above"]["count"], 1)
        self.assertEqual([e["stem"][:20] for e in rules["negative-stem"]["examples"]], ["Delta Lake supports "])

    def test_duplicates_two_option_items_topics_and_sources(self):
        items = [flat(n) for n in range(12)]
        items[1]["question"] = items[0]["question"].upper()
        items[2]["options"] = ["Alpha", "Beta"]
        items[2]["answer"] = 0
        items[3]["options"] = ["True", "False"]
        items[3]["answer"] = 0
        del items[4]["category"]
        del items[5]["sources"]
        items[6]["category"] = "rare"
        rules = self.rules(self.check(items))
        self.assertEqual(rules["duplicate-stem"]["count"], 1)
        self.assertEqual(rules["few-options"]["count"], 1, "a true or false item is not a two-option multiple choice")
        self.assertEqual((rules["topic"]["count"], rules["source"]["count"]), (1, 1))
        self.assertIn("rare (1)", rules["thin-topic"]["detail"])

    def test_wrong_options_without_feedback(self):
        items = [keyed(n) for n in range(24)]
        items[0]["options"][(1 + 0) % 4]["explanation"] = ""
        self.assertEqual(self.rules(self.check({"questions": items}))["distractor-feedback"]["count"], 1)
        bare = [flat(n) for n in range(24)]
        self.assertEqual(self.rules(self.check(bare))["distractor-feedback"]["detail"], "no item says why a wrong option is wrong")

    def test_every_rule_has_advice_and_a_source_link(self):
        for rule, (advice, source) in lc.RULES.items():
            self.assertTrue(advice.endswith("."), rule)
            self.assertIn("https://", source, rule)


if __name__ == "__main__":
    unittest.main()
