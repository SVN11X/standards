# skills

Source of the skills for Claude and for every tool that reads the open Agent Skills format.

- `repo-setup`: create a repository or adopt the standard in an existing one.
- `code-review`: review code or a pull request against the standard, with a deep mode.
- `web-improve`: audit and improve a website, for the web profile.
- `docs-review`: review documents and documentation, for the docs profile.
- `published-readme.md.tmpl`: README of the public skills repository.

A skill can carry `evals.yml`: cases with a synthetic repository, a task and criteria of success. `python scripts/skill_eval.py run code-review --executor claude --runs 3` runs each case several times, each run on a fresh copy, and a program grades every answer. A step that half the runs or more miss is flagged as a gap of the skill, since the runs share only the instruction: revise `SKILL.md` and run the eval again. `skill_eval.py grade` grades saved answers again after the criteria change, and `skill_eval.py check` validates every `evals.yml`. The idea comes from Lauren Tan's evals as ConquerAI described them on 2026-11-16. Here a program grades, never a model, as in the bench.

Do not install these folders directly. `scripts/publish-skills.ps1` (or `publish-skills.sh`) bundles each skill with a copy of the standard pinned to the current version, publishes them to the `skills` repository, and attaches the ZIP files to a release there. A skill never downloads the standard at run time.
