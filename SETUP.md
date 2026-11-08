# SETUP

Instructions for any AI agent that sets up SVN11X/standards in a repository together with its owner. Read this file to the end before acting.

1. Read `docs/000-philosophy.md` to `docs/004-radar.md` in this repository, in order.
2. Work out the situation: a new repository, an existing one without `.standard.yml`, or one that already follows the standard.
3. Say in plain words what you understood the repository is for, and wait for the owner to confirm.
4. Interview the owner one short question at a time: the profile and its parts, the setup options of that profile, the language of user-facing content, and the goals. Transcribe the answers. Never invent them.
5. Show the whole plan once: files to create, files to move and why, and what the owner still has to write. Wait for one approval.
6. Apply it with `python scripts/standard.py init` for a new repository, or `migrate` and then `init --existing` for an existing one. Moves use `git mv`.
7. Run `python scripts/standard.py check <repository>` until it has no errors.
8. Deliver on a branch with Conventional Commits and one pull request whose body fills every section of the template.

Never merge, deploy, publish secrets or rewrite history. Those always wait for the owner.
