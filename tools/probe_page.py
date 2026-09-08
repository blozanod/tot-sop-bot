"""Watch the game page load and report what is actually on it.

Run this when the backend cannot find the canvas. It opens the page, prints an
inventory of every player-ish element every couple of seconds, saves screenshots,
and then leaves the browser open so you can look.

    python -m tools.probe_page
    python -m tools.probe_page --url "https://..." --seconds 120

Send me the output and the screenshots and I can fix the detector.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tot.backends import DEFAULT_URL, PlaywrightBackend  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verify_layout_output"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--no-click", action="store_true", help="do not click anything")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=args.headless)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})

    print(f"opening {args.url}")
    page.goto(args.url, timeout=90_000, wait_until="domcontentloaded")

    deadline = time.time() + args.seconds
    tick = 0
    clicked = False
    try:
        while time.time() < deadline:
            info = page.evaluate(PlaywrightBackend._INVENTORY_JS)
            elements = info.get("elements") or {}
            print(f"\n[{tick * 2:3d}s] title={info.get('title')!r}")
            print(f"       frames: {len(page.frames)}")
            if elements:
                for tag, sizes in elements.items():
                    print(f"       {tag}: {sizes}")
            else:
                print("       no canvas / embed / object / ruffle-* elements yet")
            if info.get("text"):
                print(f"       text: {info['text'][:160]!r}")

            if tick in (2, 6) and not args.no_click:
                print("       -> clicking the middle of the page to dismiss any splash")
                try:
                    page.mouse.click(800, 500)
                    clicked = True
                except Exception as exc:
                    print(f"       (click failed: {exc})")

            shot = OUT / f"probe-{tick * 2:03d}s.png"
            page.screenshot(path=str(shot))
            tick += 1
            page.wait_for_timeout(2000)
    finally:
        print(f"\nscreenshots in {OUT}")
        print(f"clicked during probe: {clicked}")
        if not args.headless:
            try:
                input("browser left open — press Enter to close it. ")
            except EOFError:
                pass
        browser.close()
        pw.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
