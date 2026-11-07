# Prompt: setup interview

Use it to create a repository or to adopt the standard in an existing one. Copy everything below the line into the chat and attach `profiles/<profile>/profile.yml` from the standard. If you do not know the profile yet, attach all six.

---

Interview me to set up this repository under SVN11X/standards. Ask one short round of questions at a time, and offer choices with a default.

1. Profile: web, software, data-ai, hardware, docs or infra. Are there parts (subfolders that follow another profile)?
2. The setup questions in the attached profile.yml under options.
3. The language of user-facing content.
4. Goals: vision, users, objectives, non-goals, success criteria, priorities and constraints.

Rules for you:

- Reply to me in the language I write in. Write every file in English.
- Write my answers into docs/goals.md keeping my meaning. Do not invent anything I did not say. Mark gaps as TODO(owner).
- If a choice of mine conflicts with another answer, ask before writing anything.

Deliver `.standard.yml` with `setup: done`, and `docs/goals.md`. Then list what I still have to write myself.
