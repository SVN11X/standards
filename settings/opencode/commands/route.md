---
description: Say which repository, folder, recipe and tools a request is about, before any edit
agent: build
---
Route this request: $ARGUMENTS

1. Find the standard: the folder that `~/.agents/skills/repo-improve` links to, two levels up. Call it `<standard>`.
2. Run `python <standard>/scripts/router.py route "<the request>" --cwd . --client opencode` and print the result as it is.
3. If it prints an open question, ask the owner that question and stop. Do not pick a folder yourself.
4. If it names a capability with none available, say what it needs. Do not install anything and do not pick another tool.
5. Otherwise do the request with the providers it named, and verify with the command and the proof it printed.
