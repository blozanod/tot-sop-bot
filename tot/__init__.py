"""Read the Tower of Terror RideControl panel, and press its buttons.

    from tot import Game

    game = Game.launch()
    game.refresh()
    if game.elevator1.can_dispatch and not game.track.is_locked:
        game.elevator1.dispatch()

Every property is one thing on screen. Every decision is yours.
"""

from .backends import DEFAULT_URL, DesktopBackend, ImageBackend, PlaywrightBackend
from .colors import Color
from .components import Elevator, RideControl, Track, TVRoom
from .errors import (
    BackendError,
    DigitError,
    LayoutError,
    NotPlayingError,
    TotError,
    UnknownColorError,
    UnmappedStateError,
)
from .game import Game, Screen
from .states import (
    AttractionState,
    DispatchState,
    DoorState,
    EnableState,
    LoadState,
    PreshowState,
    ToggleState,
    TrackState,
    UnloadState,
)

__all__ = [
    "Game", "Screen", "Color", "TVRoom", "Elevator", "RideControl", "Track",
    "DoorState", "LoadState", "UnloadState", "PreshowState", "EnableState",
    "DispatchState", "ToggleState", "AttractionState", "TrackState",
    "PlaywrightBackend", "ImageBackend", "DesktopBackend", "DEFAULT_URL",
    "TotError", "LayoutError", "UnknownColorError", "UnmappedStateError",
    "DigitError", "NotPlayingError", "BackendError",
]
