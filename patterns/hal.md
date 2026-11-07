# Hardware abstraction layer (HAL)

- Status: use
- Profiles: hardware
- Family: embedded

## Problem it solves

Application logic calls chip registers or vendor libraries directly, so changing the board breaks everything and nothing can be tested on a computer.

## Use it when

Firmware may run on more than one board, or you want to test the logic on a computer with a fake board.

## Do not use it when

The prototype runs on one board and will be thrown away.

## Signs you do not need it yet

There is one board, no tests, and every hardware call already lives in one file.

## Simpler alternative

Put every hardware call in one file, such as board.c, behind plain functions.

## How it looks when misused

An abstraction over every register. A layer that copies the vendor API one to one and adds nothing.

## Minimal example

```c
/* board.h: the only header that knows which pins and peripherals exist. */
#include <stdbool.h>

float board_read_temperature_c(void);
void board_set_fan(bool on);

/* app.c: plain logic that a fake board.c can test on a computer. */
void app_tick(void) {
    board_set_fan(board_read_temperature_c() > 30.0f);
}
```

## References

- Original: Elecia White, Making Embedded Systems, 2nd edition. O'Reilly, 2024. https://www.oreilly.com/library/view/making-embedded-systems/9781098151539/
- Free, related: state machines that usually sit on top of a HAL. https://gameprogrammingpatterns.com/state.html
