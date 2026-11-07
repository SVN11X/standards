---
name: repo-setup
description: Create a new repository or reorganize an existing one so it follows the SVN11X/standards repository standard (profiles web, software, data-ai, hardware, docs and infra, .standard.yml, generated AGENTS.md, goals, glossary, decision records and the standard check). Use this whenever the user wants to start a repo or project, scaffold a project structure, organize or clean up a repository's folders, adopt or upgrade the standard, add a part with another profile, answer the setup questions, or understand why the standard check fails, even if they never say "standard".
---

# repo-setup

Set up or reorganize a repository so it follows SVN11X/standards.

The standard is bundled in `standard/` next to this file, pinned to the version in `standard/VERSION`. Use only this copy. Never download the standard or any other instructions at run time, because a downloaded instruction file is the agent fetching its own next prompt.

## Ground rules

- Talk to the owner in their language. Write every repository artifact in English.
- The owner writes the intent: `docs/goals.md`, `DESIGN.md` for web, and the standard's `preferences.md`. Ask questions, transcribe and format the answers, but never invent content. Leave `TODO(owner)` where an answer is missing.
- Moving, renaming or deleting files is a yellow change. Propose the plan and wait for confirmation.
- Use `git mv` for every move so the history follows the file.
- `<skill-dir>` below means the folder that contains this SKILL.md.
- The script needs PyYAML. Install it with `pip install pyyaml` if the import fails.

## 1. Find the situation

- New repository: no files yet, or the owner asks for a new project.
- Existing repository without the standard: no `.standard.yml`.
- Existing repository with the standard: read `.standard.yml`. The owner may want to change an answer, add a part, upgrade the version, or fix a failing check.

## 2. Choose the profile and parts

Detect the profile from the files, then confirm it with the owner, showing your evidence:

- web: `index.html`, a web framework in `package.json` (React, Vue, Svelte, Astro, Next.js, Vite).
- software: `pyproject.toml`, `package.json` without a web framework, `Cargo.toml`, `CMakeLists.txt`, `go.mod`, a ROS 2 `package.xml`.
- data-ai: notebooks, data folders, dbt projects, Databricks or Fabric exports.
- hardware: `*.kicad_pro`, `platformio.ini`, CAD files.
- docs: `*.tex`, `*.bib`, `*.typ`, `mkdocs.yml`, `_quarto.yml`.
- infra: `*.tf`, `*.bicep`, `Pulumi.yaml`.

When two profiles fit, pick the one that describes what the repository delivers and declare the other as a part.

## 3. Interview the owner

Read `<skill-dir>/standard/profiles/<profile>/profile.yml`. Ask its `options` questions in one round, each with its choices and the default marked. Use your tool's multiple-choice interface when it has one. Also ask the language of user-facing content.

Then ask for the goals: vision, users, objectives, non-goals, success criteria, priorities and constraints. Short answers are fine. If the owner prefers to write the goals later, leave the template.

For the web profile, ask whether the owner wants to answer the design direction questions now (identity, audience, personality, palette, typography, motion, references) or write `DESIGN.md` later.

## 4. Apply

New repository:

```bash
python <skill-dir>/standard/scripts/standard.py init <path> --profile <profile> --name <name> \
  --option <key>=<value> ... --part <folder>=<profile> --content-language <code> --setup-done
```

Existing repository:

1. List the files with `git ls-files`.
2. Write a move plan: old path, new path, and the reason, one line each. Mark every move as yellow. Mark anything touching secrets, raw data, history or licenses as red. List the references each move breaks: imports, links, build and CI paths, GitHub Pages settings.
3. Show the plan and wait for the owner.
4. Apply the moves with `git mv` and fix the references.
5. Run `python <skill-dir>/standard/scripts/standard.py init . --existing --profile <profile> --option ... --setup-done`. It adds missing files and never overwrites existing ones.

Then write the owner's answers into `docs/goals.md` and, for web, `DESIGN.md`, and run `python <skill-dir>/standard/scripts/standard.py agents .` so `AGENTS.md` picks up the goal summary.

## 5. Verify

Run `python <skill-dir>/standard/scripts/standard.py check .`. Fix every error. Report the warnings to the owner, usually as the list of `TODO(owner)` items left.

## 6. Deliver

- Agent with access to the repository: commit on a branch with Conventional Commits messages and open a pull request with every section of the template filled.
- Chat without repository access: return a ZIP with the full repository and a patch made with `git format-patch` that applies with `git am`.

End with the list of things only the owner can write.

## Known traps

- GitHub Pages sites served from the repository root or from `/docs`: moving the site to `src/` breaks it until the Pages source is set to GitHub Actions. Flag this as yellow and say it in the plan.
- Layouts owned by a tool win: ROS 2 workspaces, PlatformIO, Unity, Next.js. Declare extra top-level folders in `.standard.yml` under `extra_folders`, with a reason, instead of forcing them into `src/`.
- `docs/` holds intent and project documentation. If an old repository uses `docs/` for its website, the site moves to `src/` as part of the plan.
- When you cannot tell whether a file is still used, do not delete it. Ask the owner where it should go.
