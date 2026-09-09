# What the screenshots yielded

Derived mechanically from the 12 frames in `assets/screenshots/`. Everything here
is measured, not estimated — exact pixel values, verified across all 12 frames.

---

## 1. The palette: eight colours, not four

All button fills are **exact flat colours** with no anti-aliasing in the interior,
so classification is an equality test, not a nearest-match problem.

| Hex | Name | Meaning | Where seen |
| --- | --- | --- | --- |
| `#ffffff` | `WHITE` | idle / available | most buttons |
| `#cccccc` | `DIM_WHITE` | **Attraction Closed** | Attraction only |
| `#999999` | `GRAY` | not actionable right now | any button |
| `#66cc33` | `GREEN` | action in progress / toggle on | most buttons |
| `#ff9933` | `ORANGE` | door moving, or action ready | most buttons |
| `#00ff00` | `BRIGHT_GREEN` | **ready to dispatch** | Dispatch only |
| `#ff9900` | `BRIGHT_ORANGE` | **dispatched, in motion** | Dispatch only |
| `#ff0000` | `RED` | Track locked | Track only |

### Three corrections to what we assumed

**Red is `#ff0000`, not `#ef0817`.** The Track Locked button measures pure red in
`11-dispatched-track-blocked`. `#ef0817` is presumably the small indicator lights in
the ride diagram, which are not a control. Had we calibrated on `#ef0817`, the
distance from `#ff0000` is large enough that a strict matcher would have raised on
every blocked-track frame.

**There is a `GRAY` state nobody mentioned.** `#999999` means *this control is not
actionable right now* — either its unit is toggled off, or the attraction is closed.
In `00-attraction-closed-all-gray`, **all 32 buttons are gray**. This is a first-class
state, not an absence of one.

**`Attraction` is colour-distinguishable after all.** Closed is `#cccccc`, Active is
`#ffffff` — a 20% brightness difference that is essentially invisible to a human eye
but exact to a pixel test. Worth noting for the SOP: a person will read the *word*
(Closed / Active); the bot reads the fill. Both are reliable, but they are different
signals, and the human instruction must say "reads Closed", never "looks dimmer".

### The two greens, resolved

Your instinct was right, and there are **two oranges too**:

- `#66cc33` / `#ff9933` — the ordinary palette, used by 31 of the 32 buttons.
- `#00ff00` / `#ff9900` — used **only** by `Dispatch Elevator`.

So Dispatch has its own brighter palette, presumably because it is the one
irreversible action. Its state set is `GRAY` → `BRIGHT_GREEN` (armed) →
`BRIGHT_ORANGE` (in motion).

---

## 2. Colour semantics

Across all 12 frames the rule is consistent:

| Colour | On a door button | On an action button |
| --- | --- | --- |
| `GRAY` | not actionable | not actionable |
| `WHITE` | closed | available, nothing prompting you |
| `ORANGE` | **moving** | **ready — do this now** |
| `GREEN` | open | **in progress** |

This matches your original description exactly ("orange when something is moving or
when something is ready to occur"). The green/orange split is the useful one for an
SOP: **orange is a cue to act, green means it's already happening.**

---

## 3. Observed state trace

Machine-derived from every frame. This is the fixture ground truth the tests will
assert against.

| frame | T1.Load | T1.Unload | T1.Entrance | T1.Exit | T1.Enable | T1.Preshow | E1.Enable | E1.Doors | E1.Load | E1.Dispatch | Attraction | Track |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `153058` | GRAY | GRAY | GRAY | GRAY | GRAY | GRAY | GRAY | GRAY | GRAY | GRAY | DIM | GREEN |
| `153132` | GREEN | WHITE | ORANGE | WHITE | GREEN | WHITE | GRAY | GRAY | GRAY | GRAY | WHITE | GREEN |
| `153147` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GRAY | GRAY | GRAY | GRAY | WHITE | GREEN |
| `153205` | WHITE | WHITE | WHITE | WHITE | GREEN | GREEN | GRAY | GRAY | GRAY | GRAY | WHITE | GREEN |
| `153222` | WHITE | ORANGE | WHITE | WHITE | GREEN | WHITE | GRAY | GRAY | GRAY | GRAY | WHITE | GREEN |
| `153235` | WHITE | GREEN | WHITE | GREEN | GREEN | WHITE | GRAY | GRAY | GRAY | GRAY | WHITE | GREEN |
| `153255` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | WHITE | WHITE | GRAY | WHITE | GREEN |
| `153313` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | ORANGE | WHITE | GRAY | WHITE | GREEN |
| `153320` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | GREEN | GREEN | GRAY | WHITE | GREEN |
| `153327` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | ORANGE | WHITE | BGREEN | WHITE | GREEN |
| `153334` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | WHITE | WHITE | BGREEN | WHITE | GREEN |
| `153341` | WHITE | WHITE | WHITE | WHITE | GREEN | ORANGE | GREEN | WHITE | WHITE | BORANGE | WHITE | RED |

Read down the last two columns of the final row: `Dispatch = BRIGHT_ORANGE` and
`Track = RED` occur together, which means **the dispatched elevator is what locks
the track**. That is one of the mechanics questions answered for free.

The TV Room 1 cycle also reads straight off the table:

```
Load=GREEN, Entrance=ORANGE     loading, entrance door moving
Preshow=ORANGE                  room full, preshow is ready to start
Preshow=GREEN                   preshow running ("Preshow Active")
Unload=ORANGE                   preshow over, unload is ready
Unload=GREEN, Exit=GREEN        unloading through the open exit
```

---

## 4. Geometry: fully auto-detectable

The panel is a clean grid. Running connected-component detection over the eight
palette colours and filtering to 74–76 × 34–37 px finds **exactly 32 buttons in
every one of the 12 frames, with zero false positives.**

- Button columns (window px): `926, 1012` (TV Room 1 / Elevator 1), `1180, 1266`
  (TV Room 2 / Elevator 2), `1431, 1517` (Elevator 3), `1397, 1482, 1565`
  (RideControl toggles), `1705` (Attraction / Track)
- Button rows: `52, 97, 101, 134, 148` (upper block), `236, 283` (elevator block)
- 13 counter boxes, located by their 45 px black top/bottom edges

The crops are pixel-identical to the full-window frames — buttons are 75×36 in
both — so every frame aligns by a simple offset.

**This changes the plan: no hardcoded coordinate table.** The bot detects the grid
at calibration time and assigns names from the grid structure. Canvas size, browser
zoom and letterboxing all stop mattering. Details in `design-decisions.md` (#6).

---

## 5. Digits

**Counter font (11–12 px): all ten glyphs confirmed.** Values observed across the
frames — `0, 12, 16, 19, 21, 58, 63, 67, 84` — cover 0–9 with no gaps.

**HUD font (29 px) is a different, larger face**, used for `Current Time` and
`Your score`. Observed: `10:01 / 0`, `10:35 / 148`, `10:45 / 211`, giving digits
`0 1 2 3 4 5 8`. **Missing: 6, 7, 9.**

### Correction: exact bitmap matching will not work

The same digit renders with 1–2 pixels of anti-aliasing difference depending on its
sub-pixel position — extracting glyphs from the frames produced six distinct
bitmaps for the digit `0`. Binarised template equality would fail unpredictably.

The reader will instead use **normalised grayscale correlation** against ten
templates per font, taking the best match above a confidence floor and raising
below it. Same guarantee as before (a bad read errors rather than lying), but
tolerant of the rendering jitter that is actually present. See `design-decisions.md`
(#4).

> **Superseded on day two.** The bot no longer reads numbers — only whether a
> counter says `0`, says `21`, or says something else, because those are the only
> two values that change a decision (`design-decisions.md` #23). The correlation
> matcher survives, but it runs against the counter font alone and only ever asks
> "is this glyph a `0`?" or "is this `2` then `1`?". The HUD face is gone with the
> clock and the score, which is also what let the screenshot shrink to the panel.
> The measurements in this section stand; what was built on them changed.

---

## 6. The clock runs fast — about 1 virtual minute per real second

| Frame | Real time | Game clock | Score |
| --- | --- | --- | --- |
| `00` | 15:30:58 | 10:01 | 0 |
| `01` | 15:31:32 | 10:35 | 148 |
| `02` | 15:31:47 | 10:45 | 211 |

44 virtual minutes elapsed in 49 real seconds.

**A full 12-hour timed game is therefore about 12 minutes of real time**, not the
long grind assumed earlier. That is good news for iteration — you can A/B a
strategy change several times an hour — and it retires the concern about burning
scored runs on experiments.

It also raises the stakes on timing. At roughly one game-minute per second, the
window between a button turning orange and the moment you needed to press it is
small in human terms. This is exactly what decision #13 (log every cue-to-click
interval) was for, and it is now clearly the most important number the trace
will produce.

Scoring rate here was ~211 points in 44 game-minutes with **one** TV room and
**one** elevator in service, which is a useful baseline to beat.
