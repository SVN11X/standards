# profiles

One folder per profile. A profile describes what a repository produces.

Each `profile.yml` has:

- `folders`: the top-level layout, with what goes in each folder, what does not and how files are named.
- `fixed`: rules that always apply.
- `with_reason`: techniques allowed only with a reason written in `docs/decisions/`.
- `options`: setup questions. Each choice can add rules, folders and files.
- `patterns`, `skills`, `license`, `gitignore`, `required_files`, `files`.

The generator copies the rules into `AGENTS.md`, so keep each rule to one concrete, checkable line.
