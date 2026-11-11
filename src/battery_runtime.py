"""UPS battery-mode countdown and the Remote shutdown command.

Battery Mode starts a runtime countdown (30 minutes by default). While it
is counting, the operator sees a running-on-battery warning with the time
left. At zero the warning changes to the shutdown message and Remote is
commanded on. The UPS then removes power on its own delay (about 3 minutes).

DC OK, Alarm, and Ready are wired as inputs but are not acted on here.
"""

from __future__ import annotations

import math
from typing import Optional


DEFAULT_BATTERY_RUNTIME_S = 30 * 60
MIN_BATTERY_RUNTIME_MIN = 1
MAX_BATTERY_RUNTIME_MIN = 180


def clamp_battery_runtime_minutes(minutes: float) -> int:
    """Whole minutes inside the Status-page range, 1 to 180."""
    try:
        value = int(round(float(minutes)))
    except (TypeError, ValueError):
        value = DEFAULT_BATTERY_RUNTIME_S // 60
    return max(MIN_BATTERY_RUNTIME_MIN, min(MAX_BATTERY_RUNTIME_MIN, value))


class BatteryRuntimeTracker:
    """Countdown from the moment Battery Mode asserts."""

    def __init__(self, runtime_s: float = DEFAULT_BATTERY_RUNTIME_S) -> None:
        self.runtime_s = float(clamp_battery_runtime_minutes(float(runtime_s) / 60.0) * 60)
        self._on_since: Optional[float] = None
        self.shutdown_started = False
        self.remaining_s: Optional[float] = None

    def set_runtime_minutes(self, minutes: float) -> int:
        """Set the countdown length. A shutdown already in progress is left running."""
        applied = clamp_battery_runtime_minutes(minutes)
        self.runtime_s = float(applied * 60)
        return applied

    @property
    def remote_on(self) -> bool:
        """True once the countdown has finished. Remote stays on after that."""
        return self.shutdown_started

    def update(self, *, on_battery: bool, now: float) -> None:
        """Advance the countdown. ``now`` is a monotonic timestamp in seconds."""
        if self.shutdown_started:
            self.remaining_s = 0.0
            return
        if not on_battery:
            self._on_since = None
            self.remaining_s = None
            return
        if self._on_since is None:
            self._on_since = float(now)
        remaining = self.runtime_s - (float(now) - self._on_since)
        if remaining <= 0.0:
            self.shutdown_started = True
            self.remaining_s = 0.0
            self._on_since = None
            return
        self.remaining_s = remaining


def format_countdown(remaining_s: float) -> str:
    """Whole minutes and seconds still left, rounded up to the next second."""
    seconds_left = max(0, math.ceil(float(remaining_s) - 1e-9))
    minutes, seconds = divmod(int(seconds_left), 60)
    return f"{minutes}:{seconds:02d}"


def running_on_battery_text(remaining_s: Optional[float]) -> str:
    """Banner line while the countdown is running."""
    if remaining_s is None:
        return "Running on battery"
    return f"Running on battery {format_countdown(remaining_s)}"
