# What is still open

The bot is built and its perception layer is verified against the 12 calibration
screenshots (44 passing assertions). What remains is knowledge, not code.

---

## 1. Three unverified state meanings

Everything else was observed directly. These three were inferred from the palette's
consistent semantics but never actually seen, so the bot **flags them in the trace**
the first time it reads one (`kind: "inferred_state"`).

| Reading | Why it is a guess | How to settle it |
| --- | --- | --- |
| A toggle being **on** | All six RideControl toggles were only ever seen in one state each. Grey-is-off is anchored by the BGM button reading "BGM Disabled" while grey; green-is-on follows but was never watched flip. | One frame with Daytime, Show Fullscreen and BGM on, and Automatic Doors, Ride SFX and TV Room Sound off. |
| **`Load` in orange** | Load buttons were seen grey, white and green — never orange. It may not be a state that exists. | Any frame where a Load button is orange, or confirmation that it never happens. |
| **`Dispatch` in white** | Dispatch was seen grey, bright green and bright orange only. | Same. |

None of these block a run. If one turns out wrong, the trace shows exactly where
it was read.

## 2. Game mechanics → [`docs/game-mechanics.md`](docs/game-mechanics.md)

Still unanswered, and now the main thing standing between you and a good strategy.
The frames settled three of the 21 questions on their own:

- **What locks the track** — a dispatched elevator. `Dispatch = bright orange` and
  `Track = Locked` always co-occur.
- **The two greens** — `#66cc33` is the ordinary palette; `#00ff00` and `#ff9900`
  belong to `Dispatch Elevator` alone.
- **Clock speed** — roughly one game-minute per real second, so a 12-hour run is
  about 12 real minutes.

The rest is yours. **Scoring (Q15) and capacities (Q5, Q10) matter most** — strategy
is guesswork until we know what earns points.

## 3. TM Arcade access

`main.py` currently points at the Simulation Page, which only offers the Unlimited
game. For the timed, scored run I need:

- [ ] The **Arcade URL**.
- [ ] Whether it needs a **login**, or any click-through before the game loads.
- [ ] A screenshot of the **game-over screen**, if the timed mode has one.

> **Do not commit credentials.** Say a login is needed and I will wire it to
> environment variables.

## 4. First live run

Nothing in this repo has touched the actual game — I could not reach it from the
build environment. Before writing strategy, run:

```bash
python -m tools.verify_layout --live
```

and look at the output image. Every button should be boxed with the right state and
every counter with the right number. If the panel is not found, send me the frame
it grabbed and I will adjust the detector.

The most likely first-run problems, in order:

1. **Playwright cannot find the canvas** — the emulator may nest it in an iframe or
   need a click to start. `PlaywrightBackend` searches every frame and clicks once,
   but this is the one part I could not test.
2. **The canvas is scaled**, so buttons are not 75×36. The detector keys off the
   modal button size rather than absolute pixels, so this *should* just work.
3. **An unknown colour** — a state the screenshots never showed. It raises with the
   sampled hex and the nearest palette entry, which is enough to add it.
