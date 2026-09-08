"""The game object: one frozen frame, and everything readable off it.

``refresh()`` takes exactly one screenshot and decodes the whole panel from it.
Every property then reads that frame until the next refresh, so a condition like
``e.can_dispatch and e.loaded == 21`` is guaranteed to describe a single instant
rather than two moments a few milliseconds apart.
"""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .backends import DEFAULT_URL, Backend, ImageBackend, PlaywrightBackend
from .colors import Color, classify, nearest, sample
from .components import Elevator, RideControl, Track, TVRoom
from .digits import DigitReader
from .errors import (
    DigitError,
    LayoutError,
    NotPlayingError,
    UnknownColorError,
    UnmappedStateError,
)
from .geometry import Layout, build_layout
from .states import spec_for
from .trace import Trace


class Screen(Enum):
    """Which screen the canvas is showing."""

    PLAYING = "playing"
    #: Anything else — the mode chooser, a loading screen, a game-over card. The
    #: chooser occupies the same canvas area as the RideControl panel, so reads
    #: are refused here rather than returning a confident misreading of a dialog.
    UNKNOWN = "unknown"


class Game:
    """The whole panel, as of the last ``refresh()``."""

    def __init__(
        self,
        backend: Backend,
        trace: Trace | str | Path | None = "logs/run.jsonl",
        on_unknown: str = "raise",
        min_click_interval: float = 0.0,
        reader: DigitReader | None = None,
    ):
        if on_unknown not in ("raise", "unknown", "nearest"):
            raise ValueError("on_unknown must be 'raise', 'unknown' or 'nearest'")
        self.backend = backend
        self.trace = trace if isinstance(trace, Trace) else Trace(trace)
        self.on_unknown = on_unknown
        self.min_click_interval = min_click_interval
        self.reader = reader or DigitReader()

        self._frame: np.ndarray | None = None
        self._layout: Layout | None = None
        self._screen = Screen.UNKNOWN
        self._colors: dict[str, Color | None] = {}
        self._states: dict[str, Any] = {}
        self._counts: dict[str, int | DigitError] = {}
        self._since: dict[str, float] = {}
        self._last_click = 0.0
        self._flagged: set[str] = set()

        self.tv_rooms = {i: TVRoom(self, i) for i in (1, 2)}
        self.elevators = {i: Elevator(self, i) for i in (1, 2, 3)}
        self.tv_room1, self.tv_room2 = self.tv_rooms[1], self.tv_rooms[2]
        self.elevator1, self.elevator2, self.elevator3 = (self.elevators[i] for i in (1, 2, 3))
        self.control = RideControl(self)
        self.track = Track(self)

        self.trace.write("run_start", on_unknown=on_unknown, min_click_interval=min_click_interval)

    # -- construction ---------------------------------------------------------
    @classmethod
    def launch(cls, url: str = DEFAULT_URL, headless: bool = False, **kw: Any) -> Game:
        """Open Chromium, load the game, and attach to its canvas.

        Stops at whatever screen the game shows — choosing a mode, opening the
        attraction and enabling units are strategy, so they stay in your file.
        """
        return cls(PlaywrightBackend(url=url, headless=headless), **kw)

    @classmethod
    def from_image(cls, path: str | Path, **kw: Any) -> Game:
        """A game backed by a still PNG. Used by the fixture tests."""
        kw.setdefault("trace", None)
        g = cls(ImageBackend(path), **kw)
        g.refresh()
        return g

    # -- the frame ------------------------------------------------------------
    @property
    def screen(self) -> Screen:
        return self._screen

    @property
    def frame(self) -> np.ndarray:
        if self._frame is None:
            self.refresh()
        assert self._frame is not None
        return self._frame

    @property
    def layout(self) -> Layout:
        if self._layout is None:
            raise NotPlayingError("the panel has not been located; call refresh() first")
        return self._layout

    def refresh(self) -> Screen:
        """Take one screenshot and decode the whole panel from it."""
        self._frame = self.backend.grab()
        if self._layout is None or not self._verify():
            try:
                self._layout = build_layout(self._frame)
            except LayoutError:
                self._layout, self._screen = None, Screen.UNKNOWN
                return self._screen
        self._screen = Screen.PLAYING
        self._decode()
        return self._screen

    def _verify(self) -> bool:
        """Do the cached button rects still land on palette colours?"""
        assert self._layout is not None and self._frame is not None
        h, w = self._frame.shape[:2]
        for rect in self._layout.buttons.values():
            if rect.bottom > h or rect.right > w:
                return False
            if classify(sample(self._frame, rect.x, rect.y, rect.w, rect.h)) is None:
                return False
        return True

    def _decode(self) -> None:
        assert self._layout is not None and self._frame is not None
        now = time.monotonic()
        clock = None

        for key, rect in self._layout.buttons.items():
            rgb = sample(self._frame, rect.x, rect.y, rect.w, rect.h)
            color = classify(rgb)
            if color is None:
                near, dist = nearest(rgb)
                if self.on_unknown == "raise":
                    raise UnknownColorError(key, rgb, near.name, dist)
                color = near if self.on_unknown == "nearest" else None
            self._colors[key] = color

            spec = spec_for(key)
            state = spec.state(color) if color is not None else None
            if color is not None and state is None:
                raise UnmappedStateError(
                    key, color.name, [s.name for s in spec.by_color.values()]
                )
            old = self._states.get(key, _MISSING)
            self._states[key] = state
            if old is not _MISSING and old is not state and state is not None:
                self._since[key] = now
                self.trace.state_change(key, old, state, spec.gloss[state], clock)
            elif key not in self._since:
                self._since[key] = now
            if state is not None and spec.is_inferred(state) and key not in self._flagged:
                self._flagged.add(key)
                self.trace.write(
                    "inferred_state",
                    key=key,
                    state=state.name,
                    note="this colour was never observed on this button in the "
                    "calibration screenshots; the meaning is inferred",
                )

        for key, rect in self._layout.counters.items():
            try:
                value: int | DigitError = self.reader.read_int(self._frame, rect, key)
            except DigitError as exc:
                value = exc
            old = self._counts.get(key, _MISSING)
            self._counts[key] = value
            if old is not _MISSING and isinstance(value, int) and old != value:
                self.trace.write("state_change", key=key, **{"from": old, "to": value})

    # -- reading --------------------------------------------------------------
    def _require_playing(self) -> None:
        if self._frame is None:
            self.refresh()
        if self._screen is not Screen.PLAYING:
            raise NotPlayingError(
                "the canvas is not showing the playing field, so panel readings "
                "would be meaningless. Check game.screen before reading."
            )

    def _color(self, key: str) -> Color | None:
        self._require_playing()
        return self._colors[key]

    def _state(self, key: str) -> Any:
        self._require_playing()
        return self._states[key]

    def _count(self, key: str) -> int:
        self._require_playing()
        value = self._counts[key]
        if isinstance(value, DigitError):
            raise value
        return value

    # -- the HUD --------------------------------------------------------------
    @property
    def clock(self) -> str:
        """The Current Time box, as ``HH:MM``."""
        self._require_playing()
        rect = self.layout.hud.get("clock")
        if rect is None:
            raise NotPlayingError(
                "the Current Time box was not found — it sits outside the panel, so "
                "this frame may be cropped to the panel alone."
            )
        return self.reader.read_clock(self.frame, rect)

    @property
    def score(self) -> int:
        """The Your score box."""
        self._require_playing()
        rect = self.layout.hud.get("score")
        if rect is None:
            raise NotPlayingError("the Your score box was not found in this frame.")
        return self.reader.read_int(self.frame, rect, "score", band="last")

    # -- acting ---------------------------------------------------------------
    def _click(self, key: str) -> None:
        self._require_playing()
        rect = self.layout.buttons[key]
        spec = spec_for(key)
        state = self._states[key]

        wait = self.min_click_interval - (time.monotonic() - self._last_click)
        if wait > 0:
            time.sleep(wait)

        self.backend.click(int(rect.cx), int(rect.cy))
        self._last_click = time.monotonic()
        since = self._since.get(key)
        self.trace.action(
            key,
            spec.screen_name,
            state,
            spec.gloss.get(state, "") if state else "",
            None if since is None else time.monotonic() - since,
            None,
        )

    # -- waiting --------------------------------------------------------------
    def wait_until(
        self, predicate: Callable[[], bool], timeout: float = 30.0, poll: float = 0.1
    ) -> bool:
        """Refresh and poll until ``predicate()`` is true, or ``timeout`` elapses.

        Returns True if it came true, False on timeout — it never raises, so a
        miscalibrated colour surfaces as a False you can branch on rather than
        hanging the run forever.
        """
        deadline = time.monotonic() + timeout
        while True:
            self.refresh()
            if self._screen is Screen.PLAYING and predicate():
                return True
            if time.monotonic() >= deadline:
                self.trace.write("wait_timeout", timeout_s=timeout)
                return False
            time.sleep(poll)

    # -- inspection -----------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Every observable from the current frame, as plain values."""
        self._require_playing()
        out: dict[str, Any] = {
            k: (v.name if v is not None else None) for k, v in self._states.items()
        }
        for k, v in self._counts.items():
            out[k] = None if isinstance(v, DigitError) else v
        return out

    def describe(self) -> list[str]:
        """The current frame in plain English, one line per control."""
        self._require_playing()
        lines = []
        for key, state in self._states.items():
            if state is not None:
                lines.append(f"{key}: {spec_for(key).gloss[state]}")
        return lines

    def close(self) -> None:
        self.trace.close()
        self.backend.close()

    def __enter__(self) -> Game:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class _Missing:
    pass


_MISSING = _Missing()
