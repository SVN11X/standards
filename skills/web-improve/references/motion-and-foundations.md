# Motion and foundations

Effects, gradients, 3D and animation that the owner asked for are not refused by a general taste rule. They need a purpose, they fit the identity in `DESIGN.md`, and they pass the checks below.

## Motion that holds up

- Honor `prefers-reduced-motion` in CSS and in JavaScript: loops with `requestAnimationFrame`, rotation, parallax, pointer tracking and programmatic scroll stop too. Read the setting with `matchMedia` and listen for its change.
- Content and actions make sense with no animation at all.
- Pause continuous work when the scene is off screen or the document is hidden, unless the active function needs it.
- Clean up listeners, observers, timers, animation frames and GPU resources when a component unmounts or restarts. In React, expect StrictMode to mount twice.
- Handle resize, orientation change, late fonts and the back button.
- Reserve the space of images and objects so nothing jumps.
- Animate `transform` and `opacity` first. Measure a costly effect in its real page before keeping it.
- Load heavy assets when they are needed and check their weight on a phone.
- Failures of images, data, permissions or WebGL show a state the visitor can recover from.
- During a scroll scene the page still scrolls the way the visitor expects.
- Everything works with a coarse pointer and without hover.
- Ask for the microphone or audio only after the visitor's action that needs it.
- Write a resource budget for the project and state the conditions of every measurement. A lab result is not a promise for every phone.

## Foundations

- Tokens. `DESIGN.md` names the spacing scale, type sizes, radii, durations and easing. Components and patterns use those names.
- Native CSS first. View Transitions, container queries, `clamp()` for fluid type and `oklch` colors cover most needs. Add an animation library when the native option cannot do the interaction, and keep one owner for each animated property.
- Fonts. Set `font-display`, preload the font used above the fold, prefer a variable font over several files, and give the fallback similar metrics so the text does not shift.
- Empty and loading states. Design how they look, what they say and which action they offer.
- First visit. A person with no context understands what the page offers and what to do within the first screen.

## Tools, when the project calls for them

Check the radar of the standard before adding any of these, and the current license and terms before adopting one.

- CSS and SVG for buttons, illustrations and characters that fit them.
- Motion for React or GSAP with ScrollTrigger when the stack and the interaction justify a library.
- Three.js when handling a 3D scene gives information or function, with an accessible alternative. glTF Transform to inspect and shrink imported models. A procedural shape and an imported model need different decisions.
- Apache ECharts for interactive data, importing only the parts used.
- Storybook when the project already has it or the component catalog pays for its upkeep.
- Figma through its official MCP server only when the design is reachable on the plan at hand. It is never required.
- Playwright MCP explores a page while working. Playwright Test is the check that stays in the repository. axe-core adds automatic accessibility checks, and a keyboard walk completes them.
- Chrome DevTools MCP on demand, to trace a scene that stutters. Emulation is not a measurement on a real device.

## Site performance budget

The profile fixes two numbers taken from web.dev: the critical path under 170 KB compressed and minified, and interactive in under 5 s on a Moto G4 class phone over slow 3G. Core Web Vitals thresholds stay as in the profile. Write the budget in `docs/decisions/`, split it per page type if the content differs, and state the device and network of each measurement. A page that breaks the budget is named in the report with its measured size and time. Source: https://web.dev/articles/performance-budgets-101

## Chart palette for color blindness

Use the Okabe-Ito palette for series and categories. Take the colors in this order, so neighbors differ the most.

| Color | Hex | Contrast on white | Contrast on #121212 |
| --- | --- | --- | --- |
| Orange | #E69F00 | 2.25 | 8.32 |
| Sky blue | #56B4E9 | 2.31 | 8.12 |
| Bluish green | #009E73 | 3.42 | 5.48 |
| Yellow | #F0E442 | 1.32 | 14.17 |
| Blue | #0072B2 | 5.19 | 3.61 |
| Vermillion | #D55E00 | 3.87 | 4.84 |
| Reddish purple | #CC79A7 | 3.06 | 6.12 |
| Black | #000000 | 21.00 | 1.12 |

The ratios are computed here with the WCAG relative luminance formula. They are not part of the source.

- Color is never the only signal. Each series also has a direct label, a line style or a marker shape (WCAG 1.4.1).
- Marks need 3:1 against their background (WCAG 1.4.11). On white, orange, sky blue and yellow fail, so give them a 1 px dark outline or use a dark background. In dark theme use white in place of black.
- Use no more than five series in one chart. Beyond that, split the chart or highlight one series.
- Check: view the chart in grayscale and confirm every series is still told apart by its label or marker.
- Sources: Okabe and Ito, Color Universal Design (https://jfly.uni-koeln.de/color/) and the hex values at https://siegal.bio.nyu.edu/color-palette/.
