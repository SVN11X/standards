# State

- Status: use
- Profiles: web, software, hardware
- Family: behavioral

## Problem it solves

Behavior depends on a mode, and the code fills with conditionals on status flags. Nothing stops an invalid jump, such as going from "idle" straight to "done".

## Use it when

There are three or more modes with different behavior and rules about which transitions are allowed. Typical cases are robot modes, multi-step forms, connection lifecycles and device power states.

## Do not use it when

There are only two modes that differ in one place. A boolean and an if are clearer.

## Signs you do not need it yet

The modes share all their behavior, or any mode can go to any other.

## Simpler alternative

An enum plus a table of allowed transitions, shown below. Move to one class per state only when each state has a lot of its own behavior.

## How it looks when misused

One class per state where every method is one line. Transitions hidden inside unrelated code. States that call each other's internals.

## Minimal example

```python
from enum import Enum


class Mode(Enum):
    IDLE = "idle"
    NAVIGATING = "navigating"
    STOPPED = "stopped"


ALLOWED = {
    Mode.IDLE: {Mode.NAVIGATING},
    Mode.NAVIGATING: {Mode.STOPPED, Mode.IDLE},
    Mode.STOPPED: {Mode.IDLE},
}


def transition(current: Mode, target: Mode) -> Mode:
    if target not in ALLOWED[current]:
        raise ValueError(f"{current.value} to {target.value} is not allowed")
    return target
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free: https://refactoring.guru/design-patterns/state
- Free: https://gameprogrammingpatterns.com/state.html
