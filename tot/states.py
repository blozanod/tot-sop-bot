"""What each button colour means, and how to say it in English.

Every state carries a plain-English gloss so a run trace reads as prose rather than
as enum names — the trace is the raw material for the written procedure, so the
vocabulary is kept to what a person actually sees on the panel.

States are marked ``verified`` when they were observed in the calibration
screenshots and ``inferred`` when they follow from the palette's consistent
semantics but were never captured. Reading an inferred state is legal but is
flagged once in the trace, so a claim that turns out to be wrong shows up in the
record instead of quietly shaping the strategy.

The general rule across the panel (``docs/findings.md`` §2):

    GRAY    not actionable
    WHITE   idle; a door is closed
    ORANGE  a door is moving, or an action is ready — the cue to act
    GREEN   an action is in progress; a door is open
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class Spec:
    """One button: what it is called on screen, and what each fill means."""

    screen_name: str
    by_color: dict[Color, Enum]
    gloss: dict[Enum, str]
    verified: frozenset[Enum] = field(default_factory=frozenset)

    def state(self, color: Color) -> Enum | None:
        return self.by_color.get(color)

    def is_inferred(self, state: Enum) -> bool:
        return state not in self.verified


def _door(name: str) -> Spec:
    return Spec(
        screen_name=name,
        by_color={
            Color.GRAY: DoorState.UNAVAILABLE,
            Color.WHITE: DoorState.CLOSED,
            Color.ORANGE: DoorState.MOVING,
            Color.GREEN: DoorState.OPEN,
        },
        gloss={
            DoorState.UNAVAILABLE: f"{name} is greyed out — this unit is not in service",
            DoorState.CLOSED: f"{name} is closed",
            DoorState.MOVING: f"{name} is moving",
            DoorState.OPEN: f"{name} is open",
        },
        verified=frozenset(DoorState),
    )


def _load(name: str) -> Spec:
    return Spec(
        screen_name=name,
        by_color={
            Color.GRAY: LoadState.UNAVAILABLE,
            Color.WHITE: LoadState.READY,
            Color.ORANGE: LoadState.PROMPTED,
            Color.GREEN: LoadState.LOADING,
        },
        gloss={
            LoadState.UNAVAILABLE: f"{name} is greyed out — this unit is not in service",
            LoadState.READY: f"{name} is available",
            LoadState.PROMPTED: f"{name} has turned orange — loading is being prompted",
            LoadState.LOADING: f"{name} is green — guests are moving in",
        },
        # Orange was never seen on a Load button in the calibration frames.
        verified=frozenset({LoadState.UNAVAILABLE, LoadState.READY, LoadState.LOADING}),
    )


TV_ROOM_SPECS: dict[str, Spec] = {
    "load": _load("Load TV Room"),
    "unload": Spec(
        screen_name="Unload TV Room",
        by_color={
            Color.GRAY: UnloadState.UNAVAILABLE,
            Color.WHITE: UnloadState.IDLE,
            Color.ORANGE: UnloadState.READY,
            Color.GREEN: UnloadState.UNLOADING,
        },
        gloss={
            UnloadState.UNAVAILABLE: "Unload TV Room is greyed out — this room is not in service",
            UnloadState.IDLE: "Unload TV Room is idle — there is nothing to unload",
            UnloadState.READY: "Unload TV Room has turned orange — the preshow is over, unload now",
            UnloadState.UNLOADING: "Unload TV Room is green — guests are leaving the room",
        },
        verified=frozenset(UnloadState),
    ),
    "entrance": _door("Entrance"),
    "exit": _door("Exit"),
    "enable": Spec(
        screen_name="TV room enable",
        by_color={Color.GRAY: EnableState.DISABLED, Color.GREEN: EnableState.ENABLED},
        gloss={
            EnableState.DISABLED: "the room is switched off and takes no guests",
            EnableState.ENABLED: "the room is in service",
        },
        verified=frozenset(EnableState),
    ),
    "preshow": Spec(
        screen_name="Start Preshow",
        by_color={
            Color.GRAY: PreshowState.UNAVAILABLE,
            Color.WHITE: PreshowState.IDLE,
            Color.ORANGE: PreshowState.READY,
            Color.GREEN: PreshowState.RUNNING,
        },
        gloss={
            PreshowState.UNAVAILABLE: "Start Preshow is greyed out — this room is not in service",
            PreshowState.IDLE: "Start Preshow is idle — the room is not ready for a preshow",
            PreshowState.READY: "Start Preshow has turned orange — the room is loaded, start it now",
            PreshowState.RUNNING: "the preshow is running (the button reads Preshow Active)",
        },
        verified=frozenset(PreshowState),
    ),
}

ELEVATOR_SPECS: dict[str, Spec] = {
    "enable": Spec(
        screen_name="elevator enable",
        by_color={Color.GRAY: EnableState.DISABLED, Color.GREEN: EnableState.ENABLED},
        gloss={
            EnableState.DISABLED: "the elevator is switched off and takes no guests",
            EnableState.ENABLED: "the elevator is in service",
        },
        verified=frozenset(EnableState),
    ),
    "doors": _door("Doors"),
    "load": _load("Load Elevator"),
    "dispatch": Spec(
        screen_name="Dispatch Elevator",
        by_color={
            Color.GRAY: DispatchState.UNAVAILABLE,
            Color.WHITE: DispatchState.IDLE,
            Color.BRIGHT_GREEN: DispatchState.ARMED,
            Color.BRIGHT_ORANGE: DispatchState.IN_MOTION,
        },
        gloss={
            DispatchState.UNAVAILABLE: "Dispatch is greyed out — this elevator is not in service",
            DispatchState.IDLE: "Dispatch is idle — the elevator is not ready to go",
            DispatchState.ARMED: "Dispatch is bright green — the elevator can be sent now",
            DispatchState.IN_MOTION: "Dispatch is bright orange — the elevator is on the track",
        },
        # White was never seen on Dispatch; the other three all were.
        verified=frozenset(
            {DispatchState.UNAVAILABLE, DispatchState.ARMED, DispatchState.IN_MOTION}
        ),
    ),
}


def _toggle(name: str, on_note: str = "") -> Spec:
    return Spec(
        screen_name=name,
        by_color={Color.GRAY: ToggleState.OFF, Color.GREEN: ToggleState.ON},
        gloss={
            ToggleState.OFF: f"{name} is off",
            ToggleState.ON: f"{name} is on{on_note}",
        },
        # Gray-is-off is anchored by the BGM button, which reads "BGM Disabled"
        # while grey. Green-is-on follows from that but was never seen flip.
        verified=frozenset({ToggleState.OFF}),
    )


CONTROL_SPECS: dict[str, Spec] = {
    "automatic_doors": _toggle("Automatic Doors"),
    "daytime": _toggle("Daytime"),
    "show_fullscreen": _toggle("Show Fullscreen"),
    "ride_sfx": _toggle("Ride SFX"),
    "tv_room_sound": _toggle("TV Room Sound"),
    "bgm": _toggle("BGM"),
    "attraction": Spec(
        screen_name="Attraction",
        by_color={
            Color.DIM_WHITE: AttractionState.CLOSED,
            Color.WHITE: AttractionState.ACTIVE,
        },
        gloss={
            AttractionState.CLOSED: "the button reads Attraction Closed — no guests are entering",
            AttractionState.ACTIVE: "the button reads Attraction Active — the ride is open",
        },
        verified=frozenset(AttractionState),
    ),
    "track": Spec(
        screen_name="Track",
        by_color={Color.GREEN: TrackState.READY, Color.RED: TrackState.LOCKED},
        gloss={
            TrackState.READY: "the button reads Track Ready — the shaft is clear",
            TrackState.LOCKED: "the button reads Track Locked — an elevator is on the track",
        },
        verified=frozenset(TrackState),
    ),
}


def spec_for(key: str) -> Spec:
    """Look up the spec for a layout key such as ``elevator2.dispatch``."""
    prefix, _, name = key.partition(".")
    if prefix.startswith("tv_room"):
        table = TV_ROOM_SPECS
    elif prefix.startswith("elevator"):
        table = ELEVATOR_SPECS
    else:
        table = CONTROL_SPECS
    return table[name]
