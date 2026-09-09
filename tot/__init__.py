"""Read the Tower of Terror RideControl panel, and press its buttons.

    from tot import Game

    game = Game.launch()          # opens Chromium; clicks nothing
    game.wait_for_panel()         # you pick the game mode; this returns when it starts

    game.refresh()                # one screenshot; every property reads that frame
    if game.elevator1.can_dispatch and not game.track.is_locked:
        game.elevator1.dispatch()

Every property is one thing on screen. Every decision is yours.
"""

from .backends import DEFAULT_URL, ImageBackend, PlaywrightBackend
from .colors import Color
from .components import Elevator, RideControl, Track, TVRoom
from .counters import FULL, Count
from .errors import (
    BrowserError,
    PanelError,
    RuffleCrashed,
    TotError,
    UnknownColorError,
    UnmappedStateError,
)
from .game import Game
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
    "Game", "Color", "Count", "FULL", "TVRoom", "Elevator", "RideControl", "Track",
    "DoorState", "LoadState", "UnloadState", "PreshowState", "EnableState",
    "DispatchState", "ToggleState", "AttractionState", "TrackState",
    "PlaywrightBackend", "ImageBackend", "DEFAULT_URL",
    "TotError", "PanelError", "UnknownColorError", "UnmappedStateError",
    "BrowserError", "RuffleCrashed",
]
