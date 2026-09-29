"""Compressor heat-exchanger control temperature.

On/off hysteresis uses the average of the configured plate probes
(``compressor.heat_ex_labels``), falling back to a single
``compressor.heat_ex_label`` for older configs.
"""

from __future__ import annotations

import math
from typing import Mapping, Optional, Sequence


_DEFAULT_HEAT_EX_LABEL = "Heat Ex"

# Display name for the compressor on/off trace on the temperature graph.
COMPRESSOR_TRACE_KEY = "Compressor"
# The unit stays off this long after the last real off before it can start.
MIN_OFF_BEFORE_ON_S = 60.0


def heat_ex_labels_from_config(compressor_cfg: Optional[Mapping] = None) -> list[str]:
    """Return the probe names averaged for compressor on/off control."""
    cfg = compressor_cfg or {}
    raw = cfg.get("heat_ex_labels")
    labels: list[str] = []
    if isinstance(raw, (list, tuple)):
        labels = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        labels = [raw.strip()]
    if labels:
        return labels
    single = cfg.get("heat_ex_label")
    if single is not None and str(single).strip():
        return [str(single).strip()]
    return [_DEFAULT_HEAT_EX_LABEL]


def average_temperature_c(
    temperatures: Mapping[str, object],
    labels: Sequence[str],
) -> Optional[float]:
    """Return the mean of ``labels`` in ``temperatures``, or None if any is missing."""
    if not labels:
        return None
    values: list[float] = []
    for label in labels:
        value = temperatures.get(label)
        if value is None:
            return None
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            return None
    return sum(values) / len(values)


def commanded_compressor_on(value: object) -> Optional[bool]:
    """Return relay command as bool, or None when the sample has no reading."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number >= 0.5


class CompressorRestartDelay:
    """Map a relay command to when the compressor actually runs.

    The first start is immediate. After it switches off, a later on command
    does not run the compressor until ``min_off_s`` has passed.
    """

    def __init__(self, min_off_s: float = MIN_OFF_BEFORE_ON_S) -> None:
        self.min_off_s = float(min_off_s)
        self.reset()

    def reset(self) -> None:
        self.physical = False
        self.last_off: Optional[float] = None
        self._command_on_since: Optional[float] = None

    def push(
        self,
        ts: float,
        commanded_on: Optional[bool],
    ) -> list[tuple[float, float]]:
        """Append one commanded sample. Return physical (timestamp, 1 or 0) points.

        When the wait ends between samples, the first point is the delayed start.
        ``commanded_on is None`` leaves the trace unchanged.
        """
        if commanded_on is None:
            return []

        points: list[tuple[float, float]] = []
        if commanded_on:
            if self._command_on_since is None:
                self._command_on_since = ts
        else:
            self._command_on_since = None

        ready = None if self.last_off is None else self.last_off + self.min_off_s
        if (
            not self.physical
            and self._command_on_since is not None
            and ready is not None
            and self._command_on_since <= ready < ts
        ):
            self.physical = True
            points.append((ready, 1.0))

        if self.physical and not commanded_on:
            self.physical = False
            self.last_off = ts
        elif (
            not self.physical
            and commanded_on
            and (self.last_off is None or ts >= self.last_off + self.min_off_s)
        ):
            self.physical = True

        points.append((ts, 1.0 if self.physical else 0.0))
        return points


def compressor_overlay_spans(
    trace: Sequence[tuple[float, float]],
    start_ts: float,
    end_ts: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, bool]]]:
    """Clip a physical compressor trace to a time window.

    Returns on-intervals clipped to ``[start_ts, end_ts]``, and switch events
    whose timestamps fall inside ``(start_ts, end_ts]``.
    """
    spans: list[tuple[float, float]] = []
    switches: list[tuple[float, bool]] = []
    if not trace or end_ts <= start_ts:
        return spans, switches

    state = False
    for ts, level in trace:
        if ts <= start_ts:
            state = level >= 0.5
        else:
            break

    span_start = start_ts if state else None
    prev_on = state
    for ts, level in trace:
        if ts <= start_ts:
            continue
        if ts > end_ts:
            break
        on = level >= 0.5
        if on == prev_on:
            continue
        switches.append((ts, on))
        if on:
            span_start = ts
        elif span_start is not None:
            spans.append((span_start, ts))
            span_start = None
        prev_on = on

    if span_start is not None:
        spans.append((span_start, end_ts))
    return spans, switches
