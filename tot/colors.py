"""The button palette.

Measured from the calibration screenshots in ``assets/screenshots``. Button fills
are exact flat colours with no anti-aliasing in the interior, so classification is
an equality test on the median of a probe patch, not a nearest-match problem. The
distance machinery exists only to produce a useful error message when nothing
matches.

See ``docs/findings.md`` for how each value was derived.
"""

from __future__ import annotations

from enum import Enum

import numpy as np


class Color(Enum):
    """Every fill a RideControl button is known to take."""

    WHITE = (255, 255, 255)
    DIM_WHITE = (204, 204, 204)
    GRAY = (153, 153, 153)
    GREEN = (102, 204, 51)
    ORANGE = (255, 153, 51)
    BRIGHT_GREEN = (0, 255, 0)
    BRIGHT_ORANGE = (255, 153, 0)
    RED = (255, 0, 0)

    @property
    def hex(self) -> str:
        r, g, b = self.value
        return f"#{r:02x}{g:02x}{b:02x}"


PALETTE: tuple[Color, ...] = tuple(Color)

#: Fill of the panel behind the buttons, and of the counter box interiors.
PANEL_BACKGROUND = (39, 39, 39)

#: How far a sampled colour may sit from a palette entry before we refuse to
#: classify it. Fills are exact, so anything beyond a couple of units means the
#: probe landed off the button — a layout problem, not a colour problem.
MAX_DISTANCE = 12.0


def classify(rgb: tuple[int, int, int]) -> Color | None:
    """Return the palette colour for ``rgb``, or None if nothing is close enough."""
    best, best_d = None, float("inf")
    for c in PALETTE:
        d = float(np.linalg.norm(np.subtract(rgb, c.value)))
        if d < best_d:
            best, best_d = c, d
    return best if best_d <= MAX_DISTANCE else None


def nearest(rgb: tuple[int, int, int]) -> tuple[Color, float]:
    """Nearest palette colour and its distance, ignoring MAX_DISTANCE.

    Used to build error messages, and by ``on_unknown="nearest"``.
    """
    best, best_d = PALETTE[0], float("inf")
    for c in PALETTE:
        d = float(np.linalg.norm(np.subtract(rgb, c.value)))
        if d < best_d:
            best, best_d = c, d
    return best, best_d


def sample(frame: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[int, int, int]:
    """Modal colour of the middle of a rect.

    Takes the centre half of the rect so a border or a rounded corner can never
    contribute, and the mode rather than the mean so a stray text pixel cannot
    drag the reading between two palette entries.
    """
    x0, y0 = x + w // 4, y + h // 4
    patch = frame[y0 : y0 + max(1, h // 2), x0 : x0 + max(1, w // 2)].reshape(-1, 3)
    vals, counts = np.unique(patch, axis=0, return_counts=True)
    r, g, b = vals[int(counts.argmax())]
    return int(r), int(g), int(b)
