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

---

# Day two: what got cut, and why

The first build read everything the screen offered and recorded all of it. That
was the wrong instinct — it spent its budget on pixels and numbers that never
changed a decision. These decisions replace the ones above where they conflict.

**21. Stay in Python.**
The obvious suspect for a 2-second tick was the language. It was not. Measuring
the pieces:

| | before | after |
| --- | --- | --- |
| locate the panel (full canvas) | 1520 ms | 77 ms |
| decode one frame | 29 ms | 0.05 ms |
| capture one frame | ~85 ms | ~19 ms |

The two Python numbers fell by 20× and 600× without leaving Python, because the
cost was never the interpreter — it was a per-row numpy call inside a loop over
1198 rows, and `np.unique` sorting a patch to find a modal colour. Both are
vectorised now.

What is left is ~19 ms of screenshot, and that is Chromium's, reached over CDP.
A rewrite in Rust or Go would be competing for the remaining 2 ms of a 21 ms tick
and would still wait the same 19 ms for the browser. At ~47 Hz against a game
that advances one game-minute per real second, perception is no longer the
constraint — strategy is. Revisit only if the browser stops being the floor.

**22. Screenshot the panel, not the canvas.**
The panel is located once from a full frame; after that every capture is clipped
to its bounding box, roughly an eighth of the canvas. This is the single biggest
win in the whole loop — 85 ms → 19 ms — and everything outside that rectangle was
being decoded and thrown away.

Chromium is also launched with `--disable-frame-rate-limit`. Without it a
screenshot waits for the compositor's next 30 Hz frame, which put a 33 ms floor
under every capture *regardless of size* and hid the benefit of cropping.

**23. Read 0 and 21. Nothing else.** *(Replaces #4's full digit reader.)*
Those are the only two counter values that change what a player does: zero means
there is nothing to move, 21 means a full load. Everything between them means
wait. So a counter classifies three ways — `ZERO`, `FULL`, `OTHER` — and the
short-circuits mean most boxes never reach the matcher at all: three or more
glyphs is `OTHER` outright, and a two-glyph box whose first character is not `2`
is `OTHER` without the second being looked at.

The templates were rebuilt from the counter font only. Keeping the 29 px HUD face
in the same table was a live hazard: a HUD exemplar labelled `0` sitting next to a
counter `6` is exactly how a counter gets misread as empty.

**24. Counters are lazy; buttons are eager.**
All 32 button colours come from one vectorised read of 288 pixels, so reading
them all is cheaper than deciding which ones to skip. Counters are the opposite —
each is a segmentation — so they are read on first access and cached until the
next `refresh()`. A tick that only asks about colours never touches a digit.

**25. No clock, no score, no HUD.** *(Replaces part of #4 and #6.)*
Neither number is an input to any decision. The score is an outcome, and the
clock only says how long is left, which does not change what the right move is.
Both lived outside the panel, so dropping them is also what let the crop shrink
to the panel alone.

**26. No trace.** *(Replaces #16 and #17.)*
Every action and every state change was being written to JSONL, with a
plain-English gloss per state, on a loop that now runs at 47 Hz. The glosses and
the `verified` / `inferred` bookkeeping went with it. The trace was for drafting
the procedure; that can be reintroduced as a strategy-level concern in `main.py`,
recording the handful of decisions that matter rather than every frame.

**27. The bot never clicks its way in.** *(Replaces #9 and #12.)*
The old backend clicked play buttons, then the canvas, then the middle of the
page, trying to get past a splash screen. That could land on the mode chooser and
pick a game for you, and blind clicks into a half-loaded emulator are a fair
suspect for the crashes.

Now: it opens the page and waits. `wait_for_panel()` polls at 1 Hz until the
32-button grid is on screen, and finding it *is* the signal that the game has
started — which also retires `game.screen`, since "the panel is there" and "we
are on the playing field" were always the same question.

**28. Ruffle is configured, and its failures are detected.**
`window.RufflePlayer.config` is injected before the emulator boots:
`maxExecutionDuration` goes from 15 s to 3600 s (Ruffle panics when a frame
exceeds it, which a long game plausibly does), and the unmute overlay, splash
screen, unsupported-content warning and context menu are all turned off, since
each one can cover the panel. Audio is muted at the browser level too — it is
pure cost to us.

If Ruffle does put up its error screen, `#panic` / `#message-overlay` in its
shadow root is detected and raised as `RuffleCrashed` carrying Ruffle's own text,
rather than the frame being read as a strange-looking game.

> Unverified, and it has to be: the game is still not reachable from the machine
> this was written on, so the config values and the panic selectors come from
> Ruffle's documented interface rather than from watching your crash. If the
> orange screen survives all this, `python -m tools.probe_page` prints the
> emulator's error text — send it and this becomes a fix rather than a guess.

**29. Nothing the bot does may move the page.**
Cropping the screenshot was worth ~65 ms a tick, but the first version bought it
by calling `scroll_into_view_if_needed()` once at startup: Playwright refuses a
clip outside the viewport, so a canvas taller than the window had to be scrolled
to before it could be captured. What that looks like from the outside is the view
jumping to the control panel, which is not acceptable — you are watching the game.

Measured, on a page whose canvas runs past the fold:

| | off-screen clip | scroll events | resize events | cost |
| --- | --- | --- | --- | --- |
| `page.screenshot(clip=…)` | refuses | 0 | 0 | 18.8 ms |
| CDP, `captureBeyondViewport: false` | blank | 0 | 0 | 12.7 ms |
| CDP, `captureBeyondViewport: true` | correct | 0 | **1 per capture** | 14.3 ms |

The third row is the trap: it reaches below the fold without scrolling, so it
looks like the answer, but it fires a `resize` on the page for every single
capture. At 51 Hz into an emulator that relays out its canvas on resize, that is
both a visible twitch and a fair suspect for the crashes.

So: capture through CDP with both flags false, and intersect the wanted rect with
whatever is currently on screen. Off-screen means a short crop, which means the
panel is not found, which means the bot waits and says why — never that it moves
your page to reach it. The window is opened maximised (`--start-maximized` with
no emulated viewport) so that case is rare to begin with.

Two things fell out of it: the capture is 6 ms cheaper than Playwright's helper,
which waits for fonts and hides text carets on every call, and clicks now read the
scroll position instead of assuming it, so scrolling mid-run no longer aims them
at the wrong place.

**30. Do not ask the browser for a screenshot at all.**
Decision #29 stopped the bot scrolling, but kept the clipped capture. In a headed
window that turns out to make the page visibly flash — resized to the clip
rectangle, game gone, panel alone in the corner, once per tick. Every way of
*asking* Chromium for pixels disturbs something:

| | off-screen clip | disturbs the page | cost |
| --- | --- | --- | --- |
| `page.screenshot(clip=…)` | refuses | scroll, to satisfy the clip | 18.8 ms |
| CDP, `captureBeyondViewport: true` | reaches it | a `resize` per capture | 14.3 ms |
| CDP, clipped | blank | **flashes, headed** | 12.7 ms |
| CDP, no clip | n/a | nothing | 39 ms |

So frames are not requested. ``Page.startScreencast`` has the compositor push what
it has already painted — the channel DevTools uses for its device preview — and
the panel crop moves into numpy. There is no capture call, so there is no code
path that could install an emulation override, which is a structural guarantee
rather than a tuning one.

Three things follow:

* **Frames are PNG, never JPEG.** JPEG is smaller and decodes faster and would
  quietly shift the flat fills by a unit or two, which is exactly the signal the
  colour classification is an equality test on. `maxWidth`/`maxHeight` are set
  past any real window for the same reason: a scaled frame is a resampled frame.
* **The ack paces the stream, and goes out on arrival.** Chromium holds the next
  frame until the last is acknowledged. Acking when a frame is *taken* instead
  cost a whole paint cycle — 59 ms a tick against 41 — and bought only bandwidth
  down a local socket.
* **Clicks convert frame pixels to CSS pixels.** The frame arrives at the
  display's real resolution, so on a HiDPI screen it is twice the size the mouse
  works in. Detection never cared, since it finds the panel at whatever scale it
  is drawn; clicking did, and silently, on any Retina display.

The cost is a whole-window decode instead of a small clip: 27 ms rather than 2, so
a tick is 41 ms rather than 19. That is the right trade. 24 Hz is still twenty
times faster than a game that advances one game-minute per real second, and the
thing being paid for is that the game stays on screen, still, while it plays.

Also dropped here: `--disable-frame-rate-limit` and `--disable-gpu-vsync`. They
were worth a few ms when every tick asked for a screenshot, and uncapping a
compositor is a plausible way to make a real display flicker. The screencast takes
frames at whatever rate the page paints, so neither is needed.

> Note on how this was found: none of it reproduced under Xvfb. Scroll listeners,
> resize listeners and per-frame viewport sampling all came back clean while the
> flash was plainly visible on a real display. The fix is therefore structural —
> remove the capability rather than tune around it — because the instrumentation
> available here cannot prove a subtler fix works.
