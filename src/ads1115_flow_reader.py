"""4–20 mA flow sensor on a single-ended ADS1115 input.

The loop is dropped across a shunt (default 220 Ω) at analog input 0 of
the ADS1115 at 0x49 on I2C bus 6. Voltage → current → linear ml/min.

20 mA × 220 Ω = 4.40 V, so PGA gain 2/3 (±6.144 V) is required.
"""

from __future__ import annotations

from typing import Optional

from ads1115_thermistor_reader import _open_i2c_bus

_DEFAULT_SHUNT_OHM = 220.0
_DEFAULT_MA_LO = 4.0
_DEFAULT_MA_HI = 20.0
_DEFAULT_FLOW_LO = 0.0
_DEFAULT_FLOW_HI = 100.0
_GAIN_MAP = {
    "2/3": 2 / 3,
    "1": 1,
    "2": 2,
    "4": 4,
    "8": 8,
    "16": 16,
}


def voltage_to_ma(voltage_v: float, shunt_ohm: float = _DEFAULT_SHUNT_OHM) -> float:
    """Ohm's law: I = V / R, returned in milliamps."""
    return 1000.0 * float(voltage_v) / float(shunt_ohm)


def ma_to_flow_ml_per_min(
    ma: float,
    ma_lo: float = _DEFAULT_MA_LO,
    ma_hi: float = _DEFAULT_MA_HI,
    flow_lo: float = _DEFAULT_FLOW_LO,
    flow_hi: float = _DEFAULT_FLOW_HI,
) -> float:
    """Linear 4–20 mA → ml/min."""
    return flow_lo + (float(ma) - ma_lo) * (flow_hi - flow_lo) / (ma_hi - ma_lo)


def voltage_to_flow_ml_per_min(
    voltage_v: float,
    shunt_ohm: float = _DEFAULT_SHUNT_OHM,
    ma_lo: float = _DEFAULT_MA_LO,
    ma_hi: float = _DEFAULT_MA_HI,
    flow_lo: float = _DEFAULT_FLOW_LO,
    flow_hi: float = _DEFAULT_FLOW_HI,
) -> float:
    return ma_to_flow_ml_per_min(
        voltage_to_ma(voltage_v, shunt_ohm),
        ma_lo=ma_lo,
        ma_hi=ma_hi,
        flow_lo=flow_lo,
        flow_hi=flow_hi,
    )


class ADS1115FlowReader:
    """Read one 4–20 mA flow channel as ml/min."""

    def __init__(self, config: dict):
        fs_cfg = config.get("flow_sensor", {}) or {}
        self.enabled = bool(fs_cfg.get("enabled", False))
        self.i2c_bus = int(fs_cfg.get("i2c_bus", 6))
        self.i2c_address = int(fs_cfg.get("i2c_address", 0x49))
        self.analog_input = int(fs_cfg.get("analog_input", 0))
        self.shunt_ohm = float(fs_cfg.get("shunt_ohm", _DEFAULT_SHUNT_OHM))
        self.ma_lo = float(fs_cfg.get("ma_lo", _DEFAULT_MA_LO))
        self.ma_hi = float(fs_cfg.get("ma_hi", _DEFAULT_MA_HI))
        self.flow_lo = float(fs_cfg.get("flow_lo_ml_per_min", _DEFAULT_FLOW_LO))
        self.flow_hi = float(fs_cfg.get("flow_hi_ml_per_min", _DEFAULT_FLOW_HI))
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._i2c = None
        self._analog = None

        if not self.enabled:
            self.last_error = "Flow sensor disabled by config"
            return

        try:
            import adafruit_ads1x15.ads1115 as ADS  # type: ignore
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore

            try:
                from adafruit_ads1x15.ads1x15 import Mode  # type: ignore
            except Exception:  # pragma: no cover
                from adafruit_ads1x15.ads1115 import Mode  # type: ignore

            pin_map = {
                0: getattr(ADS, "P0", 0),
                1: getattr(ADS, "P1", 1),
                2: getattr(ADS, "P2", 2),
                3: getattr(ADS, "P3", 3),
            }
            pin = pin_map.get(self.analog_input)
            if pin is None:
                self.last_error = f"Invalid flow analog_input {self.analog_input}"
                return

            self._i2c = _open_i2c_bus(self.i2c_bus)
            ads = ADS.ADS1115(self._i2c, address=self.i2c_address)
            gain_key = str(fs_cfg.get("gain", "2/3"))
            ads.gain = _GAIN_MAP.get(gain_key, 2 / 3)
            ads.data_rate = int(fs_cfg.get("data_rate", 128))
            ads.mode = Mode.SINGLE
            self._analog = AnalogIn(ads, pin)
            self.is_initialized = True
        except Exception as exc:
            self.last_error = f"ADS1115 flow initialization failed: {exc}"

    def read_flow_ml_per_min(self) -> Optional[float]:
        if not self.is_initialized or self._analog is None:
            return None
        try:
            voltage_v = float(self._analog.voltage)
            return voltage_to_flow_ml_per_min(
                voltage_v,
                shunt_ohm=self.shunt_ohm,
                ma_lo=self.ma_lo,
                ma_hi=self.ma_hi,
                flow_lo=self.flow_lo,
                flow_hi=self.flow_hi,
            )
        except Exception as exc:
            self.last_error = f"Flow read failed: {exc}"
            return float("nan")

    def cleanup(self) -> None:
        self._analog = None
        self._i2c = None
        self.is_initialized = False
