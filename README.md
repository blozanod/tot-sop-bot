# Tower of Terror — SOP bot

A bot that plays the [Tower of Terror simulation](https://www.themagical.nl/content/plugins/flash-emulator/flash-player.php?game=tower-of-terror)
so that its behaviour can be turned into a standard operating procedure a person
can follow.

The bot is the instrument, not the product. It reads the RideControl panel the way
a player does — button colours, and whether a counter says 0 or 21 — and holds
**no strategy at all**. Every decision lives in `main.py`, hand-written, so each
branch maps to one instruction a human can carry out.

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Use

```bash
python main.py
```

It opens the page and then **waits**. You load the game and pick the mode; it
touches nothing. The moment the RideControl panel appears on screen the game has
begun, and it starts playing.

```python
from tot import Game

game = Game.launch()      # opens Chromium. Clicks nothing.
game.wait_for_panel()     # blocks while you pick a game mode

while game.refresh():                       # one screenshot per tick
    if game.tv_room1.preshow_ready:         # Start Preshow has turned orange
        game.tv_room1.start_preshow()
    for lift in game.elevators.values():
        if lift.can_dispatch and not game.track.is_locked:
            lift.dispatch()
```

Write your strategy in [`main.py`](main.py); it lists the full readable surface.

## How it works

| | |
| --- | --- |
| **Sees** | Playwright screenshots **only the RideControl panel** — about 930×290 px, an eighth of the canvas. No hardcoded coordinates: the panel is found from the pixels once, at startup, and that rectangle is what gets captured from then on. |
| **Classifies** | Eight exact flat fills. All 32 buttons are read in one vectorised majority vote over 288 probe pixels — 0.05 ms. |
| **Counts** | Only **0** and **21**. Every other value is `OTHER`, because every other value means the same thing: wait. Counters are read lazily, so a tick that only looks at colours never touches a digit. |
| **Acts** | Clicks and nothing else — no precondition checks, no waiting for animations. That is your job. |

### What it costs

Measured with `python -m tools.benchmark`:

| | |
| --- | --- |
| locate the panel, full canvas | 77 ms — **once**, at startup |
| screenshot the panel crop | ~19 ms — the browser's cost, not ours |
| read all 32 buttons | 0.05 ms |
| read one counter | 0.3 ms |
| **a whole tick** | **~21 ms → ~47 Hz** |

The screenshot is 90% of that and is entirely the browser's. See
[`docs/design-decisions.md`](docs/design-decisions.md) §21 for why the bot is
still in Python.

### One property, one observable

Nothing combines two readings. `elevator1.can_dispatch` is exactly "the Dispatch
button is bright green" — not "green *and* the doors are shut *and* the track is
clear". A compound property would hide the decision the written procedure is
supposed to make explicit.

```python
game.elevator1.dispatch_button   # DispatchState.ARMED
game.elevator1.can_dispatch      # True
game.track.is_locked             # False
game.tv_room1.waiting_is_full    # True  — the box reads 21
game.tv_room1.loaded             # Count.ZERO / Count.FULL / Count.OTHER
```

### The two numbers

A counter says one of three things, and never a number:

| | |
| --- | --- |
| `Count.ZERO` | the box reads `0` — nothing to move |
| `Count.FULL` | the box reads `21` — a full load |
| `Count.OTHER` | anything else, including a box it could not read |

`OTHER` is the safe direction: a glyph the reader is not confident about lands
there, and the bot waits instead of acting on a misread.

## Verify the calibration

```bash
python -m tools.verify_layout          # annotate the calibration frames
python -m tools.verify_layout --live   # annotate a frame from the running game
python -m tools.benchmark              # what perception costs on your machine
python -m pytest                       # 56 assertions against the screenshots
```

The test suite runs the whole stack against PNGs with no browser. That is what
makes the palette and geometry *verified* rather than guessed — the game was never
reachable from the machine this was written on.

If the panel is never found, run the probe and send me its output:

```bash
python -m tools.probe_page
```

## Docs

- [`docs/findings.md`](docs/findings.md) — the measured palette, geometry and state semantics
- [`docs/design-decisions.md`](docs/design-decisions.md) — the decisions and why, including the ones since reversed
- [`docs/game-mechanics.md`](docs/game-mechanics.md) — open questions only you can answer
- [`TODO.md`](TODO.md) — what is still unverified
