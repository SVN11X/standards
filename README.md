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

## Adopt the standard in an existing repository

Use the `repo-setup` skill, or run `init --existing`, which adds missing files and never overwrites. Moving files is always proposed first and done with `git mv`.

## Check a repository locally

```bash
python scripts/standard.py check ../my-site
```

## Change the standard

1. Edit the YAML files or templates here, then run `python scripts/standard.py selftest`.
2. Add an entry to `CHANGELOG.md` and bump `version` in `base/base.yml`.
3. Tag the release and move the major tag, one command per line:

   ```bash
   git tag v1.1.0
   git tag -f v1
   git push origin v1.1.0
   git push -f origin v1
   ```

4. Rebuild the templates with `scripts/publish-templates.sh` (bash) or `scripts/publish-templates.ps1` (Windows PowerShell), and package the skills again with `python scripts/standard.py package-skills dist/skills`.
5. In each repository, run `agents` to refresh `AGENTS.md`. Until then the check only warns.

A breaking change gets a new major tag (`v2`). Each repository moves to it when the owner decides.

## Layout

- `base/`: rules and files shared by every profile, and the `AGENTS.md` templates.
- `profiles/`: one folder per profile with `profile.yml` (folders, fixed rules, reasons, setup questions) and its extra files.
- `patterns/`: one card per design pattern.
- `prompts/`: prompts to paste into AI tools that do not have the skills.
- `skills/`: `repo-setup` and `code-review`.
- `scripts/`: `standard.py` (init, agents, check, templates, package-skills, selftest), `publish-templates.sh` and `publish-templates.ps1`.
- `preferences.md`: the owner's taste, with good and bad examples.
- `references.md`: the sources behind the rules.
