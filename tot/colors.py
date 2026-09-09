"""The button palette, and how to read a lot of pixels at once.

Button fills are exact flat colours with no anti-aliasing in the interior, and the
only other thing inside a button is pure black text. So a colour reading is a
majority vote over a handful of interior pixels — no averaging, no nearest-match,
no per-button numpy call.

Everything here works on *packed* pixels: one uint32 per pixel instead of three
uint8s. That turns colour comparison into integer equality, which is what makes
whole-frame masking cheap enough to run on every frame.
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


def pack(frame: np.ndarray) -> np.ndarray:
    """(H, W, 3) uint8 RGB -> (H, W) uint32, one integer per pixel."""
    h, w, _ = frame.shape
    buf = np.zeros((h, w, 4), np.uint8)
    buf[:, :, :3] = frame
    return buf.view(np.uint32).reshape(h, w)


#: The palette as packed pixels, in PALETTE order. Built through ``pack`` so the
#: byte order matches whatever this machine is.
CODES: np.ndarray = pack(np.array([[c.value for c in PALETTE]], np.uint8))[0]


def palette_mask(code: np.ndarray) -> np.ndarray:
    """Which pixels of a packed frame are a palette colour.

    Eight integer comparisons over the frame. ``np.isin`` would sort 2M pixels to
    answer the same question and is several times slower.
    """
    mask = code == CODES[0]
    for c in CODES[1:]:
        mask |= code == c
    return mask


def vote(frame: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Read one palette colour per row of a sample grid.

    ``ys`` and ``xs`` are (N, K) integer arrays: K probe points inside each of N
    buttons. Returns (N,) palette indices and an (N,) count of how many probes
    agreed. Probes that land on the button's black text match nothing and simply
    do not vote, so the fill wins on any grid that touches it at all.
    """
    code = pack(frame[ys, xs])
    hits = code[:, :, None] == CODES[None, None, :]
    tally = hits.sum(axis=1)
    idx = tally.argmax(axis=1)
    return idx, tally[np.arange(len(idx)), idx]


def modal_rgb(frame: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> tuple[int, int, int]:
    """The most common colour among one button's probe points.

    Used for error messages and debugging only. Sampling the button's centre
    pixel instead would as often as not report the black of its caption.
    """
    pix = frame[ys, xs].reshape(-1, 3)
    code = pack(pix.reshape(1, -1, 3))[0]
    vals, counts = np.unique(code, return_counts=True)
    first = int(np.flatnonzero(code == vals[int(counts.argmax())])[0])
    r, g, b = pix[first]
    return int(r), int(g), int(b)
