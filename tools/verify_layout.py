"""Draw what the detector found onto a frame, so you can check it at a glance.

    python -m tools.verify_layout                       # every calibration frame
    python -m tools.verify_layout --live                # the running game
    python -m tools.verify_layout shot.png -o out.png   # one image

Buttons are outlined and labelled with the state read from them, counters with the
number read. If a box is in the wrong place or a colour is misread, it is obvious
in the output image rather than three hours into a run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot import Game  # noqa: E402
from tot.digits import DigitReader  # noqa: E402
from tot.errors import DigitError  # noqa: E402
from tot.geometry import build_layout  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def annotate(frame: np.ndarray, out: Path) -> None:
    layout = build_layout(frame)
    reader = DigitReader()
    im = Image.fromarray(frame).convert("RGB")
    d = ImageDraw.Draw(im)

    game = Game(_Still(frame), trace=None)
    game.refresh()

    for key, r in layout.buttons.items():
        state = game._states.get(key)
        d.rectangle([r.x, r.y, r.right - 1, r.bottom - 1], outline=(255, 0, 255), width=2)
        d.text((r.x + 2, r.y - 11), f"{key.split('.')[-1]}={getattr(state, 'name', '?')}",
               fill=(255, 0, 255))

    for key, r in layout.counters.items():
        try:
            value: object = reader.read_int(frame, r, key)
        except DigitError:
            value = "ERR"
        d.rectangle([r.x, r.y, r.right - 1, r.bottom - 1], outline=(0, 255, 255), width=2)
        d.text((r.x, r.bottom + 1), f"{key.split('.')[-1]}={value}", fill=(0, 255, 255))

    for key, r in layout.hud.items():
        d.rectangle([r.x, r.y, r.right - 1, r.bottom - 1], outline=(255, 255, 0), width=2)
        d.text((r.x, r.y - 11), key, fill=(255, 255, 0))

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(f"  {out}  ({len(layout.buttons)} buttons, {len(layout.counters)} counters, "
          f"{len(layout.hud)} HUD)")


class _Still:
    """Minimal backend so the annotator can reuse Game's decoding."""

    def __init__(self, frame: np.ndarray):
        self._frame = frame
        self.clicks: list[tuple[int, int]] = []

    def grab(self) -> np.ndarray:
        return self._frame

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def close(self) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", help="a PNG to annotate; omit for all fixtures")
    ap.add_argument("-o", "--out", help="output path")
    ap.add_argument("--live", action="store_true", help="grab a frame from the running game")
    ap.add_argument("--url", default=None)
    args = ap.parse_args()

    outdir = ROOT / "verify_layout_output"
    if args.live:
        from tot.backends import DEFAULT_URL, PlaywrightBackend

        backend = PlaywrightBackend(url=args.url or DEFAULT_URL, headless=False)
        try:
            annotate(backend.grab(), Path(args.out) if args.out else outdir / "live.png")
        finally:
            backend.close()
        return 0

    if args.image:
        frame = np.array(Image.open(args.image).convert("RGB"))
        annotate(frame, Path(args.out) if args.out else outdir / Path(args.image).name)
        return 0

    for path in sorted((ROOT / "assets" / "screenshots").glob("*/*.png")):
        frame = np.array(Image.open(path).convert("RGB"))
        annotate(frame, outdir / path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
