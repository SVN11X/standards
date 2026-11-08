# hooks

Claude Code hooks published with the skills plugin.

- `autopilot.py` (Stop hook): while `.git/standard-autopilot` exists in a repository, the session keeps working through the pending items of `docs/improvement-plan.md` instead of stopping after each one. It stops by itself when nothing is pending, or after two stops in a row without any change to the plan. Delete the marker file to turn autopilot off.
