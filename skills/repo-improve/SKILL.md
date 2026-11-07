---
name: repo-improve
description: Improve an existing repository as a whole. Find out what "better" means for this particular repository from its goals and evidence, agree on the top improvements with the owner, then deliver them one pull request at a time. It runs the standard's check and move plan, audits structure, documentation, build, tests and CI, security and privacy, dependencies and size, licensing, the profile's own practices and presentation, and hands each topic to repo-setup, code-review, web-improve or docs-review. Use this whenever the user asks to improve, clean up, professionalize, modernize, audit or fix a repository or project, or asks what a repository needs, even when the request is vague, such as "mejora este repo".
---

# repo-improve

"Improve this repository" means something different for every repository. Decide what it means here from evidence and from the owner's goals, agree on it, then work in small steps that each leave the repository better and passing its check.

## Ground rules

- Talk to the owner in their language. Write repository artifacts in English.
- The owner's goals decide what "better" means. If `docs/goals.md` is missing or empty, ask for the vision, users, non-goals, success criteria and priorities first, and write the answers down.
- One improvement per pull request. Moving or deleting files, changing public URLs and rewriting history are yellow changes: propose them and wait.
- Never invent measurements, results or a passing check.

## 1. Understand

- Read `README.md`, `docs/goals.md`, `AGENTS.md`, `.standard.yml`, the recent commits and, if available, the open issues.
- Identify the profile and its parts the way repo-setup does. If the repository does not follow the standard yet, adopting it is the first improvement: hand it to repo-setup, which plans and applies the move.

## 2. Diagnose with the standard

Get the pinned standard the way repo-setup describes, then run:

```bash
python <standard>/scripts/standard.py check .
```

Every error is a finding. When the check reports layout errors, generate the move plan with `migrate` (it moves nothing) and use it as evidence.

## 3. Audit the dimensions that apply

Follow `references/audit-dimensions.md`. Skip the dimensions that do not apply to the profile. For each finding, keep the evidence: a file and line, a command and its output, or a measurement.

## 4. Prioritize with the owner

Present at most five findings, each with its evidence, its impact on the owner's goals, effort and risk. Order them by impact on the goals, then by risk, then by effort. Agree on the first one to three.

## 5. Execute one improvement at a time

Hand each topic to the skill that owns it:

- Layout, standard files, migration: repo-setup.
- Code quality and security: code-review, in its deep mode for a full audit.
- Website UX, interactive explanations, GitHub Pages: web-improve.
- Theses, reports and documentation: docs-review.
- Interface slop, accessibility, mobile layout and copy: the antislop skills, when installed.

For every step: a branch, the change, the check passing, and a pull request with every section filled. In a chat without repository access, deliver one patch for `git am` instead, and a ZIP only when the owner asks. Never paste whole files or logs in the reply. Record decisions in `docs/decisions/` and surviving assumptions in `docs/assumptions.md`.

## 6. Leave a trail

After each step, run the check again, update `CHANGELOG.md` when the change is visible to users, and list the remaining findings so the next session starts from evidence instead of from scratch.
