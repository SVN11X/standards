# Web sub-profiles

A sub-profile is the kind of experience that leads a site. There are five, plus `standard` for a site that needs none. The owner's choice lives in `.standard.yml` as the `experience` option, and its binding rules arrive in `AGENTS.md`. This file is the full guide. A short summary of each one, sized for a small local model, is in `profiles/web/subprofiles.yml` of the standard.

## Choose one

1. An explicit choice by the owner wins: the `experience` option, or what they ask for in the request.
2. Without one, look at the main task, the content, the audience, the identity in `DESIGN.md` and the technical limits. Then match:

| The page mainly | Sub-profile | The owner called it |
| --- | --- | --- |
| explains a transformation or a process in stages | `scroll-storytelling` | web/scroll-narrativo |
| lets the visitor see how a variable changes a result | `interactive-data` | web/datos-interactivos |
| lets the visitor handle a volume, or shows a live signal | `reactive-object` | web/objeto-reactivo |
| presents projects, an identity or a visual narrative | `editorial` | web/editorial |
| accompanies a task with an expressive figure | `characters` | web/personajes |

3. `python <standard>/scripts/standard.py subprofile "<the request>" --repo .` applies steps 1 and 2 with keywords and prints the summary to load. When it answers that it is unsure, decide from the table, say why in one line and continue with work that can be checked.

One sub-profile leads. It may borrow the shared patterns in `interaction-patterns.md` and one interaction from another sub-profile when that helps the task. Keep one coherent composition and a technical load in proportion to the page.

A structural redesign shows two short compositions with real content when exploring could change the solution. The owner's choice and its reason go into `DESIGN.md` under Examples. A small change goes straight to its component.

A chosen sub-profile is the owner's recorded reason for the scroll-driven animation, 3D or illustration it needs. Anything beyond it still needs a reason in `docs/decisions/`.

## scroll-storytelling

The mechanism: fragments that answer the pointer and come together as the page scrolls until they fill the screen.

- Design by scenes. Each scene has a start, middle states, an end, and works forward and back.
- Decide per scene whether motion follows the scroll position or plays once when the section enters. Progress that the reader controls fits an assembly or an exploded view. A one-time entry fits a title.
- Sticky elements, masks, scale changes and transitions are tied to the route, never to a timer.
- A long sequence gives direct access to each stage and to the result, with links or buttons.
- With reduced motion the stages appear as still steps in order.

Case: explaining a device. The case separates, the board appears and one connection is highlighted. Controls assemble and separate it directly.

## interactive-data

The mechanism: the visitor enters data and charts change in answer.

- Controls for parameters, comparisons and sliders. Charts whose values can be read exactly.
- Every value keeps its unit, its label and a meaning that can be checked.
- The calculation is a function apart from the animation, with its own tests. The chart only draws it.
- Sample data and simulations are labeled as such. A figure of confidence, prediction or precision needs a method that justifies it.
- Offer a reset. Test minimum, maximum and repeated changes.

Case: change the data volume and the bandwidth and read the estimated transfer time, with the conditions of the calculation written next to it.

## reactive-object

The mechanism: an object that changes with the state of a tool and with a signal such as the microphone level.

- The object answers the pointer, touch, drag, progress, selection or a real signal.
- Name its states, for example idle, listening, working, answering and error. Every visual change belongs to one state.
- Say why DOM, CSS, SVG, Canvas or Three.js. Choose the lightest one that does the job.
- The controls work without the object. Show a still image when WebGL or the main asset is missing.
- Ask for the microphone only when the visitor starts the action that needs it.

Case: an electronic part the visitor rotates and selects to read its connections.

Regression that every reactive object passes: with reduced motion and no task running, the object stays still while the pointer moves. Check the animation engine, not only the style sheet.

## editorial

The mechanism: a studio page with expressive typography, images that reveal and coordinated entries.

- Typographic composition, hierarchy and reading rhythm carry the page.
- The real content sets the size and structure of each section. Never design around filler text.
- Text revealed by lines or words is read once by a screen reader. Hide duplicated visual layers from it.
- Plan for line breaks that change with the language, late fonts and the screen width.

Case: a portfolio where the visitor explores a project, its images and the way into its detail.

## characters

The mechanism: characters whose expression answers typing, the pointer and the states of a conversation.

- A character looks at, points to or reacts to what happens.
- Name the event behind each reaction.
- The character never gates the task. Every action and every piece of information is also in controls and text.
- Reactions are short and stop with reduced motion.

Case: a tutor that points at one part of a diagram when the student asks for a hint and reacts briefly when the exercise is done.

## References are mechanisms

The examples behind these sub-profiles (the owner named them Joiner, Horizon, Murmur, Lumenis and Parlor) are references for a mechanism and a direction. Take the pattern that helps the project and keep its own identity. Never copy a brand, an image or code without checking where it comes from and its terms. A reference built with React does not mean the project moves to React.

When improving an existing site, isolate new styles and effects: check global resets, selectors, stacking, positioning, listeners and changes to scrolling. Keep the existing images and content.

## Without Figma or a given MCP

Everything here works from `DESIGN.md`, this guide and the gallery. Figma, Storybook and browser MCP servers add reach when the project already has them. Their absence never blocks the work.
