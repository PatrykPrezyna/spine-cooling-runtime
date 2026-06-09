"""Runtime sensor injection for manual and automated testing."""

from __future__ import annotations

from typing import Any, Dict, Optional

from hardware_factory import HardwareBundle
from temperature_calibration import (
    IDENTITY_CALIBRATION,
    apply_linear_calibration,
    build_two_point_calibration,
)


def digital_sensor_names(config: dict) -> list[str]:
    return [str(s["name"]) for s in config.get("sensors", []) if s.get("name")]


def temperature_labels_from_config(config: dict) -> list[str]:
    tc_cfg = config.get("thermocouples", {})
    channels = tc_cfg.get("channels", [])
    raw_labels = tc_cfg.get("labels", {}) or {}
    labels: dict[int, str] = {}
    for key, value in raw_labels.items():
        try:
            labels[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    names: list[str] = []
    for channel in channels:
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            continue
        names.append(labels.get(ch, f"Temp {ch}"))
    return names


def pressure_labels_from_config(config: dict) -> list[str]:
    ps_cfg = config.get("pressure_sensors", {})
    channels = ps_cfg.get("channels", [])
    raw_channel_cfg = ps_cfg.get("channel_configs", {}) or {}
    names: list[str] = []
    for channel in channels:
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            continue
        cfg = raw_channel_cfg.get(str(ch), raw_channel_cfg.get(ch, {}))
        if isinstance(cfg, dict) and cfg.get("label"):
            names.append(str(cfg["label"]))
        else:
            names.append(f"Pressure {ch + 1}")
    return names


def _build_label_calibration(config: dict) -> dict[str, tuple[float, float]]:
    tc_cfg = config.get("thermocouples", {})
    channels = tc_cfg.get("channels", [])
    raw_labels = tc_cfg.get("labels", {}) or {}
    label_by_channel: dict[int, str] = {}
    for key, value in raw_labels.items():
        try:
            label_by_channel[int(key)] = str(value)
        except (TypeError, ValueError):
            continue

    calibration_cfg = tc_cfg.get("calibration", {}) or {}
    default_pts = calibration_cfg.get("default", {}) or {}
    default_cal, _ = build_two_point_calibration(
        default_pts.get("measured_at_0c", 0.0),
        default_pts.get("measured_at_100c", 100.0),
    )
    per_channel = calibration_cfg.get("channels", {}) or {}
    result: dict[str, tuple[float, float]] = {}
    for channel in channels:
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            continue
        label = label_by_channel.get(ch, f"Temp {ch}")
        pts = per_channel.get(str(ch), per_channel.get(ch, default_pts))
        if isinstance(pts, dict):
            cal, err = build_two_point_calibration(
                pts.get("measured_at_0c", 0.0),
                pts.get("measured_at_100c", 100.0),
            )
            result[label] = cal if err is None else default_cal
        else:
            result[label] = default_cal
    return result


class InjectableDigitalReader:
    """Delegates digital reads and merges injection overrides."""

    def __init__(self, inner: Any, controller: "SensorInjectionController"):
        self._inner = inner
        self._controller = controller

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def read_all(self) -> Dict[str, bool]:
        values = dict(self._inner.read_all())
        for name, override in self._controller.digital_overrides.items():
            if override is not None:
                values[name] = bool(override)
        return values


class InjectableThermocoupleReader:
    """Delegates thermocouple reads and merges injection overrides."""

    def __init__(self, inner: Any, controller: "SensorInjectionController"):
        self._inner = inner
        self._controller = controller

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def notify_setpoint(
        self,
        set_temperature_c: float,
        compressor_cooling: int = 0,
        pump_running: bool = False,
    ) -> None:
        notify = getattr(self._inner, "notify_setpoint", None)
        if notify is not None:
            notify(set_temperature_c, compressor_cooling, pump_running)
        self._controller._push_temperature_overrides_to_inner(self._inner)

    def read_temperatures(self) -> Dict[str, float]:
        return self._merge_temperatures(
            dict(self._inner.read_temperatures()),
            dict(self._inner.get_last_raw_temperatures()),
        )[0]

    def get_last_raw_temperatures(self) -> Dict[str, float]:
        return self._merge_temperatures(
            dict(self._inner.read_temperatures()),
            dict(self._inner.get_last_raw_temperatures()),
        )[1]

    def _merge_temperatures(
        self,
        temps: Dict[str, float],
        raw: Dict[str, float],
    ) -> tuple[Dict[str, float], Dict[str, float]]:
        for label, override in self._controller.temperature_overrides.items():
            if override is None:
                continue
            raw[label] = float(override)
            gain, offset = self._controller._label_calibration.get(label, IDENTITY_CALIBRATION)
            temps[label] = apply_linear_calibration(float(override), gain, offset)
        return temps, raw


class InjectablePressureReader:
    """Delegates pressure reads and merges injection overrides."""

    def __init__(self, inner: Any, controller: "SensorInjectionController"):
        self._inner = inner
        self._controller = controller

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def read_pressures(self) -> Dict[str, float]:
        values = dict(self._inner.read_pressures())
        for label, override in self._controller.pressure_overrides.items():
            if override is not None:
                values[label] = float(override)
        return values


class SensorInjectionController:
    """Holds per-sensor override state and wraps hardware readers for test injection."""

    def __init__(self, config: dict):
        self.config = config
        self._label_calibration = _build_label_calibration(config)

        self.digital_names = digital_sensor_names(config)
        self.temperature_labels = temperature_labels_from_config(config)
        self.pressure_labels = pressure_labels_from_config(config)

        self.digital_overrides: Dict[str, Optional[bool]] = {
            name: None for name in self.digital_names
        }
        self.temperature_overrides: Dict[str, Optional[float]] = {
            label: None for label in self.temperature_labels
        }
        self.pressure_overrides: Dict[str, Optional[float]] = {
            label: None for label in self.pressure_labels
        }

        self._inner_thermocouple: Any = None

    def set_digital(self, name: str, active: bool) -> None:
        if name in self.digital_overrides:
            self.digital_overrides[name] = bool(active)

    def set_temperature_raw(self, label: str, raw_c: float) -> None:
        if label in self.temperature_overrides:
            self.temperature_overrides[label] = float(raw_c)

    def set_pressure(self, label: str, value: float) -> None:
        if label in self.pressure_overrides:
            self.pressure_overrides[label] = float(value)

    def clear_override(self, kind: str, name: str) -> None:
        if kind == "digital" and name in self.digital_overrides:
            self.digital_overrides[name] = None
        elif kind == "temperature" and name in self.temperature_overrides:
            self.temperature_overrides[name] = None
        elif kind == "pressure" and name in self.pressure_overrides:
            self.pressure_overrides[name] = None

    def wrap_bundle(self, bundle: HardwareBundle) -> HardwareBundle:
        self._inner_thermocouple = bundle.thermocouple_reader
        return HardwareBundle(
            sensor_reader=InjectableDigitalReader(bundle.sensor_reader, self),
            thermocouple_reader=InjectableThermocoupleReader(bundle.thermocouple_reader, self),
            pressure_reader=InjectablePressureReader(bundle.pressure_reader, self),
            stepper_driver=bundle.stepper_driver,
        )

    def _push_temperature_overrides_to_inner(self, inner: Any) -> None:
        set_raw = getattr(inner, "set_raw_temperature", None)
        release = getattr(inner, "release_temperature", None)
        if set_raw is None:
            return
        for label, value in self.temperature_overrides.items():
            if value is not None:
                set_raw(label, value)
            elif release is not None:
                release(label)

    def _sync_thermocouple_inner(self) -> None:
        if self._inner_thermocouple is not None:
            self._push_temperature_overrides_to_inner(self._inner_thermocouple)
