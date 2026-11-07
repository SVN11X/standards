# Repository

- Status: use
- Profiles: software, data-ai
- Family: domain

## Problem it solves

Business logic is mixed with storage details (SQL, files, API calls), so it cannot be tested without a database, and changing storage means touching everything.

## Use it when

Domain logic must be tested without real storage, or storage is likely to change, for example from CSV files to a database.

## Do not use it when

The program is a small script or a simple create, read, update and delete app where the ORM already is the abstraction.

## Signs you do not need it yet

Storage is accessed in one place, and there is no logic worth testing apart from it.

## Simpler alternative

A module with load and save functions for each kind of data.

## How it looks when misused

A generic repository that re-exposes every query. One repository per table instead of one per aggregate (a group of data that changes together).

## Minimal example

```python
from typing import Protocol


class ReadingStore(Protocol):
    def save(self, reading: "Reading") -> None: ...
    def latest(self, sensor_id: str) -> "Reading | None": ...


class InMemoryReadingStore:
    def __init__(self) -> None:
        self._latest: dict[str, "Reading"] = {}

    def save(self, reading: "Reading") -> None:
        self._latest[reading.sensor_id] = reading

    def latest(self, sensor_id: str) -> "Reading | None":
        return self._latest.get(sensor_id)
```

## References

- Original: Martin Fowler, Patterns of Enterprise Application Architecture. Addison-Wesley, 2002. https://martinfowler.com/eaaCatalog/repository.html
- Free: Eric Evans, DDD Reference. https://www.domainlanguage.com/ddd/reference/
