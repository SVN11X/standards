# Changelog

All notable changes to this standard are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/2.0.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
