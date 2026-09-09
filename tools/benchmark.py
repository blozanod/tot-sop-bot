"""How long the bot spends looking at the screen.

    python -m tools.benchmark          # the perception layer, no browser
    python -m tools.benchmark --live   # the whole tick, against the real game

The offline numbers are the part this repo controls. The live number includes the
screenshot, which is the browser's cost and is where nearly all of the time goes.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot import Game  # noqa: E402
from tot.backends import DEFAULT_URL, PlaywrightBackend  # noqa: E402
from tot.geometry import build_layout  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "assets/screenshots/layout/02-tvr1-loaded-preshow-ready-153147.png"
CROP = ROOT / "assets/screenshots/states/10-dispatch-armed-doors-closed-153334.png"


def timed(fn, n: int) -> float:
    fn()
    t = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t) / n * 1000


def offline() -> None:
    for label, path in (("full window", FULL), ("panel crop", CROP)):
        frame = np.array(Image.open(path).convert("RGB"))
        h, w = frame.shape[:2]
        ms = timed(lambda: build_layout(frame), 10)
        print(f"  locate the panel, {label:11s} {w}x{h}  {ms:7.1f} ms  (once per run)")

    g = Game.from_image(CROP)
    print(f"  read all 32 buttons                       {timed(g.refresh, 500):7.2f} ms")
    print(
        "  read one counter                          "
        f"{timed(lambda: (g._counts.clear(), g._count('tv_room1.loaded')), 500):7.2f} ms"
    )

    def all_counters() -> None:
        g._counts.clear()
        for k in g.layout.counters:
            g._count(k)

    print(f"  read all 13 counters                      {timed(all_counters, 200):7.2f} ms")


def live(url: str, wait: float) -> int:
    backend = PlaywrightBackend(url=url, headless=False)
    game = Game(backend)
    try:
        print(f"load the game and pick a mode — waiting up to {wait:.0f}s")
        if not game.wait_for_panel(timeout=wait):
            print("never saw the panel", file=sys.stderr)
            return 1
        r = game.layout.region
        print(f"  panel crop is {r.w}x{r.h}; the game canvas is {backend.canvas_size}")
        print(f"  full tick (frame + decode + 32 buttons)   {timed(game.refresh, 100):7.1f} ms")

        def with_counter() -> None:
            game.refresh()
            game.tv_room1.loaded_is_full

        ms = timed(with_counter, 100)
        print(f"  full tick + one counter                   {ms:7.1f} ms  -> {1000 / ms:.0f} Hz")
        return 0
    finally:
        game.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--wait", type=float, default=300.0)
    args = ap.parse_args()
    if args.live:
        return live(args.url, args.wait)
    offline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
