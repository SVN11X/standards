# Singleton

- Status: avoid unless justified
- Profiles: software
- Family: creational

## Problem it solves

It promises exactly one instance of a class with global access to it.

## Use it when

Almost never. The rare valid case is a resource that physically exists once and whose API must enforce it, such as one hardware peripheral. Even then, create it once and pass it along.

## Do not use it when

For configuration, loggers, database connections or caches. These are the common cases, and all of them are better passed as parameters.

## Signs you do not need it yet

You want it because passing the object around feels tedious. That is a design signal, not a reason for global state.

## Simpler alternative

Create one instance at startup and pass it to whatever needs it.

## How it looks when misused

Tests that fail depending on their order. Code that reads a global instead of receiving what it needs. Hidden initialization order bugs.

## Minimal example

```python
def main() -> None:
    config = load_config()
    store = SqliteReadingStore(config.database_path)
    run_server(config, store)
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free, with the case against it: https://gameprogrammingpatterns.com/singleton.html
- Free: https://refactoring.guru/design-patterns/singleton
