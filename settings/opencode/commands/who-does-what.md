---
description: List who does each task type on this machine (program, local model, free model) and why
agent: build
---
1. Find the standard: the folder that `~/.agents/skills/repo-improve` links to, two levels up. Call it `<standard>`.
2. Run `python <standard>/scripts/orchestrate.py route --all --repo . $ARGUMENTS` and print the table as it is.
3. For a row that says `blocked`, give its reason in one line. Do not look for another model and do not change any setting.
