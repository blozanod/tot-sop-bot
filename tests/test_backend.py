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
from tot.backends import ImageBackend, visible_clip
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


# -- never move the page ------------------------------------------------------

def test_a_clip_inside_the_window_is_left_alone() -> None:
    box = {"px": 100.0, "py": 200.0, "w": 1200.0, "h": 700.0}
    view = {"x": 0.0, "y": 0.0, "w": 1400.0, "h": 1000.0}
    clip = visible_clip(box, Rect(50, 60, 900, 300), view)
    assert clip == {"x": 150.0, "y": 260.0, "width": 900.0, "height": 300.0}


def test_a_clip_past_the_bottom_is_trimmed_not_scrolled_to() -> None:
    """The half that is showing, rather than moving the page to reach the rest."""
    box = {"px": 0.0, "py": 400.0, "w": 1200.0, "h": 700.0}
    view = {"x": 0.0, "y": 0.0, "w": 1400.0, "h": 900.0}
    clip = visible_clip(box, Rect(0, 400, 900, 300), view)
    assert clip["y"] == 800.0
    assert clip["height"] == 100.0, "trimmed at the fold, not chased below it"


def test_a_clip_entirely_off_screen_collapses_rather_than_scrolling() -> None:
    box = {"px": 0.0, "py": 2000.0, "w": 1200.0, "h": 700.0}
    view = {"x": 0.0, "y": 0.0, "w": 1400.0, "h": 900.0}
    clip = visible_clip(box, Rect(0, 0, 900, 300), view)
    assert (clip["width"], clip["height"]) == (900.0, 1.0)


def test_a_scrolled_page_is_followed_without_being_moved() -> None:
    """Page coordinates do not change when the user scrolls; the window's do."""
    box = {"px": 0.0, "py": 400.0, "w": 1200.0, "h": 700.0}
    scrolled = {"x": 0.0, "y": 300.0, "w": 1400.0, "h": 900.0}
    clip = visible_clip(box, Rect(0, 400, 900, 300), scrolled)
    assert clip == {"x": 0.0, "y": 800.0, "width": 900.0, "height": 300.0}
