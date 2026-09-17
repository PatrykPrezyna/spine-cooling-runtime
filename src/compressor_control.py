"""Compressor heat-exchanger control temperature.

On/off hysteresis uses the average of the configured plate probes
(``compressor.heat_ex_labels``), falling back to a single
``compressor.heat_ex_label`` for older configs.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence


_DEFAULT_HEAT_EX_LABEL = "Heat Ex"


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
