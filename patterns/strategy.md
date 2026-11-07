# Strategy

- Status: use
- Profiles: software, data-ai
- Family: behavioral

## Problem it solves

There are several interchangeable ways to do one job, chosen at run time, and the choice keeps growing. Examples are one parser per website, one path planner per robot mode, or one pricing rule per customer type.

## Use it when

Three or more variants share the same inputs and outputs, and new variants keep appearing.

## Do not use it when

There are two variants that rarely change. An if is clearer.

## Signs you do not need it yet

Only one variant exists, or every variant needs different inputs.

## Simpler alternative

Pass a function, or keep a dictionary from name to function. In most languages that is already the Strategy pattern without classes.

## How it looks when misused

A class hierarchy where plain functions would do. Strategies that reach into the caller's internals.

## Minimal example

```python
def parse_site_a(html: str) -> list[dict]:
    ...


def parse_site_b(html: str) -> list[dict]:
    ...


PARSERS = {"site-a": parse_site_a, "site-b": parse_site_b}


def parse(site: str, html: str) -> list[dict]:
    return PARSERS[site](html)
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free: https://refactoring.guru/design-patterns/strategy
