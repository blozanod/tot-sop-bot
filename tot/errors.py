"""Failure modes.

Every error here exists because the alternative was a silent misread. The bot is
calibrated from screenshots rather than from the live game, so drift between what
was measured and what is on screen must surface as a crash, never as a plausible
state.
"""

from __future__ import annotations


class TotError(Exception):
    """Base for everything this package raises."""


class LayoutError(TotError):
    """The RideControl panel could not be located, or is not the shape we expect.

    Raised at calibration. Usually means the frame is not the playing field (a
    chooser or loading screen), or the panel is partly off-screen.
    """


class UnknownColorError(TotError):
    """A probed button is a colour that is not in the palette at all.

    Almost always a real find: a game state that was never captured in the
    calibration screenshots. Add it to ``colors.PALETTE`` and give it a meaning in
    ``states.py``.
    """

    def __init__(self, button: str, rgb: tuple[int, int, int], nearest: str, distance: float):
        self.button, self.rgb, self.nearest, self.distance = button, rgb, nearest, distance
        super().__init__(
            f"{button}: sampled #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x} which is not in the "
            f"palette (nearest is {nearest}, distance {distance:.1f}). "
            f"Either the layout has drifted or this is a state we never captured."
        )


class UnmappedStateError(TotError):
    """A known palette colour appeared on a button that has no meaning for it.

    Distinct from UnknownColorError: the colour is real, we just never saw this
    button wear it. Add the mapping in ``states.py``.
    """

    def __init__(self, button: str, color_name: str, known: list[str]):
        self.button, self.color_name = button, color_name
        super().__init__(
            f"{button} is {color_name}, which is not one of its known states "
            f"({', '.join(known)}). This is a state the calibration screenshots "
            f"never showed; add it to states.py."
        )


class DigitError(TotError):
    """A counter could not be read confidently."""


class NotPlayingError(TotError):
    """A game observable was read while the canvas was not showing the playing field."""


class BackendError(TotError):
    """The browser, display or fixture image could not be driven."""
