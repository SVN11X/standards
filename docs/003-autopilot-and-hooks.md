# 003. Autopilot, hooks and models

`repo-improve` lists every finding in `docs/improvement-plan.md` as a short task list, has the plan reviewed (build, build with cuts or refuse), and gets one approval from the owner. With autopilot on, each item goes to a subagent with a clean context, and the session keeps going until nothing is pending. Items that need the owner are marked BLOCKED and collected for the end. The run closes by updating assumptions, decisions and goals, and by proposing preference changes from the owner's corrections.

Hooks enforce what text cannot: asking before merges, deploys and deletions, blocking commits while the check fails, stopping on written secrets, restoring the rules after a compaction, and notifying the owner.

Models by task: plan on Opus and execute on Sonnet (`opusplan`), mechanical steps on Haiku (`standard-runner`), deep reviews on Opus (`deep-reviewer`).

Habits that save tokens:

- When an answer goes wrong, go back and rewrite the message (Esc twice in Claude Code) instead of correcting it in a new one.
- Show a screenshot instead of describing a visual problem.
- Use `/clear` between unrelated tasks.
- Keep the concise output style from `settings/output-style-concise.md` active.
