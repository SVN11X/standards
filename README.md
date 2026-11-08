# standards

How SVN11X repositories are organized, documented and reviewed. One source of truth for people and for any AI tool (Claude, Codex, Copilot, Cursor, Gemini).

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
- `hooks/`: Claude Code hooks published with the skills, such as the autopilot for repo-improve.
- `scripts/`: `standard.py` (init, agents, check, migrate, templates, package-skills, skills-repo, selftest), and `release`, `publish-templates`, `publish-skills` and `protect-repo`, each in `.sh` and `.ps1`.
- `settings/`: repository settings as code, such as the branch ruleset.
- `preferences.md`: the owner's taste, with good and bad examples.
- `references.md`: the sources behind the rules.
