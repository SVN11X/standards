# Agents

Claude Code subagents the plugin ships. Each one starts with a clean context and its own model, so the main session keeps only the plan. Claude picks one by its description. The router context of a work order names the ones that fit the request.

| Agent | Model | Does | Edits |
|---|---|---|---|
| item-worker | Sonnet | one plan item or one independent part, several at once in their own worktrees | yes |
| repo-scout | Haiku | answers one narrow question about the code | no |
| standard-runner | Haiku | runs the standard check, moves, settings, tests and builds | no |
| deep-reviewer | Opus | deep review of a change, a repository or a plan | no |
| delegate-runner | Haiku | hands a green part to OpenCode or Ollama through the router and reports the verified run | no, the executor does |
| ci-fixer | Sonnet | fixes a failed check on a pull request, then calls merge_when_green.py | yes |
| content-auditor | Sonnet | audits question banks, text and images with learning_check, text_check and media | no |
| web-tester | Sonnet | checks a page in a real browser at 360 and 1280 px | no |
| desktop-tester | Sonnet | checks a desktop window with desktop_ux.py, screenshots and the usability heuristics | no |

A new agent needs a function no other agent has and a reason, like any rule in this repository. The selftest checks that every agent names itself after its file, uses a known model and lists only known tools.
