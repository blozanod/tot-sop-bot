# What is still open

The perception layer is verified against the 12 calibration screenshots (61
passing assertions) and is no longer the bottleneck — a tick is ~41 ms, of which
~41 ms is waiting for and decoding a frame. What remains is knowledge, not code.

---

## 1. Two unverified state meanings

Everything else was observed directly. These two were inferred from the palette's
consistent semantics but never actually seen.

(The third open question from day one — whether green means a toggle is **on** —
is settled, and did not need a new frame. The buttons say so themselves: in every
calibration frame `BGM Disabled` is grey while green `Ride SFX`, `TV Room Sound`
and `Automatic Doors` carry no "Disabled", and `TVR1 Enabled` / `Elevator 1
Enabled` are green beside grey `TVR2 Disabled` / `Elevator 2 Disabled`.)

| Reading | Why it is a guess | How to settle it |
| --- | --- | --- |
| **`Load` in orange** | Load buttons were seen grey, white and green — never orange. It may not be a state that exists. | Any frame where a Load button is orange, or confirmation that it never happens. |
| **`Dispatch` in white** | Dispatch was seen grey, bright green and bright orange only. | Same. |

Neither blocks a run: an unmapped colour raises with the button name, so if one
of these is wrong you find out immediately rather than three hours in.

## 2. Does the Ruffle fix hold?

`docs/design-decisions.md` §28 lists what was changed to stop the orange error
screen: the emulator's execution-duration cap raised, its overlays disabled, the
bot no longer clicking blindly into a loading page, and audio muted.

**All of it is unverified** — the game still is not reachable from the machine
this was written on. If the error screen comes back:

```bash
python -m tools.probe_page
```

prints Ruffle's own error text when it appears. Send that and it becomes a fix
instead of a guess. `RuffleCrashed` carries the same text at runtime.

## 3. Game mechanics → [`docs/game-mechanics.md`](docs/game-mechanics.md)

Still the main thing standing between you and a good strategy. The frames settled
three questions on their own:

- **What locks the track** — a dispatched elevator. `Dispatch = bright orange` and
  `Track = Locked` always co-occur.
- **The two greens** — `#66cc33` is the ordinary palette; `#00ff00` and `#ff9900`
  belong to `Dispatch Elevator` alone.
- **Clock speed** — roughly one game-minute per real second, so a 12-hour run is
  about 12 real minutes.

The rest is yours. **Scoring (Q15) and capacities (Q5, Q10) matter most.** Note
that 21 shows up as both a TV room's capacity and an elevator's, which is why it
is the one number besides zero the bot bothers to read — if that turns out to be
wrong for elevators, say so and `tot/counters.py` needs a second target value.

## 4. TM Arcade access

`main.py` currently points at the Simulation Page, which only offers the Unlimited
game. For the timed, scored run I need:

- [ ] The **Arcade URL**.
- [ ] Whether it needs a **login**, or any click-through before the game loads.

> **Do not commit credentials.** Say a login is needed and I will wire it to
> environment variables.

The bot no longer needs a game-over screenshot: when the panel leaves the screen,
`refresh()` returns False and the run stops.

## 5. First live run

Nothing in this repo has touched the actual game. Before writing strategy:

```bash
python -m tools.verify_layout --live
```

Load the game, pick a mode, and it saves an annotated crop of the panel. Every
button should be boxed with the right state and every counter labelled `ZERO`,
`FULL` or `OTHER`. Then:

```bash
python -m tools.benchmark --live
```

for the tick rate on your machine. Nothing on screen should move, flicker or
resize while either of those runs — if anything does, say so, because that is a
bug and not a trade-off.

Remaining first-run risks:

1. **An unknown colour** — a state the screenshots never showed. It raises with
   the button name and the sampled hex, which is enough to add it.
2. **The canvas is scaled**, so buttons are not 75×36. This is now tested rather
   than hoped for: the end-to-end check ran against a canvas downscaled to 67%,
   where buttons measure 49×23, and the detector found all 32 of them, all 13
   counter boxes, and read the digits correctly.
