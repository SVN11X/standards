---
name: tool-radar
description: Evaluate a tool, library, skill, plugin or app before anyone uses it, and record the result in the radar of SVN11X/standards (radar/radar.yml) with a status of adopt, trial, assess or hold. Use this whenever the user shares a link or a post about a new tool and asks what you think of it, whether to use it, or whether it fits their repositories, and whenever another skill wants to add a third-party dependency that is not in the radar yet.
---

# tool-radar

Turn a tool someone found into a recorded decision. Judge it with evidence, not with the post that announced it.

## Evaluate

1. Check that it exists. For a GitHub project, `git ls-remote https://github.com/<owner>/<repo>` and read its README and LICENSE. If you cannot open the source, say so and stop guessing.
2. Write down what it really does, in one or two sentences from the README, not from the announcement.
3. Record the license, the cost, and what leaves the machine (privacy).
4. Compare it with the radar entries in `<standard>/radar/radar.yml` and with the tools the owner already uses. Name any overlap.
5. Decide which profiles it serves and, for interface tools, which `DESIGN.md` expression levels it fits: sober, balanced, expressive.
6. Propose a status. Prototypes, single-maintainer projects and unsigned installers start at assess or trial. Anything that sends repository content to a provider, or acts on events from public repositories, needs an explicit warning.

## Record

- Show the owner the proposed entry and the reasoning in a few lines.
- After approval, add or update the entry in `radar/radar.yml` of the standards repository with today's date, keeping the fields described in `radar/README.md`.
- Never install the tool while evaluating it.

## Answer

Reply in the owner's language: what it is, what it is good for in their repositories, the status, and the one condition that matters most. Keep it short.
