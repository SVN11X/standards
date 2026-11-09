---
description: Apply one pending item of docs/improvement-plan.md, verify it and commit
agent: build
---
Apply exactly one item of `docs/improvement-plan.md`: $ARGUMENTS
If no item is named, take the first line that starts with `- [ ]` and is not BLOCKED.

1. Read `AGENTS.md`, the item and only the files the item touches.
2. Work on a branch, never on the default branch.
3. If the item is yellow or red in the traffic light of `AGENTS.md`, needs a design decision, touches more than five files or is unclear, change no code. Rewrite the item as `- [ ] BLOCKED: <one short question>` and stop.
4. Make the change.
5. Run the check (README.md, section Standard) and the tests. Fix what you broke. If they still fail, do not commit. Report the failing lines and stop.
6. Mark the item `- [x]` and commit with a Conventional Commits message. Do not push.
7. Reply in three lines: what changed, the commit, the check result. Never paste files or logs.
