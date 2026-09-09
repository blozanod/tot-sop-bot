"""The backend contract: clipping, click mapping, and giving up on a dead emulator.

The live browser is not reachable from the test machine, so these use the still
image backend and a stub — but they pin the parts of the protocol that the
Playwright backend has to honour.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from tot import AttractionState, Game, PanelError, RuffleCrashed
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
        self.moves: list[tuple[float, float]] = []

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))


def _fake_live_backend(scale: float, region: Rect | None, frame=(1600, 1000)):
    from tot.backends import PlaywrightBackend

    b = PlaywrightBackend.__new__(PlaywrightBackend)
    b._region, b._scale, b._frame_size = region, scale, frame
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


def test_the_pointer_is_parked_off_the_panel_after_a_click() -> None:
    """A button under the cursor may render its rollover state, and the bot
    would then be reading a colour it caused itself."""
    region = Rect(100, 50, 900, 300)
    b = _fake_live_backend(1.0, region)
    b.click(30, 20)
    (px, py), = b._page.mouse.moves
    assert not (region.x <= px < region.right and region.y <= py < region.bottom)


def test_parking_stays_inside_the_frame_when_the_panel_is_at_the_top() -> None:
    region = Rect(0, 0, 900, 300)
    b = _fake_live_backend(1.0, region, frame=(1600, 1000))
    b.click(5, 5)
    (px, py), = b._page.mouse.moves
    assert 0 <= px < 1600 and 0 <= py < 1000
    assert not (region.x <= px < region.right and region.y <= py < region.bottom)


def test_no_region_means_nowhere_to_park() -> None:
    b = _fake_live_backend(1.0, None)
    b.click(10, 10)
    assert b._page.mouse.clicks == [(10.0, 10.0)]
    assert b._page.mouse.moves == []


# -- pressing a button the panel has not answered yet ------------------------

class _Panel:
    """A backend serving one fixture frame, so a real Game can be driven."""

    def __init__(self) -> None:
        from PIL import Image

        self.full = np.array(Image.open(FRAME).convert("RGB"))
        self.region: Rect | None = None
        self.clicks: list[tuple[int, int]] = []

    def grab(self) -> np.ndarray:
        r = self.region
        return self.full if r is None else self.full[r.y : r.bottom, r.x : r.right]

    def set_region(self, region: Rect | None) -> None:
        self.region = region

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def close(self) -> None:
        pass


def test_a_button_is_not_pressed_again_until_the_panel_answers() -> None:
    """The frame the bot decides from was painted before its last click landed.
    Without this, a toggle flips on every tick, forever."""
    g = Game(_Panel())
    assert g.refresh()
    assert g.control.toggle_attraction() is True
    for _ in range(20):
        g.refresh()                       # the fixture never changes: no answer
        assert g.control.toggle_attraction() is False
    assert len(g.backend.clicks) == 1


def test_the_press_is_allowed_again_once_the_colour_moves() -> None:
    g = Game(_Panel())
    g.refresh()
    assert g.control.toggle_attraction() is True
    # pretend the panel answered: the button is now a different state
    g._states["control.attraction"] = AttractionState.CLOSED
    g._acted.pop("control.attraction", None)
    assert g.control.toggle_attraction() is True
    assert len(g.backend.clicks) == 2


def test_a_dropped_click_is_retried_rather_than_deadlocking() -> None:
    """If the game simply ignores a click, the button must not be stuck for good."""
    g = Game(_Panel(), reclick_after=0.05)
    g.refresh()
    assert g.tv_room1.load() is True
    assert g.tv_room1.load() is False
    time.sleep(0.06)
    assert g.tv_room1.load() is True


def test_the_guard_can_be_turned_off() -> None:
    g = Game(_Panel(), reclick_after=0.0)
    g.refresh()
    assert g.elevator1.dispatch() is True
    assert g.elevator1.dispatch() is True


def test_the_guard_is_per_button() -> None:
    g = Game(_Panel())
    g.refresh()
    assert g.tv_room1.load() is True
    assert g.tv_room2.load() is True, "a press on one button must not gag another"
    assert g.tv_room1.load() is False
