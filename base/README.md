# base

Rules and files shared by every profile.

- `base.yml`: version of the standard, required files, fixed rules, anti-slop rules and check limits.
- `agents.md.tmpl` and `part-agents.md.tmpl`: templates for the generated `AGENTS.md` files.
- `files/`: copied into every repository. Files ending in `.tmpl` are rendered first.
- `optional/`: copied only when a profile requires them.
- `licenses/`: license texts from the GitHub licenses API.
