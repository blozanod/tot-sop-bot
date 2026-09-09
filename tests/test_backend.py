"""The backend contract: clipping, click mapping, and giving up on a dead emulator.

The live browser is not reachable from the test machine, so these use the still
image backend and a stub — but they pin the parts of the protocol that the
Playwright backend has to honour.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tot import Game, PanelError, RuffleCrashed
from tot.backends import ImageBackend, _to_array
from tot.geometry import Rect

SHOTS = Path(__file__).resolve().parents[1] / "assets" / "screenshots"
FRAME = SHOTS / "states" / "10-dispatch-armed-doors-closed-153334.png"


def test_the_backend_is_left_clipped_to_the_panel() -> None:
    g = Game.from_image(FRAME)
    region = g.layout.region
    assert g.backend._region == region
    assert g.backend.grab().shape[:2] == (region.h, region.w)
    # and the crop is a real saving over the frame it came from
    full = g.backend._full
    assert region.w * region.h < full.shape[0] * full.shape[1]


def test_a_region_clipped_grab_is_the_same_pixels_as_the_slice() -> None:
    b = ImageBackend(FRAME)
    full = b.grab()
    b.set_region(Rect(10, 20, 100, 50))
    assert np.array_equal(b.grab(), full[20:70, 10:110])
    b.set_region(None)
    assert np.array_equal(b.grab(), full)


def test_clicks_are_mapped_out_of_the_region() -> None:
    b = ImageBackend(FRAME)
    b.set_region(Rect(10, 20, 100, 50))
    b.click(3, 4)
    assert b.clicks == [(13, 24)]


class _Panicking:
    """A backend whose emulator has died: it hands back frames with no panel."""

    def __init__(self) -> None:
        self.frame = np.zeros((200, 300, 3), np.uint8)
        self.checks = 0

    def grab(self) -> np.ndarray:
        return self.frame

    def set_region(self, region: Rect | None) -> None:
        pass

    def click(self, x: int, y: int) -> None:
        pass

    def check(self) -> None:
        self.checks += 1
        raise RuffleCrashed("the Flash emulator gave up: Something went wrong!")

    def close(self) -> None:
        pass


def test_waiting_for_the_panel_gives_up_when_the_emulator_dies() -> None:
    """A crashed emulator must not be mistaken for "still on the mode chooser"."""
    backend = _Panicking()
    g = Game(backend)
    with pytest.raises(RuffleCrashed):
        g.wait_for_panel(timeout=5, poll=0.0)
    assert backend.checks == 1
    assert not g.panel_visible


def test_no_panel_means_no_readings() -> None:
    g = Game(_NoPanel())
    assert not g.refresh()
    with pytest.raises(PanelError):
        _ = g.elevator1.can_dispatch
    with pytest.raises(PanelError):
        _ = g.tv_room1.waiting_is_full


class _NoPanel(_Panicking):
    def check(self) -> None:  # a healthy emulator showing something else
        pass


# -- the frame is cropped here, never in the browser -------------------------

class _Im:
    """The bit of PIL's Image interface the crop path uses."""

    def __init__(self, arr, mode="RGB"):
        self.arr, self.mode = arr, mode
        self.size = (arr.shape[1], arr.shape[0])
        self.cropped: tuple | None = None

    def crop(self, box):
        x0, y0, x1, y1 = box
        out = _Im(self.arr[y0:y1, x0:x1], self.mode)
        out.cropped = box
        return out

    def convert(self, mode):
        return _Im(self.arr[..., :3], mode)

    def __array__(self, dtype=None, copy=None):
        return self.arr


def test_the_crop_happens_on_the_decoded_frame() -> None:
    """The browser is never asked for a rectangle — it hands over the whole
    window and the panel is sliced out of it here."""
    full = np.arange(40 * 60 * 3, dtype=np.uint8).reshape(40, 60, 3)
    out = _to_array(_Im(full), Rect(10, 5, 20, 12))
    assert out.shape == (12, 20, 3)
    assert np.array_equal(out, full[5:17, 10:30])


def test_an_rgba_frame_loses_its_alpha_without_a_convert_pass() -> None:
    rgba = np.zeros((8, 8, 4), np.uint8)
    rgba[..., :3] = 200
    rgba[..., 3] = 255
    out = _to_array(_Im(rgba, "RGBA"), None)
    assert out.shape == (8, 8, 3)
    assert (out == 200).all()


def test_no_region_means_the_whole_frame() -> None:
    full = np.zeros((10, 12, 3), np.uint8)
    assert _to_array(_Im(full), None).shape == (10, 12, 3)


# -- clicking maps frame pixels back to CSS pixels ---------------------------

class _Mouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


def _fake_live_backend(scale: float, region: Rect | None):
    from tot.backends import PlaywrightBackend

    b = PlaywrightBackend.__new__(PlaywrightBackend)
    b._region, b._scale = region, scale
    b._page = type("P", (), {"mouse": _Mouse()})()
    return b


def test_a_click_is_offset_by_the_region() -> None:
    b = _fake_live_backend(1.0, Rect(100, 50, 900, 300))
    b.click(30, 20)
    assert b._page.mouse.clicks == [(130.0, 70.0)]


def test_a_click_is_scaled_back_on_a_hidpi_frame() -> None:
    """A frame comes back at the display's real resolution; the mouse works in
    CSS pixels, so a 2x screen needs the halving or every click misses."""
    b = _fake_live_backend(2.0, Rect(200, 100, 900, 300))
    b.click(60, 40)
    assert b._page.mouse.clicks == [(130.0, 70.0)]
