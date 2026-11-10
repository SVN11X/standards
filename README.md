# standards

How SVN11X repositories are organized, documented and reviewed. One source of truth for people and for any AI tool (Claude, Codex, Copilot, Cursor, Gemini).

## Read first

`SETUP.md` sets up the standard with any AI tool. `docs/how-it-works.md` explains how this repository works inside. The `docs/` folder explains the standard in order: `000-philosophy.md`, `001-profiles.md`, `002-intent.md`, `003-autopilot-and-hooks.md`, `004-radar.md`, `005-verification-and-orchestration.md` and `006-model-analyzer.md`.

## How a repository uses it

Each repository carries three things:

- `.standard.yml` declares the profile, the answers to the setup questions and the pinned version of this standard.
- `AGENTS.md` is generated from this repo and from the repository's own `docs/goals.md`. AI tools read it at the start of every session. People can read it too.
- `.github/workflows/standard.yml` calls the shared check in this repo on every push and pull request.

Each repository also keeps its intent in `docs/`: goals, glossary, assumptions, decisions and specs. The owner writes the goals. AI tools may ask, transcribe and format, never invent.

## Profiles

A profile describes what a repository produces.

- `web`: sites and apps used in a browser.
- `software`: programs and libraries.
- `data-ai`: data pipelines, analysis and machine learning.
- `hardware`: electronics, firmware and mechanical parts.
- `docs`: documents and research.
- `infra`: infrastructure defined as code.

A mixed repository picks a main profile and declares parts. A part is a subfolder that follows another profile and has its own nested `AGENTS.md`.

Every profile has three kinds of practice. Fixed rules always apply. Some techniques are allowed only with a reason written in `docs/decisions/`. Everything else is a setup question, answered once and stored in `.standard.yml`.

## Start a new repository

From a template: open `template-<profile>` on GitHub and click "Use this template". Then answer the setup questions, with the `repo-setup` skill in Claude or with `prompts/intake.md` in any other AI.

From the command line:

```bash
pip install pyyaml
python scripts/standard.py init ../my-site --profile web --name my-site --interactive
```

## Skills

The `repo-setup` and `code-review` skills are published at [SVN11X/skills](https://github.com/SVN11X/skills), which is also a plugin marketplace: install it once in claude.ai or Claude Code and turn on automatic sync. The skills read the rules from this repository at the version each repository pins, so most changes here reach them without republishing. `prompts/global-instructions.md` has the text that tells each tool to use them.

## Adopt the standard in an existing repository

The check fails while files sit outside the layout: loose files at the root, undeclared folders and undeclared hidden folders are errors. To fix a messy repository:

1. `python scripts/standard.py migrate <repo> --profile <profile>` writes `docs/migration-plan.yml` with every proposed move, the decisions left to the owner, and the lines that mention each moved file. Nothing moves yet.
2. Review and edit the plan, for example to translate names to English.
3. `python scripts/standard.py migrate <repo> --apply` moves the files with `git mv` and adds the missing standard files.
4. Fix the listed references, resolve the decisions, then run `agents` and `check`.

The `repo-setup` skill follows the same steps.

## GitHub settings

Everything GitHub shows around the files follows the standard too. Each repository keeps its About panel (description, website, topics) in `.standard.yml` under `github`. `settings/repository.yml` sets the rest: features on or off, merge settings, security features and labels.

```bash
python scripts/standard.py github ../my-site            # shows what would change
python scripts/standard.py github ../my-site --apply    # applies it with your GitHub login
```

The check warns when the About panel on GitHub differs from `.standard.yml`. Pushing a `v*` tag creates a GitHub release with the notes of that version from `CHANGELOG.md`.

## Enforce it

`scripts/protect-repo.ps1 -Repo OWNER/REPO` (or `protect-repo.sh`) applies `settings/ruleset-main.json`. From then on, changes reach the default branch only through a pull request whose standard check passed.

## Check a repository locally

```bash
python scripts/standard.py check ../my-site
```

## Verify everything in one run

```bash
python scripts/verify.py --level deep --live
```

It runs the selftest, the unit tests, the adversarial suite, the linters it finds and, with `--live`, the executors of this machine: Ollama, OpenCode with the free models you checked, and the MCP servers in trial. It installs nothing. The verdict and a JSON and Markdown report go inside the git folder. On Windows, `scripts/verify-all.ps1` runs the same. Without `--live`, nothing outside the machine is touched. See `docs/005-verification-and-orchestration.md`.

## Hand work to other models

`scripts/orchestrate.py` decides who does a task (a program without AI, Ollama, OpenCode on a free model, or Claude) and runs it with its own checks. Record once which folders may use free remote models and which free models you checked:

```bash
python scripts/orchestrate.py consent --path C:/my_drive/Portafolio --class personal-public --free-model <id from opencode models>
python scripts/orchestrate.py doctor --full
python scripts/orchestrate.py route edit-small --repo ../my-site
python scripts/orchestrate.py route --all --repo ../my-site
```

`route --all` prints who does each task type on this machine, with the exact model and the reason. Three cost modes decide what a run may use: `local-only`, `free-strict` and `existing-subscription`. In a free mode a task that no allowed executor can take is blocked with the reason, and nothing paid is used on its own.

## Find the best model for each task

`scripts/analyze.py` finds every model the local Ollama has installed and every model the providers of `settings/providers.yml` list, tests the ones that are allowed on synthetic tasks graded by a program, and writes a report with a proposed split. It never downloads a model or uses a paid endpoint. `prepare` shows each model found with its state and the reason.

```bash
python scripts/analyze.py prepare
python scripts/analyze.py plan
python scripts/analyze.py run
python scripts/analyze.py report
```

`docs/006-model-analyzer.md` has the cost modes, the bench classes and the night guide.

## Change the standard

1. Edit the YAML files, templates or skills here.
2. Add an entry to `CHANGELOG.md` and raise `version` in `base/base.yml`.
3. Run `scripts/release.ps1` in Windows PowerShell or `scripts/release.sh` in bash. It runs the selftest, commits, tags the version, moves the major tag, pushes, and publishes the skills and the templates.
4. In each repository, run `agents` to refresh `AGENTS.md`. Until then the check only warns.

A breaking change gets a new major tag (`v2`). Each repository moves to it when the owner decides.

## Layout

- `base/`: rules and files shared by every profile, and the `AGENTS.md` templates.
- `profiles/`: one folder per profile with `profile.yml` (folders, fixed rules, reasons, setup questions) and its extra files.
- `patterns/`: one card per design pattern.
- `prompts/`: prompts to paste into AI tools that do not have the skills.
- `skills/`: source of the skills. The published copies live in SVN11X/skills.
- `agents/`: Claude Code subagents published with the skills, each with a fixed model.
- `hooks/`: Claude Code hooks published with the skills: guardrails, secret scan, executors at startup, rules after compaction, notifications and the autopilot.
- `radar/`: evaluated tools with their status.
- `docs/`: the standard explained in reading order.
- `scripts/`: `standard.py` (init, agents, check, migrate, subprofile, templates, package-skills, skills-repo, selftest), `verify.py`, `adversarial.py`, `orchestrate.py`, `analyze.py`, `providers.py`, `bench_tasks.py`, `preserve.py`, `safe_patch.py`, `memory.py`, and `release`, `publish-templates`, `publish-skills`, `protect-repo`, `setup-opencode`, `verify-all` and `analyze-models`, each in `.sh` and `.ps1`.
- `schemas/`: JSON Schema of the verification report.
- `tests/`: unit tests of the scripts with fake executors, run with `python -m unittest discover -s tests`, and `tests/web/gallery.test.mjs`, which checks the pattern gallery in a browser.
- `settings/`: repository and tool settings as code, such as the branch ruleset, the OpenCode setup, the routing, privacy and cost policy (`orchestration.yml`), the settings of models (`models.yml`), the remote providers (`providers.yml`) and the MCP catalog.
- `preferences.md`: the owner's taste, with good and bad examples.
- `references.md`: the sources behind the rules.
