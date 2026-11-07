# Interactive explanations that teach

## Choose the representation

| Need | Representation and controls |
|------|-----------------------------|
| Explain a sequence | Numbered stages, previous and next, a summary of what changed. |
| Explore a parameter | A labeled slider with units, the current value, and a stable reference. |
| Compare methods | Aligned views with the same scale and scenario, differences marked. |
| Understand a graph | Named nodes, edges with meaning, selecting a node shows its detail. |
| Understand a map or grid | Legend, resolution and scale, selecting a cell, point or layer. |
| Understand coordinates | Origins, axes and the direction of each transformation. The same object seen in several frames. |
| Explore time | Play and pause, step forward, a time indicator and reset. |

## Build the scene

1. Write one sentence: "When you change X, watch Y to understand Z."
2. Pick an initial state that already shows the phenomenon without extra input.
3. Name the value each control changes and where its result appears.
4. Define what every line, arrow, color and symbol means. Put the legend next to the scene.
5. Add a short explanation of the current stage or selection. Show values with justified precision and units.
6. Check that the interaction answers the question from step 1.

For each component, decide before coding:

| Element | Required result |
|---------|-----------------|
| Goal | A question or idea the visitor can understand by exploring. |
| Action | Controls with concrete labels and a meaningful initial state. |
| Result | A visible change, with values or an explanation when they help. |
| Comparison | A stable reference: before and after, estimated and measured, or two scenarios. |
| Reading | Legend, units and labels next to what they describe. |
| Recovery | Reset, and run controls when the process unfolds over time. |

Keep one main relationship per scene. Reveal advanced detail progressively. Use stages when a process needs explaining: initial state, new evidence, calculation, result, and show what changed at each stage and why.

## Patterns to fix

- A slider that only changes a number: connect it to the object or result that the number represents.
- A "Correct" button without evidence: keep the previous state and explain which calculation produced the new one.
- Continuous animation that is hard to follow: add steps and a pause, and show fewer things at once.
- Several similar curves: label them directly, vary the line style, keep a stable legend.
- A map without resolution: show cell size, scale and what unknown, free and occupied mean.
- A comparison diagram without a conclusion: state the question, what is compared and what it shows.
- Text that depends on hover: offer selection, focus or visible content on touch screens.
- A partial reset: restore controls, time, selection, model state and explanation together.

## Geometry and interaction

- Convert event coordinates to scene coordinates with the real transformation. Do not assume CSS pixels equal SVG units. Test scaling, offsets and resizing.
- Use Pointer Events where they fit, and handle capture, cancel and release so a drag never leaves a control stuck.
- Keep model coordinates, physical frames and screen coordinates apart. Document when the vertical axis is flipped on screen.
- Keep physical limits, or state the abstraction explicitly. In a simulation, apply the scenario's constraints even when a sensor would not detect an obstacle.
- Stop processes, clear timers and remove listeners when a component unmounts, so repeated visits do not start several loops.
- Support keyboard and touch as well as the mouse. Keep a text explanation for figures that are not accessible on their own.
- Provide a static figure and a text fallback when JavaScript fails. Prefer SVG when labels and accessibility matter, and give Canvas a text alternative.

## Technical and scientific content

These rules come from explaining control systems, sensors and maps, and apply to any technical field.

- Separate the physical scene from the measurements of it. Show the limits of the measurement (range, resolution, occlusion) without inventing probabilities or behavior that the source does not document.
- Convert units visibly when two forms appear, for example a period and a frequency (f = 1/T): 30 Hz is about 33.3 ms per update.
- Derive the role of each parameter from the equation the project implements. Names alone (for example the gains of a PID controller) do not tell what a parameter does in that implementation.
- Name the conventions the field uses and link the primary source. In robotics, for example, REP 103 (units and axes) and REP 105 (coordinate frames for mobile platforms).
- Compose transformations with the right operation (rigid transforms, matrices), not by adding positions, unless the example is explicitly one-dimensional.
- For percentages, say what is measured and over what total. For comparisons with other studies, name the method, conditions and metrics, and do not transfer another study's results to this project.
- Verify every claim against the project's code, configuration or primary sources before stating it.
