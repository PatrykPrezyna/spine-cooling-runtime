"""Graph sample storage and Y-axis tick snapping.

Lives outside ``gui.py`` so these rules can be tested without PyQt6.
"""

from __future__ import annotations

import math
from collections import deque

# Live graphs keep a full session. The last hour stays at the UI sample rate
# so short windows stay smooth; older samples are kept every few seconds so
# panning past one hour does not store every 100 ms tick.
GRAPH_HISTORY_SEC = 48 * 3600
GRAPH_FINE_HISTORY_SEC = 60 * 60
GRAPH_COARSE_INTERVAL_SEC = 5.0

Y_TICK_COUNT = 7
Y_TICK_INTERVALS = Y_TICK_COUNT - 1


class GraphSampleHistory:
    """Time-ordered graph samples with a long, thinned tail.

    The recent ``fine_sec`` is stored at the incoming rate. Older samples are
    kept at ``coarse_sec`` spacing, and anything past ``max_sec`` is dropped.
    ``append`` skips that thinning so replay and screenshots can load a
    prepared series.
    """

    def __init__(
        self,
        max_sec: float = GRAPH_HISTORY_SEC,
        fine_sec: float = GRAPH_FINE_HISTORY_SEC,
        coarse_sec: float = GRAPH_COARSE_INTERVAL_SEC,
    ):
        self.max_sec = float(max_sec)
        self.fine_sec = float(fine_sec)
        self.coarse_sec = float(coarse_sec)
        self._coarse = deque()
        self._fine = deque()

    def clear(self) -> None:
        self._coarse.clear()
        self._fine.clear()

    def append(self, sample) -> None:
        self._fine.append(sample)

    def add(self, sample) -> None:
        self._fine.append(sample)
        self._retain(float(sample[0]))

    def _retain(self, now: float) -> None:
        max_sec = max(0.0, self.max_sec)
        fine_sec = min(max(0.0, self.fine_sec), max_sec)
        boundary = now - fine_sec
        cutoff = now - max_sec
        while self._fine and self._fine[0][0] < boundary:
            aged = self._fine.popleft()
            if aged[0] < cutoff:
                continue
            if (
                not self._coarse
                or self.coarse_sec <= 0
                or aged[0] - self._coarse[-1][0] >= self.coarse_sec
            ):
                self._coarse.append(aged)
        while self._coarse and self._coarse[0][0] < cutoff:
            self._coarse.popleft()
        while self._fine and self._fine[0][0] < cutoff:
            self._fine.popleft()

    def __iter__(self):
        yield from self._coarse
        yield from self._fine

    def __reversed__(self):
        yield from reversed(self._fine)
        yield from reversed(self._coarse)

    def __len__(self) -> int:
        return len(self._coarse) + len(self._fine)

    def __getitem__(self, index: int):
        if index == 0:
            return self._coarse[0] if self._coarse else self._fine[0]
        if index == -1:
            return self._fine[-1] if self._fine else self._coarse[-1]
        n_coarse = len(self._coarse)
        n = n_coarse + len(self._fine)
        if index < 0:
            index += n
        if index < 0 or index >= n:
            raise IndexError(index)
        if index < n_coarse:
            return self._coarse[index]
        return self._fine[index - n_coarse]


def tick_decimals(fmt: str) -> int:
    """Decimal places implied by a format string such as ``{:.1f}``."""
    try:
        sample = fmt.format(0.0)
    except (IndexError, ValueError):
        return 1
    if "." not in sample:
        return 0
    return len(sample.split(".", 1)[1])


def snap_axis_range(
    y_min: float,
    y_max: float,
    decimals: int,
    n_intervals: int = Y_TICK_INTERVALS,
) -> tuple[float, float]:
    """Expand a Y range so major ticks land on values with ``decimals`` places.

    Graphs draw a fixed number of equally spaced labels. Using the raw data
    range puts those lines at values like 1.173 that then display as 1.2.
    Integer units of ``10**(-decimals)`` keep every tick equal to its label.
    """
    scale = 10 ** max(0, int(decimals))
    # ±inf (open thermistor extrapolated past the R–T table) cannot be floored.
    if not (math.isfinite(y_min) and math.isfinite(y_max)):
        y_min, y_max = 0.0, float(n_intervals)
    lo, hi = (y_min, y_max) if y_min <= y_max else (y_max, y_min)
    i_min = math.floor(lo * scale + 1e-9)
    i_max = math.ceil(hi * scale - 1e-9)
    if i_max <= i_min:
        i_max = i_min + n_intervals
    i_step = max(1, math.ceil((i_max - i_min) / n_intervals))
    i_max = i_min + n_intervals * i_step
    return i_min / scale, i_max / scale


def axis_tick_values(
    y_min: float,
    y_max: float,
    decimals: int,
    n_intervals: int = Y_TICK_INTERVALS,
) -> list[float]:
    """Major-tick values matching ``snap_axis_range``."""
    scale = 10 ** max(0, int(decimals))
    if not (math.isfinite(y_min) and math.isfinite(y_max)):
        y_min, y_max = 0.0, float(n_intervals)
    i_min = int(round(y_min * scale))
    i_max = int(round(y_max * scale))
    i_step = max(1, (i_max - i_min) // n_intervals)
    return [(i_min + i * i_step) / scale for i in range(n_intervals + 1)]
