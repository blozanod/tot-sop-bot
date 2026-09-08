# Handoff checklist — what I need before I build

Everything below is blocking. Order roughly matters: **1 and 2 unblock the most.**

---

## 1. Screenshots → `assets/screenshots/`

Full spec, naming, and the situation-by-situation list: **[`assets/screenshots/README.md`](assets/screenshots/README.md)**

Short version:

- **PNG only.** JPEG smears exactly the colour boundaries I sample.
- **Browser zoom at 100%**, no resizing after capture.
- Whole-window captures are fine — I'll locate the canvas myself.
- Three folders: `layout/` (one clean master), `states/` (one frame per game
  situation), `digits/` (a spray of frames from one run).
- **More is strictly better.** Duplicates cost me nothing. A missing state means
  I ship a colour I have never seen and cannot verify.

The single highest-value one, if you only do a few: `states/23-track-blocked.png`.
Red `#ef0817` is the only value I have confirmed, so it's my anchor for
calibrating everything else.

## 2. Game mechanics prose → `docs/game-mechanics.md`

The file is a template with the specific questions I need answered. Prose is
fine, bullets are fine — no need to be tidy.

This is knowledge only you have. Without it my plain-English state descriptions
are guesses wearing the costume of documentation, which is worse than having
none. **Question 12 (the two greens) is the one I most need right.**

## 3. TM Arcade access

You picked the timed 12-hour scored game as the optimisation target, which lives
in the TM Arcade rather than the Simulation Page URL you gave me. I need:

- [ ] The **Arcade URL** for the game.
- [ ] Does it need an **account or login**? Any click-through before the game
      loads (cookie banner, age gate, "click to play" for the Flash emulator)?
- [ ] Does the timed mode show a **game-over screen** at 12 hours? A screenshot
      of it goes in `states/90-game-over.png`.

> **Do not commit credentials.** If a login is needed, say so here and I'll wire
> it to environment variables. Never put a password in this repo.

## 4. Environment details

- [ ] **OS and version** on the machine that will run the bot.
- [ ] **Python version** (`python3 -V`).
- [ ] **Canvas pixel size**, if you can get it. In the browser devtools console:
      `document.querySelector('canvas').getBoundingClientRect()`.
      If the canvas is inside an iframe, tell me — it changes how I attach.

---

## Then I build

Once 1–4 land I write the whole stack in one pass:

- Playwright + Chromium backend, fixture (PNG) backend, and the desktop fallback
- Colour palette sampled from your real pixels, not guessed
- Coordinate table + `verify_layout.py` overlay so you can eyeball every probe
  point in a single image
- Digit template matching for all the counters, clock and score
- `Elevator` ×3, `TVRoom` ×2, `RideControl`, `Track` classes — strict 1:1
  properties, enum + bool on every button
- JSONL run trace with plain-English glosses
- Fixture tests asserting real readings against your PNGs
- A bare `main.py` skeleton — **the strategy stays yours**

Design rationale for all 20 decisions: [`docs/design-decisions.md`](docs/design-decisions.md)
