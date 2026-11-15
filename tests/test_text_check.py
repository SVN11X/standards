"""Text check: syllables, readability in Spanish and English, the findings, and the comprehension test evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import text_check as tc  # noqa: E402

PLAIN_ES = ("El estudio espaciado ayuda a recordar. Repasa cada tema en días distintos. Responde sin mirar las notas y luego "
            "revisa la explicación. Cuando fallas una pregunta, lee por qué la opción elegida no cumple el requisito del caso.")
DENSE_ES = ("La arquitectura de referencia propuesta incorpora mecanismos de orquestación distribuida, permitiendo la coordinación "
            "heterogénea de procesos computacionales mediante interfaces estandarizadas y verificables en entornos de producción. ")
PLAIN_EN = ("Spaced practice helps people remember. Review each topic on different days. Answer without looking at your notes, "
            "then read the explanation. When you miss a question, read why the option you chose does not fit the case.")


class CountTests(unittest.TestCase):
    def test_spanish_syllables_follow_diphthongs_and_hiatus(self):
        words = {"programación": 4, "guía": 2, "país": 2, "aéreo": 4, "ciudad": 2, "cuidado": 3, "agua": 2, "leer": 2,
                 "poeta": 3, "que": 1, "guerra": 2, "pingüino": 3, "hoy": 1, "río": 2, "baúl": 2, "estudiar": 3, "oír": 2,
                 # Hyphenation does not split one letter at a word edge, so tools built on it count these one short.
                 "ayuda": 3, "días": 2, "una": 2, "lee": 2, "elegida": 4}
        self.assertEqual({w: tc.syllables_es(w) for w in words}, words)

    def test_english_syllables(self):
        words = {"the": 1, "table": 2, "reading": 2, "understand": 3, "partition": 3, "query": 2, "simple": 2, "make": 1,
                 "data": 2, "every": 3, "evidence": 3}
        self.assertEqual({w: tc.syllables_en(w) for w in words}, words)

    def test_the_language_is_detected(self):
        self.assertEqual((tc.language(PLAIN_ES), tc.language(PLAIN_EN)), ("es", "en"))


class MeasureTests(unittest.TestCase):
    def test_plain_spanish_scores_easier_than_dense_spanish(self):
        plain, dense = tc.measure(PLAIN_ES * 3, []), tc.measure(DENSE_ES * 6, [])
        self.assertEqual((plain["language"], plain["method"]), ("es", "Szigriszt-Pazos (INFLESZ scale)"))
        self.assertGreater(plain["score"], 55)
        self.assertLess(dense["score"], 40)
        self.assertEqual(dense["band"], "muy difícil")
        rules = {f["rule"] for f in dense["findings"]}
        self.assertIn("readability", rules)
        self.assertIn("long-sentences", rules)
        self.assertNotIn("readability", {f["rule"] for f in plain["findings"]})

    def test_an_expert_audience_moves_the_floor(self):
        text = (DENSE_ES.replace("La arquitectura", "La arquitectura nueva. Ahora") + "Esto se mide. ") * 5
        general, expert = tc.measure(text, [], audience="general"), tc.measure(text, [], audience="expert")
        self.assertEqual(general["score"], expert["score"])
        self.assertGreaterEqual(len(general["findings"]), len(expert["findings"]))

    def test_english_uses_the_flesch_scale(self):
        result = tc.measure(PLAIN_EN * 3, [])
        self.assertEqual((result["language"], result["method"]), ("en", "Flesch reading ease"))
        self.assertGreater(result["score"], 60)

    def test_vague_links_undefined_acronyms_headings_and_passive(self):
        text = ("# Guide\n\nThe pipeline uses IAM and a VPC. Identity and Access Management (IAM) is defined later. "
                "Cloud Storage (GCS) holds files. The table was created by the job. The files were written by the job. "
                "The report is shown daily. The data was loaded.\n\n" + "Plain words help people read. " * 120)
        result = tc.measure(text, ["click here", "the BigQuery pricing page", "aquí"])
        rules = {f["rule"]: f for f in result["findings"]}
        self.assertEqual(result["vague_links"], ["click here", "aquí"])
        self.assertIn("IAM, VPC", rules["acronyms"]["detail"])
        self.assertNotIn("GCS", result["undefined_acronyms"])
        self.assertNotIn("no-headings", rules)
        no_heading = tc.measure(text.replace("# Guide\n\n", ""), [])
        self.assertIn("no-headings", {f["rule"] for f in no_heading["findings"]})
        self.assertNotIn("no-headings", {f["rule"] for f in tc.measure(text.replace("# Guide\n\n", ""), [], structured=True)["findings"]})

    def test_a_sentence_that_starts_with_code_and_the_sentences_of_a_list_item_are_split(self):
        """Found on this repository's own docs: both were read as one long sentence."""
        text = tc.strip_markdown("These measures are proxies. `text_check.py protocol` writes a card.\n\n"
                                 "- `search` asks two services. It keeps open licenses. It drops the rest.\n")
        result = tc.measure(text, [], "en")
        self.assertEqual(result["sentences"], 5)
        self.assertEqual(tc.acronyms(tc.strip_markdown("See https://doi.org/10.3758/MC.36.3.604 for it.")), [])

    def test_every_finding_names_its_source(self):
        result = tc.measure(DENSE_ES * 8 + " Ver [aquí](https://x.org).", ["aquí"])
        self.assertTrue(result["findings"])
        for finding in result["findings"]:
            self.assertTrue(finding["source"], finding["rule"])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_markdown_html_and_json_are_read_without_code_or_markup(self):
        (self.root / "a.md").write_text("---\ntitle: x\n---\n# Title\n\n```py\nprint('NOT TEXT')\n```\n\n" + PLAIN_EN
                                        + " See [the guide](https://example.org).\n")
        (self.root / "b.html").write_text("<html><script>var NOTTEXT=1</script><h1>Hola</h1><p>" + PLAIN_ES + "</p>"
                                          "<a href='/x'>aquí</a></html>")
        (self.root / "c.json").write_text(json.dumps({"lessons": [{"id": "l1", "body": "## Concepto\n\n" + PLAIN_ES, "url": "https://x.org/a"}]}))
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "d.md").write_text(PLAIN_EN)
        report = tc.check([self.root])
        files = {Path(f["file"]).name: f for f in report["files"]}
        self.assertEqual(set(files), {"a.md", "b.html", "c.json"})
        self.assertNotIn("NOT", files["a.md"]["undefined_acronyms"])
        self.assertEqual((files["b.html"]["language"], files["b.html"]["vague_links"]), ("es", ["aquí"]))
        self.assertEqual(files["c.json"]["language"], "es")
        self.assertIn("comprehension test", report["note"])


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "comprehension"

    def test_a_protocol_holds_no_result_and_is_never_overwritten(self):
        path = tc.protocol("src/index.html", "Empieza tu primera pregunta del dominio 1", self.out)
        text = path.read_text(encoding="utf-8")
        self.assertIn("five readers of the audience", text)
        self.assertIn("completed: null", text)
        self.assertIn('"Empieza tu primera pregunta del dominio 1"', text)
        with self.assertRaises(FileExistsError):
            tc.protocol("src/index.html", "another task", self.out)
        report = tc.evidence(self.out, ["src/index.html"])
        self.assertEqual(report["tests"][0]["state"], "not run")
        self.assertEqual(report["untested_pages"], ["src/index.html"])

    def test_five_readers_make_a_page_tested_and_rates_come_from_what_they_did(self):
        import yaml
        path = tc.protocol("index.html", "Start a question", self.out)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["questions"] = [{"ask": "What is partition pruning?", "right": "Reading only the needed partitions"},
                             {"ask": "Where do you start?", "right": "Domain 1"}]
        readers = [{"who": "student", "completed": n != 4, "seconds": 40 + n, "right_answers": 2 if n < 3 else 1} for n in range(5)]
        data["rounds"] = [{"date": "2026-11-16", "readers": readers[:3], "decision": "shorter intro"},
                          {"date": "2026-11-20", "readers": readers, "decision": "keep"}]
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        test = tc.evidence(self.out, ["index.html", "about.html"])
        row = test["tests"][0]
        self.assertEqual((row["state"], row["rounds"], row["readers"], row["completed"]), ("tested", 2, 5, 4))
        self.assertEqual((row["completion_rate"], row["right_answer_rate"]), (0.8, 0.8))
        self.assertEqual(test["untested_pages"], ["about.html"])
        data["rounds"][-1]["readers"] = readers[:3]
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        self.assertEqual(tc.evidence(self.out)["tests"][0]["state"], "too few readers")

    def test_a_broken_file_is_reported_not_fatal(self):
        self.out.mkdir(parents=True)
        (self.out / "bad.yml").write_text("rounds: [unclosed\n")
        self.assertIn("not valid YAML", tc.evidence(self.out)["tests"][0]["problem"])


if __name__ == "__main__":
    unittest.main()
