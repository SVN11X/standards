# Audit dimensions

Check the dimensions that apply to the repository's profile. Record evidence for every finding.

## 1. Structure

- Errors from the standard check: loose files at the root, undeclared folders, undeclared hidden folders.
- Names that are not in English, for files and folders. Translate them through the move plan.
- Generated output committed to git, such as build folders (`dist`, `_astro`, `_site`), exported HTML next to its source, or copies of data that a script produces.
- Executables committed to git. Replace them with a setup script that downloads them.

## 2. Documentation

- `README.md` says what the project is, for whom, how to use it, its status, its layout and its license.
- `docs/goals.md`, `docs/glossary.md` and the decision records exist and are filled.
- Repository documentation is in English. Content for end users stays in their language.

## 3. Build and reproducibility

- One documented command builds or runs the project from a clean clone. Try it when you can.
- A lockfile is committed and versions are pinned.
- Setup steps that only work on the owner's machine are written down or scripted.

## 4. Tests and CI

- Tests cover the core behavior, and CI runs them together with the standard check.
- Workflows use the minimum permissions they need.

## 5. Security and privacy

- No secrets in files or history. Gitleaks runs in the standard check.
- No personal data in the repository. Data about people that is published needs a written decision on its legal basis, retention and pseudonymization.
- Dependencies without known vulnerabilities, for example with `npm audit` or `pip-audit`.
- Third-party scripts in web pages are listed with a written reason.

## 6. Dependencies and size

- No unused or duplicated dependencies.
- No folders with thousands of data files or files over 5 MB in git. Large data goes to external storage, release assets or Git LFS.
- Vendored third-party code or assets keep their license, ideally under `LICENSES/` (REUSE).

## 7. Licensing

- A `LICENSE` in every public repository. Data, content and hardware carry their own licenses where they differ from the code.
- Third-party licenses kept next to what they cover.

## 8. Profile practices

- web: the fixed rules in `AGENTS.md`, deploy through GitHub Actions, the base path, no committed build output, `DESIGN.md` written. Hand UX work to web-improve.
- software: command line help and exit codes, logging, error handling, packaging, tests.
- data-ai: raw data never edited, layers (medallion or raw and processed), data outside git, schema checks, notebooks without outputs, personal data handled.
- hardware: design sources, bill of materials, revisions with tags, ERC and DRC, pin map and power budget.
- docs: one-command build, citations that resolve, figure sources, tags for submitted versions. Hand content review to docs-review.
- infra: remote state, no secrets, separate environments, plan before apply.

## 9. Maintainability

When the code is substantial, run the maintainability pass of code-review's deep mode.

## 10. Presentation

What a visitor sees first: the repository description, website link and topics in the About panel, a README that opens with what the project does and a link to the live site or demo, and screenshots that are real.
