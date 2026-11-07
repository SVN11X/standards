# Prompt: review a change

Copy everything below the line into the chat. Attach `AGENTS.md`, `.standard.yml`, `docs/goals.md`, any decision records the change mentions, and the diff or the changed files.

---

Review this change against the attached AGENTS.md. Report findings only, ordered by severity:

- Blocker: breaks a fixed rule, the task's Do not touch, an accepted decision, or safety.
- Should fix: a technique from "Allowed only with a written reason" or a new design pattern without a decision record, AI slop, missing tests for Done when.
- Consider: a simpler alternative.

For each finding give the file and line, the rule it breaks with its section in AGENTS.md, what is wrong in one sentence, and the fix. No praise and no summary of what the code does. If nothing is wrong, say so in one line. Reply in the language I write in.
