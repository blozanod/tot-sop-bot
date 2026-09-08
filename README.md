# Tower of Terror — SOP bot

A bot that plays the [Tower of Terror simulation](https://www.themagical.nl/content/plugins/flash-emulator/flash-player.php?game=tower-of-terror)
so that its behaviour can be turned into a standard operating procedure a person
can follow.

The bot is the instrument, not the product. It reads the RideControl panel the way
a player does — button colours and counter digits — and holds **no strategy at
all**. Every decision lives in `main.py`, hand-written, so each branch maps to one
instruction a human can carry out.

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Use

```python
from tot import Game

game = Game.launch()          # opens Chromium, attaches to the game canvas
game.refresh()                # one screenshot; every property reads that frame

if game.tv_room1.preshow_ready:            # Start Preshow has turned orange
    game.tv_room1.start_preshow()

for lift in game.elevators.values():
    if lift.can_dispatch and not game.track.is_locked:
        lift.dispatch()

game.wait_until(lambda: game.tv_room1.unload_ready, timeout=60)
```

Write your strategy in [`main.py`](main.py); it lists the full readable surface.

## How it works

| | |
| --- | --- |
| **Sees** | Playwright screenshots the game canvas. No hardcoded coordinates — the button grid is detected from the pixels, so canvas size, browser zoom and letterboxing are irrelevant. |
| **Classifies** | Eight exact flat fills measured from the calibration screenshots. An unrecognised colour raises rather than guessing. |
| **Counts** | One pixel font covers every number on screen. Digits are matched by normalised grayscale correlation with a confidence floor; a low-confidence read raises. |
| **Acts** | Clicks and nothing else — no precondition checks, no waiting for animations. That is your job. |
| **Records** | JSONL trace of every action with the state it was taken in, plus an event whenever anything on the panel changes. |

### One property, one observable

Nothing combines two readings. `elevator1.can_dispatch` is exactly "the Dispatch
button is bright green" — not "green *and* the doors are shut *and* the track is
clear". A compound property would hide the decision the written procedure is
supposed to make explicit.

Every button exposes both a meaning-enum and a boolean alias:

```python
game.elevator1.dispatch_button   # DispatchState.ARMED
game.elevator1.can_dispatch      # True
game.track.is_locked             # False
```

### The trace is the draft procedure

```
0.42  elevator1.doors     CLOSED -> MOVING
0.42  elevator1.load      READY -> LOADING
0.43  elevator1.loaded    0 -> 3
0.47  elevator1.dispatch  UNAVAILABLE -> ARMED
0.48  ACTION Dispatch Elevator while ARMED (cue age 0.025s)
      :: Dispatch is bright green — the elevator can be sent now
0.55  control.track       READY -> LOCKED
```

`cue_age_s` is how long a button sat in its state before being pressed — the
number that says whether a step is humanly achievable. The game runs at roughly
one game-minute per real second, so this matters.

## Verify the calibration

```bash
python -m tools.verify_layout          # annotate the calibration frames
python -m tools.verify_layout --live   # annotate a frame from the running game
python -m pytest                       # 44 assertions against the screenshots
```

The test suite runs the whole stack against PNGs with no browser. That is what
makes the palette and geometry *verified* rather than guessed — the game was never
reachable from the machine this was written on.

## Docs

- [`docs/findings.md`](docs/findings.md) — the measured palette, geometry and state semantics
- [`docs/design-decisions.md`](docs/design-decisions.md) — 20 decisions and why
- [`docs/game-mechanics.md`](docs/game-mechanics.md) — open questions only you can answer
- [`TODO.md`](TODO.md) — what is still unverified
