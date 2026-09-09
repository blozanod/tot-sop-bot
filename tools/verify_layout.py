"""Draw what the detector found onto a frame, so you can check it at a glance.

    python -m tools.verify_layout                       # every calibration frame
    python -m tools.verify_layout --live                # the running game
    python -m tools.verify_layout shot.png -o out.png   # one image

Buttons are outlined and labelled with the state read from them, counters with
ZERO / FULL / OTHER. If a box is in the wrong place or a colour is misread, it is
obvious in the output image rather than three hours into a run.

The image is the panel crop, not the whole canvas — that is what the bot actually
looks at, so that is what you should be checking.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot import Game  # noqa: E402
from tot.backends import DEFAULT_URL, ImageBackend, PlaywrightBackend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "debug_output"


def annotate(game: Game, out: Path) -> None:
    im = Image.fromarray(game.frame).convert("RGB")
    d = ImageDraw.Draw(im)
    for key, r in game.layout.buttons.items():
        state = game._states[key]
        d.rectangle([r.x, r.y, r.right - 1, r.bottom - 1], outline=(255, 0, 255), width=2)
        d.text((r.x + 2, r.y - 10), f"{key.split('.')[-1]}={state.name}", fill=(255, 0, 255))
    for key, r in game.layout.counters.items():
        d.rectangle([r.x, r.y, r.right - 1, r.bottom - 1], outline=(0, 255, 255), width=2)
        d.text((r.x, r.bottom + 1), game._count(key).name, fill=(0, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(
        f"  {out}  ({len(game.layout.buttons)} buttons, {len(game.layout.counters)} counters, "
        f"crop {game.layout.region.w}x{game.layout.region.h} at "
        f"{game.layout.region.x},{game.layout.region.y})"
    )


def _still(path: Path, out: Path) -> int:
    game = Game(ImageBackend(path))
    if not game.refresh():
        print(f"  {path.name}: no RideControl panel found", file=sys.stderr)
        return 1
    annotate(game, out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", help="a PNG to annotate; omit for all fixtures")
    ap.add_argument("-o", "--out", help="output path")
    ap.add_argument("--live", action="store_true", help="grab a frame from the running game")
    ap.add_argument("--url", default=None)
    ap.add_argument("--wait", type=float, default=300.0,
                    help="seconds to wait for you to start a game (--live)")
    args = ap.parse_args()

    if args.live:
        backend = PlaywrightBackend(url=args.url or DEFAULT_URL, headless=False)
        game = Game(backend)
        try:
            print(f"load the game and pick a mode — waiting up to {args.wait:.0f}s")
            started = time.monotonic()
            if not game.wait_for_panel(timeout=args.wait):
                OUTDIR.mkdir(parents=True, exist_ok=True)
                raw = OUTDIR / "live-raw.png"
                Image.fromarray(backend.grab()).save(raw)
                print(
                    f"the panel never appeared within {args.wait:.0f}s.\n"
                    f"what was on screen is in {raw} — if that shows the mode chooser, "
                    f"pick a game first; if it shows the panel, send me the image and "
                    f"I will adjust the detector.\n\n{backend.describe_page()}",
                    file=sys.stderr,
                )
                return 1
            print(f"panel found after {time.monotonic() - started:.1f}s")
            annotate(game, Path(args.out) if args.out else OUTDIR / "live.png")
            return 0
        finally:
            game.close()

    if args.image:
        path = Path(args.image)
        return _still(path, Path(args.out) if args.out else OUTDIR / path.name)

    return max(
        _still(p, OUTDIR / p.name)
        for p in sorted((ROOT / "assets" / "screenshots").glob("*/*.png"))
    )


if __name__ == "__main__":
    raise SystemExit(main())
