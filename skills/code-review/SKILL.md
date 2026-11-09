---
name: code-review
description: Review code, a diff or a pull request against the SVN11X/standards rules of the repository's profile, including fixed rules, option rules, techniques that need a written reason, design pattern use, AI slop, tests and the pull request contract. Use this whenever the user asks to review, audit, check or critique code or a pull request in a repository that has a .standard.yml or a generated AGENTS.md, or asks whether a change follows the standard, even if they only say "review this" or "revisa esto".
---

# code-review

Review a change against the rules the repository already declares. The rules live in the repository, so read them first and do not apply generic taste on top.

## Read first

- `.standard.yml`, `AGENTS.md`, and the nested `AGENTS.md` of every folder the change touches.
- `docs/goals.md` and the decision records in `docs/decisions/` that the change mentions.
- The task or the pull request description.
- For any pattern the change introduces, its card. Read the cards from the pinned standard: clone `https://github.com/SVN11X/standards` at the tag in `.standard.yml` into a temporary folder and open `patterns/`. Without network access, use the copies in `references/patterns/`.

## Check, in this order

1. Contract. Does the change serve the task's Why and stay inside Where and Do not touch? Does the pull request have every section filled?
2. Fixed rules of the profile and the rules of the chosen options, as listed in `AGENTS.md`.
3. Techniques under "Allowed only with a written reason". Each one needs a decision record. A missing record is a finding. A new dependency that is not in the radar of the standard is also a finding: evaluate it with tool-radar.
4. Design patterns. Any new pattern, abstraction layer or indirection needs a named problem and a decision record. Flag over-engineering: one implementation behind an interface, a factory that builds one thing, layers that only pass calls through. Suggest the simpler alternative from the pattern card.
5. AI slop. Comments that restate the code or narrate steps, banners and emoji, dead code, unused dependencies, placeholder or fabricated data, marketing words, vague TODOs.
6. Tests. Is there a test or command for Done when? Do the tests check behavior rather than implementation details?
7. Specialized reviews. For interface work, defer to antislop-ui and antislop-human when they are available. For security-sensitive changes, recommend a dedicated security review. For a change made by another agent or model, or one that touches data, workflows or permissions, run adversarial-testing and cite its report as evidence.

## Deep review

When the owner asks for a deep, strict or "thermo" review, or before a release, run two separate passes over the whole change and its surrounding code, not only the diff:

1. Correctness and security. Look for bugs, behavior that breaks existing features, breaking changes to public interfaces or data formats, security problems (injection, missing authorization, exposed secrets, unsafe deserialization, path traversal, server-side request forgery), resource leaks, concurrency errors, swallowed errors, unfinished features exposed by mistake, and migrations that cannot be undone. Read the pull request discussion only after your own audit, so your view stays independent.
2. Maintainability. Look for a restructuring that makes the change smaller and more direct without changing behavior: layers that only pass calls through, duplicated branches, growing chains of conditions, files that keep growing, abstractions with a single implementation. Propose the concrete restructuring, not cosmetic renames.

Report each pass separately with the severity format below. In Claude Code, delegate this mode to the `deep-reviewer` subagent, which runs on Opus, when it is available. This mode is inspired by the thermo-nuclear reviews published in cursor/plugins under the MIT license.

## Output

Findings only, ordered by severity:

- Blocker: breaks a fixed rule, the task's Do not touch, an accepted decision, or safety.
- Should fix: a missing decision record, slop, missing tests.
- Consider: a simpler alternative.

Each finding: file and line, the rule and where it comes from (the `AGENTS.md` section or the pattern card), what is wrong in one sentence, and the fix. Do not praise and do not summarize what the code does. If nothing is wrong, say so in one line. Reply in the owner's language and quote rule text in English.
