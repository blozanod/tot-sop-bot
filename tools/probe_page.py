"""Watch the game page load and report what is actually on it.

Run this when the bot cannot find the canvas. It opens the page, prints an
inventory of every player-ish element every couple of seconds, saves screenshots,
and then leaves the browser open so you can look.

    python -m tools.probe_page
    python -m tools.probe_page --url "https://..." --seconds 120

It never clicks anything unless you pass ``--click``. Send me the output and the
screenshots and I can fix the detector.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot.backends import DEFAULT_URL, PlaywrightBackend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "debug_output"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--click", action="store_true",
                    help="click the middle of the page twice, to test a splash screen")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    backend = PlaywrightBackend(url=args.url, headless=args.headless, debug_dir=OUT)
    page = backend._page
    print(f"opened {args.url}")

    deadline = time.time() + args.seconds
    tick = 0
    try:
        while time.time() < deadline:
            info = page.evaluate(PlaywrightBackend._INVENTORY_JS)
            elements = info.get("elements") or {}
            print(f"\n[{tick * 2:3d}s] title={info.get('title')!r}  frames={len(page.frames)}")
            for tag, sizes in elements.items():
                print(f"       {tag}: {sizes}")
            if not elements:
                print("       no canvas / embed / object / ruffle-* elements yet")
            if info.get("text"):
                print(f"       text: {info['text'][:160]!r}")
            trouble = backend.trouble()
            if trouble:
                print(f"       !! the emulator is showing an error: {trouble}")
            size = backend.canvas_size
            if size:
                print(f"       canvas is {size[0]}x{size[1]}, "
                      f"{backend._frame_seq} screencast frames so far")

            if args.click and tick in (2, 6):
                print("       -> clicking the middle of the page")
                try:
                    page.mouse.click(700, 450)
                except Exception as exc:
                    print(f"       (click failed: {exc})")

            frame = backend.grab()
            from PIL import Image
            Image.fromarray(frame).save(OUT / f"probe-{tick * 2:03d}s.png")
            tick += 1
            page.wait_for_timeout(2000)
    finally:
        print(f"\nscreenshots in {OUT}")
        if not args.headless:
            try:
                input("browser left open — press Enter to close it. ")
            except EOFError:
                pass
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
