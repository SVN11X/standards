# 001. Profiles

A profile describes what a repository produces: `web`, `software`, `data-ai`, `hardware`, `docs` or `infra`. Each profile in `profiles/<name>/profile.yml` has three kinds of practice:

- Fixed rules that always apply.
- Techniques allowed only with a reason written in `docs/decisions/`.
- Setup questions, answered once and stored in `.standard.yml`.

A mixed repository picks a main profile and declares parts: subfolders that follow another profile with their own `AGENTS.md`. When a language or framework imposes its own layout, the tool wins and the profile adapts.

Tone is not fixed by the standard. For web repositories, `DESIGN.md` records the audience, the personality and the expression level (sober, balanced or expressive), and the setup options record motion and 3D.
