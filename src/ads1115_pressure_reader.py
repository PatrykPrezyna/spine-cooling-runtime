"""ADS1115-based pressure sensor reader."""

from __future__ import annotations

from typing import Dict, Optional

import board  # type: ignore
import busio  # type: ignore
from adafruit_ads1x15.ads1115 import ADS1115, Mode, P0, P1, P2, P3  # type: ignore
from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore


class ADS1115PressureReader:
    """Read pressure channels from ADS1115 and convert voltage to pressure units."""

    _GAIN_MAP = {
        "2/3": 2 / 3,
        "1": 1,
        "2": 2,
        "4": 4,
        "8": 8,
        "16": 16,
    }
    _PIN_MAP = {0: P0, 1: P1, 2: P2, 3: P3}

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        self.i2c_address = int(ps_cfg.get("i2c_address", 0x48))
        self.channels = ps_cfg.get("channels", [0, 1])
        self.channel_configs = ps_cfg.get("channel_configs", {})
        self.last_error: Optional[str] = None
        self.is_initialized = False

        self._i2c = None
        self._ads: Optional[ADS1115] = None
        self._analog_inputs: Dict[int, AnalogIn] = {}

        if not self.enabled:
            self.last_error = "ADS1115 pressure reader disabled by config"
            return

        try:
            self._i2c = busio.I2C(board.SCL, board.SDA)
            self._ads = ADS1115(self._i2c, address=self.i2c_address)
            gain_key = str(ps_cfg.get("gain", "1"))
            self._ads.gain = self._GAIN_MAP.get(gain_key, 1)
            self._ads.data_rate = int(ps_cfg.get("data_rate", 128))
            self._ads.mode = Mode.SINGLE
            for channel in self.channels:
                ch = int(channel)
                pin = self._PIN_MAP.get(ch)
                if pin is None:
                    continue
                self._analog_inputs[ch] = AnalogIn(self._ads, pin)
            self.is_initialized = bool(self._analog_inputs)
            if not self.is_initialized:
                self.last_error = "No valid ADS1115 channels configured"
        except Exception as exc:
            self.last_error = f"ADS1115 initialization failed: {exc}"

    def _channel_label(self, channel: int) -> str:
        cfg = self.channel_configs.get(str(channel), self.channel_configs.get(channel, {}))
        if isinstance(cfg, dict):
            label = cfg.get("label")
            if label:
                return str(label)
        return f"Pressure {channel + 1}"

    def _channel_limits(self, channel: int) -> tuple[float, float, float, float]:
        cfg = self.channel_configs.get(str(channel), self.channel_configs.get(channel, {}))
        if not isinstance(cfg, dict):
            cfg = {}
        v_min = float(cfg.get("voltage_min", 0.5))
        v_max = float(cfg.get("voltage_max", 4.5))
        p_min = float(cfg.get("pressure_min", 0.0))
        p_max = float(cfg.get("pressure_max", 300.0))
        return v_min, v_max, p_min, p_max

    @staticmethod
    def _convert_voltage_to_pressure(
        voltage: float, voltage_min: float, voltage_max: float, pressure_min: float, pressure_max: float
    ) -> float:
        if abs(voltage_max - voltage_min) < 1e-9:
            return float("nan")
        ratio = (float(voltage) - voltage_min) / (voltage_max - voltage_min)
        ratio = max(0.0, min(1.0, ratio))
        return pressure_min + ratio * (pressure_max - pressure_min)

    def read_pressures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        values: Dict[str, float] = {}
        for channel, analog in self._analog_inputs.items():
            try:
                voltage = float(analog.voltage)
                v_min, v_max, p_min, p_max = self._channel_limits(channel)
                pressure = self._convert_voltage_to_pressure(voltage, v_min, v_max, p_min, p_max)
                values[self._channel_label(channel)] = pressure
            except Exception as exc:
                self.last_error = f"Pressure read failed on channel {channel}: {exc}"
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._ads = None
        self._i2c = None
        self.is_initialized = False
