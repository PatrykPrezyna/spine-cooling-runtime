import logging
from pathlib import Path
from typing import Any, Dict

import yaml


class AppConfig:
    """Application configuration loader."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw
        self.app = raw.get("app", {})
        self.hardware = raw.get("hardware", {})
        self.thresholds = raw.get("thresholds", {})

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            raise ValueError("Invalid configuration format")
        return cls(raw)

    def ensure_directories(self) -> None:
        for key in ["log_path", "data_path", "csv_folder"]:
            value = self.app.get(key)
            if value:
                directory = Path(value).parent if key == "log_path" else Path(value)
                directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        return self.app.get(key, default)

    def get_hardware(self, key: str, default: Any = None) -> Any:
        return self.hardware.get(key, default)

    def get_threshold(self, key: str, default: Any = None) -> Any:
        return self.thresholds.get(key, default)

    @property
    def log_path(self) -> Path:
        return Path(self.app.get("log_path", "logs/spine_cooling.log"))

    @property
    def db_path(self) -> Path:
        return Path(self.app.get("db_path", "data/spine_cooling.db"))

    @property
    def csv_folder(self) -> Path:
        return Path(self.app.get("csv_folder", "data/csv"))

    @property
    def sensor_poll_interval(self) -> float:
        return float(self.app.get("sensor_poll_interval_s", 0.1))

    @property
    def logger_poll_interval(self) -> float:
        return float(self.app.get("logger_poll_interval_s", 0.1))

    @property
    def ui_update_interval(self) -> int:
        return int(self.app.get("ui_update_interval_ms", 200))

    @property
    def compressor_poll_interval(self) -> float:
        return float(self.app.get("compressor_poll_interval_s", 0.5))

    @property
    def watchdog_interval(self) -> float:
        return float(self.app.get("watchdog_interval_s", 15.0))

    @property
    def watchdog_timeout(self) -> int:
        return int(self.app.get("watchdog_timeout_s", 30))

    @property
    def sensor_cs_pins(self) -> list[int]:
        pins = self.hardware.get("sensor_cs_pins", [])
        return [int(pin) for pin in pins]

    @property
    def spi_bus(self) -> int:
        return int(self.hardware.get("spi_bus", 0))

    @property
    def spi_device(self) -> int:
        return int(self.hardware.get("spi_device", 0))

    @property
    def uart_port(self) -> str:
        return str(self.hardware.get("uart_port", "/dev/ttyAMA0"))

    @property
    def uart_baudrate(self) -> int:
        return int(self.hardware.get("uart_baudrate", 19200))

    @property
    def watchdog_reset_pin(self) -> int:
        return int(self.hardware.get("watchdog_reset_pin", 17))

    @property
    def cooling_enable(self) -> float:
        return float(self.thresholds.get("cooling_enable_c", 65.0))

    @property
    def cooling_disable(self) -> float:
        return float(self.thresholds.get("cooling_disable_c", 55.0))

    @property
    def alarm_threshold(self) -> float:
        return float(self.thresholds.get("alarm_c", 90.0))

    @property
    def fault_threshold(self) -> float:
        return float(self.thresholds.get("fault_c", 100.0))

    @property
    def daemonize(self) -> bool:
        return bool(self.app.get("daemonize", False))
