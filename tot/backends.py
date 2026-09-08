"""Where frames come from and where clicks go.

Three implementations behind one small protocol:

``PlaywrightBackend``  the real thing — drives its own Chromium and talks to the
                      game canvas directly, so coordinates are canvas-relative and
                      the physical mouse is never touched.
``ImageBackend``       serves a PNG as "the current frame". Runs the entire stack
                      with no browser, which is how the fixture tests work.
``DesktopBackend``     fallback that screenshots the display and moves the real
                      mouse, for when driving the page from code is not an option.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Protocol

import numpy as np

from .errors import BackendError

DEFAULT_URL = (
    "https://www.themagical.nl/content/plugins/flash-emulator/"
    "flash-player.php?game=tower-of-terror"
)


class Backend(Protocol):
    """Everything the game needs from the outside world."""

    def grab(self) -> np.ndarray:
        """The current frame as an (H, W, 3) uint8 RGB array."""

    def click(self, x: int, y: int) -> None:
        """Click at a point in frame coordinates."""

    def close(self) -> None: ...


def _png_to_array(data: bytes) -> np.ndarray:
    from PIL import Image

    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


class ImageBackend:
    """A still frame. Clicks are recorded rather than delivered."""

    def __init__(self, path: str | Path):
        from PIL import Image

        self.path = Path(path)
        if not self.path.exists():
            raise BackendError(f"no such fixture image: {self.path}")
        self._frame = np.array(Image.open(self.path).convert("RGB"))
        self.clicks: list[tuple[int, int]] = []

    def grab(self) -> np.ndarray:
        return self._frame

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def close(self) -> None:  # nothing to release
        pass


class PlaywrightBackend:
    """Drives Chromium and talks to the game's canvas element.

    The canvas bounding box is the only calibration this needs: frames come from
    ``element.screenshot()`` and clicks are dispatched at canvas-relative
    coordinates, so window position, page scroll and display scaling are all
    irrelevant, and a long run never fights the user for the mouse.
    """

    #: Walks open shadow roots, because Ruffle mounts its canvas inside a
    #: <ruffle-player> custom element rather than in the light DOM.
    _FIND_JS = r"""
    () => {
      const found = [];
      const visit = (root) => {
        let els;
        try { els = root.querySelectorAll('*'); } catch (e) { return; }
        for (const el of els) {
          const tag = el.tagName.toLowerCase();
          if (tag === 'canvas' || tag === 'embed' || tag === 'object' ||
              tag.startsWith('ruffle-')) found.push(el);
          if (el.shadowRoot) visit(el.shadowRoot);
        }
      };
      visit(document);
      const canvases = found.filter(e => e.tagName.toLowerCase() === 'canvas');
      const pool = canvases.length ? canvases : found;
      let best = null, area = -1;
      for (const el of pool) {
        const r = el.getBoundingClientRect();
        const a = r.width * r.height;
        if (a > area) { best = el; area = a; }
      }
      return best;
    }
    """

    _INVENTORY_JS = r"""
    () => {
      const inv = {};
      const visit = (root) => {
        let els;
        try { els = root.querySelectorAll('*'); } catch (e) { return; }
        for (const el of els) {
          const tag = el.tagName.toLowerCase();
          if (['canvas','embed','object','iframe'].includes(tag) || tag.startsWith('ruffle-')) {
            const r = el.getBoundingClientRect();
            (inv[tag] = inv[tag] || []).push(Math.round(r.width) + 'x' + Math.round(r.height));
          }
          if (el.shadowRoot) visit(el.shadowRoot);
        }
      };
      visit(document);
      return {
        title: document.title,
        elements: inv,
        text: document.body ? document.body.innerText.replace(/\s+/g, ' ').slice(0, 300) : ''
      };
    }
    """

    #: Things a Flash-emulator page tends to put in front of the player.
    _PLAY_SELECTORS = (
        "ruffle-player", "#play", ".play", "#start", ".start",
        "[class*='play']", "[id*='play']", "button",
    )

    def __init__(
        self,
        url: str = DEFAULT_URL,
        headless: bool = False,
        viewport: tuple[int, int] = (1600, 1000),
        timeout_ms: int = 90_000,
        click_to_play: bool = True,
        min_canvas_px: int = 100_000,
        debug_dir: str | Path | None = "verify_layout_output",
    ):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise BackendError(
                "playwright is not installed. Run:\n"
                "    pip install playwright && playwright install chromium"
            ) from exc

        self.min_canvas_px = min_canvas_px
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless)
            self._page = self._browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}
            )
            self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            self._canvas = self._await_canvas(timeout_ms, click_to_play)
        except Exception:
            self.close()
            raise

    def _search_frames(self):
        """Largest player-ish element across every frame, or None."""
        best, best_area = None, -1
        for frame in self._page.frames:
            try:
                el = frame.evaluate_handle(self._FIND_JS).as_element()
            except Exception:
                continue
            if el is None:
                continue
            box = el.bounding_box()
            area = box["width"] * box["height"] if box else 0
            if area > best_area:
                best, best_area = el, area
        return best, best_area

    def _try_click_play(self) -> bool:
        """Click whatever looks like a start affordance. Ruffle often will not
        create its canvas until the splash is dismissed."""
        for sel in self._PLAY_SELECTORS:
            for frame in self._page.frames:
                try:
                    el = frame.query_selector(sel)
                    if el is None:
                        continue
                    box = el.bounding_box()
                    if box and box["width"] > 80 and box["height"] > 40:
                        el.click(timeout=2000)
                        return True
                except Exception:
                    continue
        try:  # last resort: the middle of the page
            self._page.mouse.click(
                self._page.viewport_size["width"] // 2, self._page.viewport_size["height"] // 2
            )
            return True
        except Exception:
            return False

    def _await_canvas(self, timeout_ms: int, click_to_play: bool):
        """Poll until the player canvas exists and has real size.

        A Flash emulator has to download and start a whole game, which takes far
        longer than a page load, and the canvas may not exist at all until a
        splash screen is dismissed. So this polls for the full timeout and tries
        clicking a start affordance along the way, rather than looking once.
        """
        started = time.monotonic()
        deadline = started + timeout_ms / 1000
        next_click = started + 4.0
        best_area_seen = 0
        while time.monotonic() < deadline:
            el, area = self._search_frames()
            best_area_seen = max(best_area_seen, int(area))
            if el is not None and area >= self.min_canvas_px:
                if click_to_play:
                    try:
                        el.click(timeout=3000)
                        self._page.wait_for_timeout(1500)
                    except Exception:
                        pass
                return el
            if click_to_play and time.monotonic() >= next_click:
                self._try_click_play()
                next_click = time.monotonic() + 10.0
            self._page.wait_for_timeout(500)

        raise BackendError(self._diagnose(best_area_seen, timeout_ms))

    def _diagnose(self, best_area_seen: int, timeout_ms: int) -> str:
        """Say what was actually on the page, and leave a screenshot behind."""
        lines = [
            f"could not find the game canvas after {timeout_ms / 1000:.0f}s.",
            f"largest player-ish element seen was {best_area_seen} px "
            f"(need {self.min_canvas_px}).",
        ]
        try:
            info = self._page.evaluate(self._INVENTORY_JS)
            lines.append(f"page title: {info.get('title')!r}")
            elements = info.get("elements") or {}
            lines.append(
                "elements found: "
                + (", ".join(f"{k}={v}" for k, v in elements.items()) if elements else "none")
            )
            if info.get("text"):
                lines.append(f"page text: {info['text'][:200]!r}")
        except Exception as exc:
            lines.append(f"(could not inspect the page: {exc})")
        lines.append(f"frames: {[f.url for f in self._page.frames]}")
        if self.debug_dir:
            try:
                self.debug_dir.mkdir(parents=True, exist_ok=True)
                shot = self.debug_dir / "canvas-not-found.png"
                self._page.screenshot(path=str(shot), full_page=True)
                lines.append(f"screenshot of what was on screen: {shot}")
            except Exception:
                pass
        lines.append("Run `python -m tools.probe_page` to watch the page load interactively.")
        return "\n  ".join(lines)

    @property
    def canvas_size(self) -> tuple[int, int]:
        box = self._canvas.bounding_box()
        if box is None:
            raise BackendError("the game canvas is no longer on the page")
        return int(box["width"]), int(box["height"])

    def grab(self) -> np.ndarray:
        return _png_to_array(self._canvas.screenshot())

    def click(self, x: int, y: int) -> None:
        self._canvas.click(position={"x": float(x), "y": float(y)})

    def close(self) -> None:
        for attr in ("_browser", "_pw"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                obj.close() if attr == "_browser" else obj.stop()
            except Exception:
                pass


class DesktopBackend:
    """Screenshots the display and moves the real mouse.

    A fallback for when the page cannot be driven from code. It costs you the
    mouse for the length of the run and needs the game window left alone, so
    prefer PlaywrightBackend unless that is impossible.
    """

    def __init__(self, region: tuple[int, int, int, int] | None = None):
        try:
            import mss  # noqa: F401
            import pyautogui  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise BackendError(
                "the desktop backend needs `pip install mss pyautogui`"
            ) from exc
        import mss

        self._sct = mss.mss()
        self.region = region

    def grab(self) -> np.ndarray:
        mon = self._sct.monitors[1] if self.region is None else {
            "left": self.region[0],
            "top": self.region[1],
            "width": self.region[2],
            "height": self.region[3],
        }
        shot = self._sct.grab(mon)
        return np.array(shot)[:, :, [2, 1, 0]]  # BGRA -> RGB

    def click(self, x: int, y: int) -> None:
        import pyautogui

        ox, oy = (self.region[0], self.region[1]) if self.region else (0, 0)
        pyautogui.click(ox + x, oy + y)

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass
