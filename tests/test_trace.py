"""The run trace: state changes, actions, and the cue-to-click timing.

Replays the calibration frames in order as if they were a live run, which is the
closest thing to an end-to-end test available without the game.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tot import Game, Screen

SHOTS = Path(__file__).resolve().parents[1] / "assets" / "screenshots"
SEQUENCE = sorted((SHOTS / "states").glob("*.png"))


class Replay:
    """A backend that yields the calibration frames in order."""

    def __init__(self, paths: list[Path]):
        self.frames = [np.array(Image.open(p).convert("RGB")) for p in paths]
        self.i = 0
        self.clicks: list[tuple[int, int]] = []

    def grab(self) -> np.ndarray:
        frame = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return frame

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def close(self) -> None:
        pass


@pytest.fixture
def run(tmp_path: Path) -> list[dict]:
    log = tmp_path / "run.jsonl"
    game = Game(Replay(SEQUENCE), trace=str(log))
    for _ in SEQUENCE:
        game.refresh()
        if game.screen is Screen.PLAYING and game.elevator1.can_dispatch and not game.track.is_locked:
            game.elevator1.dispatch()
    game.close()
    return [json.loads(line) for line in log.read_text().splitlines()]


def events(run: list[dict], kind: str) -> list[dict]:
    return [r for r in run if r["kind"] == kind]


def test_the_run_records_the_tv_room_cycle(run: list[dict]) -> None:
    changes = [(r["key"], r["from"], r["to"]) for r in events(run, "state_change")]
    assert ("tv_room1.preshow", "RUNNING", "IDLE") in changes
    assert ("tv_room1.unload", "IDLE", "READY") in changes
    assert ("tv_room1.unload", "READY", "UNLOADING") in changes
    assert ("tv_room1.exit", "CLOSED", "OPEN") in changes


def test_the_run_records_the_elevator_cycle(run: list[dict]) -> None:
    changes = [(r["key"], r["from"], r["to"]) for r in events(run, "state_change")]
    assert ("elevator1.doors", "CLOSED", "MOVING") in changes
    assert ("elevator1.doors", "MOVING", "OPEN") in changes
    assert ("elevator1.load", "READY", "LOADING") in changes
    assert ("elevator1.dispatch", "UNAVAILABLE", "ARMED") in changes
    assert ("elevator1.dispatch", "ARMED", "IN_MOTION") in changes


def test_dispatching_locks_the_track(run: list[dict]) -> None:
    changes = [(r["key"], r["from"], r["to"]) for r in events(run, "state_change")]
    assert ("control.track", "READY", "LOCKED") in changes


def test_counters_are_traced_as_numbers(run: list[dict]) -> None:
    moves = [(r["key"], r["from"], r["to"]) for r in events(run, "state_change")]
    assert ("elevator1.loaded", 0, 3) in moves
    assert ("elevator1.loaded", 3, 21) in moves


def test_actions_carry_the_state_and_the_cue_age(run: list[dict]) -> None:
    acts = events(run, "action")
    assert acts, "the strategy should have dispatched at least once"
    for a in acts:
        assert a["button"] == "Dispatch Elevator"
        assert a["state_when_clicked"] == "ARMED"
        assert a["cue_age_s"] is not None and a["cue_age_s"] >= 0
        assert "bright green" in a["gloss"]


def test_unverified_states_are_flagged_once(run: list[dict]) -> None:
    """Toggle 'on' was never observed, so reading it should say so in the record."""
    flagged = {r["key"] for r in events(run, "inferred_state")}
    assert "control.automatic_doors" in flagged
    assert len(events(run, "inferred_state")) == len(flagged), "should flag once per button"
