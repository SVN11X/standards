# AGENTS.md

Rules for any AI agent editing this standards repository.

- Write everything in English. Reply to the owner in the language they write in.
- Profiles live in `profiles/<name>/profile.yml`. Shared rules live in `base/base.yml`. Keep each rule to one concrete, checkable line.
- A new rule needs a reason: a repeated mistake, a source in `references.md`, or an owner decision. Do not add rules for completeness.
- Files ending in `.tmpl` are rendered by `scripts/standard.py`. Placeholders look like `{{name}}`. GitHub expressions keep their own `${{ ... }}` form.
- `preferences.md` is written by the owner. You may format it. Never add entries the owner did not state.
- Generated `AGENTS.md` files must stay under 150 lines. Run `python scripts/standard.py selftest` after every change.
- Pattern cards follow `patterns/_template.md`. Every card cites one original source and one free source.
- Avoid AI slop: no filler, no marketing words, no em dashes or semicolons as separators, no comments that restate code.
