# Observer

- Status: use
- Profiles: web, software, hardware
- Family: behavioral

## Problem it solves

Several parts of the program must react when something changes, and the source should not need to know who they are.

## Use it when

One change has many consumers, such as a UI reacting to data or several modules reading the same sensor. Prefer the event system the platform already gives you: DOM events, EventTarget, ROS 2 topics, signals in a GUI toolkit.

## Do not use it when

There is exactly one consumer. A direct function call is easier to follow.

## Signs you do not need it yet

Only one subscriber exists, or the order of the reactions matters.

## Simpler alternative

Call the function directly. When a second consumer appears, use the platform's built-in events before writing your own.

## How it looks when misused

Chains of events that nobody can trace. Listeners that are never removed, which leaks memory. Events used to ask a question and wait for an answer.

## Minimal example

```js
const readings = new EventTarget();

export function publishTemperature(celsius) {
  readings.dispatchEvent(new CustomEvent("temperature", { detail: celsius }));
}

readings.addEventListener("temperature", (event) => {
  document.querySelector("#temperature").textContent = `${event.detail} °C`;
});
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free: https://refactoring.guru/design-patterns/observer
- Free: https://gameprogrammingpatterns.com/observer.html
