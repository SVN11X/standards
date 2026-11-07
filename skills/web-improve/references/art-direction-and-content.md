# Art direction, UX and content

## Heuristic audit of an existing page

1. Within five seconds, is it clear what the site offers, for whom, and what to do next?
2. Does the main heading make a concrete promise without marketing jargon?
3. Does the layout separate blocks by purpose, or just repeat identical cards?
4. Is the menu consistent, usable with a keyboard and on mobile, and does it show where you are?
5. Does the interface show its states: loading, success, error, empty and sending?
6. Are contrast, visible focus, touch targets, typography and responsive scales right?
7. Do images support the message, or are they generic decoration?
8. Do scrolling and animation tell a story, or distract?
9. Do forms ask for the minimum useful information and explain privacy?
10. Does the content repeat ideas, use long paragraphs, or have vague calls to action?

## Visual decisions

- Document tokens for color, type, spacing, radii, shadows and states, and use them consistently.
- Keep one clear visual direction anchored in the brand and in `DESIGN.md`. Do not impose a dark, futuristic or trendy look on every project.
- Use a grid, consistent alignment and deliberate whitespace. Vary density with the story instead of repeating the same three-card grid.
- Check the layout at about 360, 390, 768, 1024 and 1440 px when the tools allow it.

## Demos with real value

A demo must answer a visitor's question, work, be usable with a keyboard and on mobile, not depend on a backend that does not exist, and say when it uses illustrative data. Examples:

- Automation: a before and after scenario with steps and clearly labeled simulated savings.
- Web development: a load or accessibility comparison with real measurements, or an illustrative example that does not pretend to be data.
- Custom software: an interactive flow from needs to an indicative proposal, without promising results.
- Processes: an interactive timeline with states, decisions and a useful output.

## Content

- Cut repetition. One idea per block.
- Specific headings, very short subheadings, useful calls to action.
- Show process, deliverables and real examples where there is evidence.
- Never invent client logos, testimonials, ratings, portfolio pieces, statistics or security badges.
- Less text must not mean ambiguous icons. Keep the information people need.

## Images and media

- Prefer real, licensed photos, real screenshots, accurate custom diagrams and useful mockups. Mark missing assets as provisional.
- Use AVIF or WebP where supported, responsive versions and explicit dimensions to avoid layout shift.
- Compress carefully. No pixelation or artifacts on important images.
- Video needs controls, captions when relevant and a light poster. No autoplay with sound.

## Motion and resilience

- `prefers-reduced-motion: reduce` turns off non-essential motion.
- Transitions must never block keyboard navigation or hide content.
- JavaScript enhances working HTML. The page degrades gracefully when scripts or animation are blocked.
- 3D and WebGPU need an accessible 2D fallback and resource control.
