"""Assertions against the calibration screenshots.

These run the entire stack — panel detection, colour reading, state mapping,
counter classification — with no browser, using the PNG backend. They are the
reason the palette and geometry can be called verified rather than guessed: the
game was never reachable from the machine this was written on.

Expected values were read by eye from the frames and are recorded in
``docs/findings.md`` §3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tot import (
    AttractionState,
    Count,
    DispatchState,
    DoorState,
    EnableState,
    Game,
    LoadState,
    PanelError,
    PreshowState,
    TrackState,
    UnloadState,
)

SHOTS = Path(__file__).resolve().parents[1] / "assets" / "screenshots"
ALL_FRAMES = sorted(SHOTS.glob("*/*.png"))

FULL = "layout/00-attraction-closed-all-gray-153058.png"
LOADING = "layout/01-tvr1-loading-entrance-moving-153132.png"
PRESHOW_READY = "layout/02-tvr1-loaded-preshow-ready-153147.png"
PRESHOW_ACTIVE = "states/03-preshow-active-153205.png"
UNLOAD_READY = "states/04-preshow-done-unload-ready-153222.png"
UNLOADING = "states/05-unloading-exit-open-153235.png"
ELEV_READY = "states/06-elev1-enabled-doors-closed-153255.png"
DOORS_MOVING = "states/07-elev1-doors-moving-153313.png"
DOORS_OPEN = "states/08-elev1-doors-open-loading-153320.png"
ARMED_MOVING = "states/09-dispatch-armed-doors-moving-153327.png"
ARMED_CLOSED = "states/10-dispatch-armed-doors-closed-153334.png"
DISPATCHED = "states/11-dispatched-track-blocked-153341.png"


def game(rel: str) -> Game:
    return Game.from_image(SHOTS / rel)


# -- the panel is found in every frame ---------------------------------------

@pytest.mark.parametrize("path", ALL_FRAMES, ids=lambda p: p.name[:28])
def test_every_frame_yields_the_whole_panel(path: Path) -> None:
    g = Game.from_image(path)
    assert g.panel_visible
    assert len(g.layout.buttons) == 32
    assert len(g.layout.counters) == 13


@pytest.mark.parametrize("path", ALL_FRAMES, ids=lambda p: p.name[:28])
def test_the_crop_region_holds_every_control(path: Path) -> None:
    """The region the bot screenshots must contain everything it reads."""
    g = Game.from_image(path)
    region = g.layout.region
    h, w = g.frame.shape[:2]
    assert (h, w) == (region.h, region.w)
    for rect in list(g.layout.buttons.values()) + list(g.layout.counters.values()):
        assert 0 <= rect.x and rect.right <= w
        assert 0 <= rect.y and rect.bottom <= h


@pytest.mark.parametrize("path", ALL_FRAMES, ids=lambda p: p.name[:28])
def test_every_button_reads_a_state(path: Path) -> None:
    g = Game.from_image(path)
    assert len(g._states) == 32
    assert all(s is not None for s in g._states.values())


# -- the TV room cycle --------------------------------------------------------

def test_attraction_closed_greys_out_the_whole_panel() -> None:
    g = game(FULL)
    assert g.control.attraction is AttractionState.CLOSED
    assert not g.control.attraction_is_active
    assert g.tv_room1.load_button is LoadState.UNAVAILABLE
    assert g.tv_room1.enable_button is EnableState.DISABLED
    assert g.elevator1.dispatch_button is DispatchState.UNAVAILABLE
    # The track stays green even with the attraction shut.
    assert g.track.is_ready


def test_loading_shows_green_load_and_a_moving_entrance() -> None:
    g = game(LOADING)
    assert g.tv_room1.is_loading
    assert g.tv_room1.entrance_is_moving
    assert g.tv_room1.enabled
    assert g.control.attraction_is_active


def test_preshow_ready_is_orange() -> None:
    g = game(PRESHOW_READY)
    assert g.tv_room1.preshow_ready
    assert g.tv_room1.preshow is PreshowState.READY
    assert g.tv_room1.entrance_is_closed


def test_preshow_running_is_green() -> None:
    g = game(PRESHOW_ACTIVE)
    assert g.tv_room1.preshow_running
    assert not g.tv_room1.preshow_ready


def test_unload_ready_then_unloading() -> None:
    ready, running = game(UNLOAD_READY), game(UNLOADING)
    assert ready.tv_room1.unload_ready
    assert ready.tv_room1.unload_button is UnloadState.READY
    assert running.tv_room1.is_unloading
    assert running.tv_room1.exit_is_open
    assert running.tv_room1.exit is DoorState.OPEN


# -- the elevator cycle -------------------------------------------------------

def test_an_enabled_elevator_has_closed_doors_and_a_white_load() -> None:
    g = game(ELEV_READY)
    assert g.elevator1.enabled
    assert g.elevator1.doors_are_closed
    assert g.elevator1.can_load
    assert not g.elevator1.can_dispatch
    # The other two are still switched off.
    assert not g.elevator2.enabled
    assert not g.elevator3.enabled


def test_elevator_doors_move_then_open() -> None:
    assert game(DOORS_MOVING).elevator1.doors_are_moving
    g = game(DOORS_OPEN)
    assert g.elevator1.doors_are_open
    assert g.elevator1.is_loading


def test_dispatch_armed_is_the_second_green() -> None:
    for rel in (ARMED_MOVING, ARMED_CLOSED):
        g = game(rel)
        assert g.elevator1.can_dispatch
        assert g.elevator1.dispatch_button is DispatchState.ARMED
        assert g.track.is_ready, "the track is still clear while an elevator is armed"


def test_a_dispatched_elevator_locks_the_track() -> None:
    g = game(DISPATCHED)
    assert g.elevator1.is_dispatched
    assert g.elevator1.dispatch_button is DispatchState.IN_MOTION
    assert g.track.is_locked
    assert g.track.state is TrackState.LOCKED
    assert not g.track.is_ready


# -- counters: zero, twenty-one, and everything else --------------------------

def test_zero_is_recognised() -> None:
    g = game(PRESHOW_ACTIVE)
    assert g.control.back_waiting is Count.ZERO  # reads 0
    assert g.elevator1.waiting_is_zero
    assert g.elevator1.loaded_is_zero


def test_twenty_one_is_recognised() -> None:
    g = game(PRESHOW_ACTIVE)
    assert g.tv_room1.waiting_is_full  # reads 21
    assert g.tv_room1.loaded_is_full
    assert g.tv_room1.loaded is Count.FULL


def test_everything_else_reads_as_other() -> None:
    """A number that is neither 0 nor 21 must not masquerade as either."""
    g = game(PRESHOW_ACTIVE)
    assert g.control.front_waiting is Count.OTHER  # reads 16
    assert not g.control.front_queue_is_full
    assert g.control.front_waiting.is_zero is False

    single = game(LOADING)
    assert single.tv_room1.loaded is Count.OTHER  # reads 3, a single glyph
    assert not single.tv_room1.loaded_is_zero


def test_a_full_front_queue_is_read_as_full() -> None:
    g = game(UNLOAD_READY)
    assert g.control.front_queue_is_full  # reads 21


# -- clicking -----------------------------------------------------------------

def test_a_click_lands_in_the_middle_of_the_button_in_full_frame_coords() -> None:
    g = game(ARMED_CLOSED)
    g.elevator1.dispatch()
    (x, y), = g.backend.clicks
    # The backend is region-clipped, so it maps back to the original image.
    rect = g.layout.buttons["elevator1.dispatch"]
    region = g.layout.region
    assert (x, y) == (int(rect.cx) + region.x, int(rect.cy) + region.y)


def test_reading_without_a_panel_refuses_rather_than_guessing(tmp_path: Path) -> None:
    import numpy as np
    from PIL import Image

    blank = tmp_path / "blank.png"
    Image.fromarray(np.zeros((300, 400, 3), np.uint8)).save(blank)
    g = Game.from_image(blank)
    assert not g.panel_visible
    with pytest.raises(PanelError):
        _ = g.track.is_locked
