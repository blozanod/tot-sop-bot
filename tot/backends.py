"""Where frames come from and where clicks go.

``PlaywrightBackend``  the real thing — drives its own Chromium and screenshots a
                       clipped rectangle of the page.
``ImageBackend``       serves a PNG as "the current frame", so the whole stack runs
                       with no browser. That is how the fixture tests work.

Two things make the live backend fast, and both are about *not capturing pixels*:

1. Once the panel has been located, ``set_region`` clips every subsequent
   screenshot to it. Capturing the whole canvas costs ~85 ms; the panel crop costs
   ~19 ms, and the pixels outside it were never read.
2. Chromium is launched with ``--disable-frame-rate-limit``. Without it a
   screenshot waits for the compositor's next 30 Hz frame, which by itself put a
   ~33 ms floor under every capture regardless of size.

It also never clicks anything on its own. You load the game and pick the mode; the
bot waits until it can see the RideControl panel. Blind click-to-play was both a
way to lose your mode choice and a good way to upset the emulator.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .errors import BrowserError, RuffleCrashed
from .geometry import Rect

DEFAULT_URL = (
    "https://www.themagical.nl/content/plugins/flash-emulator/"
    "flash-player.php?game=tower-of-terror"
)


class Backend(Protocol):
    """Everything the game needs from the outside world."""

    def grab(self) -> np.ndarray:
        """The current frame as an (H, W, 3) uint8 RGB array."""

    def set_region(self, region: Rect | None) -> None:
        """Restrict later grabs to ``region`` of the current frame, or undo that."""

    def click(self, x: int, y: int) -> None:
        """Click at a point in the *current* frame's coordinates."""

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
            raise BrowserError(f"no such fixture image: {self.path}")
        self._full = np.array(Image.open(self.path).convert("RGB"))
        self._region: Rect | None = None
        self.clicks: list[tuple[int, int]] = []

    def grab(self) -> np.ndarray:
        r = self._region
        if r is None:
            return self._full
        return self._full[r.y : r.bottom, r.x : r.right]

    def set_region(self, region: Rect | None) -> None:
        self._region = region

    def click(self, x: int, y: int) -> None:
        r = self._region
        self.clicks.append((x, y) if r is None else (x + r.x, y + r.y))

    def close(self) -> None:  # nothing to release
        pass


#: Ruffle reads this before it boots. Everything here either removes an overlay
#: that would sit on top of the panel, or removes a reason for Ruffle to give up
#: mid-run — ``maxExecutionDuration`` in particular defaults to 15 seconds, after
#: which a slow ActionScript frame is treated as a hang and the player panics.
RUFFLE_CONFIG: dict[str, Any] = {
    "autoplay": "on",
    "unmuteOverlay": "hidden",
    "splashScreen": False,
    "warnOnUnsupportedContent": False,
    "contextMenu": False,
    "showSwfDownload": False,
    "maxExecutionDuration": 3600,
    "logLevel": "error",
}

#: Flags that matter, and why:
#:   frame-rate-limit  a capped compositor puts a 33 ms floor under every capture
#:   backgrounding     a window that loses focus otherwise gets throttled to 1 Hz
#:   mute-audio        the game's sound is pure cost to us, and muting it also
#:                     stops Ruffle wanting a click to unmute
_CHROME_ARGS = (
    "--mute-audio",
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=CalculateNativeWinOcclusion",
)


class PlaywrightBackend:
    """Drives Chromium and screenshots a rectangle of the page."""

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

    #: Ruffle renders its failures into its own shadow root: #panic for a hard
    #: crash, #message-overlay for the softer "this content is not supported"
    #: banner. Both cover the panel, so both end the run rather than being read
    #: as a strange-looking game.
    _TROUBLE_JS = r"""
    () => {
      let hit = null;
      const visit = (root) => {
        let els;
        try { els = root.querySelectorAll('*'); } catch (e) { return; }
        for (const el of els) {
          const id = (el.id || '').toLowerCase();
          if (!hit && (id === 'panic' || id === 'message-overlay' ||
                       id === 'panic-body' || id === 'error')) {
            hit = (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400) || id;
          }
          if (el.shadowRoot) visit(el.shadowRoot);
        }
      };
      visit(document);
      return hit;
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

    _BOX_JS = r"""
    (el) => {
      const r = el.getBoundingClientRect();
      return {vx: r.left, vy: r.top, px: r.left + window.scrollX,
              py: r.top + window.scrollY, w: r.width, h: r.height};
    }
    """

    def __init__(
        self,
        url: str = DEFAULT_URL,
        headless: bool = False,
        viewport: tuple[int, int] = (1400, 900),
        timeout_ms: int = 90_000,
        min_canvas_px: int = 100_000,
        uncapped_capture: bool = True,
        ruffle_config: dict[str, Any] | None = None,
        debug_dir: str | Path | None = "debug_output",
    ):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise BrowserError(
                "playwright is not installed. Run:\n"
                "    pip install playwright && playwright install chromium"
            ) from exc

        self.url = url
        self.min_canvas_px = min_canvas_px
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self._region: Rect | None = None
        self._canvas: Any = None
        self._box: dict[str, float] | None = None

        args = list(_CHROME_ARGS)
        if uncapped_capture:
            args += ["--disable-frame-rate-limit", "--disable-gpu-vsync"]

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless, args=args)
            self._page = self._browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}
            )
            cfg = json.dumps({**RUFFLE_CONFIG, **(ruffle_config or {})})
            self._page.add_init_script(
                "window.RufflePlayer = window.RufflePlayer || {};"
                "window.RufflePlayer.config = Object.assign("
                f"{{}}, window.RufflePlayer.config || {{}}, {cfg});"
            )
            self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        except Exception:
            self.close()
            raise

    # -- attaching ------------------------------------------------------------
    def attach(self) -> bool:
        """Try to find the player canvas. Safe to call repeatedly.

        Returns False rather than raising while the emulator is still starting —
        the caller is in a wait loop, not an error path.
        """
        if self._canvas is not None and self._box is not None:
            return True
        best, area = None, -1.0
        for frame in self._page.frames:
            try:
                el = frame.evaluate_handle(self._FIND_JS).as_element()
            except Exception:
                continue
            if el is None:
                continue
            box = el.bounding_box()
            a = box["width"] * box["height"] if box else 0.0
            if a > area:
                best, area = el, a
        if best is None or area < self.min_canvas_px:
            return False
        try:
            best.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        self._canvas = best
        self._box = self._page.evaluate(self._BOX_JS, best)
        return True

    @property
    def canvas_size(self) -> tuple[int, int] | None:
        return None if self._box is None else (int(self._box["w"]), int(self._box["h"]))

    # -- frames ---------------------------------------------------------------
    def _clip(self) -> dict[str, float]:
        """The rectangle to capture, in page coordinates."""
        if self._box is None:
            vp = self._page.viewport_size or {"width": 1400, "height": 900}
            return {"x": 0.0, "y": 0.0, "width": float(vp["width"]), "height": float(vp["height"])}
        ox, oy = self._box["px"], self._box["py"]
        w, h = self._box["w"], self._box["h"]
        if self._region is not None:
            r = self._region
            return {"x": ox + r.x, "y": oy + r.y, "width": float(r.w), "height": float(r.h)}
        return {"x": ox, "y": oy, "width": w, "height": h}

    def grab(self) -> np.ndarray:
        self.attach()
        return _png_to_array(self._page.screenshot(clip=self._clip()))

    def set_region(self, region: Rect | None) -> None:
        if region is not None and self._box is None:
            raise BrowserError("cannot clip to the panel before the canvas is attached")
        self._region = region

    # -- acting ---------------------------------------------------------------
    def click(self, x: int, y: int) -> None:
        if self._box is None:
            raise BrowserError("no canvas attached, so there is nothing to click on")
        ox, oy = self._box["vx"], self._box["vy"]
        if self._region is not None:
            ox += self._region.x
            oy += self._region.y
        self._page.mouse.click(ox + x, oy + y)

    # -- the emulator ---------------------------------------------------------
    def trouble(self) -> str | None:
        """Ruffle's own error text, if it is showing an error screen."""
        try:
            return self._page.evaluate(self._TROUBLE_JS)
        except Exception:
            return None

    def check(self) -> None:
        """Raise if the emulator has died. Cheap enough to call between ticks."""
        msg = self.trouble()
        if msg:
            raise RuffleCrashed(f"the Flash emulator gave up: {msg}")

    def reload(self, timeout_ms: int = 90_000) -> None:
        """Start the page over. The game restarts, so you pick the mode again."""
        self._canvas, self._box, self._region = None, None, None
        self._page.goto(self.url, timeout=timeout_ms, wait_until="domcontentloaded")

    # -- diagnosis ------------------------------------------------------------
    def describe_page(self) -> str:
        """What is actually on the page. Used when the canvas never turns up."""
        lines = [f"no game canvas at {self.url}"]
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
                shot = self.debug_dir / f"page-{int(time.time())}.png"
                self._page.screenshot(path=str(shot), full_page=True)
                lines.append(f"screenshot: {shot}")
            except Exception:
                pass
        lines.append("Run `python -m tools.probe_page` to watch the page load.")
        return "\n  ".join(lines)

    def close(self) -> None:
        for attr in ("_browser", "_pw"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                obj.close() if attr == "_browser" else obj.stop()
            except Exception:
                pass
