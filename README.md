# Tower of Terror — SOP bot

A bot that plays the [Tower of Terror simulation](https://www.themagical.nl/content/plugins/flash-emulator/flash-player.php?game=tower-of-terror)
well, so that its behaviour can be translated into a standard operating procedure
a person can follow.

The bot is the instrument, not the product. It reads the RideControl panel the
same way a player does — button colours and counter digits — and every decision
it makes lives in `main.py`, hand-written, so each line maps to one human step.

## Status

**Awaiting calibration assets.** Design is settled; nothing is built yet.

- **What's needed:** [`TODO.md`](TODO.md)
- **Screenshot spec:** [`assets/screenshots/README.md`](assets/screenshots/README.md)
- **Mechanics questionnaire:** [`docs/game-mechanics.md`](docs/game-mechanics.md)
- **Why it's designed this way:** [`docs/design-decisions.md`](docs/design-decisions.md)

## Intended shape

```python
game.refresh()

for e in game.elevators:
    if e.can_dispatch and not game.track.is_locked:
        e.dispatch()

if game.tv_room1.waiting >= 21:
    game.tv_room1.load()
    game.wait_until(lambda: game.tv_room1.entrance_is_closed, timeout=30)
    game.tv_room1.start_preshow()
```

Every property reads exactly one thing off the screen. Every branch is yours.
