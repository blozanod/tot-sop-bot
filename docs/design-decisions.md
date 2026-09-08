# Design decisions

Twenty decisions resolved in the design interview, with the reasoning behind
each. Recorded so the rationale survives — and so that when something turns out
to be wrong, we know what it was trading against.

## Constraints that shaped everything

Two facts drove most of the choices below:

1. **I cannot reach the game.** The egress proxy blocks `themagical.nl`, so I
   have never seen the live page, its DOM, or a single real pixel. Every colour
   and coordinate is derived from screenshots and must be verifiable without me.
2. **The bot is a means, not the end.** The deliverable is a written procedure a
   person follows. Anything the bot does that a human can't observe or reproduce
   is a liability, not a feature.

---

## Perception

**1. Playwright + Chromium, canvas-relative coordinates.**
The canvas bounding box *is* the calibration: nominal coordinates scale to it
exactly, with no window-position drift, no display-scaling maths, and no stealing
your physical mouse during a 12-hour run. Rejected desktop capture as the primary
path — it needs re-anchoring every session and is painful on macOS permissions
and Wayland. Kept as a fallback behind the backend protocol.

**2. Strict 1:1 properties — one property, one observable.**
Every property maps to exactly one button's colour or one counter's digits.
Nothing combines two. A compound property like `ready_to_dispatch = enabled AND
doors_closed AND track_ready` would hide exactly the decision we're trying to
extract, and would translate to a human instruction nobody can verify at a
glance. Each button exposes a meaning-enum *and* a bool alias.

**3. Explicit `game.refresh()`, frozen frame.**
One screenshot per tick; all properties read that frame until the next refresh.
Guarantees `if e.can_dispatch and e.loaded == 2` describes a single instant.
Rejected TTL-based auto-refresh: two properties in one condition could straddle
the boundary and describe different moments — a rare and undebuggable class of
bug. Auto-capture on first access so a script without `refresh()` still runs.

**4. Digit template matching.**
The game renders a fixed font at a fixed size, so digits are pixel-identical
every time. Exact and deterministic, with no OCR dependency. Rejected Tesseract:
small crisp digits are precisely where it confuses 8/3 and 1/7, and a misread
count corrupts strategy silently instead of erroring.

> **Amended after measuring the screenshots.** Digits are *not* pixel-identical:
> the same glyph renders with 1–2 pixels of anti-aliasing difference depending on
> sub-pixel position (the digit `0` produced six distinct bitmaps across the 12
> frames). Exact template equality would fail unpredictably. The reader now uses
> **normalised grayscale correlation** against ten templates per font, with a
> confidence floor below which it raises. The guarantee is unchanged — a bad read
> errors rather than lying — but the method tolerates the jitter that is really
> there. Two fonts are needed: the 11–12 px counter face and the 29 px HUD face.

**5. Palette sampled from committed PNGs, plus a live calibrator.**
Correct on day one from real pixels, and self-healing if the emulator renders
differently on the target machine. Guessing was rejected outright: the "two
greens" distinction is the single most likely thing to silently misclassify, and
confusing action-green with toggle-green would poison the entire strategy.

**6. I write the coordinate table; `verify_layout.py` proves it.**
Coordinates stored as fractions of canvas size, derived from the master
screenshot. The verifier draws every probe point and crop box onto a live frame
so the whole table is checkable in one glance. Rejected a click-to-label wizard
(~40 prompted clicks, and a misclick bakes in a bad coordinate silently) and
auto-detection (unverifiable cleverness that fails into plausible-but-wrong
numbers rather than obvious errors).

**7. Unknown colours raise by default.**
Beyond a maximum colour distance, raise with a full diagnostic: which button, the
sampled hex, the nearest palette entry, the distance. Configurable to `unknown`
or `nearest` for long runs. Given blind calibration, the failure mode we must
never have is a button silently classified wrong while the strategy quietly does
nothing — which is indistinguishable from a legitimate game state. A loud crash
on run one is cheap.

**8. Text channel designed in, enabled only where needed.** *(Now: probably not
needed.)* The one suspected colour collision — `Attraction Closed` vs
`Attraction Active` — turned out to be `#cccccc` vs `#ffffff`, distinguishable
exactly. No collision remains among the 32 buttons across the frames available, so
the machinery gets built but stays dormant. Revisit if a new state shows up.
Every button spec carries an optional text region; the label-matching machinery
gets built but switches on only for buttons where the screenshots show two
distinct meanings sharing one colour. Pay the cost only where colour is genuinely
insufficient — and I'll know exactly where once I can sample the PNGs.

**9. Screen detection, with reads refused off the playing field.**
`game.screen` identifies which screen is up; reading an elevator property
elsewhere raises. Necessary because the mode chooser occupies the *same canvas
region* as the RideControl panel — without this, probing during the chooser
samples a dialog pixel and reports a confident, meaningless state. This is the
most likely first-run failure.

## Actions

**10. Dumb clicks that log their pre-state.**
Actions click, full stop — no precondition check, no animation wait, no
auto-refresh. All of that lives in `main.py`. Each records the button's colour at
click time, so the trace shows `clicked Dispatch while INACTIVE, nothing
happened`. Guarded actions were rejected: they relocate a real decision out of
the strategy file and into a class, making it invisible to the SOP.

**11. `game.wait_until(predicate, timeout)` returning a bool.**
Refreshes and polls internally; returns False on timeout rather than raising.
Translates literally to "wait until the Dispatch button turns green; if it hasn't
after 30 seconds, something is wrong." The timeout is the point — without one, a
miscalibrated colour hangs the bot forever instead of surfacing the bug.

**12. `launch()` is plumbing only.**
Opens Chromium, navigates, waits for the emulator, finds the canvas, asserts its
size — then stops at whatever screen the game shows. Mode choice, opening the
attraction and enabling units are exposed as actions and called from `main.py`,
because the opening sequence is genuinely part of the procedure a human follows.

**13. Unconstrained play, with timing logged.**
The bot may watch all five units at once and click faster than a person. Rather
than capping it up front, log every inter-action interval and every cue-to-click
delay, so afterwards you can see which steps demand superhuman timing and decide
what they cost. Finds the ceiling first, then negotiates down. A rate limiter
ships but defaults off, so the same strategy can be run both ways and the score
gap tells you which steps are timing-critical.

## Interfaces

**14. Indexed collections plus flat aliases.**
`game.elevators[1..3]` and `game.tv_rooms[1..2]` keyed by the on-screen numbers,
plus `game.elevator1` / `game.tv_room1` aliases, with `game.control` and
`game.track` for globals. Loops for scanning all three elevators; literal names
for steps that become "dispatch Elevator 2". One-indexed so code and screen
labels never disagree.

**15. Fixture backend and assertion tests.**
A third backend serves a PNG as "the current frame", so the whole stack runs with
no browser. Tests assert real readings against the screenshots. This is the main
answer to constraint (1): it means the coordinate table and palette I hand over
are *verified* rather than guessed, despite my never touching the live game.

**16. Trace = actions plus state-change events, JSONL.**
Every action with a full state snapshot, plus an event whenever any observable
changes. That's the causal record — "preshow started, 47s later Unload turned
orange" — which is exactly what an SOP step is made of. Idle frames write
nothing, so it stays small. Logging every refreshed frame would bury the signal
in hundreds of thousands of near-identical records.

**17. Human phrasing lives on the state definitions.**
Each button knows its on-screen name and a plain-English gloss per state, so the
trace reads as prose and the vocabulary stays locked to what a person actually
sees. Keeping the mapping beside the enum that defines it stops the two drifting.

## Scope

**18. Target: the timed 12-hour scored game in the TM Arcade.**
Not the Simulation Page link, which only offers Unlimited. Needs the Arcade URL
and a decision about login. *(Open — see `TODO.md`.)*

> The screenshots show the clock advancing ~1 game-minute per real second, so a
> full 12-hour run is only **~12 real minutes**. The worry that scored runs would
> be too slow to iterate on does not apply.

**19. Mechanics documented by you, in prose.**
Guest flow, capacities, scoring and what blocks the track are knowledge only you
have. Where you're unsure, glosses describe only what's visible rather than
asserting a mechanism.

**20. Build held until assets land.**
No placeholder scaffolding. Everything gets written in one pass against real
pixels once the screenshots and mechanics doc are in.
