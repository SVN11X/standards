# Adapter

- Status: use
- Profiles: software, data-ai
- Family: structural

## Problem it solves

An external source has a different shape from what your code expects, and that shape leaks everywhere.

## Use it when

You integrate a third-party API, data sources with different formats, or drivers with different interfaces, and you want the rest of the code to see one format.

## Do not use it when

You control both sides. Change one of them instead.

## Signs you do not need it yet

There is only one source and its format is already the one you want.

## Simpler alternative

One conversion function at the boundary, shown below.

## How it looks when misused

Adapters wrapping adapters. Adapting your own code instead of fixing it.

## Minimal example

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    sensor_id: str
    celsius: float


def from_vendor_payload(payload: dict) -> Reading:
    return Reading(sensor_id=payload["id"], celsius=(payload["tempF"] - 32) * 5 / 9)
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free: https://refactoring.guru/design-patterns/adapter
