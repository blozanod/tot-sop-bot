"""Build the digit template set from the calibration screenshots.

Ground truth is the values read by eye from the frames in ``assets/screenshots``
and recorded below. Every entry is asserted against the segmenter: if a frame does
not yield exactly as many glyphs as the label has characters, this fails loudly
rather than learning a misaligned template.

    python -m tools.extract_templates
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot.digits import Templates, cut_glyphs, normalise  # noqa: E402
from tot.geometry import build_layout  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "assets" / "screenshots"

#: frame -> {layout key: (value, band)}. Values were read by eye from the frames.
GROUND_TRUTH: dict[str, dict[str, tuple[str, str]]] = {
    "states/03-preshow-active-153205.png": {
        "control.front_waiting": ("16", "all"),
        "control.back_waiting": ("0", "all"),
        "control.visitor_counter": ("58", "all"),
        "tv_room1.waiting": ("21", "all"),
        "tv_room1.loaded": ("21", "all"),
    },
    "states/04-preshow-done-unload-ready-153222.png": {
        "control.front_waiting": ("21", "all"),
        "control.visitor_counter": ("63", "all"),
    },
    "states/05-unloading-exit-open-153235.png": {
        "control.back_waiting": ("12", "all"),
        "control.visitor_counter": ("63", "all"),
    },
    "states/06-elev1-enabled-doors-closed-153255.png": {
        "control.front_waiting": ("19", "all"),
        "control.back_waiting": ("16", "all"),
        "control.visitor_counter": ("67", "all"),
    },
    "states/11-dispatched-track-blocked-153341.png": {
        "control.front_waiting": ("21", "all"),
        "control.visitor_counter": ("84", "all"),
    },
    "layout/00-attraction-closed-all-gray-153058.png": {
        "clock": ("10:01", "last"),
        "score": ("0", "last"),
    },
    "layout/01-tvr1-loading-entrance-moving-153132.png": {
        "clock": ("10:35", "last"),
        "score": ("148", "last"),
        "tv_room1.waiting": ("18", "all"),
        "tv_room1.loaded": ("3", "all"),
        "control.front_waiting": ("8", "all"),
        "control.back_waiting": ("0", "all"),
        "control.visitor_counter": ("29", "all"),
    },
    "layout/02-tvr1-loaded-preshow-ready-153147.png": {
        "clock": ("10:45", "last"),
        "score": ("211", "last"),
        "tv_room1.waiting": ("7", "all"),
        "tv_room1.loaded": ("21", "all"),
        "control.front_waiting": ("10", "all"),
        "control.back_waiting": ("0", "all"),
        "control.visitor_counter": ("38", "all"),
    },
}


def main() -> int:
    chars: list[str] = []
    vecs: list[np.ndarray] = []
    problems: list[str] = []

    for rel, entries in GROUND_TRUTH.items():
        frame = np.array(Image.open(SHOTS / rel).convert("RGB"))
        layout = build_layout(frame)
        for key, (label, band) in entries.items():
            rect = layout.hud.get(key) or layout.counters.get(key)
            if rect is None:
                problems.append(f"{rel}: no box for {key}")
                continue
            glyphs = cut_glyphs(frame, rect, band=band)
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
