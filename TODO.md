# Handoff checklist

**Status:** 12 screenshots received and fully mined — see
[`docs/findings.md`](docs/findings.md). Palette, geometry and colour semantics are
all settled and measured. What's left is small and specific.

---

## 1. Six more screenshots

Same rules as before: **PNG, 100% zoom, no resizing.** Drop them anywhere in
`assets/screenshots/` — I'll file and rename them.

Your 12 frames ran the whole session with **only TV Room 1 and Elevator 1 in
service**, so TV Room 2 and Elevators 2 and 3 are gray in every frame. Everything
below is a gap that leaves a real state unverified.

### Blocking — I'd be guessing without these

- [ ] **`busy` — all five units in service at once.** TV Room 2 enabled, Elevators 2
      and 3 enabled, ideally each doing something different. One frame covers 20 of
      the gaps. It also checks the assumption my whole naming scheme rests on: that
      unit 2 and 3 render identically to unit 1. If they don't, my grid labelling is
      wrong and I need to know now.
- [ ] **`toggles-flipped` — the six RideControl toggles in their opposite states.**
      Daytime, Show Fullscreen and BGM on; Automatic Doors, Ride SFX and TV Room
      Sound off. I've only ever seen each of those six in *one* state, so I can't
      currently tell "on" from "off" for any of them.

### Wanted — states I suspect exist but have never seen

- [ ] **Entrance door fully open** (I have closed and moving, never open).
- [ ] **Exit door moving** (I have closed and open, never moving).
- [ ] **`Load TV Room` or `Load Elevator` in orange**, if either ever goes orange.
- [ ] **Anything jammed or unusual** — a stuck state, an error, a full queue with
      guests leaving. Unknown colours make the bot raise, so a surprise state found
      now is far cheaper than one found mid-run.

### Digits — three glyphs, and they're nearly free

All ten digits are confirmed in the small counter font. The large HUD font
(`Current Time`, `Your score`) is a *different face*, and I'm missing **6, 7 and 9**.

- [ ] Two or three full-window frames where the clock minute or the score contains
      a 6, 7 or 9 — e.g. `10:16`, `10:27`, `10:59`, or any score like `96`.

**Must be full-window frames, not panel crops** — the HUD sits outside the panel, so
none of the nine crops contain it.

> You said I only need `0` and `21`. That's true for the TV room Waiting/Loaded
> boxes, but `Visitor Counter` already reached 84 in your own frames, `Front Waiting`
> ranged 16–21, and the score passed 211 in 44 game-minutes. The clock alone walks
> through every digit on its way from 10:00 to 22:00. If I can't read those, I can't
> read the score — and the score is how we compare strategies.

## 2. Game mechanics prose → [`docs/game-mechanics.md`](docs/game-mechanics.md)

Still needed. Three of the 21 questions are now answered by the frames themselves
(what blocks the track, what the two greens mean, roughly how fast the clock runs) —
I've noted those in the file. The rest is knowledge only you have.

Highest value now that the colours are settled: **scoring** (Q15) and **capacities**
(Q5, Q10). Strategy is meaningless until we know what earns points.

## 3. TM Arcade access

- [ ] The **Arcade URL** for the timed game.
- [ ] Does it need an **account or login**, or any click-through before the game loads?
- [ ] A screenshot of the **game-over screen**, if the timed mode has one.

> **Do not commit credentials.** Say a login is needed and I'll wire it to
> environment variables.

## 4. Environment

- [ ] **OS and version** of the machine that will run the bot.
- [ ] **Python version** (`python3 -V`).

> No longer needed: the canvas bounding box. The bot now detects the button grid
> itself, so canvas size and zoom don't matter. See `findings.md` §4.

---

## Then I build

- Playwright + Chromium backend, PNG fixture backend, desktop fallback
- Grid auto-detection with the eight measured colours
- Grayscale-correlation digit reader, both fonts
- `Elevator` ×3, `TVRoom` ×2, `RideControl`, `Track` — strict 1:1 properties,
  enum + bool per button
- JSONL trace with plain-English glosses and cue-to-click timing
- Fixture tests asserting the state table in `findings.md` §3
- A bare `main.py` skeleton — **the strategy stays yours**
