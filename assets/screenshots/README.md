# Screenshot capture spec

I am calibrating colours and coordinates entirely from these files — I cannot
reach the game from my container (the egress proxy blocks `themagical.nl`). Every
pixel I get wrong here becomes a button the bot misreads on your machine.

## Rules

| Rule | Why |
| --- | --- |
| **PNG, never JPEG** | JPEG ringing smears button edges and shifts flat fill colours by several units — exactly the signal I sample. |
| **Browser zoom 100%** | I store coordinates as fractions of canvas size; a zoom mismatch between capture and run breaks the mapping. |
| **No resizing or cropping after capture** | Resampling invents intermediate colours that match nothing in the palette. |
| **Whole-window is fine** | I locate the canvas myself. Don't hand-crop to the canvas unless it's easy. |
| **Same browser you'll run the bot in** | Different renderers can differ by a unit or two on anti-aliased text. |

Duplicates and extras cost me nothing. **Dump in more than you think I need.**

---

## `layout/` — one clean master

`layout/00-master.png` — full canvas, RideControl panel open, nothing mid-animation.

This is the frame I derive all ~40 probe coordinates from. If you can grab two
at different window sizes, even better: it lets me verify the fractional scaling
actually holds instead of assuming it.

---

## `states/` — one frame per situation

Naming: `NN-short-description.png`. I care about the number prefix (it orders
them), not the wording.

One frame catches many buttons at once, so this list is by **game situation**,
not by button.

### Screens outside the playing field
| File | What to capture |
| --- | --- |
| `00-chooser.png` | The timed/unlimited mode chooser |
| `01-loading.png` | Any loading or click-to-play screen, if one exists |
| `90-game-over.png` | End of a timed 12-hour game, if it shows one |

These three are what `game.screen` detects. Without them the bot's most likely
first-run failure is probing the chooser dialog — which sits in the *exact same
canvas region* as the RideControl panel — and confidently reporting nonsense.

### Baseline
| File | What to capture |
| --- | --- |
| `10-idle-closed.png` | Attraction Closed, everything inactive/white |
| `11-open-empty.png` | Attraction Open, no guests yet |
| `12-queue-building.png` | Guests in Front/Back Waiting, TV rooms still idle |

### TV room cycle
| File | What to capture |
| --- | --- |
| `13-tvroom-loading.png` | Just after Load TV Room — Entrance orange/Moving |
| `14-tvroom-loaded.png` | Entrance closed again, room loaded, preshow available |
| `15-preshow-running.png` | During the preshow |
| `16-preshow-done.png` | Unload TV Room gone orange |
| `17-tvroom-unloading.png` | Exit moving, guests leaving toward the elevators |

### Elevator cycle
| File | What to capture |
| --- | --- |
| `20-elevator-loading.png` | Just after Load Elevator — doors open |
| `21-elevator-armed.png` | **Dispatch green** — this is the second green |
| `22-elevator-dispatched.png` | Elevator gone, whatever the panel shows |
| `23-track-blocked.png` | **Track red `#ef0817`** |
| `24-elevator-returning.png` | Only if it looks different from `22` |

### Toggles and disabled states
| File | What to capture |
| --- | --- |
| `30-toggles-off.png` | Automatic Doors / Ride SFX / TV Room Sound off, BGM on, Nighttime |
| `31-disabled.png` | An elevator toggled Disabled *and* a TV room toggled Disabled |

### The valuable one
| File | What to capture |
| --- | --- |
| `40-busy.png` | Peak activity — all three elevators in *different* states at once, both TV rooms busy |

Grab several of these. One busy frame gives me more distinct button states than
five idle ones, and it's the only way I see states co-occurring the way they
actually will at runtime.

### If you can, burst-capture the animations

For `13`, `17`, `20` — take 3–4 shots a second or so apart rather than one.
Anything mid-transition tells me whether "moving" is a stable colour I can rely
on or a brief blend I need to guard against. Name them `13a`, `13b`, `13c`.

---

## `digits/` — glyph coverage

I read counters by matching each digit against a template library, so **I need
all ten glyphs 0–9** in both fonts:

1. The small counter boxes (Waiting / Loaded / Front Waiting / Back Waiting / Visitor Counter)
2. The larger HUD font (Current Time / Your score) — these look different to me

**Easiest approach:** during one full run, screenshot every ~30 seconds and dump
everything in here. The clock walks through digits on its own, the score climbs,
and the counters bounce around. I'll mine whatever glyphs I find and tell you
precisely which are missing rather than you having to plan coverage.

Aim for a run that reaches a **three-or-four-digit score** and a **two-digit
visitor counter** — high digits in the large font are the ones a short session
never produces.
