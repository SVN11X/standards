---
name: web-improve
description: Audit and improve an existing website or web app, especially static sites on GitHub Pages. Covers UX and visual quality, interactive explanations and simulations that teach, content clarity, accessibility, performance, SEO and safe static deployment, then delivers verified changes as a pull request or as a full ZIP plus a patch for git am. Use this whenever the user wants to improve, modernize, fix or polish a web page, landing page, portfolio, documentation site or interactive demo, make a diagram or simulation easier to understand, prepare a site for GitHub Pages, or review a site's UX, even if they never say "audit".
---

# web-improve

Improve a real site so visitors understand it, can use it, and it stays fast, accessible and easy to maintain. Quality comes from execution, not from the number of libraries.

## Ground rules

- Talk to the owner in their language. Write code, comments and repository docs in English. User-facing text stays in the site's content language.
- Work on what exists. Keep the brand, valuable content, URLs and working features. Do not migrate frameworks without evidence that the change pays off.
- Check which tools you really have: files, git, terminal, browser, network, GitHub. Never claim you ran, tested or published something you did not.
- Find information yourself before asking. Ask only for what you cannot get, such as an original measurement or the base commit for a patch.
- Do not delete content, push, merge, publish, change DNS or credentials, or add paid services without the owner's go-ahead.

## Read the repository's own rules first

If the repository has an `AGENTS.md`, follow it. Its options (motion, 3D, flows, theme), fixed rules and recorded decisions win over this skill. `DESIGN.md` is the visual direction. If it is missing or has `TODO(owner)` items, interview the owner before any visual change (identity, audience, personality, palette, typography, motion, references), transcribe the answers and show them for confirmation. If the antislop skills are installed, use antislop-ui, antislop-human, antislop-layoutmobile and antislop-copywriting for their topics.

Its `experience` option names the web sub-profile that leads the site. Read `references/subprofiles.md` for the full guide of each one and for how to choose when the owner named none. `python <standard>/scripts/standard.py subprofile "<the request>" --repo .` gives the choice and a short summary to load.

## 1. Inventory without changing anything

- Read the real files, the deploy setup (GitHub Actions, Pages source, base path), dependencies and lockfile. Record the branch and the starting commit.
- If you can run code, run `python scripts/audit_site.py <site-folder>`. It only reads files, and its `design` section lists measured findings: font families, durations outside the tokens of `DESIGN.md`, scripts that animate without reading the reduced motion setting, images without alt or size, heading order.
- When the project has Playwright, `node scripts/measure_page.mjs <url-or-file>` measures the page in a browser at 360 and 1280 px: horizontal scroll, touch targets, text contrast, line length, clipped text and font families.
- When the owner gives a public URL, compare it with the code. They can differ.
- Read `references/stack-and-hosting.md` for hosting limits and technology choices.

## 2. Audit the experience

Review the home page and main routes: what the site offers and for whom within five seconds, hierarchy, navigation, calls to action, mobile, accessibility, states (loading, empty, error, success), text length and repetition, images, motion and forms. Use the heuristics in `references/art-direction-and-content.md`.

Judge design in the three layers of `references/design-judgment.md`: measured without AI, compared with the owner's examples in `DESIGN.md`, and screenshots reviewed by a model that reads images and passed the judge test. Every finding says its layer and carries the measurement, the screenshot or the example behind it. Never give an overall design score.

Judge the use of space with `references/layout-and-space.md`, not by taste. Every layout finding cites the rule and its source, and gives a measurement: characters per line, how much of the first screen the main task uses, side margins, at 360, 768, 1280 and 1920 px.

## 3. Prioritize

Report at most five findings, each with the evidence you saw, its impact, effort and risk. Pick one to three improvements per iteration that you can demonstrate. Do not ask permission again for reversible steps inside the agreed scope.

## 4. Explain before decorating

When the site teaches something, such as a diagram, a model, a simulation or technical results:

- Define each new term where it first appears. State units, conventions, assumptions and where the data comes from.
- Show cause and effect: input, then processing, then a visible change. Say what stays fixed so comparisons are fair.
- Separate measured data, derived calculations and illustrative examples, and label each one.
- Read `references/interactive-explanations.md` before designing controls, diagrams or simulations.
- For study sites and explainers (progress, bookmarks, profiles, hotspots, why-it-matters introductions), read `references/learning-experience.md`.

## 5. Implement

- Build reusable components. Cut repeated text. One idea per block.
- An interactive demo must work, start in a meaningful state, show current values with units, offer a reset, and have a static fallback.
- Use motion only to show continuity, state or cause. Always respect `prefers-reduced-motion`, in CSS and in the JavaScript that animates. `references/motion-and-foundations.md` lists what motion must survive, the foundations (tokens, native CSS first, fonts, empty states, first visit) and when a library is justified.
- For buttons and microinteractions, copy a pattern from `references/interaction-patterns.md`. Patterns 1 to 6 run in `gallery/index.html`, which opens straight from the file on a computer or a phone. Patterns 7 and 8 (form and link preview) are written out without a demo.
- A structural redesign shows two short versions with real content. Record the owner's choice and its reason in `DESIGN.md` under Examples.
- Choose technology with the matrix in `references/stack-and-hosting.md`: the simplest option that meets the goal. Prefer tools marked adopt or trial in the radar of the standard, and only those whose expression levels include the one in `DESIGN.md`. A tool outside the radar is evaluated with tool-radar first.
- Keep the output static when the host is GitHub Pages. Never put secrets in frontend code.

## 6. Verify with evidence

Follow `references/quality-and-delivery.md`. Check syntax and paths under the repository base path. Test every control at its minimum, maximum, repeated changes and reset. Test mobile at 360 px, desktop, keyboard, touch, reduced motion, dark mode if the site has it, the build and existing tests. Report exactly what ran. Say "verified in a browser" only after a real browser test.

A site with a reactive object or a pointer effect gets this test: with reduced motion and no task running, the object stays still while the pointer moves.

Keep the evidence in the repository: add or update Playwright Test cases with `references/regression-testing.md`, and run adversarial-testing at the standard level before delivering. When the change touches data files, take a data-preservation snapshot before it.

## 7. Deliver

- Agent with repository access: commit on a branch with Conventional Commits messages and open a pull request with every template section filled. Open the pull request with a Conventional Commits title (for example `refactor: adopt the repository standard`) and a body that copies `.github/pull_request_template.md` with every section filled: Task, What I understood, Assumptions, Decisions, Not done, How to verify. Write the body to a file outside the repository and use `gh pr create --title "..." --body-file <file>`. Then wait for the check and fix it if it fails.
- Chat without repository access: clone the repository if it is public, commit the change on top of its real base, and deliver one patch for `git am`, made and verified with `scripts/deliver_git.py`. Deliver a full ZIP only when the owner asks for it, or when there is no git base at all.
- Save tokens: never paste whole files, logs or unchanged code in the reply. Show only the lines that change when the owner needs to see them.
- End with a short summary: what changed and why, the files, the checks that ran and their results, pending risks, and how to deploy.
