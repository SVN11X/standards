# Learning experiences

Patterns for sites that teach: study notes, exam preparation, explainers, documentation people read in short sessions. Pick the ones the goals in `docs/goals.md` need. None of them is required, and no profile imposes 3D, a framework, an account or animation.

## Start with why it matters

- Open every lesson or section with one or two plain sentences: what problem this solves and when the reader will need it. Then the detail.
- Reveal depth in steps: a summary first, then "how it works", then edge cases, each one opened by the reader.
- Keep each block to one idea, and give each block a heading the reader can scan.
- Keep technical terms in their original language when the owner asks for it (for example Google Cloud product names), and explain them on first use in the content language.

## Remember the reader, without an account

- Store preferences and progress in `localStorage` under one versioned key (`site:v1`), read inside `try` with a default, so a full or blocked storage never breaks the page.
- Profile fields worth keeping: language, theme (light, dark or system), level, reduced motion, text size, favorites, history, progress and the last position.
- Offer export and import of that state as a JSON file. Sync between devices needs a backend and the owner's go-ahead.
- Show "continue where you left off" and a list of recently seen items on the start page.

## Bookmarks, highlights and notes

- Give every paragraph and question a stable id that does not depend on its position, for example a short hash of the original text stored in the content file. Links use `#id`.
- Store highlights as the block id plus the start and end of the text, and check them again when the content changes. When the text moved, show the note as detached instead of losing it.
- A copy-link button on each heading and block lets the reader share the exact fragment.

## Interaction that explains

- Hotspots on a diagram, a board or a 3D model open a side panel with what the part is, why it matters and a link to the lesson. Every hotspot is also reachable from a plain list, for keyboards and screen readers.
- Tabs for "concept, example, code" keep long pages short. The active tab is in the URL.
- Code examples that run in the page show their output next to them and reset to the original.
- 3D only when space is the subject (a board, a mechanism). Load it on demand with a still image first, and keep the page usable without WebGL.

## Buttons and feedback

- Every control has hover, focus-visible, pressed, disabled and loading states. Focus is always visible.
- Answer each action in under 100 ms with a visible change. Use motion of 150 to 250 ms for state changes, and nothing at all under `prefers-reduced-motion: reduce`.
- Touch targets of at least 24 by 24 CSS pixels (WCAG 2.2, target size minimum), 44 or more for primary actions.

## Measure before keeping it

Check each pattern with the goals: Core Web Vitals on a mid-range phone, the size of the JavaScript added, keyboard and screen reader use, and the regression tests in `regression-testing.md`. Drop a pattern that costs more than it teaches.

Sources: WCAG 2.2 (https://www.w3.org/TR/WCAG22/), MDN on prefers-reduced-motion (https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion), web.dev on Core Web Vitals (https://web.dev/articles/vitals).
