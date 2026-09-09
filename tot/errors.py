"""Failures the bot can hit, each with a name that says what to do about it."""

from __future__ import annotations


class TotError(Exception):
    """Base class for everything this package raises."""


class PanelError(TotError):
    """The RideControl panel is not on screen, or is not the shape we expect.

    Raised while looking for the panel (which is normal — that is how the bot
    waits for you to start a game) and when reading from a frame that has none.
    """


class UnknownColorError(TotError):
    """A button is showing a fill that is not in the palette."""

    def __init__(self, key: str, rgb: tuple[int, int, int], votes: int):
        self.key, self.rgb, self.votes = key, rgb, votes
        r, g, b = rgb
        super().__init__(
            f"{key} is #{r:02x}{g:02x}{b:02x}, which is not a palette colour "
            f"({votes} of 9 probes agreed). Either the panel has moved under the "
            f"probe points or this is a fill the calibration never saw."
        )


class UnmappedStateError(TotError):
    """A button is a palette colour that has no meaning on *that* button."""

    def __init__(self, key: str, color: str, known: list[str]):
        self.key, self.color, self.known = key, color, known
        super().__init__(f"{key} is {color}, which maps to no state. Known: {', '.join(known)}")


class BrowserError(TotError):
    """The browser or the Flash emulator could not be brought up."""


class RuffleCrashed(BrowserError):
    """Ruffle threw up its error screen. The run cannot continue on this page."""
