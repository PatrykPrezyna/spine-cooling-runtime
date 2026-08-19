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
DEFAULT_USB_VOLUME_LABEL = "SPINELOGS"
DEFAULT_USB_DEST_SUBDIR = "logs"
DEFAULT_USB_INTERVAL_S = 2.0


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


def usb_config(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = _logging_cfg(config).get("usb") or {}
    return cfg if isinstance(cfg, dict) else {}


def usb_enabled(config: dict[str, Any] | None) -> bool:
    cfg = usb_config(config)
    if "enabled" in cfg:
        return bool(cfg["enabled"])
    return True


def usb_volume_label(config: dict[str, Any] | None) -> str:
    return str(usb_config(config).get("volume_label") or DEFAULT_USB_VOLUME_LABEL)


def usb_destination_subdir(config: dict[str, Any] | None) -> str:
    return str(usb_config(config).get("destination_subdir") or DEFAULT_USB_DEST_SUBDIR)


def usb_interval_s(config: dict[str, Any] | None) -> float:
    try:
        value = float(usb_config(config).get("interval_s", DEFAULT_USB_INTERVAL_S))
    except (TypeError, ValueError):
        value = DEFAULT_USB_INTERVAL_S
    return max(0.2, value)


def usb_mount_path_override(config: dict[str, Any] | None) -> str | None:
    value = usb_config(config).get("mount_path")
    if value is None or str(value).strip() == "":
        return None
    return str(value)
