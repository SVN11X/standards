# How a design is judged

A model that looks at a screenshot and gives an opinion is not a reliable judge on its own. Research on interface critique found that model feedback improves when it is given commented examples, and that designers themselves often disagree when choosing between two screens (see UICrit and DesignPref in the standard's `references.md`). So "good design" is decided in three layers, from the cheapest to the most expensive, and every finding says which layer it comes from.

## Layer 1. Measured, without AI

A program opens the page on a phone and a desktop size and measures what is there.

- `python scripts/audit_site.py <site-folder>` reads the files: font families, distinct colors, durations outside the tokens of `DESIGN.md`, images without size or alt text, heading order, a missing `lang`, and scripts that animate without reading the reduced motion setting.
- `node scripts/measure_page.mjs <url-or-file>` opens the page in a real browser at 360 and 1280 px and reports horizontal scroll, touch targets under 24 px, text contrast under the WCAG ratio, lines over 80 characters, clipped text and the number of font families in use. It needs Playwright in the project.
- The antislop skills cover wording and layout habits.

A finding from this layer carries its measurement: the element, the value and the limit.

## Layer 2. Compared with the owner's examples

`DESIGN.md` holds commented examples of what is right and what is wrong for this site, each with its reason. Before a structural change, show two versions and record which one the owner chose and why, in `DESIGN.md` under Examples or as a decision record. Those choices are then given to the model as examples.

Compare pairs. Never score from 1 to 10.

## Layer 3. Screenshots reviewed by a model that sees

Use a short list of questions, each tied to a decision:

- What does a first-time visitor understand in the first seconds?
- What is the main action, and what competes with it?
- Where does the eye go first, and is that the right place?

The answer is a hypothesis until layer 1, the owner or real use confirms it. A model that cannot read images takes no part in this layer. Before a local vision model gets this work, measure that it fits the graphics card.

## The judge test

A model reviews design only after it passes `design-judge`, a bench class of the standard: pairs of screens where the owner already chose, asked in both orders, counted as agreement only when the model picks the owner's choice both times. The owner's pairs live in `~/.standards/design-pairs/`. Without them the test runs on a made-up sample that never counts. Never state an agreement rate that was not measured.

## Conditions

- No overall design score.
- No finding without the measurement, the screenshot or the example behind it.
- No general taste rule above `DESIGN.md`.

## Taste and the working loop

This adapts the Taste Profile and the Express, Tailor, Amplify, Evolve cycle described in Loop, by Kipp Bodnar and Kieran Flanagan, to design work. It is an adaptation in our own words, not a validated method.

Record about the audience, in `DESIGN.md` under Audience evidence, each line marked as a fact, a stated preference or a guess:

1. Their state of mind and situation when they arrive.
2. The words they use for their need.
3. The examples, proof and formats that help them.
4. What makes them distrust or leave.
5. Their daily context: device, time and prior knowledge.
6. The sources and evidence they believe.

A preference has a scope. What fits a portfolio may not fit a practice tool. Never infer a personal trait or a universal preference from one choice in one project.

The cycle, as work:

| Step | What it produces |
| --- | --- |
| Express | The problem, the audience, the identity, the criteria and the decision to take |
| Tailor | An experience fitted to the situation, with one interaction that helps the task |
| Amplify | A proven pattern that can be reused without losing its context |
| Evolve | Evidence, corrections and a proposed change to the instructions |

After each iteration write what was decided, why, what was seen and what to adjust, in a decision record or with `memory.py`. A lesson keeps its context and evidence. A finding from one project, a preference of the owner and a general rule of the standard are three different things, and only the review flow of the standard turns the first into the third.

A simulated audience finds possible doubts and obstacles. Its remarks are hypotheses, not research with real people. Every evaluation says which decision it helps to take. Small tools on a page must produce something useful: calculate, compare, explore, select, practice or understand a change.
