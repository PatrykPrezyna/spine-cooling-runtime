"""Helpers for two-point temperature calibration."""

from __future__ import annotations

from typing import Optional


IDENTITY_CALIBRATION = (1.0, 0.0)


def build_two_point_calibration(
    measured_at_0c: object,
    measured_at_100c: object,
) -> tuple[tuple[float, float], Optional[str]]:
    """Return linear (gain, offset) and optional validation error.

    The transfer function is:
        corrected = raw * gain + offset
    """
    if measured_at_0c is None or measured_at_100c is None:
        return IDENTITY_CALIBRATION, "missing measured_at_0c or measured_at_100c"
    try:
        low = float(measured_at_0c)
        high = float(measured_at_100c)
    except (TypeError, ValueError):
        return IDENTITY_CALIBRATION, "values must be numeric"

    span = high - low
    if abs(span) < 1e-9:
        return (
            IDENTITY_CALIBRATION,
            "measured_at_100c must differ from measured_at_0c",
        )

    gain = 100.0 / span
    offset = -low * gain
    return (gain, offset), None


def apply_linear_calibration(raw_temperature_c: float, gain: float, offset: float) -> float:
    """Apply linear calibration to a raw Celsius reading."""
    return float(raw_temperature_c) * float(gain) + float(offset)
