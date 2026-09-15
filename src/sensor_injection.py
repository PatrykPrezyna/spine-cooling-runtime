"""Runtime sensor injection for manual and automated testing."""

from __future__ import annotations

from typing import Any, Dict, Optional

from hardware_factory import HardwareBundle
from ads1115_thermistor_reader import labels_from_config


def digital_sensor_names(config: dict) -> list[str]:
    return [str(s["name"]) for s in config.get("sensors", []) if s.get("name")]


def thermistor_labels_from_config(config: dict) -> list[str]:
    """Return thermistor names from ``thermistor_sensors.labels``, channel order."""
    names: list[str] = []
    seen: set[str] = set()
    for _channel, name in sorted(labels_from_config(config).items()):
        if name not in seen:
            names.append(name)
            seen.add(name)
    return names


def temperature_labels_from_config(config: dict) -> list[str]:
    """Return ordered logical temperature labels for control / UI / CSV.

    ``config["temperature_sources"]`` is an ordered map of display names
    (values are ignored; every listed name is a thermistor). When absent,
    fall back to ``thermistor_sensors.labels`` in channel order.
    """
    raw = config.get("temperature_sources")
    if isinstance(raw, dict) and raw:
        names: list[str] = []
        for label in raw:
            name = str(label).strip()
            if name:
                names.append(name)
        if names:
            return names
    return thermistor_labels_from_config(config)


def select_temperatures(
    thermistor_temps: Optional[dict],
    config: dict,
) -> dict[str, float]:
    """Resolve each logical temperature name to a °C value from thermistors.

    Missing or unread channels become ``nan`` so the UI still shows the row.
    """
    th = thermistor_temps or {}
    selected: dict[str, float] = {}
    for label in temperature_labels_from_config(config):
        value = th.get(label)
        try:
            selected[label] = float(value) if value is not None else float("nan")
        except (TypeError, ValueError):
            selected[label] = float("nan")
    return selected


def pressure_channel_labels_from_config(config: dict) -> dict[int, str]:
    """Return channel → label for pressure sensors.

    Prefers flat ``pressure_sensors.labels`` (same shape as thermistors).
    ``channel_configs[].label`` overrides when present.
    """
    ps_cfg = config.get("pressure_sensors", {}) or {}
    labels: dict[int, str] = {}
    raw_labels = ps_cfg.get("labels", {}) or {}
    for key, value in raw_labels.items():
        try:
            labels[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    channel_configs = ps_cfg.get("channel_configs", {}) or {}
    for key, cfg in channel_configs.items():
        if not isinstance(cfg, dict) or not cfg.get("label"):
            continue
        try:
            labels[int(key)] = str(cfg["label"])
        except (TypeError, ValueError):
            continue
    return labels


def pressure_labels_from_config(config: dict) -> list[str]:
    """Return ordered pressure channel labels from config."""
    ps_cfg = config.get("pressure_sensors", {}) or {}
    channels = ps_cfg.get("channels", [])
    labels = pressure_channel_labels_from_config(config)
    names: list[str] = []
    for channel in channels:
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            continue
        names.append(labels.get(ch, f"Pressure {ch + 1}"))
    return names


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


class InjectableThermistorReader:
    """Delegates thermistor reads and merges injection overrides."""

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
        pump_speed_rpm: int = 0,
    ) -> None:
        notify = getattr(self._inner, "notify_setpoint", None)
        if notify is not None:
            notify(set_temperature_c, compressor_cooling, pump_running, pump_speed_rpm)
        self._controller._push_thermistor_overrides_to_inner(self._inner)

    def read_temperatures(self) -> Dict[str, float]:
        values = dict(self._inner.read_temperatures())
        for label, override in self._controller.thermistor_overrides.items():
            if override is not None:
                values[label] = float(override)
        return values


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

        self.digital_names = digital_sensor_names(config)
        self.thermistor_labels = thermistor_labels_from_config(config)
        self.pressure_labels = pressure_labels_from_config(config)

        self.digital_overrides: Dict[str, Optional[bool]] = {
            name: None for name in self.digital_names
        }
        self.thermistor_overrides: Dict[str, Optional[float]] = {
            label: None for label in self.thermistor_labels
        }
        self.pressure_overrides: Dict[str, Optional[float]] = {
            label: None for label in self.pressure_labels
        }

        self._inner_thermistor: Any = None

    def set_digital(self, name: str, active: bool) -> None:
        if name in self.digital_overrides:
            self.digital_overrides[name] = bool(active)

    def set_thermistor_raw(self, label: str, raw_c: float) -> None:
        if label in self.thermistor_overrides:
            self.thermistor_overrides[label] = float(raw_c)

    def set_pressure(self, label: str, value: float) -> None:
        if label in self.pressure_overrides:
            self.pressure_overrides[label] = float(value)

    def clear_override(self, kind: str, name: str) -> None:
        if kind == "digital" and name in self.digital_overrides:
            self.digital_overrides[name] = None
        elif kind == "thermistor" and name in self.thermistor_overrides:
            self.thermistor_overrides[name] = None
        elif kind == "pressure" and name in self.pressure_overrides:
            self.pressure_overrides[name] = None

    def wrap_bundle(self, bundle: HardwareBundle) -> HardwareBundle:
        self._inner_thermistor = bundle.thermistor_reader
        return HardwareBundle(
            sensor_reader=InjectableDigitalReader(bundle.sensor_reader, self),
            thermistor_reader=InjectableThermistorReader(
                bundle.thermistor_reader, self
            ),
            pressure_reader=InjectablePressureReader(bundle.pressure_reader, self),
            stepper_driver=bundle.stepper_driver,
            flow_reader=bundle.flow_reader,
        )

    def _push_thermistor_overrides_to_inner(self, inner: Any) -> None:
        set_raw = getattr(inner, "set_raw_temperature", None)
        release = getattr(inner, "release_temperature", None)
        if set_raw is None:
            return
        for label, value in self.thermistor_overrides.items():
            if value is not None:
                set_raw(label, value)
            elif release is not None:
                release(label)

    def _sync_thermistor_inner(self) -> None:
        if self._inner_thermistor is not None:
            self._push_thermistor_overrides_to_inner(self._inner_thermistor)
