"""Shared session-log folder and filename helpers.

Every run writes three CSVs into one folder, all stamped with the same
startup datetime:

    logs/20260819_125800_sensors.csv
    logs/20260819_125800_pressure_100Hz.csv
    logs/20260819_125800_status_and_errors.csv
"""

from __future__ import annotations

from typing import Any

DEFAULT_DIRECTORY = "logs"
DEFAULT_SENSORS_FILENAME_FORMAT = "%Y%m%d_%H%M%S_sensors.csv"
DEFAULT_PRESSURE_FILENAME_FORMAT = "%Y%m%d_%H%M%S_pressure_100Hz.csv"
DEFAULT_STATUS_FILENAME_FORMAT = "%Y%m%d_%H%M%S_status_and_errors.csv"


def _logging_cfg(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = (config or {}).get("logging") or {}
    return cfg if isinstance(cfg, dict) else {}


def log_directory(config: dict[str, Any] | None, *prefer_keys: str) -> str:
    """Return the session-log folder, honouring legacy per-logger keys."""
    cfg = _logging_cfg(config)
    for key in prefer_keys:
        value = cfg.get(key)
        if value:
            return str(value)
    return str(
        cfg.get("directory")
        or cfg.get("csv_directory")
        or DEFAULT_DIRECTORY
    )


def sensors_filename_format(config: dict[str, Any] | None) -> str:
    cfg = _logging_cfg(config)
    return str(
        cfg.get("sensors_filename_format")
        or cfg.get("filename_format")
        or DEFAULT_SENSORS_FILENAME_FORMAT
    )


def pressure_filename_format(config: dict[str, Any] | None) -> str:
    cfg = _logging_cfg(config)
    return str(
        cfg.get("pressure_filename_format") or DEFAULT_PRESSURE_FILENAME_FORMAT
    )


def status_filename_format(config: dict[str, Any] | None) -> str:
    cfg = _logging_cfg(config)
    return str(
        cfg.get("status_filename_format") or DEFAULT_STATUS_FILENAME_FORMAT
    )
