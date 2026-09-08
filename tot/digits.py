"""Reading the counters, the clock and the score.

One pixel font is used for every number on screen, at one size — the HUD digits
measure the same 12px as the counter-box digits, so a single template set covers
everything (``docs/findings.md`` §5).

Glyphs are *not* pixel-identical between renders: the same digit picks up one or
two pixels of anti-aliasing difference depending on its sub-pixel position, which
is why matching is normalised grayscale correlation rather than bitmap equality.
A match below ``MIN_SCORE`` raises instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .errors import DigitError
from .geometry import Rect

#: Every glyph is resampled to this (width, height) before comparison.
CANON = (12, 16)

#: Correlation floor. Below this we refuse to read rather than return a number
#: that might be wrong — a bad count corrupts strategy silently. Across the 224
#: glyphs in the calibration frames the worst correct match scored 0.753, so this
#: leaves headroom for renders we have not seen without being reckless.
MIN_SCORE = 0.65

#: The best match must also beat the best *different* character by this much.
#: Worst observed margin was 0.144, so genuine ambiguity is well clear of it.
MIN_MARGIN = 0.05

TEMPLATE_FILE = Path(__file__).with_name("templates.npz")


def _text_mask(patch: np.ndarray) -> np.ndarray:
    """Bright, near-neutral pixels: the white text, not the box or the game art."""
    return (patch.max(axis=2).astype(int) - patch.min(axis=2).astype(int) < 45) & (
        patch.max(axis=2) > 120
    )


def _spans(flags: np.ndarray) -> list[tuple[int, int]]:
    if not flags.any():
        return []
    d = np.diff(np.concatenate(([0], flags.view(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def normalise(patch: np.ndarray) -> np.ndarray:
    """A glyph reduced to a zero-mean unit-norm vector at a canonical size."""
    from PIL import Image

    im = Image.fromarray(np.clip(patch, 0, 255).astype(np.uint8)).resize(CANON, Image.BILINEAR)
    v = np.asarray(im, dtype=float)
    v -= v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else v


def cut_glyphs(frame: np.ndarray, rect: Rect, band: str = "all") -> list[np.ndarray]:
    """Grayscale patches for each glyph inside ``rect``, left to right.

    ``band="last"`` keeps only the bottom line of text, which is how the HUD boxes
    are read — they carry a label above the value.
    """
    patch = frame[rect.y : rect.bottom, rect.x : rect.right]
    if patch.size == 0:
        return []
    mask = _text_mask(patch)
    rows = _spans(mask.any(axis=1))
    if not rows:
        return []
    if band == "last":
        r0, r1 = rows[-1]
        mask = mask[r0:r1]
        gray = patch[r0:r1].mean(axis=2)
    else:
        gray = patch.mean(axis=2)

    out = []
    for c0, c1 in _spans(mask.any(axis=0)):
        col = mask[:, c0:c1]
        rr = np.flatnonzero(col.any(axis=1))
        if len(rr) < 3 or c1 - c0 < 2:
            continue
        out.append(gray[rr.min() : rr.max() + 1, c0:c1])
    return out


@dataclass
class Templates:
    """Labelled glyph exemplars. Several variants per character are kept, because
    the same digit renders slightly differently at different sub-pixel offsets."""

    chars: list[str]
    vectors: np.ndarray  # (n, H, W), each normalised

    @classmethod
    def load(cls, path: Path = TEMPLATE_FILE) -> Templates:
        if not path.exists():
            raise DigitError(
                f"no digit templates at {path}. Run `python -m tools.extract_templates` "
                f"to build them from the calibration screenshots."
            )
        d = np.load(path, allow_pickle=False)
        return cls([str(c) for c in d["chars"]], d["vectors"])

    def save(self, path: Path = TEMPLATE_FILE) -> None:
        np.savez_compressed(path, chars=np.array(self.chars), vectors=self.vectors)

    def match(self, patch: np.ndarray) -> tuple[str, float, float]:
        """Best character, its score, and its margin over the runner-up character."""
        v = normalise(patch)
        scores = (self.vectors * v).sum(axis=(1, 2))
        order = np.argsort(scores)[::-1]
        top = self.chars[order[0]]
        runner = next((scores[i] for i in order if self.chars[i] != top), 0.0)
        return top, float(scores[order[0]]), float(scores[order[0]] - runner)


class DigitReader:
    """Reads numbers off the panel. One instance is shared by the whole game."""

    def __init__(
        self,
        templates: Templates | None = None,
        min_score: float = MIN_SCORE,
        min_margin: float = MIN_MARGIN,
    ):
        self.templates = templates or Templates.load()
        self.min_score = min_score
        self.min_margin = min_margin

    def read_string(self, frame: np.ndarray, rect: Rect, name: str, band: str = "all") -> str:
        glyphs = cut_glyphs(frame, rect, band=band)
        if not glyphs:
            raise DigitError(f"{name}: no text found in its box at {rect}")
        chars = []
        for i, g in enumerate(glyphs):
            ch, score, margin = self.templates.match(g)
            if score < self.min_score:
                raise DigitError(
                    f"{name}: glyph {i + 1} of {len(glyphs)} matched '{ch}' at only "
                    f"{score:.2f} (floor {self.min_score:.2f}). Either the layout has "
                    f"drifted or this glyph is not in the template set."
                )
            if margin < self.min_margin:
                raise DigitError(
                    f"{name}: glyph {i + 1} of {len(glyphs)} is ambiguous — '{ch}' scored "
                    f"{score:.2f} but the next character is only {margin:.3f} behind."
                )
            chars.append(ch)
        return "".join(chars)

    def read_int(self, frame: np.ndarray, rect: Rect, name: str, band: str = "all") -> int:
        s = self.read_string(frame, rect, name, band=band)
        if not s.isdigit():
            raise DigitError(f"{name}: read {s!r}, which is not a number")
        return int(s)

    def read_clock(self, frame: np.ndarray, rect: Rect, name: str = "clock") -> str:
        """The game clock as ``HH:MM``."""
        s = self.read_string(frame, rect, name, band="last")
        if len(s) == 4 and s.isdigit():  # a missed colon
            s = f"{s[:2]}:{s[2:]}"
        if len(s) != 5 or s[2] != ":" or not (s[:2] + s[3:]).isdigit():
            raise DigitError(f"{name}: read {s!r}, which is not a HH:MM time")
        return s
