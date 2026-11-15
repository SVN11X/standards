"""Visual assets: license-aware search with fake Openverse and Commons answers, attach with credits, media audit."""
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import media  # noqa: E402

# Field names as api/api/serializers/media_serializers.py of WordPress/openverse returns them.
OPENVERSE = {"result_count": 3, "results": [
    {"id": "a1", "title": "Data pipeline", "url": "https://live.example/a1.jpg", "foreign_landing_url": "https://flickr.example/a1",
     "creator": "Ana", "creator_url": "https://flickr.example/ana", "license": "by", "license_version": "4.0",
     "license_url": "https://creativecommons.org/licenses/by/4.0/", "provider": "flickr", "source": "flickr",
     "width": 1600, "height": 900, "filetype": "jpg", "attribution": "\"Data pipeline\" by Ana is licensed under CC BY 4.0."},
    {"id": "a2", "title": "Pipes", "url": "https://live.example/a2.jpg", "foreign_landing_url": "https://flickr.example/a2",
     "creator": "Bo", "license": "by-nc", "license_version": "2.0", "width": 800, "height": 600},
    {"id": "a3", "title": "Public pipes", "url": "https://live.example/a3.png", "foreign_landing_url": "https://museum.example/a3",
     "creator": None, "license": "cc0", "license_version": "1.0", "width": 1200, "height": 800}]}
# Keys of imageinfo and extmetadata as the CommonsMetadata extension returns them.
COMMONS = {"query": {"pages": {
    "11": {"pageid": 11, "index": 2, "title": "File:Etl diagram.svg", "imageinfo": [{
        "url": "https://upload.example/Etl_diagram.svg", "thumburl": "https://upload.example/thumb/Etl_diagram.svg.png",
        "descriptionurl": "https://commons.example/wiki/File:Etl_diagram.svg", "width": 1024, "height": 512, "mime": "image/svg+xml",
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                        "Artist": {"value": "<a href='//commons.example/wiki/User:Carla'>Carla</a>"}, "AttributionRequired": {"value": "true"}}}]},
    "12": {"pageid": 12, "index": 1, "title": "File:Logo.png", "imageinfo": [{
        "url": "https://upload.example/Logo.png", "descriptionurl": "https://commons.example/wiki/File:Logo.png", "width": 64, "height": 64,
        "mime": "image/png", "extmetadata": {"LicenseShortName": {"value": "Fair use"}}}]}}}}


def fake_fetch(calls):
    def fetch(url, timeout=20.0):
        calls.append(url)
        return OPENVERSE if "openverse" in url else COMMONS
    return fetch


class LicenseTests(unittest.TestCase):
    def test_commons_license_names_map_to_openverse_codes(self):
        cases = {"CC BY-SA 4.0": "by-sa", "CC BY 2.0": "by", "CC0": "cc0", "Public domain": "pdm", "CC BY-NC-ND 3.0": "by-nc-nd",
                 "Fair use": None, "": None, "GFDL": None}
        self.assertEqual({k: media.license_code(k) for k in cases}, cases)

    def test_only_commercial_and_changeable_licenses_by_default(self):
        self.assertEqual(media.allowed_licenses(None), {"cc0", "pdm", "by", "by-sa"})
        self.assertEqual(media.allowed_licenses(["nc"]) - media.allowed_licenses(None), {"by-nc", "by-nc-sa"})


class SearchTests(unittest.TestCase):
    def test_both_sources_keep_only_allowed_licenses_with_their_credit(self):
        calls = []
        report = media.search("data pipeline", fetch=fake_fetch(calls))
        found = {(r["source"], r["id"]): r for r in report["results"]}
        self.assertEqual(set(found), {("openverse", "a1"), ("openverse", "a3"), ("commons", 11)})
        ana = found[("openverse", "a1")]
        self.assertEqual((ana["license_name"], ana["creator"], ana["landing_url"]), ("CC BY 4.0", "Ana", "https://flickr.example/a1"))
        self.assertEqual(ana["credit"], "\"Data pipeline\" by Ana, CC BY 4.0, https://flickr.example/a1")
        carla = found[("commons", 11)]
        self.assertEqual((carla["license"], carla["creator"], carla["url"]), ("by-sa", "Carla", "https://upload.example/thumb/Etl_diagram.svg.png"))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0]).query)
        self.assertEqual(query["license"], ["by,by-sa,cc0,pdm"])
        self.assertEqual(report["leaves_machine"], "the query words, sent to Openverse and Wikimedia")

    def test_a_source_that_fails_leaves_the_other(self):
        def half(url, timeout=20.0):
            if "openverse" in url:
                raise OSError("Tunnel connection failed: 403 Forbidden")
            return COMMONS
        report = media.search("pipeline", fetch=half)
        self.assertEqual([r["source"] for r in report["results"]], ["commons"])
        self.assertIn("openverse: OSError", report["problems"][0])

    def test_non_commercial_results_appear_only_when_the_owner_allows_them(self):
        report = media.search("pipes", source="openverse", extra=["nc"], fetch=fake_fetch([]))
        self.assertIn("a2", [r["id"] for r in report["results"]])


class AttachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.item = media.search("x", source="openverse", fetch=fake_fetch([]))["results"][0]

    def test_a_result_is_saved_with_its_credit_and_alt_text(self):
        out = media.attach(self.item, Path("assets/img/pipeline.jpg"), "Data flowing from storage into a warehouse", self.root,
                           download=lambda url: b"JPEGDATA")
        self.assertEqual((self.root / "assets/img/pipeline.jpg").read_bytes(), b"JPEGDATA")
        credits = json.loads((self.root / "assets/CREDITS.json").read_text())
        entry = credits["assets"][0]
        self.assertEqual((entry["path"], entry["creator"], entry["license"], entry["alt"]),
                         ("assets/img/pipeline.jpg", "Ana", "by", "Data flowing from storage into a warehouse"))
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertIn('alt="Data flowing from storage into a warehouse"', out["markup"])
        self.assertIn('width="1600" height="900"', out["markup"])
        media.attach(self.item, Path("assets/img/pipeline.jpg"), "A new description", self.root, download=lambda url: b"JPEG2")
        self.assertEqual(len(json.loads((self.root / "assets/CREDITS.json").read_text())["assets"]), 1)

    def test_refused_without_alt_with_a_bad_license_without_author_or_outside_the_repository(self):
        nc = {**self.item, "license": "by-nc"}
        anonymous = {**self.item, "creator": None}
        cases = [(self.item, "assets/a.jpg", "", False, "alt text"), (nc, "assets/a.jpg", "Pipes", False, "not allowed"),
                 (anonymous, "assets/a.jpg", "Pipes", False, "names none"), (self.item, "../outside.jpg", "Pipes", False, "inside the repository"),
                 (self.item, "assets/a.jpg", "x" * 260, False, "250 characters")]
        for item, target, alt, decorative, message in cases:
            with self.subTest(message), self.assertRaisesRegex(media.MediaError, message):
                media.attach(item, Path(target), alt, self.root, decorative=decorative, download=lambda url: b"X")
        self.assertFalse((self.root / "assets").exists(), "nothing is written when the attach is refused")

    def test_a_decorative_image_needs_no_alt_and_public_domain_needs_no_author(self):
        public = {**self.item, "license": "cc0", "creator": None}
        out = media.attach(public, Path("assets/bg.jpg"), None, self.root, decorative=True, download=lambda url: b"X")
        self.assertEqual((out["entry"]["decorative"], out["entry"]["alt"]), (True, None))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text) if isinstance(text, bytes) else path.write_text(text, encoding="utf-8")

    def test_images_and_video_that_a_reader_would_miss(self):
        self.write("index.html", '<img src="a.png" alt="A pipeline" width="10" height="10"><img src="b.png">'
                                 '<img src="c.png" alt="imagen" width="1" height="1"><img src="d.png" alt="" role="presentation">'
                                 '<video src="v.mp4" autoplay></video><video src="w.webm" poster="w.jpg" muted></video>'
                                 '<video src="x.mp4" poster="x.jpg"><track kind="captions" src="x.vtt"></video>')
        self.write("doc.md", "Text ![](shot.png) and code `<img src=x>` and\n```\n<img src=y>\n```\n![Chart of costs](chart.png)\n")
        self.write("big.png", b"0" * 400_000)
        self.write("icon.svg", '<svg onload="alert(1)"></svg>')
        issues = media.audit(self.root)["issues"]
        self.assertEqual([(i["file"], i["src"]) for i in issues["no-alt"]], [("doc.md", "shot.png"), ("index.html", "b.png")])
        self.assertEqual([i["alt"] for i in issues["vague-alt"]], ["imagen"])
        self.assertEqual(len(issues["no-size"]), 2)
        self.assertEqual(len(issues["video-no-captions"]), 1)
        self.assertEqual(len(issues["video-no-poster"]), 1)
        self.assertEqual(len(issues["video-autoplay-sound"]), 1)
        self.assertEqual(issues["heavy"], [{"file": "big.png", "bytes": 400_000}])
        self.assertEqual(issues["svg-script"], [{"file": "icon.svg"}])
        self.assertEqual(issues["no-credits-at-all"][0]["files"], 2)

    def test_credits_come_from_the_file_a_page_a_folder_mention_or_reuse(self):
        for name in ("assets/icons/a.svg", "assets/img/b.png", "assets/img/c.png", "assets/video/d.mp4", "e.png"):
            self.write(name, b"x")
        self.write("assets/CREDITS.json", json.dumps({"assets": [{"path": "assets/img/b.png"}]}))
        self.write("docs/credits.md", "| Lucide icons | ISC | `assets/icons/` |\n| Clip | owner | d.mp4 |\n")
        self.write("REUSE.toml", 'version = 1\n[[annotations]]\npath = "e.png"\nSPDX-License-Identifier = "CC0-1.0"\n')
        report = media.audit(self.root)
        self.assertEqual(report["issues"].get("no-credit"), [{"file": "assets/img/c.png"}])
        self.assertEqual(report["credit_sources"], {"file_entries": 1, "pages": 1, "reuse_globs": 1})

    def test_ignored_folders_are_not_audited(self):
        self.write("node_modules/pkg/x.html", "<img src=a>")
        self.write("dist/index.html", "<img src=a>")
        self.assertEqual(media.audit(self.root)["issues"], {})


if __name__ == "__main__":
    unittest.main()
