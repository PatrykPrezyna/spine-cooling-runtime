"""Read grouped ``config.yaml`` sections, with the old flat keys as a fallback.

The file is organized as ``ui``, ``actuators``, ``sensors``, and ``logging``,
then ``alarms`` and ``simulation``. Device blocks keep their old names inside
those groups (``actuators.compressor``, ``sensors.thermistors``, and so on).
Callers that still pass a flat dict — mostly tests — resolve the same way.
"""

from __future__ import annotations

from typing import Any, Mapping


def _mapping(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return config if isinstance(config, Mapping) else {}


def _from_group_or_top(
    config: Mapping[str, Any] | None,
    group: str,
    key: str,
    default: Any = None,
) -> Any:
    """Return ``config[group][key]`` when that group exists, else the top-level key."""
    raw = _mapping(config)
    grouped = raw.get(group)
    if isinstance(grouped, dict):
        if key in grouped and grouped[key] is not None:
            return grouped[key]
        return default
    if key in raw and raw[key] is not None:
        return raw[key]
    return default


def actuator_device(config: Mapping[str, Any] | None, key: str) -> dict:
    """Return one actuator block (compressor, stepper, pump, cooling power)."""
    value = _from_group_or_top(config, "actuators", key)
    return value if isinstance(value, dict) else {}


def ensure_actuator_device(config: dict, key: str) -> dict:
    """Return an actuator block stored on ``config``, creating it if missing.

    Edits to the returned dict are saved with the grouped file when
    ``actuators`` is present, and with the legacy top-level key otherwise.
    """
    group = config.get("actuators")
    if isinstance(group, dict):
        block = group.get(key)
        if not isinstance(block, dict):
            block = {}
            group[key] = block
        return block
    block = config.get(key)
    if not isinstance(block, dict):
        block = {}
        config[key] = block
    return block


def control_temp_label(config: Mapping[str, Any] | None, default: str = "CSF 2") -> str:
    """Probe name used as the pump-control temperature."""
    value = _from_group_or_top(config, "actuators", "control_temp_label")
    text = str(value).strip() if value is not None else ""
    return text or default


def _digital_sensor_block(config: Mapping[str, Any] | None) -> Any:
    sensors = _mapping(config).get("sensors")
    if not isinstance(sensors, dict):
        return None
    if "digital_sensors" in sensors:
        return sensors.get("digital_sensors")
    return sensors.get("gpio")


def digital_sensor_entries(config: Mapping[str, Any] | None) -> list:
    """Digital input entries (Level Low, Leak Sensor, and the rest).

    Grouped configs store the list at ``sensors.digital_sensors.sensors``.
    Older configs used ``sensors.gpio`` or a top-level ``sensors`` list.
    """
    raw = _mapping(config)
    sensors = raw.get("sensors")
    if isinstance(sensors, list):
        return sensors
    block = _digital_sensor_block(config)
    if isinstance(block, list):
        return block
    if isinstance(block, dict):
        entries = block.get("sensors", block.get("gpio"))
        return entries if isinstance(entries, list) else []
    return []


def gpio_sensors(config: Mapping[str, Any] | None) -> list:
    """Backward-compatible name for :func:`digital_sensor_entries`."""
    return digital_sensor_entries(config)


def digital_sample_rate_hz(
    config: Mapping[str, Any] | None,
    default: float = 1.0,
) -> float:
    """Poll rate for the digital inputs, not the pressure chips.

    Lives at ``sensors.digital_sensors.sample_rate_hz``. Older configs put
    it on ``sensors`` or at the top level.
    """
    block = _digital_sensor_block(config)
    if isinstance(block, dict) and block.get("sample_rate_hz") is not None:
        return float(block["sample_rate_hz"])
    value = _from_group_or_top(config, "sensors", "sample_rate_hz", default=None)
    if value is None:
        return float(default)
    return float(value)


def _sensor_device(
    config: Mapping[str, Any] | None,
    grouped_key: str,
    legacy_key: str,
) -> dict:
    raw = _mapping(config)
    sensors = raw.get("sensors")
    if isinstance(sensors, dict):
        block = sensors.get(grouped_key)
        if isinstance(block, dict):
            return block
        legacy = sensors.get(legacy_key)
        return legacy if isinstance(legacy, dict) else {}
    block = raw.get(legacy_key)
    return block if isinstance(block, dict) else {}


def thermistor_cfg(config: Mapping[str, Any] | None) -> dict:
    """``sensors.thermistors``, or legacy ``thermistor_sensors``."""
    return _sensor_device(config, "thermistors", "thermistor_sensors")


def flow_cfg(config: Mapping[str, Any] | None) -> dict:
    """``sensors.flow``, or legacy ``flow_sensor``."""
    return _sensor_device(config, "flow", "flow_sensor")


def pressure_cfg(config: Mapping[str, Any] | None) -> dict:
    """``sensors.pressure``, or legacy ``pressure_sensors``."""
    return _sensor_device(config, "pressure", "pressure_sensors")
