"""Repository fingerprint: signals with their evidence, subprojects, the owner's declaration and the cache."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repo_fingerprint as fingerprint  # noqa: E402


def write(root: Path, files: dict) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")


def repo(root: Path, files: dict, commit: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write(root, files)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    if commit:
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


WEB = {"package.json": {"scripts": {"test": "vitest run", "build": "vite build"}, "dependencies": {"react": "19"},
                        "devDependencies": {"vite": "7", "typescript": "5", "vitest": "3", "@playwright/test": "1", "@axe-core/playwright": "4"}},
       "src/app.tsx": "export const a = 1\n", "tests/app.spec.ts": "x\n",
       ".standard.yml": "standard: SVN11X/standards@v1\nprofile: web\noptions:\n  experience: editorial\n"}
GO = {"go.mod": "module foco\n\ngo 1.23\n", "main.go": 'package main\nimport "golang.org/x/sys/windows"\nvar _ = windows.Handle(0)\n',
      "main_test.go": "package main\n"}
DATA = {"pyproject.toml": '[project]\nname = "x"\ndependencies = ["httpx", "beautifulsoup4"]\n[project.optional-dependencies]\ndev = ["pytest"]\n',
        "extract.py": "import httpx\n", "tests/test_resume.py": "def test_a(): pass\n"}
MONO = {"package.json": {"private": True}, "pnpm-workspace.yaml": "packages:\n  - apps/*\n", "pnpm-lock.yaml": "",
        "apps/web/package.json": {"dependencies": {"react": "19"}, "devDependencies": {"vite": "7", "vitest": "3"}, "scripts": {"test": "vitest run"}},
        "apps/web/src/main.tsx": "x\n",
        "apps/desktop/package.json": {"dependencies": {"@tauri-apps/api": "2"}},
        "apps/desktop/src-tauri/Cargo.toml": '[package]\nname = "d"\n'}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        os.environ["STANDARDS_HOME"] = str(self.root / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)

    def signals(self, data):
        return {s["id"]: s["evidence"] for s in data["signals"]}


class FingerprintTests(Base):
    def test_a_web_project_names_the_file_behind_every_signal(self):
        data = fingerprint.fingerprint(repo(self.root / "web", WEB))
        found = self.signals(data)
        for name in ("node", "react", "vite", "typescript", "vitest", "playwright", "axe", "tests", "web"):
            self.assertIn(name, found)
        self.assertEqual((found["react"], found["playwright"], found["tests"]), ("package.json", "package.json", "tests/app.spec.ts"))
        self.assertEqual(data["commands"], {"test": "npm test", "build": "npm run build"})
        self.assertEqual(data["schema"], "standards/repo-fingerprint/v1")
        self.assertRegex(data["revision"], r"^[0-9a-f]{40}$")

    def test_the_owners_declaration_is_read_before_the_files(self):
        data = fingerprint.fingerprint(repo(self.root / "web", WEB))
        self.assertEqual(data["standard"], {"present": True, "profile": "web", "experience": "editorial", "privacy": None, "parts": []})
        bare = fingerprint.fingerprint(repo(self.root / "go", GO))
        self.assertEqual((bare["standard"]["present"], bare["standard"]["profile"]), (False, None))

    def test_go_code_for_windows_is_a_desktop_project_with_go_tests(self):
        found = self.signals(fingerprint.fingerprint(repo(self.root / "go", GO)))
        self.assertEqual((found["go"], found["windows"], found["desktop"]), ("go.mod", "main.go", "main.go"))
        self.assertNotIn("web", found)
        self.assertEqual(fingerprint.fingerprint(self.root / "go")["commands"], {"test": "go test ./..."})

    def test_a_python_extractor_shows_its_libraries_and_its_test_command(self):
        data = fingerprint.fingerprint(repo(self.root / "data", DATA))
        found = self.signals(data)
        for name in ("python", "scraper", "http-client", "pytest", "tests"):
            self.assertIn(name, found)
        self.assertEqual(data["commands"]["test"], "python -m pytest -q")

    def test_a_single_page_without_a_manifest_is_a_static_site(self):
        found = self.signals(fingerprint.fingerprint(repo(self.root / "page", {"index.html": "<h1>x</h1>\n"})))
        self.assertEqual((found["static-web"], found["web"]), ("index.html", "index.html"))
        self.assertNotIn("node", found)

    def test_a_monorepo_lists_each_project_with_its_own_signals(self):
        data = fingerprint.fingerprint(repo(self.root / "mono", MONO))
        subs = {s["path"]: {x["id"] for x in s["signals"]} for s in data["subprojects"]}
        self.assertEqual(set(subs), {"apps/web", "apps/desktop"})
        self.assertIn("web", subs["apps/web"])
        self.assertIn("tauri", subs["apps/desktop"])
        self.assertIn("desktop", subs["apps/desktop"])
        self.assertNotIn("tauri", subs["apps/web"])
        web = next(s for s in data["subprojects"] if s["path"] == "apps/web")
        self.assertEqual(web["commands"], {"test": "pnpm test"})

    def test_latex_hardware_and_infrastructure_files_are_seen(self):
        files = {"thesis/main.tex": "x", "thesis/refs.bib": "x", "board/main.kicad_pcb": "x", "fw/platformio.ini": "x",
                 "infra/main.tf": "x", "Dockerfile": "FROM scratch\n", ".github/workflows/ci.yml": "on: push\n"}
        found = self.signals(fingerprint.fingerprint(repo(self.root / "mix", files)))
        for name in ("latex", "bibliography", "kicad", "firmware", "terraform", "docker", "ci"):
            self.assertIn(name, found)

    def test_ignored_folders_and_files_never_give_a_signal(self):
        files = {**DATA, ".gitignore": "node_modules/\ndist/\n", "node_modules/react/package.json": {"dependencies": {"react": "19"}},
                 "dist/index.html": "<h1>built</h1>"}
        found = self.signals(fingerprint.fingerprint(repo(self.root / "data", files)))
        self.assertNotIn("react", found)
        self.assertNotIn("web", found)

    def test_a_folder_outside_git_is_read_with_a_bounded_walk(self):
        folder = self.root / "plain"
        write(folder, {"index.html": "<h1>x</h1>", "node_modules/pkg/package.json": "{}"})
        data = fingerprint.fingerprint(folder)
        self.assertIsNone(data["revision"])
        self.assertEqual(self.signals(data)["static-web"], "index.html")
        self.assertNotIn("node", self.signals(data))

    def test_a_broken_manifest_is_skipped_not_fatal(self):
        data = fingerprint.fingerprint(repo(self.root / "bad", {"package.json": "{not json", "index.js": "x\n"}))
        self.assertIn("node", self.signals(data))


class RealLayoutTests(Base):
    """Layouts of the owner's repositories that a first run on the real repositories got wrong."""

    def test_a_built_site_with_its_manifest_at_the_root_is_one_web_project(self):
        files = {"package.json": {"scripts": {"build": "node scripts/build.mjs", "test": "node --test tests/*.test.mjs"},
                                  "devDependencies": {"@mermaid-js/mermaid-cli": "11"}},
                 "src/index.html": "<h1>x</h1>", "scripts/build.mjs": "x", "tests/core.test.mjs": "x"}
        data = fingerprint.fingerprint(repo(self.root / "site", files))
        found = self.signals(data)
        self.assertEqual((found["web"], found["node"]), ("src/index.html", "package.json"))
        self.assertNotIn("static-web", found)
        self.assertEqual(data["subprojects"], [])
        self.assertEqual(data["commands"]["test"], "npm test")

    def test_tests_written_with_unittest_give_the_unittest_command(self):
        files = {"requirements_dev.txt": "PyYAML>=6\n", "extractor.py": "import json\n",
                 "tests/test_extractor.py": "import unittest\n\n\nclass T(unittest.TestCase):\n    pass\n"}
        data = fingerprint.fingerprint(repo(self.root / "ext", files))
        self.assertEqual(data["commands"]["test"], "python -m unittest discover -s tests")
        self.assertEqual(self.signals(data)["unittest"], "tests/test_extractor.py")


class CacheTests(Base):
    def test_the_same_commit_is_read_once_and_a_changed_manifest_is_read_again(self):
        root = repo(self.root / "web", WEB)
        first = fingerprint.fingerprint(root)
        again = fingerprint.fingerprint(root)
        self.assertEqual((first["cached"], again["cached"]), (False, True))
        self.assertEqual(again["signals"], first["signals"])
        manifest = json.loads((root / "package.json").read_text())
        manifest["dependencies"]["three"] = "0.170"
        (root / "package.json").write_text(json.dumps(manifest) + "\n")
        changed = fingerprint.fingerprint(root)
        self.assertFalse(changed["cached"])
        self.assertIn("three", self.signals(changed))

    def test_no_cache_reads_again_and_nothing_is_written_inside_the_repository(self):
        root = repo(self.root / "web", WEB)
        fingerprint.fingerprint(root)
        self.assertFalse(fingerprint.fingerprint(root, use_cache=False)["cached"])
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
        self.assertEqual(status, "")
        self.assertEqual(len(list((self.root / "home" / "fingerprints").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
