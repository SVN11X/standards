# Layout and use of space

Judge space with measurements and documented rules. Too much empty space and a wall of content are both findings, and each finding names the rule it breaks.

## Measure first

When you can run a browser (for example Playwright), capture the page at 360, 768, 1280 and 1920 px wide and record:

- Characters per line in the main text.
- How much of the first screen, before scrolling, shows what the page is for and its main action.
- The width of the empty side margins at 1280 and 1920 px.
- How many screens a visitor scrolls to finish the main task.

Without a browser, read the CSS: container `max-width`, grids, breakpoints, font size and line height. Say that the visual check is still pending.

## Rules and sources

| Rule | Source |
|------|--------|
| Lines of body text between about 50 and 75 characters. Shorter lines break the reading rhythm, longer ones make it hard to find the next line. | Baymard Institute, line length and readability: https://baymard.com/blog/line-length-readability |
| Text blocks no wider than 80 characters. | WCAG 2.2, success criterion 1.4.8 Visual Presentation: https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation.html |
| At 320 px wide, no horizontal scrolling and no lost content. | WCAG 2.2, success criterion 1.4.10 Reflow: https://www.w3.org/WAI/WCAG22/Understanding/reflow.html |
| Visitors spend most of their viewing time on the first screen and the next one. The purpose and the main action belong there. | Nielsen Norman Group, scrolling and attention: https://www.nngroup.com/articles/scrolling-and-attention/ |
| People scan in patterns such as the F pattern. Headings, the first words of lines and the left edge carry the most weight. | Nielsen Norman Group, F-shaped pattern: https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/ |
| Related elements sit closer to each other than to unrelated ones. Space groups, it is not filler. | Nielsen Norman Group, proximity principle: https://www.nngroup.com/articles/gestalt-proximity/ |
| Show the essential first and reveal advanced options on demand. | Nielsen Norman Group, progressive disclosure: https://www.nngroup.com/articles/progressive-disclosure/ |
| Layouts adapt by window width class, and wide windows can show two panes side by side, such as input and result. | Material Design 3, window size classes: https://m3.material.io/foundations/layout/applying-layout/window-size-classes |

## How to apply them

- Prose keeps a readable width (about `max-width: 70ch`) at every screen size. Extra width on large screens is not a reason to stretch text.
- A tool page, where the visitor gives an input and gets a result, can use a wide screen for two panes: input and settings on one side, the result on the other. On narrow screens the panes stack in task order.
- A single tall column on a 1920 px screen is a finding only when it forces scrolling to reach the main action or result, or leaves the result far from the input. Empty margins alone are not a problem.
- Spacing comes from one scale (for example multiples of 4 or 8 px). Larger gaps separate sections, smaller gaps join related items.
- Do not fill space for its own sake. Every proposed change says which rule it satisfies and what measurement improves.
