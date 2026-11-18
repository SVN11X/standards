# 011. Request router

A request in plain words gets a decision before any work starts: which repository and folder it is about, what kind of request it is, which recipe fits and which tool on this machine provides each capability. A program decides. No model is asked.

It answers the gap `docs/010-multiagent-autopilot.md` left open: the orchestrator could run a plan, and nothing connected the sentence the owner types to the repository, the goal and the tools.

## Parts

| File | What it does |
| --- | --- |
| `scripts/repo_fingerprint.py` | Reads `.standard.yml`, the manifests and the file names of a folder. Every signal names the file that shows it. |
| `settings/recipes.yml` | Recipes (signals and words to capabilities) and, per capability, its providers in order of preference. |
| `scripts/router.py` | Classifies the request, picks the folder, the recipe and the providers, opens or updates one task, prints the decision. |
| `schemas/route-decision.schema.json` | The shape of a decision. |
| `hooks/route_prompt.py` | The Claude Code `UserPromptSubmit` hook. It adds the decision to a work request as context. "Continúa", "sigue" or "retoma" also starts one supervisor pass in the background, which resumes only plans already started. |
| `settings/opencode/commands/route.md` | The `/route` command for OpenCode, which has no such hook. |

## What a request is

`router.classify` reads the first sentence.

| Kind | Recognized by | Example | What happens |
| --- | --- | --- | --- |
| work | A change verb in the first words, also after "please" or "can you" | "Corrige esta página", "Can you add a dark mode?" | One task opens |
| query | A question word first, or "explain", "describe" | "¿Qué cambiarías?", "Explícame por qué se duplica" | No task and no context: the answer is an explanation |
| review | "revisa", "review", "audit" with no change verb, or a question whether a PR, change or branch is ready to merge | "Revisa este PR", "¿Está listo el PR 42 para fusionar?" | One task opens, read only. A readiness question adds `merge-readiness`, which runs `readiness.py` |
| control | "pausa", "cancela", "reanuda", the status of the work, or why it stopped | "Pausa el plan", "¿Por qué no puedes hacerlo?" | The plan control files only, through `execute.py` and `blockers.py` |
| message | "manda", "dile", "avisa", "send" with a session, an agent or OpenCode | "Manda un mensaje a la otra sesión de OpenTutor" | No edit. The context gives the `peerbox.py send` command, the session's peerbox name and the groups on this machine |
| setup | "incorpora", "adopta", "set up" with "repository" | "Incorpora este repositorio al estándar" | One task opens |
| publish | "sube", "publica", "push", "deploy" with no change verb | "Sube los cambios" | The owner's configured permission decides |
| other | Nothing above | "gracias", "The build fails on CI" | Nothing, or a follow-up of the open task |

A Spanish verb counts only in a verb form, so the noun "cambios" is not an order. An English verb counts only as the first word, because "build" and "release" are nouns everywhere else. A statement such as "The build fails on CI" is not routed. Start it with a verb to make it an order.

## Which folder

In this order: the folder the session is in, the folder the request names, the only project that could take the request, the project whose subject words the request uses. Anything else is one question and no task, for example a sound problem in a repository with a web app and a desktop app.

## Which tools

A recipe names capabilities, never tools. For each capability the router takes the first provider that passes every filter:

- its status is not `hold`. The status comes from `radar/radar.yml` or `settings/mcp/catalog.yml`. A provider in `assess` is offered and marked as not proven yet
- this client can use it (`claude`, `opencode` or `coordinator`)
- the folder has its language, for a language server
- it is not a third party server while the cost mode is `local-only` or the folder is `work` or `restricted`
- it is seen: a signal of the project, a program on the PATH, a server in `.mcp.json` or `opencode.json`, a skill of this standard

A provider that cannot be seen from here, such as a Claude Code plugin, is offered as "not checked". When no provider is left, the decision names what is missing and nothing is installed.

The first recipes:

| Recipe | Fits | Capabilities | Done means |
| --- | --- | --- | --- |
| `web-experience` | A web folder and words about design, the page or attention | visual-design, browser-test, accessibility, unit-test | The main activity works on a phone and a desktop, with the keyboard |
| `web-fix` | A web folder and a fix verb | code-navigation, browser-test, unit-test | A test that fails without the change passes with it |
| `windows-app` | Windows or desktop code | code-navigation, unit-test, native-ui-test | The failure is fixed in the window of the executable, on Windows |
| `data-pipeline` | A scraper, an HTTP client, a notebook or a database | code-navigation, unit-test, data-integrity | Cursor, ids and assets are the same after an interruption |
| `docs-academic` | LaTeX and a bibliography | docs-review | The document builds and every reference resolves |
| `pr-review` | A review request | code-review, github, unit-test | Every finding names a line of the diff |
| `repo-onboarding` | A setup request | repo-setup, unit-test | Profile, restrictions and one verifying command are recorded |
| `general-code` | Any other code folder | code-navigation, unit-test | A test that fails without the change passes with it |

`library-docs` is added to any recipe when the request talks about a version, an upgrade or a migration. The project's own lockfile and documentation come first, Context7 after.

## The decision

`python scripts/router.py route "REQUEST" --cwd DIR --json` prints it. It records the repository, folder and revision, the kind of request and why, the profile and the web experience with their source, the signals with their files, the recipe with the others that matched, the provider of each capability with the ones passed over and why, the permission the request needs, what leaves the machine, how the result is verified, what was reused and any open question. No confidence percentage is given: the evidence is listed instead.

The owner's `.standard.yml` wins over the recipe for the profile and the experience. A repository without it is told so. The standard's own repository, which holds `base/base.yml` and `profiles/`, counts as software. Once the profile is known, a recipe of another profile is chosen only when the request names its words.

The prompt hook routes the owner's words only. It drops the `<system-reminder>` blocks a client adds and, in a session that another session started, the background and the shared notes line around the task.

## Tasks

A work, review, setup or publish request opens one task in `~/.standards/router/tasks`, with a key and a state. In the same session and repository:

- a short reply, or one that starts with "también", "además", "mejor", "also" or "instead", updates the open task
- a new order closes the old task as superseded and opens another
- `python scripts/router.py done KEY` closes a task. A task with no news for `routing.task_ttl_h` hours (12) is no longer followed

A new session in the same repository is told about a task an old session left, so work is found again after a restart.

## In Claude Code

The plugin's `UserPromptSubmit` hook runs on every prompt, in about a quarter of a second on a small repository. It adds context only to a work, review, setup or publish request inside a git repository. A question gets nothing. It never blocks a prompt: on any error it prints nothing. The context is a list of facts, at most `routing.max_context_chars` characters (2400). When it is longer, the notes go first, then lines from the end, and the line that closes the task always stays.

By default the session does the work with that context (`routing.owner: session`). The context of a work order then also names the agents and executors the standard ships, because a session left alone does everything itself with its own model: independent parts go to `item-worker` agents at once, each in its own worktree, lookups go to `repo-scout`, `orchestrate.py route --all` says which parts OpenCode or Ollama take and `delegate-runner` hands them over, and a failed check goes to `ci-fixer`. A learning or documentation recipe also names `content-auditor`, and a web recipe or a web folder names `web-tester`. `agents/README.md` lists every agent with its model.

To hand every work order to the coordinator instead, the owner runs:

```
python scripts/orchestrate.py consent --route coordinator
```

It writes `router: {owner: coordinator}` to `~/.standards/local.yml`. `consent --route session` turns it off. Then the context says the session edits no file and names the `plan_autopilot.py go --detach` command that starts the run. One owner per task keeps the session and the coordinator from editing the same files.

`plan_autopilot.py` also stores the router's decision in the plan (`route`), so a run shows why its tools were chosen.

## Packaged plugin

The package built by `standard.py skills-repo` now ships the executor loop, the planner and the router. Before, its `verify.py` and `adversarial.py` failed at start with `No module named 'execute'`. The selftest starts every packaged script and sends a work request and a question through the packaged hook.

## Measured on the owner's repositories

On 2026-11-15, on shallow clones of four public repositories of the owner, with the requests of the owner's guide. Each decision took 0.22 to 0.23 s. Nothing was edited and no task was opened (`--dry`).

| Repository | Request | Folder | Recipe | Verification |
| --- | --- | --- | --- | --- |
| GCP_Data_Engineer_Fieldnotes | Improve this page so someone with little time understands why to study the topic | root | web-experience, profile web from `.standard.yml` | `npm test` |
| foco_local_desktop | Fix the focus of the active window when it is minimized | root | windows-app | `go test ./...` and a run of the executable on Windows |
| extractor_exambase | Fix why questions are doubled when the extraction resumes | root | data-pipeline | `python -m unittest discover -s tests` |
| oratoria_lab | Fix the audio problem | `packages/audio`, named by the request | general-code | `pnpm test` at the root |

The first run got three of them wrong, and each became a test. The `src/index.html` of Fieldnotes counted as a second project beside its root `package.json`, and a site built with Node but no framework did not count as web. The extractor's tests use `unittest`, which no requirements file names. In the oratoria_lab workspace every test runs from the root, so the audio package showed no tests.

## Adding a tool or a kind of project

1. Add the tool to `radar/radar.yml` with its status, or to `settings/mcp/catalog.yml` if it is an MCP server.
2. Add it as a provider of a capability in `settings/recipes.yml`: `id`, `kind`, `runs`, `clients`, `leaves_machine`, how it is detected, and `radar` or `mcp` to read its status from.
3. For a new kind of project, add its file signals to `scripts/repo_fingerprint.py`, one recipe and two tests that show which requests it takes.
4. Run `python scripts/router.py check`. `verify.py` runs it as `S.recipes`.

## Not done

- Every family of the owner's guide of 2026-11-15 now has its providers, and the visual, learning and writing tools of `docs/012-learning-visuals-writing.md` too. The ones not tested here stay in `assess`.
- The OpenCode MCP format was checked in the OpenCode source. See `docs/012-learning-visuals-writing.md`.
- The three pilots of the guide (a study site, a native Windows app, a data extractor) need the owner's repositories and a Windows machine.
- No change was made to the other repositories, to `SVN11X/skills` or to the templates. Publishing the plugin is the release step.
- Whether a Claude Code plugin is installed cannot be seen from a hook, so such a provider is always "not checked".

## Checks

```powershell
python -m unittest tests.test_router tests.test_fingerprint
```

```powershell
python scripts\router.py check
```

```powershell
python scripts\router.py route "Mejora esta página" --cwd . --dry
```
