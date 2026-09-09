"""Build the glyph template set from the calibration screenshots.

Only the counter-box font is mined. The bot no longer reads the clock or the
score, so the larger HUD face is not in here — and keeping it out matters: a
HUD exemplar labelled '0' sitting next to a counter '6' is exactly how a counter
gets misread as empty.

Ground truth is the values read by eye from the frames in ``assets/screenshots``.
Every entry is asserted against the segmenter: if a frame does not yield exactly
as many glyphs as the label has characters, this fails loudly rather than
learning a misaligned template.

    python -m tools.extract_templates
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot.counters import Templates, cut_glyphs, normalise  # noqa: E402
from tot.geometry import build_layout  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "assets" / "screenshots"

#: frame -> {counter key: value}. Values were read by eye from the frames.
GROUND_TRUTH: dict[str, dict[str, str]] = {
    "states/03-preshow-active-153205.png": {
        "control.front_waiting": "16",
        "control.back_waiting": "0",
        "control.visitor_counter": "58",
        "tv_room1.waiting": "21",
        "tv_room1.loaded": "21",
    },
    "states/04-preshow-done-unload-ready-153222.png": {
        "control.front_waiting": "21",
        "control.visitor_counter": "63",
    },
    "states/05-unloading-exit-open-153235.png": {
        "control.back_waiting": "12",
        "control.visitor_counter": "63",
    },
    "states/06-elev1-enabled-doors-closed-153255.png": {
        "control.front_waiting": "19",
        "control.back_waiting": "16",
        "control.visitor_counter": "67",
    },
    "states/11-dispatched-track-blocked-153341.png": {
        "control.front_waiting": "21",
        "control.visitor_counter": "84",
    },
    "layout/01-tvr1-loading-entrance-moving-153132.png": {
        "tv_room1.waiting": "18",
        "tv_room1.loaded": "3",
        "control.front_waiting": "8",
        "control.back_waiting": "0",
        "control.visitor_counter": "29",
    },
    "layout/02-tvr1-loaded-preshow-ready-153147.png": {
        "tv_room1.waiting": "7",
        "tv_room1.loaded": "21",
        "control.front_waiting": "10",
        "control.back_waiting": "0",
        "control.visitor_counter": "38",
    },
}


def main() -> int:
    chars: list[str] = []
    vecs: list[np.ndarray] = []
    problems: list[str] = []

    for rel, entries in GROUND_TRUTH.items():
        full = np.array(Image.open(SHOTS / rel).convert("RGB"))
        layout = build_layout(full)
        r = layout.region
        frame = full[r.y : r.bottom, r.x : r.right]
        for key, label in entries.items():
            rect = layout.counters.get(key)
            if rect is None:
                problems.append(f"{rel}: no counter box for {key}")
                continue
            glyphs = cut_glyphs(frame, rect, max_glyphs=len(label))
            if len(glyphs) != len(label):
                problems.append(
                    f"{rel}: {key} labelled {label!r} ({len(label)} glyphs) but "
                    f"segmented into {len(glyphs)}"
                )
                continue
            for ch, g in zip(label, glyphs):
                chars.append(ch)
                vecs.append(normalise(g))

    if problems:
        print("Ground truth did not segment cleanly:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    Templates(chars, np.stack(vecs)).save()
    have = sorted(set(chars))
    missing = [d for d in "0123456789" if d not in have]
    print(f"{len(chars)} exemplars covering {''.join(have)}")
    print(f"missing digits: {missing or 'none'}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
