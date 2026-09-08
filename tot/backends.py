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

    def __init__(
        self,
        url: str = DEFAULT_URL,
        headless: bool = False,
        viewport: tuple[int, int] = (1600, 1000),
        timeout_ms: int = 60_000,
        click_to_play: bool = True,
    ):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise BackendError(
                "playwright is not installed. Run:\n"
                "    pip install playwright && playwright install chromium"
            ) from exc

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless)
            self._page = self._browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}
            )
            self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            self._canvas = self._find_canvas(timeout_ms)
            if click_to_play:
                self._canvas.click()
                self._page.wait_for_timeout(1500)
        except Exception:
            self.close()
            raise

    def _find_canvas(self, timeout_ms: int):
        """The largest <canvas> on the page or in any of its frames.

        Flash emulators commonly nest the player in an iframe, and some pages keep
        a decorative canvas around, so pick by area rather than by document order.
        """
        self._page.wait_for_timeout(min(timeout_ms, 2000))
        best, best_area = None, 0
        for frame in self._page.frames:
            try:
                for handle in frame.query_selector_all("canvas"):
                    box = handle.bounding_box()
                    if box and box["width"] * box["height"] > best_area:
                        best, best_area = handle, box["width"] * box["height"]
            except Exception:
                continue
        if best is None or best_area < 100_000:
            raise BackendError(
                "could not find the game canvas. The emulator may still be loading, "
                "the page may have changed, or it may need a click to start. "
                "Try headless=False and watch what happens."
            )
        return best

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
