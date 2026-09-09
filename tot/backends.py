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

It also never *touches* the page. It clicks nothing on its own — you load the game
and pick the mode — and it never scrolls, resizes or otherwise moves what you are
watching. Capturing goes through CDP directly rather than through Playwright's
screenshot helper, for exactly that reason:

* ``page.screenshot(clip=...)`` refuses a clip outside the viewport, so reaching a
  panel below the fold means scrolling the page to it. That is visible.
* CDP's ``captureBeyondViewport`` reaches it without scrolling, but fires a
  ``resize`` event on the page for *every* capture — 47 times a second, into an
  emulator that relays out its canvas on resize. Also visible, and a fair suspect
  for the crashes.
* CDP with ``captureBeyondViewport: false`` moves nothing at all, and is 6 ms
  faster than the Playwright helper besides. So the capture rect is intersected
  with whatever is currently on screen, and the bot works with what it can see.

If the panel is off-screen the crop comes back short, the panel is simply not
found, and the bot keeps waiting — rather than yanking your view to reach it.
"""

from __future__ import annotations

import base64
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


def visible_clip(
    box: dict[str, float] | None,
    region: Rect | None,
    view: dict[str, float],
) -> dict[str, float]:
    """The rect to capture, in page coordinates, trimmed to what is on screen.

    ``box`` is the canvas in page coordinates, ``region`` the panel crop within
    it, ``view`` the window's scroll position and size. Trimming rather than
    scrolling is the whole point: if the panel is half off the bottom of the
    window, this returns the half that is showing, the panel is not found, and
    the bot waits — instead of moving the page out from under the person
    watching the game.
    """
    if box is None:
        return {"x": float(view["x"]), "y": float(view["y"]),
                "width": float(view["w"]), "height": float(view["h"])}
    x0, y0 = box["px"], box["py"]
    x1, y1 = x0 + box["w"], y0 + box["h"]
    if region is not None:
        x0, y0 = x0 + region.x, y0 + region.y
        x1, y1 = x0 + region.w, y0 + region.h
    x0, y0 = max(x0, view["x"]), max(y0, view["y"])
    x1 = min(x1, view["x"] + view["w"])
    y1 = min(y1, view["y"] + view["h"])
    return {"x": float(x0), "y": float(y0),
            "width": float(max(1, x1 - x0)), "height": float(max(1, y1 - y0))}


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
      return {px: r.left + window.scrollX, py: r.top + window.scrollY,
              w: r.width, h: r.height};
    }
    """

    #: Where the window is looking, in page coordinates.
    _VIEW_JS = "() => ({x: window.scrollX, y: window.scrollY, " \
               "w: window.innerWidth, h: window.innerHeight})"

    def __init__(
        self,
        url: str = DEFAULT_URL,
        headless: bool = False,
        viewport: tuple[int, int] | None = None,
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
        self._clip: dict[str, float] | None = None

        args = list(_CHROME_ARGS)
        if uncapped_capture:
            args += ["--disable-frame-rate-limit", "--disable-gpu-vsync"]
        # A maximised window is the one way to make sure the whole game is on
        # screen without the bot ever having to move the page to reach part of it.
        if viewport is None and not headless:
            args.append("--start-maximized")

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless, args=args)
            self._page = self._browser.new_page(
                no_viewport=viewport is None,
                **({} if viewport is None else
                   {"viewport": {"width": viewport[0], "height": viewport[1]}}),
            )
            try:
                self._cdp: Any = self._page.context.new_cdp_session(self._page)
            except Exception:  # pragma: no cover - non-Chromium, in theory
                self._cdp = None
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
        # Deliberately no scroll_into_view_if_needed: moving the page to bring the
        # game into frame is the one thing this class must never do.
        self._canvas = best
        self._box = self._page.evaluate(self._BOX_JS, best)
        self._recompute_clip()
        return True

    @property
    def canvas_size(self) -> tuple[int, int] | None:
        return None if self._box is None else (int(self._box["w"]), int(self._box["h"]))

    # -- frames ---------------------------------------------------------------
    def _recompute_clip(self) -> dict[str, float]:
        """What to capture, in page coordinates, intersected with the window.

        Cached, because the hot path must not spend a round trip per frame asking
        the page where it is. It is recomputed whenever the region changes or the
        canvas is re-attached — and if you scroll the panel off screen in between,
        the crop comes back short, the probes miss, and that re-attach happens on
        the very next tick.
        """
        self._clip = visible_clip(
            self._box, self._region, self._page.evaluate(self._VIEW_JS)
        )
        return self._clip

    def visible_fraction(self) -> float:
        """How much of the game canvas is actually on screen, 0.0 to 1.0."""
        if self._box is None:
            return 0.0
        view = self._page.evaluate(self._VIEW_JS)
        w = min(self._box["px"] + self._box["w"], view["x"] + view["w"]) - max(
            self._box["px"], view["x"])
        h = min(self._box["py"] + self._box["h"], view["y"] + view["h"]) - max(
            self._box["py"], view["y"])
        area = self._box["w"] * self._box["h"]
        return max(0.0, w) * max(0.0, h) / area if area else 0.0

    def grab(self) -> np.ndarray:
        if not self.attach() or self._clip is None:
            self._recompute_clip()
        assert self._clip is not None
        return _png_to_array(self._capture(self._clip))

    def _capture(self, clip: dict[str, float]) -> bytes:
        if self._cdp is not None:
            reply = self._cdp.send(
                "Page.captureScreenshot",
                {
                    "format": "png",
                    "clip": {**clip, "scale": 1},
                    # Both False on purpose: see the module docstring. Either one
                    # true means the page moves under the person watching it.
                    "captureBeyondViewport": False,
                    "fromSurface": True,
                },
            )
            return base64.b64decode(reply["data"])
        return self._page.screenshot(clip=clip)

    def set_region(self, region: Rect | None) -> None:
        if region is not None and self._box is None:
            raise BrowserError("cannot clip to the panel before the canvas is attached")
        self._region = region
        if region is None:
            # Back to searching: the page may have reflowed, so re-measure rather
            # than trusting a box from before whatever moved.
            self._canvas, self._box = None, None
            self.attach()
        self._recompute_clip()

    # -- acting ---------------------------------------------------------------
    def click(self, x: int, y: int) -> None:
        """Click a point in the current frame. Never scrolls to reach it."""
        if self._box is None:
            raise BrowserError("no canvas attached, so there is nothing to click on")
        ox, oy = self._box["px"], self._box["py"]
        if self._region is not None:
            ox += self._region.x
            oy += self._region.y
        # The mouse works in viewport coordinates and the box is in page
        # coordinates, so this reads the scroll position rather than assuming it.
        # Clicks are rare enough that the round trip does not matter.
        view = self._page.evaluate(self._VIEW_JS)
        self._page.mouse.click(ox + x - view["x"], oy + y - view["y"])

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
        lines = [
            f"the RideControl panel was not found at {self.url}"
            if self._box is not None
            else f"no game canvas at {self.url}"
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
        if self._box is not None:
            seen = self.visible_fraction()
            lines.append(
                f"canvas is {int(self._box['w'])}x{int(self._box['h'])}, "
                f"{seen:.0%} of it on screen"
            )
            if seen < 0.99:
                lines.append(
                    "part of the game is outside the window, and this bot will not "
                    "scroll your page to reach it. Enlarge the window or scroll the "
                    "RideControl panel into view yourself."
                )
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
