"""Debounce for the digital leak sensor to ignore brief signal flicker.

A leak is only reported once the sensor has read low (fluid detected)
continuously for ``hold_s`` seconds. Any high reading in between resets the
timer, so short glitches on the line do not trip the safety stop.
"""

from typing import Optional


class LeakDebounceTracker:
    """Reports a leak only after the signal stays low for a hold time."""

    def __init__(self, hold_s: float = 0.5) -> None:
        self._hold_s = max(0.0, float(hold_s))
        self._low_since: Optional[float] = None

    def update(self, *, signal_low: bool, now: float) -> bool:
        """Feed the raw reading; return the debounced leak state.

        ``signal_low`` is True when the sensor currently reads 0 (fluid).
        """
        if not signal_low:
            self._low_since = None
            return False
        if self._low_since is None:
            self._low_since = now
        return (now - self._low_since) >= self._hold_s

    def reset(self) -> None:
        self._low_since = None
