# Changelog

All notable changes to this standard are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/2.0.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Every Ollama call, in the bench and in real work, runs at temperature 0 with seed 42, and puts every layer on the card when the model file plus `executors.ollama.full_gpu_margin_mib` fits in its memory. Ollama's own split had left 18 % of `qwen2.5:7b` on the CPU, 6.45 s on classify instead of 2.23 s. Bench rows record the options they ran with.

### Fixed

- The proposed split of `analyze.py report` named `opencode/glm-5.3-flash-free` first for the edit tasks after `opencode models` stopped listing it. The split now leaves out every model the last run found retired.
- A blocked OpenCode route gave only the first refusal. In local-only that blamed the retired glm model, while the cost mode was what refused deepseek and mimo. The reason now names every distinct refusal.

## [1.24.0] - 2026-11-21

The owner asked on 2026-11-21 for the four principles of andrej-karpathy-skills (MIT), drawn from Andrej Karpathy's post on the coding mistakes of language models, and for what fits from HyperQwen. Both are written here in the standard's own words.

### Added

- Base rules: every changed line traces to the task, with no reformatting, renaming or refactoring of the code next to it and the style around it kept. An agent removes what its own change left unused and mentions other dead code in the pull request instead of deleting it. A new slop rule: no feature, option or error handling that nobody asked for or that covers a case that cannot happen.
- The code-review skill checks the scope of a change right after its contract, and `prompts/review.md` does the same for tools without skills. `skills/code-review/evals.yml` gets a case with a rename and a deleted function next to the fix.
- A radar entry for andrej-karpathy-skills at adopt, and its sources in `references.md`.
- From HyperQwen (Apache-2.0), which the owner sent on 2026-11-21. Bench rows record the GPU driver and power limit that `nvidia-smi` reports, and the Ollama version, and the analyzer report prints them. `docs/006-model-analyzer.md` asks an engine pilot for the six things that make two runs comparable, to discard the first run after a server start, to pair every speed with a quality check, and to measure prompt drafting on edit tasks apart. The software profile lists a patch against a pinned dependency among the techniques that need a reason, with one line per patch in `docs/patches.md`. HyperQwen goes on hold in the radar: it needs 24 GB on one card or several cards together.

### Changed

- `AGENTS.md`: the Understanding block gives the check of each step of the plan, names both readings of an ambiguous request, says when a simpler way exists and stops on what is unclear. Before code changes, the task becomes a check: a test that fails first for a bug, the tests passing before and after for a refactor.
- The slop rule on dead code now covers the code an agent writes, so it no longer tells an agent to delete dead code that was there before.

## [1.23.0] - 2026-11-21

The owner's plan of 2026-11-21 ("Plan de mejoras para STANDARDS") asked for these changes. What needs the notebook, its RTX 2060 or the owner's accounts is prepared here and listed in `docs/improvement-plan.md`.

### Added

- The analyzer lists the model Colibri serves as a coding agent through OpenCode, a stopped Colibri as not reachable, and each id its bench history names with its own evidence. OpenCode announcing the same model as `colibri/<id>` is counted once. Colibri's agent runs are planned only with `--local-agents`, and no Ollama model stays on the card while they run.
- `orchestrate.py route TASK --executor colibri [--model colibri/<id>]` pins one executor: it is used or the route is blocked with the reason, with no fallback, and the answer names the served model and its bench evidence for the task. The prompt hook does the same for a work request that says "con Colibri", "with Ollama" or "using OpenCode". Delegated runs record model, input and output tokens and seconds, and `delegate` and `runs` print them with `n/a` for a counter nobody reported.
- `executors.ollama.prefer_by_task` gives a task type its own order of local models, and a task type without one inherits `prefer`. The short tasks keep `qwen3.5:4b` first and `qwen2.5:7b` to compare. `route` lists each model it passed over in `rejected_models` with the reason. A catalog entry of kind `embedding`, `reranker` or `speech` never gets a chat task.
- `memory.py index`, `find` and `eval`: meaning vectors from the local Ollama embedding model, added to the FTS5 word search and fused by key, with repository, source, content hash, model, revision and dimensions for every vector. `recall.py` uses them once a repository is indexed, so a Spanish question finds an English note with its source, and its lines stay within a budget. `eval` prints hits in the first 3 and 10 per language and kind for words alone and for words and meaning.
- Radar entries for the engines and options of the plan: llama.cpp, llama.cpp-BELLS, FreeToken-Kai, ik_llama.cpp and InferSSD at assess, KTransformers, MoE-Infinity, Slipstream, AirLLM, Diffusers_minimax-h3 and Memorilla on hold with what reopens each, and Transformers.js, model-viewer, OpenSandbox and T3 Code at assess. Licenses nobody read say `not verified`.
- `settings/models.yml` lists the specialists per job (extraction, plans and code, screenshots, documents, audio) with the order to evaluate them and the test before each is wired to a real caller. Nothing routes to them.
- Recipes and capabilities: `web-visitor-ai` with `static-search` and `visitor-ai` (static first, Cloudflare Workers AI through the site's own Worker, ModelBest on hold), `3d-preview` for hardware, `isolated-test` and `remote-node`.
- `scripts/workqueue.py`: a queue between the owner's remote VM and the notebook over SSH, with claims that expire and wait for a check, one result per task, a secret scan of every result, backup and restore, and no entry for a local-only task or a repository outside `remote_node.allow_classes`.
- `standard.py check` warns on an STL over the 10 MB limit of the GitHub viewer and on an STL with no STEP or STP master. The hardware profile with mechanical design gets the matching rule.
- `docs/006-model-analyzer.md` has the rule of an engine pilot: a median 15 % better with the same quality, or a task the current setup cannot finish in time. `docs/005-verification-and-orchestration.md` explains recall by meaning, public sites with the owner's machine off, the 3D view, disposable tests and the remote node with its sizing on Oracle Always Free.

- From the ConquerAI video of 2026-11-16 on Lauren Tan's agent workflow. Guardrails in `.standard.yml`: forbidden patterns per file glob and module boundaries read from Python and JavaScript or TypeScript imports, enforced by `standard.py check` as errors and listed in the generated `AGENTS.md`. `scripts/skill_eval.py` runs the cases of a skill's `evals.yml` several times on fresh fixtures, grades each answer with a program and flags a step half the runs or more missed, with a first case for `code-review`. `AGENTS.md` asks an agent to follow the person's steps in the running app before and after a change. The optional `docs/feature-map.md` says where each feature, its code and its test live, the check warns on a missing path, and the web and desktop testers read it. Delegated runs record the files and lines of their commit, and the execution report gives each unit's size and test seconds.
- `standard.py check . --pr --title "<title>" --body-file <file>` checks a pull request before it is opened.
- `orchestrate.py consent --merge-workflows when-green` lets `merge_when_green.py` merge a change to `.github/workflows/` once every check passed, unless an added line reaches secrets, write permissions or the triggers that run with them. Deploy and secret files still wait for the owner.
- Base rules from the owner's agent reports of 2026-11-21: text is read and written as UTF-8 with LF line endings (the Windows failures of three pull requests), every image, video and document is opened before publishing (card data in billing screenshots, a Wi-Fi password in a document and MAC addresses in a capture), and a file many parallel changes edit is generated at build time or split into one file per item (the conflicts on a search index and lists of items). `docs/003-autopilot-and-hooks.md` explains the three sources of permission prompts and what the owner can change.

### Changed

- `AGENTS.md`: a step that must wait for a merge is done after it, or given with "after merging" first. Removing what the task created, such as a scratch file, the agent's own worktree with `git worktree remove` or its merged branch with `git branch -d`, is green. The report of a long run, now step 7, gives the size of each change, what was reverted and how long verifying it took. The `item-worker` agent follows the same steps.
- A failure in a row doubles a model's cooldown up to `health.max_cooldown_s`, and an agent that ends without error and writes nothing gets the new `no_change` code, so a local model that timed out twice on texts is skipped instead of costing another 10 minutes.
- The night run plans only the evidence that is missing. Two fresh passes get one more run, and a combination that failed is not run again until its evidence lapses or its grader, OpenCode minor or GPU changes. `--runs N` still measures every combination. Bench rows of a coding agent record the size of the task packet in `input_chars`.
- A local Ollama model that failed the bench class of the task is refused, as a failed Colibri model already was.

### Fixed

- `orchestrate.py models` never showed a coding agent as authorized for `edit-small` or any other task type whose name is not a bench class: it compared the task type with the bench classes of the coverage. It now counts the classes that measure the task type.
- `delegate colibri --model colibri/<id>` ran OpenCode with that id even when Colibri served another one. It is now blocked with both ids.
- The commit gate blocked every commit while the check failed, also for a loose file the owner added meanwhile. It now blocks only for check errors about the files the commit holds.
- `git branch -d` asked the owner, because the rule for `git branch -D` ignored case. Only a forced deletion asks now.
- The pull request template held a bare "Closes #", which fails the check. It now says to link the issue or write None, and the check names the expected title and Task line.
- A re-run of the Pages workflow of the web profile failed on two artifacts with one name. Each attempt now names its own artifact.

## [1.22.2] - 2026-11-18

### Fixed

- A hook fed from Windows PowerShell stayed silent: PowerShell puts a BOM in front of what it pipes, so `json.load` failed and the hook read an empty input. The eight hooks that read stdin now decode it as `utf-8-sig`, which drops a BOM and reads the rest as UTF-8. Claude Code sends no BOM, so only a hook tested by hand was affected.

## [1.22.1] - 2026-11-18

### Fixed

- `orchestrate.py delegate opencode` without `--model` took the first free model in the owner's `local.yml` and only then asked the gate. After the owner renewed the checks on 2026-11-18, `mimo-v2.6-flash-free` came first. It may train on what it receives, so in a private folder the run would end blocked although `deepseek-v4.1-flash-free` was allowed, and in a public one it skipped the faster verified model `route` chose. Delegate now chooses with the same function as `route`, `pick_opencode_model()`, using the bench evidence of `edit-small`.

## [1.22.0] - 2026-11-18

### Added

- A generated `AGENTS.md` asks the agent to close a long run with one report: what works without a command, the version each client loads, real and simulated checks, the models used, links to the changes, and for each item left to the owner the exact action, its source, what is prepared and what happens once it is done. The owner's final acceptance test on 2026-11-18 found the summary missing half of it.

## [1.21.2] - 2026-11-18

### Fixed

- A session that another session started got no router context. The desktop app puts `<system-reminder>` blocks and a "Background" and "Task:" wrapper around the prompt, so "Continúa con todo lo autorizado" was `other` and started no supervisor pass. The prompt hook now routes only the owner's words. Found by the owner's final acceptance test on 2026-11-18.
- In the standard's own repository the startup hook said nothing, and the router called it a website because it has no `.standard.yml` and a small HTML gallery, so "Continúa" got the `web-experience` recipe and a phone proof. The standard's own source now counts as a software repository for both hooks, and a known profile beats the folder's signals when the request names nothing of a recipe.
- `orchestrate.py delegate opencode` without `--model` still took the first free model checked by the owner, so it sent every task to the retired `glm-5.3-flash-free` and failed in 3 seconds with "Unexpected server error", while `route` already chose `deepseek-v4.1-flash-free`. Delegation now skips a model that `opencode models` no longer lists, by the same rule as `route`.

## [1.21.1] - 2026-11-18

### Fixed

- The router sent every edit task to `opencode/glm-5.3-flash-free` after OpenCode retired it on 2026-11-18, so each delegation would fail with Model unavailable. A free OpenCode model that `opencode models` no longer lists is now refused with that reason, and `doctor` always records the list. `tests/test_scripts.py` fails before the fix and passes after.
- The bench classes `review-diff` and `decompose` cut every reply at 400 tokens, so a 5 unit work plan from `qwen3.5:4b` (637 tokens) was invalid JSON, and `gpt-oss` spent all 400 on thinking because it ignores `think: false`. Each class now has its own reply budget of 1500 tokens, and a model whose thinking only has levels gets its lowest one. Both graders move to version 2, so the 6 rows measured with the old budget stop counting.

### Changed

- `settings/models.yml`: the ten local candidates now carry license, size and context read on 2026-11-18 from `ollama show`, the Ollama registry and the tags pages. `qwen2.5-coder:3b` is under the Qwen Research License, for research and evaluation only. The OpenCode models page lists `glm-5.3-flash-free` as deprecated and a new free `hy4-flash-free`.
- The three new bench classes ran against real models on this machine. `refactor` and `edit-large` now route to `opencode/deepseek-v4.1-flash-free` instead of being blocked. Only `web-visual-review` stays blocked, until the owner's design pairs exist.
- `opencode run --file` is confirmed to send an image when the model declares image input. `docs/006-model-analyzer.md` says so and keeps the limit that the analyzer has no OpenCode vision run yet.

## [1.21.0] - 2026-11-18

### Added

- A request to send a message to another session, such as "Manda un mensaje a la otra sesión de OpenTutor", is its own `message` intent. The prompt hook gives the session the `peerbox.py send` command, its own peerbox name and the groups on this machine, and the session edits nothing. Before, the request was `other` and got no context, so Murmur's messaging never started from a normal request.
- The `merge-readiness` capability, provided by `scripts/readiness.py` after Interlock. An addition in `settings/recipes.yml` can name the `intents` it applies to.

### Fixed

- "¿Está listo el PR 42 para fusionar?" was a plain question, so the readiness check never ran. A question whether a pull request, change or branch is ready to merge is now a review with `merge-readiness`. Found by the owner's acceptance test of the seven tools on 2026-11-17.

## [1.20.1] - 2026-11-17

### Fixed

- On Windows `secret_scan.py` missed a credential written to a file with an accented name, such as `configuración.py`: the misread path pointed to no file, so nothing was scanned. It now reads its input as UTF-8 too. `tests/test_secret_scan.py` fails before the fix and passes after.

## [1.20.0] - 2026-11-17

### Added

- "Continúa", "sigue" or "retoma" now starts one supervisor pass in the background from the prompt hook, so a started plan resumes at once instead of at the next 5 minute run of the Task Scheduler. The pass only resumes plans already started with pending work, no live process and no owner pause. A new request still goes through the session, so the owner sees the plan before any edit. The owner chose this on 2026-11-17. `STANDARDS_NO_SUPERVISOR=1` turns it off. `router.resumes` recognizes the words and leaves a question such as "¿Sigue abierto el PR?" alone.

### Fixed

- On Windows every hook read its input as cp1252, while Claude Code sends UTF-8. "Continúa" reached the router as "ContinÃºa", so a request with an accented verb got no decision at all, and a path with ñ was misread. The hooks now read their input as UTF-8. `secret_scan.py` gets the same change in its own pull request, because the owner reviews that file. The guard was not opened by this: undefined bytes were replaced, so its checks on commands still ran. `test_router` sends the hook UTF-8 bytes as Claude Code does.

## [1.19.0] - 2026-11-17

### Added

- Three ideas of jcode (MIT), the coding agent harness the owner sent on 2026-11-16, as own code. `hooks/shift_notice.py` tells a Claude Code session when another session on this machine changed a file it read, in the same working tree or in another worktree of the repository, where both changes will meet at integration. `hooks/cache_notice.py` reads the cache use the provider reports in the local transcript, names the likely reason of a prompt cache miss (idle past the cache lifetime, a new UTC day, a model change, a compaction) and warns before a prompt that starts on a cold cache. `scripts/agentgrep.py` shows each match under its enclosing class and function and collapses what was already shown, for delegates with small context windows. jcode itself is in the radar at assess: its usage telemetry is on by default.

- Four tools the owner sent on 2026-11-16, in the radar at assess with what was read from their source. explainroo makes narrated explainer and product demo videos with a voice made on this machine: the `narrated-video` capability, and a provider of `short-video` in a project that has its `scenes.js`. PlanExe2 plans a real project and lists the decisions left to the owner: the `project-plan` capability, which sends the plan to Claude and is never offered in local-only mode. Promptline pastes saved prompts with a hotkey on Windows. copy-buttons adds copy buttons to Claude Code's fullscreen mode.
- `scripts/arithmetic_check.py` re-computes the calculations a document writes out and lists the wrong ones, with PlanExe2's checker copied under its MIT license. It is the `calculation-check` capability of the `docs-academic` recipe and a step of the docs-review skill.
- `media.py video-check` also measures loudness against a target (`--loudness-target`, -14 LUFS by default), true peak, near silences of 2.5 s or more and black frames, with the thresholds of explainroo's `verify`. A peak above 0 dBTP is a problem, the rest are warnings.
- `scripts/promptline_pack.py` writes a Promptline pack with the requests the router understands, such as "muéstrame el estado", "Pausa" and "revisa el PR {pr}", and checks the pack against Promptline's format before writing it.
- Animated films by scenes, after Cinecode (MIT): the `animated-film` capability, added when a request says película, cortometraje, storyboard or animated film. Cinecode's test film made a 61 s captioned animatic here without voices. Voices need a voice provider the owner authorized, and the router says what would leave the machine. `media.py video-check` reads a finished video from the file itself: streams, length, silent sound, soft subtitle tracks and frames saved to look at. It found that the animatic has no soft subtitle track although Cinecode's log says it muxed one: its captions are drawn into the picture.
- The radar lists Interlock, Festival, Murmur, ProjectArchitect, Ponytail and Cinecode with what was verified, and i-have-adhd with its MIT license.
- `scripts/recall.py`, after the idea of ProjectArchitect, whose license forbids redistributing it, so nothing of it is copied: a work, review or publish request gets at most two decision records and two memory entries that share words with it, each with its status and where it came from. A finished or paused plan stores a handoff in the local memory: what passed, what stopped and why. A new session starts from that, not from the whole history. "Guarda" is now a work verb.
- The direct answer style, after i-have-adhd (MIT), in `hooks/style.py`: the result or next action first, numbered steps, one next action, visible progress, at most 5 items in a list, no preamble or closing offers. The SessionStart hooks add it at startup and after a compaction. "Explícame" or "en detalle" gets a full answer that turn. "Modo normal" turns it off for the session and the choice survives a compaction. `style: off` in `~/.standards/local.yml` turns it off everywhere. It never reshapes JSON or other output a tool reads.
- `scripts/peerbox.py`, after Murmur (MIT): messages between sessions on one machine, with named peers, groups, threads, replies and a state per recipient (queued, delivered, acknowledged). It keeps everything in one SQLite file, so it works on Windows, where Murmur cannot run: Murmur reads the process table with `ps` and listens on a Unix socket. The prompt hook registers each Claude Code session, adds it to the group of its folder and hands it its waiting messages as data from another session. OpenCode and scripts use the command line. An acknowledgement proves delivery, never that a change was made. `STANDARDS_NO_PEERBOX=1` turns it off.
- `scripts/reuse.py`, after Ponytail (MIT): `similar` ranks the existing functions and classes that share words with a task, `map` prints one line per definition, and `debt` collects `shortcut:` comments with their `revisit when` condition. The packet an executor receives now lists the code to reuse first, so OpenCode sees `slugify` before writing a second one.
- `scripts/readiness.py`, after Interlock (MIT): links a spec's requirements, its linked decisions, its open tasks and the tests that name each requirement into READY, NEEDS_DECISION or BLOCKED. The worst signal wins, and a critical requirement no test names blocks the change even with green CI. A plan with a `spec` puts the verdict in its pull request. The specs template now gives requirements an id and a `critical` mark.
- A second session with the same request joins a plan that is already running instead of starting a second executor.
- `scripts/supervisor.py`: one supervisor per user, held by a lock file. It resumes every started plan that has pending work, no live process and no owner pause. `install` registers it in the Windows Task Scheduler every 5 minutes. The SessionStart hook starts one pass in the background, so opening a repository recovers a plan whose process died. `STANDARDS_NO_SUPERVISOR=1` turns that off. A plan resumed 3 times without any change to its state is left for the owner, so a plan that always fails at start cannot loop. `detach` now writes a pid file.
- `scripts/blockers.py` saves one record per stopped action with six facts: exact action, evidence with source and text, kind of obstacle, existing approval, work done and unblock condition. A vague record, or an agent precaution without the effect it hides, is refused. `why` answers "why can't you do it?" from the records. `execute.py` writes a record for every blocked unit, with the attempts made and the units waiting on it, and closes it when the unit passes after a resume. "¿Por qué no puedes hacerlo?" now reaches these records through the router's `control` intent.
- The router has a `control` intent. "Pausa", "cancela el plan", "reanuda" and "muéstrame el estado" are recognized and told to use `execute.py` instead of starting edits. "Continúa", "sigue" and "retoma" start work.

### Changed

- The radar entry of Festival says what Obey's documentation shows and why the supervisor stays: Obey ships as a binary without a stated license, uses the same Task Scheduler on Windows and opens network listeners by default.
- The standard check flags a decision record with `Status: proposed` that names who accepted it, and an `accepted` one that does not. The decision template used to carry `Accepted by: owner` on a proposed record, so an AI tool could leave that false claim behind. It now says `pending`. OpenTutor decision 0001 had this mistake.
- A work order goes to the coordinator by default, so the owner no longer types `consent --route coordinator`. `consent --route session` still keeps the session as the owner of the work.
- `blockers.py` and `supervisor.py` are part of the scripts the skills plugin ships.

### Fixed

- A git worktree outside the owner's folders, such as one in a temporary folder, fell back to the default class `personal-private`, so free remote models were refused for a `personal-public` repository. The owner's session saw OpenCode blocked this way on 2026-11-16. A linked worktree now takes the privacy entry of the repository it belongs to, wherever it sits, and a worktree of a restricted repository stays restricted inside a public folder.
- "Revisa el PR 12" in a web repository picked the learning-site recipe, because the folder's web signals outweighed a review recipe with no words. A recipe can now name the object it reviews in `wins_on`, and naming it beats any signal of the folder.
- `delegate opencode` without `--model` took the first free model the owner checked even while it was cooling down after a failure. It now skips models in cooldown, as `route` does. The `delegate-runner` agent and the repo-improve skill now pass the model the router chose, and the agent reports the model asked for and the model the run record shows.
- `execute.py` counted an attempt for a unit that never reached a model, so one unit without an executor could use the whole `max_total_attempts` and starve independent units.
- Attempt and remote-session budgets, and elapsed wall time, are saved in the plan state and survive a resume.
- After a timeout that left the code intact, the executor asks the router again with the updated health and takes a model it has not tried. A timeout that changed files keeps the worktree, marks the unit `partial` and blocks reassignment until it is inspected. The execution report shows `attempt_log` and `partial` per unit. Every attempt is logged with executor, model, duration, worktree, branch, commit, changed files and test result.

## [1.18.1] - 2026-11-16

### Fixed

- A script stopped half way through its report on Windows when its output went to a pipe, which is how Claude Code and a PowerShell pipeline read it. The pipe wrote in the ANSI code page, cp1252, which has no check mark, arrow or emoji, so text quoted from OpenCode, a question bank or a run record raised UnicodeEncodeError. The owner's session saw it with `orchestrate.py`. Every script now starts with `console.safe_output()`: a pipe gets UTF-8 and a console replaces what it cannot draw. `tests/test_console.py` shows `orchestrate.py runs` failing before and passing after.

## [1.18.0] - 2026-11-16

### Added

- `desktop_ux.py --save RUN.json` and `--compare RUN.json`. A second review says what was fixed, what is still there and what is new, matched by rule, control and window state rather than by tkinter's widget paths. With `--strict` only a new error fails. The owner asked how a second review would find the UX errors again.
- `desktop_ux.py tk` measures a dialog, quiz or notice: the factory may return a Toplevel or an object holding one as `.window`. Two rules more: an action below the visible part of a scrolled window, and a paragraph in bold.
- The desktop-improve skill saves the first run and compares the run after the fix.

### Fixed

- `desktop_ux.py tk` reported a clean window when the window was never on screen. It is now an error, and a hidden window measures nothing. Found on the OpenTutor quiz window, whose first measurement read no control.

## [1.17.0] - 2026-11-16

### Added

- Desktop UX (`docs/013-desktop-ux.md`). The owner found that no tool or agent improved the UX of the desktop apps OpenTutor (Python, tkinter) and FocoLocal (Go, Win32): every UX tool of the standard read web pages. `scripts/desktop_ux.py tk MODULE:FACTORY` builds a tkinter interface, opens every tab at every size, saves screenshots, and checks contrast, text size, target size and spacing, text cut by its widget, content hidden by a small window, and clicks without a key. `uia --title` reads the UI Automation tree of a running window of any technology with pywinauto and checks names, keyboard focus, target size and controls outside the window. `shot --title` saves a window. `protocol` and `evidence` prepare and read a usability test with five people, with task success, time and the System Usability Scale. Each rule names its source in WCAG 2.2 or the Windows UX guidelines.
- On a clone of OpenTutor in a Linux virtual display it found a minimum window height of 640 px where the content needs 663, which hides the last setting without a scrollbar, and five checkboxes 21 px tall and too close together. Nothing was run on Windows yet.
- The `desktop-tester` agent (Sonnet) runs those measures, judges the screenshots against the ten usability heuristics and reports which findings were measured and which were judged. The router names it for the `windows-app` and `learning-app` recipes and for a desktop or tkinter folder.
- The capabilities `desktop-ux` (desktop_ux.py, Axe.Windows, Windows-MCP) and `usability-test` in `settings/recipes.yml`, on the `windows-app` and `learning-app` recipes. `learning-app` drops the web `ux-review`. Axe.Windows and Windows-MCP are radar entries with status assess, and Windows-MCP 0.8.8 is in the MCP catalog with its warning that it has full access to the desktop.
- The `desktop-improve` skill: do the task the way a person does in the running executable, fix the code, do the same task again, and show the screenshots before and after. It works on a test profile and checks that a window the system opens does not take the keyboard from the app the person is typing in, as the Windows window management guidelines ask. The owner proposed this loop and FlaUI-MCP on 2026-11-16.
- FlaUI-MCP is the first MCP server of `desktop-ux`, with no shell, file or registry tool. Windows-MCP is on hold, because it has full access to the system and needs Python 3.14. Accessibility Insights for Windows is in the radar. The windows-app recipe also answers to notice, tray, dialog, popup and keyboard words.
- The MCP catalog holds remote servers reached by URL. `mcp config` prints an `http` block for Claude Code and a `remote` block for OpenCode, and `verify.py` asks such a server for an https URL. The Microsoft Learn MCP server moves to trial, after it returned the Windows guidelines behind these rules.
- The fingerprint has a `tkinter` signal, and its cache key names the detector version, so a fingerprint saved by an older detector is not reused.

## [1.16.1] - 2026-11-16

### Fixed

- The guard hook asked the owner to delete `delegate/<run id>`, the scratch branch a delegation makes, when Claude cleaned up after a run on OpenTutor. It no longer asks for a `delegate/` branch whose run record is in `~/.standards/runs`. Any other `git branch -D` still asks.
- The guard hook asked before `rm -rf` of a folder inside Claude's own scratchpad. A recursive deletion no longer asks when every target is inside a temporary folder: the system temp folder, `/tmp` or a delegation's worktree. Variables set earlier in the same command are resolved. A target outside those folders, an unresolved variable, a glob or a `..` still asks.
- `orchestrate.py runs <id> --clean` removes the worktree and branch of a finished run. It refuses while the run is going and while a verified commit is not in the current branch, unless `--force`. The run record keeps the commit.
- `orchestrate.py runs` prints why each run ended, so a failed delegation shows its reason without opening the record.

## [1.16.0] - 2026-11-16

### Added

- Four Claude Code agents, each for a function the standard had a script for and no agent: `delegate-runner` (Haiku) hands a green part to OpenCode or Ollama through the router and reports the verified run, `ci-fixer` (Sonnet) fixes a failed check and calls `merge_when_green.py` again, `content-auditor` (Sonnet) runs `learning_check.py`, `text_check.py` and `media.py audit` and ranks what they find, and `web-tester` (Sonnet) checks a page in a real browser at 360 and 1280 px. The owner asked for more agents after a session did everything with one model.
- The router context names `delegate-runner` and `ci-fixer` in every work order the session keeps, `content-auditor` for a learning or documentation recipe and `web-tester` for a web recipe or folder. The repo-improve and web-improve skills name them too.
- The router context names the folder of the standard's scripts once and the scripts by name, because the plugin's path on Windows is long. Its limit is 2400 characters, up from 1800, which a web work order with merges allowed passed on Windows, so the line that closes the task was cut. When the context is too long, notes go first and that line always stays.
- `agents/README.md` lists every agent with its model. The selftest fails when an agent is missing from it, names itself differently from its file, or uses a model, tool or field Claude Code does not know, because Claude Code ignores those without a word.

## [1.15.0] - 2026-11-16

### Added

- The router context of a work order the Claude session keeps now names the agents and executors: independent parts go to `item-worker` agents at once, each with isolation worktree, up to 3, lookups go to `repo-scout`, and `orchestrate.py route --all` says which parts OpenCode or Ollama take. In a session on OpenTutor the owner found that Claude did every task itself, one after another, with one model, and never asked the router, because only the repo-improve skill mentioned the agents and the executors.
- `item-worker` says to use it proactively and to start several at once for parts that touch different files. Run in its own worktree, it opens its own pull request. The repo-improve skill runs independent items at once, up to `concurrency.max_parallel`.
- `orchestrate.py consent --route coordinator` hands every work order typed in Claude Code to `plan_autopilot.py`, which plans by score with Haiku, Sonnet or Opus and runs the units in parallel with OpenCode, Ollama or Colibri. Before, the owner had to edit `~/.standards/local.yml` by hand.

## [1.14.0] - 2026-11-16

### Added

- Merges without the owner, when the owner allows them. `python scripts/orchestrate.py consent --merge when-green` writes `autopilot: {merge: when-green}` to `~/.standards/local.yml`. `scripts/merge_when_green.py <PR>` then merges a pull request only when it is open, has no conflict, changes no workflow, deploy or secret file, and every check on its head passed. It names that head with `--match-head-commit` and never uses `--admin`. With `--wait` it follows running checks. Before, Autopilot always stopped for the owner: the guard hook asked on every `gh pr merge`, the skills said never merge, and `--publish auto-merge` asked for classic branch protection with strict checks, which the owner's repositories do not have because they use a ruleset.
- With that setting the guard hook answers a direct `gh pr merge` with the path of `merge_when_green.py`, so the agent merges through the checks and the owner is not asked. A merge with `--admin` still asks. Without the setting every merge still asks. The router tells the agent the same in its context.
- `plan_autopilot.py --publish pr` merges once its checks pass when the owner allowed merges, and `--publish auto-merge` with checks followed does the same through `merge_when_green.py`. GitHub's own auto-merge now also accepts a ruleset with required checks.
- `SETUP.md`, `agents/item-worker.md` and the repo-improve skill say when an agent may merge. Deploys, secrets and history rewrites still wait for the owner.

## [1.13.0] - 2026-11-16

### Added

- Router fixes found on OpenTutor, a Windows tutor. A learning request outside a web page now gets the `learning-app` recipe, where it got the windows-app recipe and a web experience. A Python package under `src/` gets `python -m pip install -e .` in its install step, because its tests cannot import it before that.
- Learning, visual assets and writing (`docs/012-learning-visuals-writing.md`). `scripts/learning_check.py` audits question banks of any shape for integrity errors and for the rules of the research on practice testing and item writing, each with its source, and reads the code to see whether the page shuffles the options. On three of the owner's banks it found a key in position B in 34% of 418 items where 20% is expected, keys that are the longest option in 37% and 39% of items, and 306 imported questions without an explanation.
- `scripts/text_check.py` measures readability (Szigriszt-Pazos with the INFLESZ scale for Spanish, Flesch for English), long sentences and paragraphs, acronyms, vague links and passive voice, and writes and reads a comprehension test with five readers, the only evidence that a page helps. `scripts/media.py` searches Openverse and Wikimedia Commons for images whose license allows the use, attaches one with its alt text and credit, and audits the media of a repository.
- `skills/web-improve/references/learning-science.md` and `writing-and-usability.md`. The web-improve and docs-review skills call the three scripts.
- The router has the recipes `learning-site`, `content-clarity`, `visual-asset`, `powershell-script`, `api-service`, `infra`, `hardware`, `mobile-app` and `ci-maintenance`, and 36 capabilities with 121 providers, among them HyperFrames, Manim, Mermaid, D2, Graphviz, draw.io, Excalidraw, Remotion, Motion Canvas and every family of the owner's guide. Twelve radar entries are new. The decision says what to install before the tests: with it, extractor_exambase passed 110 of 110 tests where it had passed 97 of 98.
- `orchestrate.py mcp config --client opencode --opencode-format v2` prints the native OpenCode 2 shape (`mcp.servers`). The default shape stays the one OpenCode 1 and 2 both read, as the OpenCode migration guide says.
- Request router (`docs/011-request-router.md`), from the owner's guide of 2026-11-15. `scripts/repo_fingerprint.py` reads what a folder is from `.standard.yml`, its manifests and its file names, with the file behind every signal and a cache per commit. `settings/recipes.yml` maps signals and words to capabilities and lists the providers of each capability in order. `scripts/router.py` classifies a request (work, query, review, setup, publish), picks the folder, the recipe and the first provider this client and machine have, and records the permission, what leaves the machine and the verification. A question opens no task, an order opens one and a follow-up updates it. A third party server is never offered in `local-only` mode or for a `work` or `restricted` folder. Several possible folders are one question, never a guess. On four of the owner's repositories each decision took about 0.22 s, and the first run there found three detection defects, now fixed with tests: a page under a root manifest counted as a second project, `unittest` tests had no command, and a workspace package lost the test command of its root.
- `hooks/route_prompt.py` is the Claude Code `UserPromptSubmit` hook: it adds that decision to a work request as context, stays silent on a question and never blocks a prompt. `/route` does the same in OpenCode. `routing.owner` (default `session`) lets the owner hand work orders to the coordinator from `~/.standards/local.yml`. A plan stores the router's decision as `route`.
- Fixed the packaged plugin: `verify.py` and `adversarial.py` failed at start with `No module named 'execute'`, because the package shipped them without the executor loop. It now ships the loop, the planner and the router, and the selftest starts every packaged script and sends a request through the packaged hook.
- Fixed a race between units that end at the same moment. `write_json` used one temp file name for every writer, so a second writer of the same file raised `FileNotFoundError` (439 of 800 writes from four threads), and `record_health` read, changed and wrote the health file without a lock, so one of two cooldowns could be lost. Each writer now has its own temp file and the health file changes under a lock. `verify.py` prints the full evidence of every check that did not pass, because a CI run on `main` failed `S.unit-tests` once and its log showed only the first 110 characters. That failure did not repeat in 16 local runs of the suite on Python 3.12 and 3.13, so its cause is still unknown.
- `tests/web/control.test.mjs` drives the Autopilot view of Standards AI Control in a real browser against a real server and seeded state (12 checks, `S.control-page` in `verify.py`). Its first run found three defects, now fixed: the page looked for `plan_autopilot.py` inside the repository a plan changes, so it only worked on this repository. An opened log stopped the view from following the state. The plan table made the page scroll sideways at 360 px. A plan started from the page now runs in the repository it was made for.
- Planner score: a folder counts only when the request names one of its files by path, by a file name one tracked file has, or names the folder. Before, any word of the request that appeared in a path counted, so a large repository pushed small requests to Sonnet. Design words inside a file path no longer count. Found with a real Sonnet call, which drafted a valid four unit plan in 14.05 s. The planner prompt now lists the protected paths, and the input tokens of a planning call include the cached part of the prompt.
- Multi-agent Autopilot (`docs/010-multiagent-autopilot.md`). `scripts/scheduler.py` replaces the batches of the executor loop with a ready queue: a unit starts when its own dependencies passed and its pool has a slot. `concurrency` in `settings/orchestration.yml` sets 3 units at once, 2 free remote slots, 1 local model and 1 test suite. A pool loses a slot after a rate limit and gets it back after three passes. `scripts/resources.py` keeps a local model waiting while the graphics card is full, and a unit moves to a free remote model only when the route already allowed it.
- `scripts/planner.py` picks the planner from a score a program computes: Haiku, Sonnet or Opus through one `claude -p` call, or the local Ollama planner when cost or privacy keep Claude out. Opus needs an advanced score or a written reason, never repairs a structure and runs one call at a time. `ANTHROPIC_API_KEY` is removed from the call.
- `scripts/plan_contract.py` is the one contract for the prompt, parser, normalizer, validator and repair guard of a plan draft. It reports every problem at once, fixes what cannot widen anything (an invalid `risk` becomes `red`), sends the rest to a model in one message and refuses a repair that changed an unnamed field or added a path. `depends_on` from the draft is honored, so independent units can run together.
- `execute.py` records model, channel, seconds and failure code per unit and total time, peak concurrency, waiting, integration time, conflicts and retries per plan. New commands `pause`, `unpause` and `cancel`. A unit reviewed before a restart is integrated without a new run. `clean` never removes by force and keeps any worktree with pending work. A unit whose diff adds a credential fails before review.
- `plan_autopilot.py` follows the checks of its pull request, runs one fixing unit inside the plan's files when they fail and leaves the pull request open and unmerged when they keep failing. New `run` command, `--parallel`, `--detach`, `--planner` and `--opus-reason`. The same request on the same commit reuses the saved plan.
- Standards AI Control has an Autopilot view: agents, model and provider per unit, dependencies, metrics, pull request and controls to plan, start, pause and cancel.
- Fixed: `delegate_opencode` committed every file in the worktree, so two units that ran at once collided on the `__pycache__` files their tests created. It now commits only the files the agent changed. Found by the first parallel run of a real plan.
- `scripts/bench_parallel.py` measures the loop with simulated agents. On a 4 CPU container, six 2 s units took 15.37 s one at a time, 8.05 s with two and 5.86 s with three, with no failure or conflict. Ninety-one new tests and four adversarial scenarios cover the scheduler, the contract, the planner, the checks and the dashboard.
- `limits.max_p90_s` is a ceiling on the p90 seconds to an accepted result per route task type (default `{}`, no limit). A model over it does not count as proven for that task and the route says so. `limits.refresh_before_days` (default 7) puts the evidence that lapses within that many days first in the night analyzer plan, so it is measured again before it expires. Redone on `fresh_rows` and `model_states` after an earlier run was written on an old base.
- `docs/delivery-report-2026-11-12.md`: the consolidated delivery report with versions, measurements, the pilot, the acceptance criteria with their real state, the defects found and the blocked items.
- Fixed the CI `verify` failures: the policy check did not know `colibri` as an executor and two imports were unused. They failed since the Colibri commit. Run `python scripts/verify.py --level standard` before every push, not only the selftest.
- `execute.py` records the commit the integration worktree was built on and refuses to continue when the repository moved, with the command to clean and restart. A real pilot run reused a worktree built on an old base after the fixture changed, and a second `run` silently reused the commits of the first.
- `orchestrate.py models` also lists a model the bench proved but the coverage does not know, such as a local Ollama model run through OpenCode, so `ollama/qwen3.5-9b-ctx16k` with 3 of 3 `fix-bug` runs is no longer missing.
- `colibri.py register` also adds Colibri's own MCP server to the OpenCode config and denies its `install`, `start` and `stop` tools, which could download a model of tens of gigabytes or stop a server in use. The tool names and the deny rules were checked with `opencode debug agent`.
- A blocked route now names why each candidate was refused, such as a cooldown after a timeout, instead of only saying that no executor is allowed. A real pilot run showed the old text hid a 15 minute cooldown.
- Second web change. A site performance budget in the web profile (critical path under 170 KB compressed, interactive in under 5 s on slow 3G, from web.dev). The Okabe-Ito chart palette with its colors, contrast ratios and a grayscale check, as a rule of the `interactive-data` option. Interaction patterns 7 (form) and 8 (link preview), each with two sources that were opened. The two new patterns have no gallery demo yet.
- Gateway adapter. A provider with a `gateway:` block in `settings/providers.yml` is sent nothing without an allowed list of provider/model pairs, always with fusion, caching and billing off, and a reply is refused when the answering provider is missing or outside the list, or the reply was fused or cached. The answering provider is recorded as `effective_provider`. `orchestrate.py` counts a gateway address as remote even for the ollama and colibri executors on loopback. Seventeen tests in `tests/test_gateway.py` run against a fake gateway. FreeLLMAPI stays at assess and the real service is unproven.
- Executor loop enforces `max_total_attempts`, `max_wall_s`, `max_remote_sessions`, `max_split_depth` and `max_units_after_split`. A unit stopped by a budget is blocked and independent units go on. `docs/007` lists what each budget does and says `final_regression` is not run yet. Each budget has a test that fails without it.
- Executor loop splits a unit that is larger than its `max_input_chars` with `split_unit`, runs the parts in order and passes the parent only when every part passed. A Colibri unit is blocked, never split. Tests cover the split, a failed part, a single file unit and Colibri.
- Radar entry for Impeccable at assess. The official repository is pbakaus/impeccable, the license file and the npm package are Apache-2.0, and its detector has 62 deterministic rules that need no model or key.
- Routing fix. A model with `bench_fail_runs` fresh failed runs in the class of a task is refused, where before it counted as not measured and `local-only` sent `edit-small` to Colibri (0 of 2 passed). A local Ollama model that passed the bench is now a candidate of the OpenCode executor, so `local-only` picks `ollama/qwen3.5-9b-ctx16k` (3 of 3, p50 334 s).
- Docs and agent texts. `docs/007` now describes the executor loop as built, `docs/005`, `docs/006` and the `repo-improve` skill no longer keep Claude as a worker, and the new `/run-plan` OpenCode command checks and runs a work plan.
- Bench class `decompose`: three task specs where a model returns work units. `workplan.validate` rejects a bad schema, an unknown type or a cycle, then the grader checks the unit count, that every file to change is covered and that units able to run together share no file. A program grades it, grader version 1.
- Bench class `review-diff`: six synthetic diffs of new files, each with one seeded defect. A diff passes when a finding names the file and overlaps the defect lines (a finding over ten lines or more does not count) and no high finding sits elsewhere. A program grades it, grader version 1.
- Bench class `refactor-module`: an 8 file fixture where `slugify` is copied into three modules and must move to `app/text.py`. Hidden tests check the behavior and, with `ast`, that the function is defined once and imported by each module. It is the proof class of the `refactor` task type, grader version 1.
- Seven executor-loop scenarios in the adversarial suite (`X.` ids): planner types, Claude as a unit executor, overlapping units, attempt budgets, invented review lines, the privacy class of worktrees and a stopped Colibri with no fallback. `tests/test_adversarial.py` breaks each one on purpose and expects it to fail.
- Execution report: `python scripts/execute.py report PLAN.json` prints one consolidated report per plan, built only from the saved state (status, commit, tests, review findings, retries, executor and model per unit). A value the state does not hold is null. The shape is `schemas/execution-report.schema.json`.
- `orchestrate.py models` prints, per task type, whether a model is discovered, tested and authorized, with the date its bench evidence expires. Evidence comes from `fresh_rows`, discovery from the analyze coverage.
- Executor loop: `scripts/execute.py` has check, run, status, resume and clean. Each unit runs in its own worktree, batches come from `workplan`, and a unit passes only when its tests pass and cross-model review has no high finding. State is written after every unit so `resume` skips finished ones. A blocked unit never stops independent units, and a Colibri unit is never replaced by another model.
- Health and failover. A timeout, rate limit, auth or unavailable failure of an OpenCode or Colibri run is written to `~/.standards/health.json` with a cooldown from `health.cooldown_s` in `settings/orchestration.yml`. `route()` skips a model that rests and lists later candidates in `fallbacks`. A Colibri task gets no fallback and never moves to another model.
- Health is recorded for Ollama and API delegates too: a network, timeout, rate limit or auth failure starts a cooldown and a reply clears it.
- Cross-model review: `scripts/review.py` has a different model than the author return a JSON verdict on a diff. Findings that cite files or lines outside the diff are dropped, and one fix round runs when a high finding remains. The same model as the author is blocked before any call.
- `split_unit` in `scripts/workplan.py` splits a unit by files, then by acceptance criteria, then with a model proposal passed in as a callable. Every candidate is validated and must stay inside the parent's files.
- Measured Colibri on the RTX 2060 (6 GiB) with `qwen3-coder-30b`. Prefill runs at about 6 tokens per second (1009 tokens in 177 s, 3011 in 451 s), so the 12000 token OpenCode prompt needs about 30 minutes. `fix-bug` timed out at 600 s. Every model Colibri supports is a 27B or larger MoE, Repeating the same prompt, or changing only its last words, took the same 115 s, so Colibri does not reuse the prompt prefix. With the GPU free of Ollama models the prefill rose to about 8.6 tokens per second, still about 23 minutes for 12000 tokens. `coli tune` measures decode speed on short prompts and failed with "engine reported no decode speed" on a long one. Colibri stays installed and answers short prompts, and the router must not use it as a coding agent on this machine.
- Ollama context variants in `settings/ecosystem.yml`. OpenCode sends a prompt of about 12000 tokens and Ollama cut it to 2050, so no model saw the task. With a 16K variant `qwen3.5-9b` passed the `fix-bug` bench through OpenCode in 334 s. `qwen2.5-coder:7b` changed nothing. One run each is a first signal, not statistics.
- Standards AI Control: `scripts/control.py serve` opens a read-only dashboard on 127.0.0.1:8765 with providers, tasks, resources, measured tokens, history, settings and logs. `control.py statusline` prints a compact line for the Claude Code `statusLine` setting. A metric a provider does not report shows "Not available".
- Colibri as a local provider. `scripts/colibri.py` starts, checks, stops and registers it in OpenCode, and `orchestrate.py delegate colibri` runs a task with its model. A stopped Colibri blocks the run and no other model replaces it. `scripts/ecosystem.py` (entry `scripts/standards.ps1`) has the modes doctor, status, install, repair, update and verify, driven by `settings/ecosystem.yml`.
- Work plan contract: `schemas/work-plan.schema.json` and `scripts/workplan.py` with `validate`, dependency order, glob expansion, file conflicts and parallel batches. Units that share a file or both touch a lockfile never run together.
- Bench evidence expires. Runs older than `bench_recheck_days`, or measured with another OpenCode minor (opencode rows) or GPU (ollama rows), no longer count for routing. Runs without a date or identity keep counting.
- Cost modes `local-only`, `free-strict` and `existing-subscription` in `settings/orchestration.yml`. The owner's mode lives in `~/.standards/local.yml` (`orchestrate.py consent --cost-mode`). A run can ask for a stricter mode with `--mode` or `STANDARDS_COST_MODE`, never a looser one.
- `settings/models.yml`: model candidates with cost category, data use, stated capabilities, source, date and evidence level. An entry enables nothing.
- Data use per privacy class (`remote_data`). Public code may go to a free model that trains. Private code goes only to one that keeps nothing. A model with no recorded data policy is never used. `consent --free-model <id> --data-use none|stores|trains` records what the owner read.
- One gate for every model call (`orchestrate.gate`): cost mode, privacy class, the owner's free check, the catalog and the data use. Route, delegate, bench and the analyzer all pass through it.
- `orchestrate.py route --all` and `doctor` print who does each task type on the machine, with the exact model and the reason. `doctor` also names the catalog entries, owner checks and measurements that are due again.
- Bench classes `extract`, `summarize`, `web-subprofile`, `tool-call`, `vision`, `design-judge`, `fix-multi` and `docs-small` in `scripts/bench_tasks.py`, each graded by a program. The design judge uses the owner's pairs of screens, and a made-up sample that never counts when there are none.
- `scripts/analyze.py` with `prepare`, `plan`, `run` and `report`, and the wrappers `analyze-models.ps1` and `analyze-models.sh`. It tests the candidates that are installed and allowed, one local model at a time, with a session budget per remote model, stops a model or provider that reports its limit, continues after an interruption and writes the report outside the repository. It never downloads a model.
- Discovery instead of a fixed list. The analyzer takes every model the local Ollama lists, in the catalog or not, and classifies it from `/api/tags` and `/api/show`: chat or embedding, images, tools, local or cloud, and whether it fits the memory of the machine.
- `scripts/providers.py` and `settings/providers.yml`: one transport for providers with an OpenAI-compatible API, with settings for OpenRouter, Groq, Mistral, Google Gemini API and Cloudflare Workers AI. It lists models, checks the account, sends text, images and tools, and names every failure. Tested against a fake server only. No adapter was run against its real service.
- `api` as an executor: `bench --executors api:<provider>/<model>`, `delegate api --model <provider>/<model>`, and a route candidate for short tasks that a provider model may take only after it passed the bench class.
- `consent --free-provider <id>` records the owner's check that an account is on the free plan with no billing attached.
- Coverage in `analyze.py prepare`: every model found, by provider, model and endpoint, with one state and its reason. `--all` and `--json` print each one.
- `docs/how-it-works.md` in every repository, from a new template. The check warns when it is missing, names a path that does not exist or is still a draft. The missing file becomes an error in version 2.0.0. The standard has its own.
- Web sub-profiles as the `experience` option: `scroll-storytelling`, `interactive-data`, `reactive-object`, `editorial` and `characters`. `standard.py subprofile "<request>"` names the one a request calls for. `profiles/web/subprofiles.yml` holds a short summary of each for small models.
- web-improve: `references/subprofiles.md`, `interaction-patterns.md`, `motion-and-foundations.md` and `design-judgment.md`, a gallery of six patterns and a reactive object in `gallery/index.html`, and `scripts/measure_page.mjs`, which measures contrast, touch targets, line length, overflow and font families in a browser. `audit_site.py` lists design findings measured from the files.
- Web task types in the router: `web-direction`, `web-pattern`, `web-test`, `web-copy`, `web-classify`, `web-visual-review` and `fix-check`.
- `DESIGN.md` sections for tokens, first visit, states, audience evidence and commented examples.
- `/who-does-what` for OpenCode, where no startup hook runs.
- `memory.py export` and `memory.py expire`. Entries older than 90 days are marked old.
- `docs/006-model-analyzer.md`, with the cost modes and the night guide.
- Six policy scenarios in the adversarial suite, checks of the cost policy, the model catalog, the explanation and the gallery in `verify.py`, and tests of the analyzer with a fake Ollama and a fake agent.
- 20 radar entries at `assess` for tools named by the owner, with the check that decides each trial. Their license, cost and privacy say `not verified`.
- Radar entries for Manim Community and Mermaid CLI, both in trial, from their use in GCP_Data_Engineer_Fieldnotes.

### Changed

- Every bench run records the version of the rule that graded it. When a grader is corrected its version goes up, and the runs graded by the older rule stay in the history and stop counting for the router and the report. `tool-call` is at version 2.
- `analyze.py run` says so when no model was ready and nothing ran.

- `analyze.py plan` and `run` list what is not in the plan as one line per provider with a count per state. The reason and the fix for each model stay in `prepare`.

- `settings/models.yml` no longer decides which models exist. It holds settings and limits, and `blocked: <reason>` keeps a model out. Its `services` notes moved to `settings/providers.yml`.
- Cerebras and the NVIDIA API catalog are listed as trials with credits, so they are never called. GitHub Models is listed as retired since 2026-07-30.
- A task a model was not run on is reported as not evaluated with the reason, never as a failed run. A run that a provider cut short with a limit, a payment request or an outage is not kept.
- The report separates inference by API from runs of a full agent.

- Web fixed rules, by the owner's decision of 2026-11-10: tokens from `DESIGN.md`, native CSS before a library, font loading, a first screen a new visitor understands, empty and loading states that say what happened, and reduced motion honored in JavaScript too.
- Risk no longer names a brand. Yellow and red work needs the owner's review, and a model other than the planner needs measured passes in the bench class of the task. With the default cost mode Claude still goes first.
- `edit-large` and `refactor` accept OpenCode after it passes `fix-multi`. An edit over five files asks for the same proof.
- A local model split with the CPU is used when its own bench history passes for the task, instead of never.
- Among free models, one that keeps or trains on what it receives sorts after one that does not, whatever its name.
- `consent` no longer needs `--path` and `--class` to record a free model or the cost mode.
- Ollama is in the radar for the web profile, limited to classifying, short text and screenshot review by a proven vision model.

### Fixed

- The `summarize` grader failed a command that a model had wrapped in quotes, although the command was in the text word for word. Quotes and backticks around a command are ignored. `summarize` is at grader version 3. Found in a real run.

- A model that failed the bench class of a task was still proposed for it, through a broader class it had passed. The broader class now counts only for a model that was never run in the specific one. Found in the first full night.
- An agent run that passed the visible tests and failed the hidden ones reported the success note as its reason. It now says so.
- The `summarize` grader asked for several exact words per text and failed correct summaries. It now asks for one word group on the subject, and still fails any command that is not in the text.

- The `tool-call` grader failed a model that read more than one file before running the tests. It now checks that each required tool was called and in the right order, and allows repeats. Found in a real run.
- `bench` prints why a run was not accepted.

- A limit reached at the host behind a router stopped the whole provider for the night. It now stops only that model. A limit of the account still stops the provider. Found in the first real run against OpenRouter.
- A refusal because a model is only served by hosts that train on what they receive was reported as "not evaluated". It is reported as privacy.
- A model that also outputs audio or images was listed as a chat model. It is no longer a candidate.

- An unknown task type returned Claude before any cost or privacy check, also for a restricted folder. It now passes the same rules as every task.
- `bench` recorded its own model as checked by the owner. It now uses the owner's real checks.
- An Ollama cloud tag, a model served from a remote host and an Ollama URL on another machine counted as local. They count as remote.
- An Ollama reply from a model other than the one asked for now fails the run.

### Migration

- A free model that is not in `settings/models.yml` is no longer used until its data use is recorded with `consent --free-model <id> --data-use ...`. The three models used before (GLM, DeepSeek, MiMo) are in the catalog. MiMo may train on what it receives, so it is no longer used for private folders.
- Existing web repositories need no change. `experience` defaults to `standard`, which adds no rule. Run `agents` to pick up the new fixed rules.
- Run `init --existing` to add `docs/how-it-works.md`. Until then the check only warns.

### Fixed

- The link check retries each URL up to 5 times with a 10 second wait, uses at most 8 parallel requests and a 30 second timeout. Without this, runs failed on random `docs.cloud.google.com` pages with connection errors while every link was valid.

## [1.12.0] - 2026-11-09

### Added

- `scripts/verify.py`: independent verifier with PASS, FAIL, SKIP, ERROR and NOT_RUN, a JSON report validated by `schemas/verify-report.schema.json` and a Markdown report. `--level deep --live` checks everything in one run. `scripts/verify-all.ps1` and `.sh` run it.
- `scripts/adversarial.py`: adversarial suite in quick, standard and deep levels. Fake executors in real worktrees test prompt injection, edits to tests and protected files, edits outside scope, false success, timeouts, leaked credentials, a broken or absent Ollama, privacy classes, broken patches, lost data and workflow security.
- `scripts/orchestrate.py`: detects OpenCode, Ollama, GPU and shells, routes each task by type, risk, size, privacy class and measured history, delegates for real to OpenCode in its own worktree or to Ollama by API, verifies the result, records every run, benchmarks executors with hidden acceptance tests, records the owner's consent and merges the OpenCode config.
- `scripts/preserve.py`, `scripts/safe_patch.py` and `scripts/memory.py`: data snapshots and comparisons, extraction coverage and resume lists, patches proven to apply, and a local SQLite FTS5 memory that refuses secrets.
- Skills `adversarial-testing`, `safe-patch`, `data-preservation` and `agent-benchmark`. web-improve gains `references/learning-experience.md` and `references/regression-testing.md`.
- `settings/orchestration.yml` (routing and privacy policy) and `settings/mcp/catalog.yml` (MCP servers at exact versions, off by default).
- `hooks/session_probe.py`: lists the executors when a session starts in a repository that follows the standard.
- Unit tests in `tests/`, a `verify` job in CI with actionlint, zizmor and Ruff at pinned versions, and 18 radar entries.
- `docs/005-verification-and-orchestration.md`.

### Changed

- repo-improve routes and delegates each approved item with `orchestrate.py` instead of asking the owner to run `/next-item` by hand. The command still works.
- setup-opencode merges the standard's rules into the owner's `opencode.json` (the stricter rule wins, `share` stays disabled) instead of replacing it.
- The guard hook also asks before pulling or deleting local models, global installs, consent changes and force pushes with a `+` refspec. The OpenCode config asks for the same.
- The bundled copy of the standard in repo-setup carries the new scripts, schemas, settings and the hooks they use.

### Fixed

- Autopilot and the rules after compaction work in linked worktrees, where `.git` is a file. The switch lives at `git rev-parse --git-path standard-autopilot`.
- Workflows pin every third-party action to a commit and no longer leave the token in the checkout (16 zizmor findings).
- Files that running the tests creates (`__pycache__`, `*.pyc` and other caches listed under `generated` in `settings/orchestration.yml`) no longer count as edits outside the allowed files. Real executors run the tests themselves, so every live delegation failed on them.
- The router now uses the bench history: `fix-bug` results count for `edit-small`, `fix-test` and `docs-small`, and among the free models the owner checked it picks the one with the lowest p50 that has at least three runs and a pass rate of 0.8. Before, the history was looked up under the wrong task name and never changed the choice.
- On Windows the scripts start `opencode`, `npx` and other `.cmd` programs by their full path, MCP servers launched with npx or uvx go through `cmd /c`, and the PowerShell parse check finds Windows PowerShell even when its folder is missing from the PATH.

## [1.11.0] - 2026-11-08

### Added

- OpenCode as a second agent for small work on free models: `settings/opencode/` with a global config that asks before commits, pushes, merges, deploys and deletions and blocks edits to `AGENTS.md`, limits for small models, and the `/next-item` and `/fix-check` commands.
- `scripts/setup-opencode.ps1` and `.sh` install it for every repository and link the standard's skills into `~/.agents/skills`.
- OpenCode in the radar as trial.

- `settings/claude-managed-settings.json` makes `opusplan` the default model of Claude Code on the machine.

### Changed

- repo-improve hands approved plan items to OpenCode by default. Autopilot runs only when the owner asks, or in repositories with work or client code.

### Fixed

- A Material Design link in web-improve that returned 404 now points to the Android Developers page on window size classes.

## [1.10.0] - 2026-11-08

### Added

- Hooks as guardrails: ask before merges, deploys, force pushes, history rewrites, mass deletions, publishing and secrets. Block commits while the check fails. Stop on secrets written to files. Restore the rules of `AGENTS.md` after a compaction. Notify the owner with a sound.
- `item-worker` subagent: one plan item per clean context, so the autopilot session does not fill up.
- Plan review by `deep-reviewer` (build, build with cuts or refuse) before the owner approves.
- Closing a run reconciles assumptions, decisions and goals, and proposes preference changes from the owner's corrections.
- Radar of evaluated tools (`radar/`) and the `tool-radar` skill.
- `SETUP.md` for setting up the standard with any AI tool, and `docs/` in reading order.
- Concise output style for Claude Code in `settings/`.
- Expression level (sober, balanced, expressive) in `DESIGN.md`.
- Base rules: credit third-party assets and models, and write diagrams as Mermaid text.

### Changed

- The check validates the format of `docs/improvement-plan.md` and warns on items over 240 characters.
- The web stack reference uses CSS scroll-driven animations and Mermaid-compatible diagrams.

## [1.9.0] - 2026-11-07

### Added

- Autopilot for repo-improve: a Stop hook published with the plugin keeps the session working through `docs/improvement-plan.md` while `.git/standard-autopilot` exists. Items that need the owner are marked BLOCKED and collected for the final summary.

### Changed

- `docs/improvement-plan.md` is a Markdown task list with pending, done, skipped and blocked items.

## [1.8.2] - 2026-11-07

### Fixed

- The check runs again when the title or text of a pull request is edited, so fixing them no longer needs closing and reopening the pull request. Existing repositories update `.github/workflows/standard.yml` from the template.
- The link check skips localhost and loopback addresses, such as local development URLs in a README.

## [1.8.1] - 2026-11-07

### Fixed

- The skills open pull requests with a Conventional Commits title and the sections of the pull request template, the two things the check enforces.

## [1.8.0] - 2026-11-07

### Added

- `web-improve` reference `layout-and-space.md`: measurements and documented rules (Baymard, WCAG, Nielsen Norman Group, Material Design) to judge the use of space.

### Changed

- `repo-improve` starts by stating what it understood and getting the owner's confirmation, then interviews the owner for goals, design direction and README status before any diagnosis.
- `web-improve` interviews the owner for `DESIGN.md` before any visual change, and every layout finding cites a rule and a measurement.

## [1.7.1] - 2026-11-07

### Fixed

- Rebase merging is allowed, so a pull request from repo-improve keeps one commit per improvement on the default branch. Squash merging stays available for single-change pull requests.

## [1.7.0] - 2026-11-07

### Added

- Claude Code subagents published with the skills: `standard-runner` on Haiku for mechanical steps, `deep-reviewer` on Opus for deep reviews.

### Changed

- `repo-improve` lists every finding, gets one approval for the whole list, and applies all of it in order, tracking progress in `docs/improvement-plan.md`.
- `repo-improve` and `code-review` explain how to use `opusplan` and the subagents to choose the model by task.

## [1.6.1] - 2026-11-07

### Changed

- The skills deliver one patch for `git am` in chats and a ZIP only when the owner asks. `deliver_git.py` builds the ZIP only with `--zip`.
- The skills never paste whole files or logs in their replies, to save tokens.

## [1.6.0] - 2026-11-07

### Added

- `github` command and `settings/repository.yml`: the About panel (description, website, topics), features, merge settings, security features and labels, applied with the GitHub CLI.
- `github:` section in `.standard.yml`, with a default website for GitHub Pages sites and default topics per profile.
- Release workflow: a `v*` tag creates a GitHub release with the notes of that version from `CHANGELOG.md`, through the `notes` command.
- The check requires the About description once setup is done, and warns when GitHub differs from `.standard.yml`.
- The publish and release scripts fill the About panel of the standard's own repositories and create their releases.

### Changed

- The Task issue form applies the `task` label.

## [1.5.0] - 2026-11-07

### Added

- `repo-improve` skill: improves a repository as a whole, from diagnosis to one pull request per improvement.
- `release` scripts that run the whole release in one step and refuse to reuse a version tag that points elsewhere.
- Checks for committed executables and for top-level folders with thousands of files.
- `layout: monorepo` option in the software profile, with `apps/` and `packages/`.
- Move plan aliases for common Spanish folder names and for `e2e/`.

### Changed

- The web profile follows tool conventions when it builds with npm: `index.html` at the root and `public/` for static files.
- Root files such as `LICENSE-*`, `NOTICE`, `THIRD-PARTY*`, `ROADMAP.md` and `AUTHORS` are allowed, and `LICENSES/` (REUSE) is allowed in every profile.

## [1.4.0] - 2026-11-07

### Added

- `web-improve` skill for the web profile: audit and improve a site, interactive explanations, GitHub Pages, and verified delivery as a pull request or a ZIP plus a patch for git am.
- `docs-review` skill for the docs profile: purpose, consistency, evidence, citations, figures and build.
- Deep review mode in `code-review`: separate passes for correctness and security, and for maintainability.
- The skills repository lists recommended skills from other authors and where to install them.

### Changed

- The web and docs profiles list their new skills, so `AGENTS.md` names them.
- Publishing includes every skill folder in `skills/`.

## [1.3.0] - 2026-11-07

### Added

- The skills repository is a plugin marketplace (`.claude-plugin/`), so claude.ai and Claude Code can install the skills once and sync updates automatically.

### Changed

- The skills read the rules from SVN11X/standards at the version the repository pins, the same source the check uses. The bundled copy is only a fallback without network access.
- Generated files are always written with LF line endings, also on Windows.
- A new standard version alone no longer flags `AGENTS.md`. Only a change in its content does.

## [1.2.0] - 2026-11-07

### Added

- `migrate` command: writes a move plan for a messy repository, then applies it with `git mv` and lists the lines that need fixing.
- `settings/ruleset-main.json` and `protect-repo` scripts that require a pull request with a passing standard check.

### Changed

- Loose files at the repository root are errors, not warnings. Only standard files and tool manifests may stay there.
- Undeclared hidden folders are errors.
- Official actions moved to their Node 24 versions (`actions/checkout@v5`, `actions/setup-python@v6`, `actions/setup-node@v5`).

## [1.1.0] - 2026-11-07

### Added

- `skills-repo` command and `publish-skills` scripts that publish the skills to SVN11X/skills, with a release holding the ZIP files.
- `prompts/global-instructions.md` so every tool knows the standard outside a repository.
- Every repository lists the `code-review` skill, and `AGENTS.md` says where the standard's skills are published.

## [1.0.0] - 2026-11-07

### Added

- Six profiles: web, software, data-ai, hardware, docs and infra. Each has fixed rules, techniques that need a written reason, and setup questions.
- Generated `AGENTS.md` with a goal summary, the traffic light, source priority, language rules and anti-slop rules.
- Intent files for every repository: goals, glossary, assumptions, decisions and specs.
- Reusable check workflow covering structure, intent, slop, the pull request contract, secrets and links.
- Ten pattern cards and an index.
- Skills `repo-setup` and `code-review`, and prompts for tools without skills.
- Template publishers for bash (`publish-templates.sh`) and Windows PowerShell (`publish-templates.ps1`).
- `.gitattributes` that keeps line endings as LF on every system.
