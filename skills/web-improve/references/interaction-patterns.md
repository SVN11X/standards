# Interaction patterns

Six small patterns for buttons and microinteractions. Each one runs in the gallery at `gallery/index.html` of this skill, so it can be opened on a phone and read as working code. A small model may copy a pattern as it is written. It does not invent a new one.

## Rules for every pattern

- Use a link to navigate and a button to act. Never a `div` with a click handler.
- Describe the states that apply: rest, hover, focus, selected, running, success, error and disabled.
- The area that reacts stays in place while the element moves, so the control is always reachable.
- A hover effect has an equivalent on touch and on keyboard focus. Nothing depends on hover alone.
- Feedback follows the real result. "Copied" appears after the copy worked. An error leaves a way to recover.
- Touch targets are at least 24 by 24 CSS px, and 44 where space allows.
- Durations and easing come from the tokens in `DESIGN.md`. Do not add a second token system.
- With reduced motion the state still changes, at once and without travel.

## 1. Depth button

- Purpose: make a main action feel pressable.
- Events: pointer down, pointer up, Space and Enter.
- States: rest (raised over its shadow), hover and focus (slightly higher or outlined), active (moved down onto its shadow), disabled (flat).
- Keyboard and touch: the press shows on `:active` for both. Focus is visible.
- Reduced motion: the offset changes with no transition.
- Use it for one primary action per view. Many raised buttons compete with each other.

## 2. Segmented control with a sliding indicator

- Purpose: choose one of a few modes, such as Study, Practice and Review.
- Events: click, tap, arrow keys, Home and End.
- States: each option is rest, hover, focus or selected. The indicator sits behind the selected option.
- Behavior: the indicator takes the left position and the width of the selected option, measured from the element. It is measured again when the language changes, the fonts finish loading or the container resizes.
- Semantics: a `radiogroup` with `radio` options and one tab stop. Arrow keys move and select.
- State kept: the selected option survives a language change.
- Reduced motion: the indicator jumps to its place.
- Use it for two to five options that fit in one row at 320 px.

## 3. Action button with a result

- Purpose: run something that takes time and report it truthfully.
- Events: click or tap, then the end of the real operation.
- States: rest, running (disabled, with a progress label), success, error with a retry.
- Behavior: the button is disabled while it runs, so nothing is sent twice. Success and error are announced in a live region.
- Reduced motion: no spinner travel. The label alone changes.
- Use it for save, copy, send and any call that can fail.

## 4. Focus panel

- Purpose: show where the visitor is typing.
- Events: focus entering and leaving the fields of a panel.
- States: rest and focused within.
- Behavior: the panel outline or elevation changes with `:focus-within`. The field keeps its own visible focus.
- Reduced motion: the change is instant.
- Use it for forms with several groups.

## 5. Expanding content

- Purpose: open detail without leaving the page.
- Events: click, tap, Enter and Space on the summary.
- States: closed and open.
- Behavior: built on `details` and `summary`, so it works without JavaScript and is found by the browser's search. The height animates only where the browser supports it.
- Reduced motion: it opens at once.
- Use it for secondary detail. Never hide the main content of the page inside it.

## 6. Progress or achievement signal

- Purpose: confirm that a step is done.
- Events: an action that completed.
- States: before, done.
- Behavior: a short mark or a bar that fills, next to a text that says what was completed. The text is the message, the motion is the accent.
- Reduced motion: the final state shows with no animation.
- Use it after real progress. Never for an action that did nothing.
