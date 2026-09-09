"""What each button colour means.

One table per button family, mapping a palette colour to a meaning. Nothing here
does any work at runtime beyond a dict lookup — the colour has already been read.

The general rule across the panel (``docs/findings.md`` §2):

    GRAY    not actionable
    WHITE   idle; a door is closed
    ORANGE  a door is moving, or an action is ready — the cue to act
    GREEN   an action is in progress; a door is open
"""

from __future__ import annotations

from enum import Enum

from .colors import Color


class DoorState(Enum):
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"
    MOVING = "moving"
    OPEN = "open"


class LoadState(Enum):
    UNAVAILABLE = "unavailable"
    READY = "ready"
    PROMPTED = "prompted"
    LOADING = "loading"


class UnloadState(Enum):
    UNAVAILABLE = "unavailable"
    IDLE = "idle"
    READY = "ready"
    UNLOADING = "unloading"


class PreshowState(Enum):
    UNAVAILABLE = "unavailable"
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"


class EnableState(Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"


class DispatchState(Enum):
    UNAVAILABLE = "unavailable"
    IDLE = "idle"
    ARMED = "armed"
    IN_MOTION = "in_motion"


class ToggleState(Enum):
    OFF = "off"
    ON = "on"


class AttractionState(Enum):
    CLOSED = "closed"
    ACTIVE = "active"


class TrackState(Enum):
    READY = "ready"
    LOCKED = "locked"


_DOOR = {
    Color.GRAY: DoorState.UNAVAILABLE,
    Color.WHITE: DoorState.CLOSED,
    Color.ORANGE: DoorState.MOVING,
    Color.GREEN: DoorState.OPEN,
}
_LOAD = {
    Color.GRAY: LoadState.UNAVAILABLE,
    Color.WHITE: LoadState.READY,
    Color.ORANGE: LoadState.PROMPTED,
    Color.GREEN: LoadState.LOADING,
}
_UNLOAD = {
    Color.GRAY: UnloadState.UNAVAILABLE,
    Color.WHITE: UnloadState.IDLE,
    Color.ORANGE: UnloadState.READY,
    Color.GREEN: UnloadState.UNLOADING,
}
_PRESHOW = {
    Color.GRAY: PreshowState.UNAVAILABLE,
    Color.WHITE: PreshowState.IDLE,
    Color.ORANGE: PreshowState.READY,
    Color.GREEN: PreshowState.RUNNING,
}
_ENABLE = {Color.GRAY: EnableState.DISABLED, Color.GREEN: EnableState.ENABLED}
_TOGGLE = {Color.GRAY: ToggleState.OFF, Color.GREEN: ToggleState.ON}
#: Dispatch has its own brighter palette — it is the one irreversible action.
_DISPATCH = {
    Color.GRAY: DispatchState.UNAVAILABLE,
    Color.WHITE: DispatchState.IDLE,
    Color.BRIGHT_GREEN: DispatchState.ARMED,
    Color.BRIGHT_ORANGE: DispatchState.IN_MOTION,
}
_ATTRACTION = {Color.DIM_WHITE: AttractionState.CLOSED, Color.WHITE: AttractionState.ACTIVE}
_TRACK = {Color.GREEN: TrackState.READY, Color.RED: TrackState.LOCKED}

_TV_ROOM = {
    "load": _LOAD,
    "unload": _UNLOAD,
    "entrance": _DOOR,
    "exit": _DOOR,
    "enable": _ENABLE,
    "preshow": _PRESHOW,
}
_ELEVATOR = {"enable": _ENABLE, "doors": _DOOR, "load": _LOAD, "dispatch": _DISPATCH}
_CONTROL = {
    "automatic_doors": _TOGGLE,
    "daytime": _TOGGLE,
    "show_fullscreen": _TOGGLE,
    "ride_sfx": _TOGGLE,
    "tv_room_sound": _TOGGLE,
    "bgm": _TOGGLE,
    "attraction": _ATTRACTION,
    "track": _TRACK,
}


def meanings(key: str) -> dict[Color, Enum]:
    """The colour -> state table for a layout key such as ``elevator2.dispatch``."""
    prefix, _, name = key.partition(".")
    if prefix.startswith("tv_room"):
        return _TV_ROOM[name]
    if prefix.startswith("elevator"):
        return _ELEVATOR[name]
    return _CONTROL[name]
