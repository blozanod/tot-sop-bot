"""Assertions against the calibration screenshots.

These run the entire stack — colour classification, grid detection, digit reading,
state mapping — with no browser, using the PNG backend. They are the reason the
coordinate table and palette can be called verified rather than guessed: the game
was never reachable from the machine this was written on.

Expected values were read by eye from the frames and are recorded in
``docs/findings.md`` §3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tot import (
    AttractionState,
    DispatchState,
    DoorState,
    EnableState,
    Game,
    LoadState,
    PreshowState,
    Screen,
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
    assert g.screen is Screen.PLAYING
    assert len(g.layout.buttons) == 32
    assert len(g.layout.counters) == 13


@pytest.mark.parametrize("path", ALL_FRAMES, ids=lambda p: p.name[:28])
def test_every_counter_reads(path: Path) -> None:
    g = Game.from_image(path)
    snap = g.snapshot()
    unreadable = [k for k in g.layout.counters if snap[k] is None]
    assert not unreadable, f"could not read {unreadable}"


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
    assert g.control.attraction_is_active
    assert g.tv_room1.is_loading
    assert g.tv_room1.entrance is DoorState.MOVING
    assert g.tv_room1.entrance_is_moving
    assert not g.tv_room1.entrance_is_closed
    assert g.tv_room1.waiting == 18
    assert g.tv_room1.loaded == 3
    assert g.clock == "10:35"
    assert g.score == 148


def test_preshow_becomes_ready_then_runs_then_prompts_unload() -> None:
    ready = game(PRESHOW_READY)
    assert ready.tv_room1.preshow is PreshowState.READY
    assert ready.tv_room1.preshow_ready
    assert ready.tv_room1.loaded == 21

    running = game(PRESHOW_ACTIVE)
    assert running.tv_room1.preshow is PreshowState.RUNNING
    assert running.tv_room1.preshow_running
    assert not running.tv_room1.preshow_ready
    assert (running.tv_room1.waiting, running.tv_room1.loaded) == (21, 21)

    done = game(UNLOAD_READY)
    assert done.tv_room1.unload_button is UnloadState.READY
    assert done.tv_room1.unload_ready
    assert done.tv_room1.preshow is PreshowState.IDLE


def test_unloading_opens_the_exit() -> None:
    g = game(UNLOADING)
    assert g.tv_room1.unload_button is UnloadState.UNLOADING
    assert g.tv_room1.is_unloading
    assert g.tv_room1.exit is DoorState.OPEN
    assert g.tv_room1.exit_is_open
    assert g.control.back_waiting == 12


# -- the elevator cycle -------------------------------------------------------

def test_elevator_doors_walk_closed_moving_open() -> None:
    assert game(ELEV_READY).elevator1.doors is DoorState.CLOSED
    assert game(DOORS_MOVING).elevator1.doors is DoorState.MOVING
    assert game(DOORS_OPEN).elevator1.doors is DoorState.OPEN


def test_loading_an_elevator_moves_guests_from_waiting_to_loaded() -> None:
    mid = game(DOORS_OPEN)
    assert mid.elevator1.is_loading
    assert (mid.elevator1.waiting, mid.elevator1.loaded) == (18, 3)

    full = game(ARMED_MOVING)
    assert (full.elevator1.waiting, full.elevator1.loaded) == (0, 21)


def test_dispatch_uses_its_own_brighter_palette() -> None:
    """The two greens: an armed Dispatch is #00ff00, not the #66cc33 used elsewhere."""
    armed = game(ARMED_CLOSED)
    assert armed.elevator1.dispatch_button is DispatchState.ARMED
    assert armed.elevator1.can_dispatch
    assert armed.elevator1.enable_button is EnableState.ENABLED

    from tot import Color

    assert armed.layout.buttons["elevator1.dispatch"] is not None
    assert armed._color("elevator1.dispatch") is Color.BRIGHT_GREEN
    assert armed._color("elevator1.enable") is Color.GREEN


def test_a_dispatched_elevator_is_what_blocks_the_track() -> None:
    g = game(DISPATCHED)
    assert g.elevator1.dispatch_button is DispatchState.IN_MOTION
    assert g.elevator1.is_dispatched
    assert not g.elevator1.can_dispatch
    assert g.track.state is TrackState.LOCKED
    assert g.track.is_locked
    assert not g.track.is_ready


def test_track_is_ready_whenever_no_elevator_is_out() -> None:
    for rel in (ELEV_READY, DOORS_MOVING, DOORS_OPEN, ARMED_MOVING, ARMED_CLOSED):
        g = game(rel)
        assert g.track.is_ready, rel
        assert not g.track.is_locked, rel


# -- units 2 and 3 are the same widgets --------------------------------------

def test_idle_units_are_greyed_out_not_absent() -> None:
    g = game(DISPATCHED)
    for room in (g.tv_room2,):
        assert room.load_button is LoadState.UNAVAILABLE
        assert not room.enabled
    for lift in (g.elevator2, g.elevator3):
        assert lift.dispatch_button is DispatchState.UNAVAILABLE
        assert not lift.can_dispatch
        assert not lift.enabled


# -- API shape ----------------------------------------------------------------

def test_collections_and_flat_aliases_are_the_same_objects() -> None:
    g = game(DISPATCHED)
    assert g.elevators[1] is g.elevator1
    assert g.elevators[3] is g.elevator3
    assert g.tv_rooms[2] is g.tv_room2
    assert sorted(g.elevators) == [1, 2, 3]


def test_actions_click_the_centre_of_their_button() -> None:
    g = game(DISPATCHED)
    rect = g.layout.buttons["elevator1.dispatch"]
    g.elevator1.dispatch()
    assert g.backend.clicks == [(int(rect.cx), int(rect.cy))]


def test_actions_do_not_check_preconditions() -> None:
    """A dumb click is deliberate: the decision belongs in the strategy file."""
    g = game(FULL)  # everything greyed out
    assert not g.elevator1.can_dispatch
    g.elevator1.dispatch()
    assert len(g.backend.clicks) == 1


def test_every_state_has_a_gloss() -> None:
    g = game(DISPATCHED)
    lines = g.describe()
    assert len(lines) == 32
    assert any("Track Locked" in line for line in lines)
    assert all(": " in line for line in lines)
