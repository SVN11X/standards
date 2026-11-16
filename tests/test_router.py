"""Router: what a request asks, which recipe and providers it gets, one task per order, and the hook that adds it.

The control cases of the owner's guide of 2026-11-15 are the tests named `test_control_*`.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import router  # noqa: E402
import workplan  # noqa: E402
from test_fingerprint import DATA, GO, MONO, WEB, repo, write  # noqa: E402

OPEN = {"owner": "session", "task_ttl_h": 12, "max_context_chars": 1800, "local_only": False, "privacy": "personal-public",
        "cost_mode": "existing-subscription", "why_local": ""}
LOCAL = {**OPEN, "local_only": True, "cost_mode": "local-only", "why_local": "cost mode local-only"}
RECIPES = router.load_recipes()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        os.environ["STANDARDS_HOME"] = str(self.root / "home")
        self.addCleanup(os.environ.pop, "STANDARDS_HOME", None)
        self.web = repo(self.root / "web", WEB)

    def decide(self, prompt, cwd=None, **kw):
        kw.setdefault("limits", OPEN)
        kw.setdefault("session", "s1")
        return router.decide(prompt, cwd or self.web, **kw)

    def provider(self, decision, capability):
        return next(c for c in decision["capabilities"] if c["capability"] == capability)


class ClassifyTests(unittest.TestCase):
    CASES = [
        ("Corrige esta página", "work"), ("¿Qué cambiarías?", "query"), ("Explícame por qué se duplica", "query"),
        ("Corrige por qué se duplica una transcripción al reanudar", "work"), ("¿Puedes corregir el formulario?", "work"),
        ("Por favor, agrega un test", "work"), ("Quiero que arregles el header", "work"), ("Corrígelo y súbelo", "work"),
        ("Sube los cambios y abre un PR", "publish"), ("Publica la versión", "publish"), ("push it", "publish"),
        ("Revisa este PR", "review"), ("Revísalo antes de subir", "review"), ("Revisa y corrige el formulario", "work"),
        ("Incorpora este repositorio al estándar", "setup"), ("Set up this repository", "setup"),
        ("Fix the login bug", "work"), ("Can you add a dark mode?", "work"), ("how would you fix this?", "query"),
        ("What does this function do?", "query"), ("Es mejor usar React o Svelte?", "query"),
        ("The build fails on CI", "other"), ("The release notes are wrong", "other"), ("Los cambios no se guardan", "other"),
        # A bug report written as "it generates an error" reads as an order to fix it.
        ("Genera un error al guardar", "work"), ("gracias", "other"), ("/help", "other"), ("", "other"),
        ("Busca una foto libre de un centro de datos", "work"), ("Dibuja un diagrama del flujo", "work"),
        ("Find a free photo of a data center", "work"), ("La ventana tarda en cargar, mejora el rendimiento", "work"),
        ("El botón falla, arréglalo", "work"), ("Los cambios no se guardan, ¿por qué?", "query"),
        ("Esto está lento y no sé por qué", "other"),
    ]

    def test_orders_questions_reviews_setups_and_publications(self):
        for text, expected in self.CASES:
            with self.subTest(text):
                self.assertEqual(router.classify(text)[0], expected)

    def test_every_answer_says_why(self):
        self.assertIn("corrige", router.classify("Corrige esta página")[1])
        self.assertIn("qué", router.classify("¿Qué cambiarías?")[1])


class ControlCases(Base):
    def test_control_a_question_ends_with_an_explanation_and_opens_no_task(self):
        decision = self.decide("¿Qué cambiarías en esta página?")
        self.assertEqual((decision["intent"], decision["task"]["state"], decision["recipe"]), ("query", "none", None))
        self.assertEqual(router.render(decision), "")
        self.assertEqual(router.read_tasks(), [])
        self.assertFalse(decision["writes"])

    def test_control_an_order_in_a_known_project_starts_exactly_one_task(self):
        decision = self.decide("Corrige el botón de la portada")
        self.assertEqual((decision["intent"], decision["task"]["state"], decision["owner"]), ("work", "new", "session"))
        tasks = router.read_tasks()
        self.assertEqual([(t["key"], t["state"], t["session"]) for t in tasks], [(decision["task"]["key"], "active", "s1")])
        self.assertEqual(decision["repository"]["name"], "web")
        self.assertRegex(decision["repository"]["revision"], r"^[0-9a-f]{40}$")

    def test_control_a_follow_up_updates_that_task(self):
        first = self.decide("Corrige el botón de la portada")
        for text in ("también cambia el color", "en azul", "mejor en verde"):
            again = self.decide(text)
            self.assertEqual((again["task"]["state"], again["task"]["key"]), ("updated", first["task"]["key"]), text)
        tasks = router.read_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual([u["text"] for u in tasks[0]["updates"]], ["también cambia el color", "en azul", "mejor en verde"])
        self.assertIn("follow-up of task " + first["task"]["key"], router.render(again))

    def test_control_a_missing_tool_gets_a_compatible_alternative_or_names_the_requirement(self):
        bare = repo(self.root / "bare", {"package.json": {"dependencies": {"react": "19"}}, "src/app.jsx": "x\n"})
        decision = self.decide("Mejora el diseño de la página", bare)
        browser = self.provider(decision, "browser-test")
        self.assertIsNone(browser["provider"])
        self.assertEqual(browser["requirement"], "The folder shows no playwright")
        self.assertIn("playwright-mcp", [a["provider"] for a in browser["alternatives"]])
        write(bare, {".mcp.json": {"mcpServers": {"playwright": {"command": "npx"}}}})
        configured = self.provider(self.decide("Mejora el diseño de la página", bare, session="s2"), "browser-test")
        self.assertEqual((configured["provider"], configured["available"]), ("playwright-mcp", True))
        with_test = self.provider(self.decide("Mejora el diseño de la página"), "browser-test")
        self.assertEqual(with_test["provider"], "playwright-test")

    def test_control_a_task_in_local_mode_keeps_its_data_on_the_machine(self):
        write(self.web, {".mcp.json": {"mcpServers": {"context7": {"command": "npx"}}}})
        recipes = copy.deepcopy(RECIPES)
        docs = recipes["capabilities"]["library-docs"]["providers"]
        docs.sort(key=lambda p: p["id"] != "context7")
        prompt = "Actualiza la página a la nueva versión de React"
        open_mode = self.provider(self.decide(prompt, recipes=recipes), "library-docs")
        self.assertEqual(open_mode["provider"], "context7")
        self.assertIn("context7: library names and the questions asked, sent to Upstash", self.decide(prompt, recipes=recipes, session="s2")["leaves_machine"])
        for limits in (LOCAL, {**OPEN, "local_only": True, "privacy": "work", "why_local": "a work folder"}):
            decision = self.decide(prompt, recipes=recipes, limits=limits, session="s3")
            local = self.provider(decision, "library-docs")
            self.assertEqual(local["provider"], "project-docs")
            refused = next(a for a in local["alternatives"] if a["provider"] == "context7")
            self.assertIn("keeps the task on this machine", refused["why_not"])
            self.assertFalse(any("context7" in line for line in decision["leaves_machine"]))
            self.assertFalse(any(c["runs"] == "remote" for c in decision["capabilities"] if c["provider"]))

    def test_with_merges_allowed_the_permission_names_the_checked_merge(self):
        home = Path(os.environ["STANDARDS_HOME"])
        home.mkdir(parents=True, exist_ok=True)
        (home / "local.yml").write_text("autopilot:\n  merge: when-green\n", encoding="utf-8")
        decision = self.decide("Sube los cambios y abre un PR", permission_mode="default")
        self.assertIn("merge_when_green.py", decision["permission"])
        self.assertIn("deploying waits for the owner", decision["permission"])
        self.assertNotIn("merge_when_green", self.decide("Explica el router")["permission"])

    def test_control_a_publication_goes_through_the_configured_permission(self):
        decision = self.decide("Sube los cambios y abre un PR", permission_mode="default")
        self.assertEqual((decision["intent"], decision["permission_mode"]), ("publish", "default"))
        self.assertIn("owner's configured permission decides", decision["permission"])
        self.assertIn("Permission: pushing, merging or deploying", router.render(decision))
        both = self.decide("Corrígelo y súbelo", session="s2")
        self.assertEqual(both["intent"], "work")
        self.assertIn("also asks to publish", both["permission"])


class SelectionTests(Base):
    def test_the_guide_examples_get_their_recipe_with_the_evidence(self):
        cases = [
            (self.web, "Mejora esta página para que alguien con poco tiempo entienda por qué estudiar el tema", "web-experience", "web"),
            (repo(self.root / "go", GO), "Corrige el foco de la ventana al cerrar", "windows-app", "software"),
            (repo(self.root / "data", DATA), "Corrige por qué se duplica una transcripción al reanudar", "data-pipeline", "data-ai"),
        ]
        for folder, prompt, recipe, profile in cases:
            with self.subTest(recipe):
                decision = self.decide(prompt, folder, session=recipe)
                self.assertEqual((decision["recipe"], decision["profile"]), (recipe, profile))
                self.assertTrue(all(s["evidence"] for s in decision["signals"]))
                self.assertTrue(decision["verification"]["proof"])

    def test_the_owners_profile_and_experience_win_over_the_recipe(self):
        decision = self.decide("Mejora el diseño de esta página")
        self.assertEqual((decision["profile"], decision["profile_why"]), ("web", "declared in .standard.yml"))
        self.assertEqual(decision["experience"]["subprofile"], "editorial")
        self.assertIn("owner chose it", decision["experience"]["why"])

    def test_a_repository_without_the_standard_is_told_so(self):
        decision = self.decide("Corrige el foco de la ventana", repo(self.root / "go", GO))
        self.assertTrue(any("no .standard.yml" in note for note in decision["notes"]))
        self.assertIn("The repository has no .standard.yml", decision["profile_why"])

    def test_a_native_window_is_never_proven_by_a_browser(self):
        decision = self.decide("Corrige el foco de la ventana al cerrar", repo(self.root / "go", GO))
        self.assertNotIn("browser-test", [c["capability"] for c in decision["capabilities"]])
        self.assertIn("a browser test does not prove that a native window works", decision["notes"])
        native = self.provider(decision, "native-ui-test")
        if os.name != "nt":
            self.assertEqual((native["provider"], native["requirement"]), (None, "It needs a windows machine and this one is not"))

    def test_several_possible_folders_ask_first_and_open_no_task(self):
        mono = repo(self.root / "mono", MONO)
        decision = self.decide("Arregla el problema de audio", mono)
        self.assertEqual(decision["questions"], ["Which folder is this about: apps/desktop, apps/web?"])
        self.assertEqual((decision["task"]["state"], decision["folder"]), ("none", "."))
        self.assertIn("Open question before any edit", router.render(decision))

    def test_the_words_of_the_request_pick_the_folder_when_only_one_kind_of_project_uses_them(self):
        mono = repo(self.root / "mono", MONO)
        desktop = self.decide("Corrige el foco de la ventana al cerrar", mono)
        self.assertEqual((desktop["folder"], desktop["recipe"], desktop["questions"]), ("apps/desktop", "windows-app", []))
        self.assertIn("words of this folder", desktop["folder_why"])
        web = self.decide("Mejora el diseño de la página", mono, session="s2")
        self.assertEqual((web["folder"], web["recipe"]), ("apps/web", "web-experience"))

    def test_a_package_of_a_workspace_is_verified_with_the_tests_of_the_root(self):
        files = {**MONO, "package.json": {"private": True, "scripts": {"test": "vitest run"}, "devDependencies": {"vitest": "3"}},
                 "packages/audio/package.json": {"name": "@x/audio"}, "packages/audio/src/index.ts": "x\n",
                 "tests/unit/audio.test.ts": "x\n"}
        mono = repo(self.root / "workspace", files)
        decision = self.decide("Arregla el problema de audio", mono)
        self.assertEqual((decision["folder"], decision["folder_why"]), ("packages/audio", "the request names this folder"))
        self.assertEqual((decision["verification"]["command"], decision["verification"]["where"]), ("pnpm test", "."))
        self.assertEqual(self.provider(decision, "unit-test")["provider"], "project-tests")

    def test_the_folder_of_the_session_or_the_one_the_request_names_needs_no_question(self):
        mono = repo(self.root / "mono", MONO)
        inside = self.decide("Arregla el problema de audio", mono / "apps" / "desktop")
        self.assertEqual((inside["folder"], inside["folder_why"], inside["questions"]), ("apps/desktop", "the session is inside this folder", []))
        named = self.decide("Arregla el problema de audio en apps/web", mono, session="s2")
        self.assertEqual((named["folder"], named["folder_why"]), ("apps/web", "the request names this folder"))
        self.assertEqual(named["verification"], {"command": "pnpm test", "where": "apps/web", "proof": named["verification"]["proof"],
                                                 "install": "pnpm install --frozen-lockfile"})

    def test_a_client_only_gets_the_providers_it_can_use(self):
        claude = self.decide("Mejora el diseño de la página", client="claude")
        design = self.provider(claude, "visual-design")
        self.assertEqual(design["provider"], "web-improve")
        coordinator = self.decide("Mejora el diseño de la página", client="coordinator", session="s2")
        refused = {a["provider"]: a["why_not"] for a in self.provider(coordinator, "visual-design")["alternatives"]}
        self.assertEqual(refused["frontend-design"], "not offered in coordinator")
        self.assertEqual(self.provider(coordinator, "visual-design")["provider"], "impeccable")
        with self.assertRaises(ValueError):
            self.decide("x", client="cursor")

    def test_a_tool_on_hold_is_never_offered_and_one_in_assessment_says_so(self):
        recipes = copy.deepcopy(RECIPES)
        recipes["capabilities"]["browser-test"]["providers"][0]["status"] = "hold"
        recipes["capabilities"]["browser-test"]["providers"][0].pop("radar")
        browser = self.provider(self.decide("Mejora el diseño de la página", recipes=recipes), "browser-test")
        self.assertNotEqual(browser["provider"], "playwright-test")
        self.assertIn({"provider": "playwright-test", "why_not": "on hold in the radar"}, browser["alternatives"])
        axe = self.provider(self.decide("Mejora el diseño de la página", session="s2"), "accessibility")
        self.assertEqual((axe["provider"], axe["status"]), ("axe-playwright", "assess"))
        self.assertIn("In assessment", axe["why"])

    def test_a_language_server_is_offered_only_where_its_language_is(self):
        decision = self.decide("Corrige el cálculo del total", repo(self.root / "data", DATA))
        refused = {a["provider"]: a["why_not"] for a in self.provider(decision, "code-navigation")["alternatives"]}
        self.assertEqual(refused["gopls"], "the folder has no go files")
        self.assertEqual(refused["typescript-lsp"], "the folder has no typescript files")

    def test_a_decision_follows_its_schema(self):
        schema = json.loads((ROOT / "schemas" / "route-decision.schema.json").read_text(encoding="utf-8"))
        for prompt in ("Mejora el diseño de la página", "¿Qué cambiarías?", "Sube los cambios", "Revisa este PR", "gracias"):
            with self.subTest(prompt):
                decision = self.decide(prompt, session=prompt)
                self.assertEqual(workplan.check_schema(decision, schema, "decision"), [])
        broken = {**decision, "intent": "guess"}
        self.assertTrue(workplan.check_schema(broken, schema, "decision"))

    def test_the_fingerprint_of_the_same_commit_is_reused_and_said(self):
        self.decide("Mejora el diseño de la página")
        self.assertEqual(self.decide("Corrige el título", session="s2")["reused"], ["the fingerprint saved for this commit"])

    def test_the_context_stays_short(self):
        text = router.render(self.decide("Mejora el diseño de la página"), 600)
        self.assertLessEqual(len(text), 600)
        self.assertIn("(shortened)", text)
        self.assertRegex(text.splitlines()[-1], r"^Task \w+ opened")
        lines = ["first fact", "Note: a", "second fact", "Note: b", "Task k opened. `router.py done k` closes it."]
        self.assertEqual(router.shorten(lines, 80), "first fact\nsecond fact\n(shortened)\nTask k opened. `router.py done k` closes it.")
        self.assertEqual(router.shorten(["a" * 50, "b" * 50], 70), "a" * 50 + "\n(shortened)")


class LearningVisualWritingTests(Base):
    """Recipes added on 2026-11-16: learning sites, visual assets, clarity of the text, and the guide's other families."""

    QUIZ = {"package.json": {"scripts": {"test": "vitest run"}, "dependencies": {"react": "19"}, "devDependencies": {"vitest": "3"}},
            "src/App.tsx": "x\n", "src/content/questions.json": [{"question": "q", "options": ["a", "b", "c"], "answer": 0}]}

    def test_a_learning_request_in_a_repository_with_a_question_bank(self):
        quiz = repo(self.root / "quiz", self.QUIZ)
        decision = self.decide("Mejora el aprendizaje, que las preguntas ayuden a recordar", quiz)
        self.assertEqual(decision["recipe"], "learning-site")
        chosen = {c["capability"]: c["provider"] for c in decision["capabilities"]}
        self.assertEqual((chosen["question-quality"], chosen["learning-design"], chosen["comprehension-test"]),
                         ("learning-check", "learning-science", "reader-test"))
        self.assertIn("recall later", decision["notes"][0])
        self.assertIn("five learners", decision["verification"]["proof"])

    def test_a_learning_request_in_a_desktop_tutor_gets_the_learning_app_recipe(self):
        """Found on OpenTutor: a Windows tutor whose questions live in code got the windows-app recipe."""
        files = {"pyproject.toml": '[project]\nname = "t"\n', "requirements-dev.txt": "ruff\n", "src/tutor/__init__.py": "",
                 "src/tutor/desktop.py": "import tkinter\n", "tests/test_core.py": "import unittest\n"}
        tutor = repo(self.root / "tutor", files)
        decision = self.decide("Mejora las preguntas para que ayuden a recordar", tutor)
        self.assertEqual((decision["recipe"], decision["experience"]), ("learning-app", None))
        self.assertNotIn("browser-test", [c["capability"] for c in decision["capabilities"]])
        self.assertEqual(self.decide("Corrige el foco de la ventana del cuestionario", tutor, session="s2")["recipe"], "windows-app")
        self.assertEqual(decision["verification"]["install"],
                         ["python -m pip install -r requirements-dev.txt", "python -m pip install -e ."])

    def test_a_diagram_and_a_clip_get_the_visual_recipe_with_their_tools(self):
        files = {**WEB, "docs/flow.mmd": "graph LR\n a-->b\n", "assets/clip.webm": "x", "assets/clip.vtt": "WEBVTT\n"}
        decision = self.decide("Agrega un diagrama de la arquitectura y un video corto que lo explique", repo(self.root / "vis", files))
        self.assertEqual(decision["recipe"], "visual-asset")
        chosen = {c["capability"]: c["provider"] for c in decision["capabilities"]}
        self.assertEqual((chosen["diagram"], chosen["image-attach"]), ("mermaid-cli", "media-attach"))
        self.assertIn(chosen["short-video"], ("hyperframes", "manim", "motion-canvas", "remotion", "opencut"))
        self.assertIn("media-search: the search words, sent to Openverse and Wikimedia", decision["leaves_machine"])
        self.assertIn("captions and a poster", decision["verification"]["proof"])

    def test_an_image_search_never_leaves_the_machine_in_local_mode(self):
        decision = self.decide("Busca una foto libre para la portada", limits=LOCAL)
        search = self.provider(decision, "image-search")
        self.assertIsNone(search["provider"])
        self.assertIn("keeps the task on this machine", search["alternatives"][0]["why_not"])
        self.assertFalse(any("Openverse" in line for line in decision["leaves_machine"]))

    def test_a_request_about_the_text_gets_the_writing_check_and_the_reader_test(self):
        decision = self.decide("Reescribe el README para que se entienda mejor", repo(self.root / "data", DATA))
        self.assertEqual(decision["recipe"], "content-clarity")
        self.assertEqual([c["provider"] for c in decision["capabilities"]], ["text-check", "reader-test", "web-improve"])
        self.assertIn("a readability score is a proxy", decision["notes"][0])

    def test_words_add_capabilities_to_another_recipe(self):
        decision = self.decide("Mejora el diseño de la página, agrega un diagrama y que cargue más rápido, está lenta")
        names = [c["capability"] for c in decision["capabilities"]]
        self.assertEqual(decision["recipe"], "web-experience")
        self.assertIn("diagram", names)
        self.assertIn("performance", names)
        self.assertTrue(any(note.startswith("diagram added") for note in decision["notes"]))

    def test_the_families_of_the_guide_get_their_recipes(self):
        cases = [({"setup.ps1": "Write-Host hi\n", "tests/setup.Tests.ps1": "Describe x {}\n"}, "Corrige el script de instalación", "powershell-script"),
                 ({"openapi.yaml": "openapi: 3.1.0\n", "package.json": {"devDependencies": {"msw": "2"}}}, "Agrega un endpoint al contrato de la API", "api-service"),
                 ({"main.tf": "terraform {}\n"}, "Ajusta la infraestructura de terraform", "infra"),
                 ({"board/main.kicad_pcb": "x", "fw/platformio.ini": "[env]\n"}, "Corrige el firmware del sensor", "hardware"),
                 ({"project.godot": "x", "main.gd": "x"}, "Corrige el salto del personaje", "mobile-app"),
                 ({".github/workflows/ci.yml": "on: push\n", "a.py": "x"}, "Actualiza el workflow de CI", "ci-maintenance")]
        for files, prompt, recipe in cases:
            with self.subTest(recipe):
                self.assertEqual(self.decide(prompt, repo(self.root / recipe, files), session=recipe)["recipe"], recipe)

    def test_the_catalog_names_hyperframes_and_every_provider_says_who_keeps_it(self):
        providers = [p for c in RECIPES["capabilities"].values() for p in c["providers"]]
        ids = {p["id"] for p in providers}
        for name in ("hyperframes", "manim", "mermaid-cli", "d2", "graphviz", "remotion", "motion-canvas", "media-search",
                     "learning-check", "text-check", "reader-test", "lighthouse-ci", "vale", "tesseract", "ffprobe"):
            self.assertIn(name, ids)
        for provider in providers:
            self.assertTrue(provider.get("radar") or provider.get("source") or provider.get("maintainer"), provider["id"])


class TaskTests(Base):
    def test_a_new_order_in_the_same_session_closes_the_old_task(self):
        first = self.decide("Corrige el botón de la portada")
        second = self.decide("Agrega una página de contacto")
        states = {t["key"]: t["state"] for t in router.read_tasks()}
        self.assertEqual(states, {first["task"]["key"]: "superseded", second["task"]["key"]: "active"})

    def test_a_new_session_is_told_about_the_work_an_old_one_left(self):
        first = self.decide("Corrige el botón de la portada", session="before-restart")
        after = self.decide("Mejora el título", session="after-restart")
        self.assertEqual(after["task"]["unfinished"]["key"], first["task"]["key"])
        self.assertIn("Unfinished task " + first["task"]["key"], router.render(after))
        asked = self.decide("gracias", session="third")
        self.assertEqual(asked["task"]["state"], "none")

    def test_done_closes_a_task_and_an_old_task_is_not_followed(self):
        first = self.decide("Corrige el botón de la portada")
        self.assertTrue(router.finish(first["task"]["key"]))
        self.assertFalse(router.finish("nope"))
        self.assertEqual(self.decide("también cambia el color")["task"]["state"], "new")
        stale = self.decide("Corrige el pie", session="old")
        row = next(t for t in router.read_tasks() if t["key"] == stale["task"]["key"])
        row["updated"] = "2020-01-01T00:00:00+00:00"
        router.write_task(row)
        self.assertEqual(self.decide("en azul", session="old")["task"]["state"], "none")

    def test_a_dry_decision_writes_no_task(self):
        decision = self.decide("Corrige el botón", save=False)
        self.assertEqual((decision["task"], router.read_tasks()), ({"key": None, "state": "none"}, []))

    def test_the_coordinator_owns_a_work_order_only_where_the_owner_said_so(self):
        session = self.decide("Corrige el botón")
        self.assertEqual((session["owner"], session["handoff"]), ("session", None))
        handed = self.decide("Corrige el botón", limits={**OPEN, "owner": "coordinator"}, session="s2")
        self.assertEqual(handed["owner"], "coordinator")
        self.assertIn("plan_autopilot.py", handed["handoff"])
        self.assertIn("the session edits no file", router.render(handed))
        for prompt, client in (("Revisa este PR", "claude"), ("Corrige el botón", "opencode")):
            kept = self.decide(prompt, client=client, limits={**OPEN, "owner": "coordinator"}, session=prompt + client)
            self.assertEqual(kept["owner"], "session")


    def test_a_work_order_the_session_keeps_names_the_agents_and_the_executors(self):
        text = router.render(self.decide("Corrige el botón"))
        self.assertIn("item-worker agents at once, each with isolation worktree", text)
        self.assertIn("route --all --repo .", text)
        handed = router.render(self.decide("Corrige el botón", limits={**OPEN, "owner": "coordinator"}, session="s2"))
        self.assertNotIn("item-worker", handed)
        self.assertNotIn("item-worker", router.render(self.decide("Revisa este PR", session="s3")))
        self.assertNotIn("item-worker", router.render(self.decide("Corrige el botón", client="opencode", session="s4")))

    def test_the_agents_that_fit_the_repository_are_named(self):
        web = router.render(self.decide("Corrige el botón"))
        self.assertIn("delegate-runner", web)
        self.assertIn("ci-fixer", web)
        self.assertIn("web-tester", web)
        self.assertNotIn("content-auditor", web)
        self.assertEqual(router.fitting_agents({"recipe": "learning-app", "signals": []}),
                         ["content-auditor before and after content changes."])
        self.assertEqual(router.fitting_agents({"recipe": "api-service", "signals": [{"id": "python"}]}), [])

    def test_consent_hands_work_orders_to_the_coordinator(self):
        home = Path(os.environ["STANDARDS_HOME"])
        home.mkdir(parents=True, exist_ok=True)
        (home / "local.yml").write_text("cost_mode: local-only\n", encoding="utf-8")
        ran = subprocess.run([sys.executable, str(ROOT / "scripts" / "orchestrate.py"), "consent", "--route", "coordinator"],
                             capture_output=True, text=True, env=os.environ.copy(), timeout=60)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(router.owner_limits(self.web)["owner"], "coordinator")
        self.assertIn("cost_mode: local-only", (home / "local.yml").read_text(encoding="utf-8"))

class PlanRouteTests(Base):
    def test_a_plan_keeps_the_route_of_its_request(self):
        import plan_autopilot
        route = plan_autopilot.route_of("Mejora el diseño de la página", self.web)
        self.assertEqual((route["recipe"], route["folder"], route["profile"]), ("web-experience", ".", "web"))
        self.assertIn({"capability": "browser-test", "provider": "playwright-test"}, route["capabilities"])
        self.assertEqual(router.read_tasks(), [], "planning opens no router task")
        with mock.patch.object(router, "decide", side_effect=RuntimeError("broken")):
            self.assertIsNone(plan_autopilot.route_of("Mejora el diseño", self.web))


class RecipeFileTests(unittest.TestCase):
    def test_the_recipes_point_only_at_things_that_exist(self):
        self.assertEqual(router.check(), [])

    def test_a_broken_recipe_file_is_reported(self):
        recipes = copy.deepcopy(RECIPES)
        recipes["recipes"][0]["capabilities"].append("teleport")
        recipes["recipes"].append({**recipes["recipes"][1], "proof": ""})
        recipes["capabilities"]["browser-test"]["providers"][0]["radar"] = "No Such Tool"
        recipes["capabilities"]["library-docs"]["providers"][1]["leaves_machine"] = "nothing"
        recipes["capabilities"]["github"]["providers"][0]["clients"] = ["cursor"]
        problems = " | ".join(router.check(recipes))
        for text in ("unknown capability teleport", "listed twice", "no proof of done", "radar entry 'No Such Tool' does not exist",
                     "a remote provider must say what leaves the machine", "clients must be a list"):
            self.assertIn(text, problems)

    def test_the_owners_limits_fail_closed(self):
        with mock.patch.dict(sys.modules, {"orchestrate": None}):
            limits = router.owner_limits(ROOT)
        self.assertTrue(limits["local_only"])
        self.assertEqual(limits["owner"], "session")


class HookTests(Base):
    def hook(self, payload, env=None):
        ran = subprocess.run([sys.executable, str(ROOT / "hooks" / "route_prompt.py")], input=payload if isinstance(payload, str) else json.dumps(payload),
                             capture_output=True, text=True, timeout=60, env={**os.environ, **(env or {})})
        return ran.returncode, ran.stdout.strip()

    def test_a_work_request_gets_the_decision_as_context(self):
        code, out = self.hook({"prompt": "Mejora el diseño de la página", "cwd": str(self.web), "session_id": "h1", "permission_mode": "default"})
        self.assertEqual(code, 0)
        added = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(added["hookEventName"], "UserPromptSubmit")
        for text in ("work request", "repository web", "Recipe web-experience", "browser-test: playwright-test", "Verification: `npm test`", "Task "):
            self.assertIn(text, added["additionalContext"])
        self.assertLessEqual(len(added["additionalContext"]), 1800)

    def test_a_question_a_thanks_and_a_folder_outside_git_get_nothing(self):
        plain = self.root / "plain"
        write(plain, {"index.html": "<h1>x</h1>"})
        for payload in ({"prompt": "¿Qué cambiarías?", "cwd": str(self.web)}, {"prompt": "gracias", "cwd": str(self.web)},
                        {"prompt": "Corrige el título", "cwd": str(plain)}, {"prompt": "", "cwd": str(self.web)}):
            with self.subTest(payload["prompt"]):
                self.assertEqual(self.hook(payload), (0, ""))

    def test_the_hook_never_blocks_a_request(self):
        self.assertEqual(self.hook("not json"), (0, ""))
        self.assertEqual(self.hook({"prompt": "Corrige el título", "cwd": "/no/such/folder"}), (0, ""))
        self.assertEqual(self.hook({"prompt": ["not", "text"], "cwd": str(self.web)}), (0, ""))

    def test_hooks_json_runs_it_on_every_prompt(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        entry = hooks["UserPromptSubmit"][0]
        self.assertNotIn("matcher", entry)
        self.assertIn("route_prompt.py", entry["hooks"][0]["command"])
        self.assertLessEqual(entry["hooks"][0]["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
