# Double buffer

- Status: use
- Profiles: hardware, software
- Family: data-oriented

## Problem it solves

A reader sees a half-written state, such as screen tearing or a sensor array read in the middle of an update.

## Use it when

One side writes a whole state while another side reads it: display frames, simulation steps, DMA (direct memory access) transfers.

## Do not use it when

Updates are small and atomic. A lock or a queue is simpler.

## Signs you do not need it yet

You have not observed torn or inconsistent reads.

## Simpler alternative

A queue, or a lock around a single buffer.

## How it looks when misused

Copying large buffers instead of swapping references. A swap that is not synchronized with the reader.

## Minimal example

```python
class DoubleBuffer:
    def __init__(self, size: int) -> None:
        self._front = [0.0] * size
        self._back = [0.0] * size

    def write(self, index: int, value: float) -> None:
        self._back[index] = value

    def swap(self) -> None:
        self._front, self._back = self._back, self._front

    def read(self) -> list[float]:
        return self._front
```

## References

- Book: Robert Nystrom, Game Programming Patterns. Genever Benning, 2014. Chapter Double Buffer.
- Free: the same chapter online. https://gameprogrammingpatterns.com/double-buffer.html
