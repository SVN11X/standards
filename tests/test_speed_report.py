"""Lighthouse JSON reports read into medians, failing audits and a before and after comparison."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "web-improve" / "scripts"))

import speed_report  # noqa: E402


def report(perf=0.8, lcp=3200, tbt=350, cls=0.05, form="mobile", version="12.8.2", lazy_saving=900):
    """The parts of a Lighthouse 12 result the report reads, in the shape Lighthouse writes them."""
    return {"lighthouseVersion": version, "finalDisplayedUrl": "https://example.org/",
            "configSettings": {"formFactor": form, "throttlingMethod": "simulate"},
            "categories": {"performance": {"score": perf}, "accessibility": {"score": 0.96},
                           "best-practices": {"score": 1}, "seo": {"score": 0.92}},
            "audits": {
                "first-contentful-paint": {"score": 0.9, "numericValue": 1500, "scoreDisplayMode": "numeric"},
                "largest-contentful-paint": {"score": 0.5, "numericValue": lcp, "scoreDisplayMode": "numeric"},
                "total-blocking-time": {"score": 0.6, "numericValue": tbt, "scoreDisplayMode": "numeric"},
                "cumulative-layout-shift": {"score": 1, "numericValue": cls, "scoreDisplayMode": "numeric"},
                "speed-index": {"score": 0.9, "numericValue": 3000, "scoreDisplayMode": "numeric"},
                "largest-contentful-paint-element": {"score": 0, "scoreDisplayMode": "metricSavings", "details": {
                    "type": "list", "items": [{"type": "table", "items": [{"node": {
                        "snippet": '<img src="hero.avif" loading="lazy">', "selector": "main > img"}}]}]}},
                "lcp-lazy-loaded": {"score": 0, "scoreDisplayMode": "metricSavings", "title": "LCP image was lazily loaded",
                                    "metricSavings": {"LCP": lazy_saving}},
                "render-blocking-resources": {"score": 0.5, "scoreDisplayMode": "metricSavings",
                                              "details": {"overallSavingsMs": 300, "items": [{"url": "/site.css"}]}},
                "unused-javascript": {"score": 0.95, "scoreDisplayMode": "metricSavings", "metricSavings": {"LCP": 50}},
                "uses-http2": {"score": None, "scoreDisplayMode": "notApplicable"}}}


class SpeedReportTests(unittest.TestCase):
    def test_three_runs_give_medians_and_the_failing_audits_of_the_median_run(self):
        data = speed_report.summary([report(0.78, lcp=3400), report(0.82, lcp=3000), report(0.8, lcp=3200)])
        self.assertEqual((data["runs"], data["scores"]["performance"], data["performance_spread"]), (3, 80, 4))
        self.assertEqual(data["metrics"]["LCP"], 3.2)
        self.assertFalse(data["good"]["LCP"])
        self.assertTrue(data["good"]["CLS"])
        self.assertEqual([a["id"] for a in data["failing"]], ["lcp-lazy-loaded", "render-blocking-resources", "largest-contentful-paint-element"])
        self.assertIn('loading="lazy"', data["lcp_element"])
        self.assertIsNone(data["note"])

    def test_one_run_is_flagged_as_too_few(self):
        self.assertIn("fewer than 3 runs", speed_report.summary([report()])["note"])

    def test_a_change_inside_the_spread_is_not_an_improvement(self):
        before = [report(0.78), report(0.82), report(0.8)]
        self.assertEqual(speed_report.compare(before, [report(0.8), report(0.82), report(0.83)])["performance"],
                         "inside the spread between runs, not an improvement")
        better = speed_report.compare(before, [report(0.95, lcp=1900, lazy_saving=0)] * 3)
        self.assertEqual((better["performance"], better["score_change"]["performance"], better["metric_change"]["LCP"]),
                         ("better", 15, -1.3))
        self.assertEqual(better["warnings"], [])

    def test_runs_on_another_form_factor_are_not_comparable(self):
        result = speed_report.compare([report()] * 3, [report(form="desktop")] * 3)
        self.assertIn("not comparable", result["warnings"][0])

    def test_a_pagespeed_insights_reply_is_read_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "psi.json"
            path.write_text(json.dumps({"lighthouseResult": report()}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(speed_report.main(["summary", str(path)]), 0)
        self.assertIn("LCP 3.2s (not good)", out.getvalue())
        self.assertIn("lcp-lazy-loaded", out.getvalue())


if __name__ == "__main__":
    unittest.main()
