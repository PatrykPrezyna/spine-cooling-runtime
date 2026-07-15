"""ADS1115 differential pressure reader (psi).

Each sensor uses one differential pair (two analog inputs), so one chip
serves two sensors:

    channel 0 → address[0], P0-P1
    channel 1 → address[0], P2-P3
    channel 2 → address[1], P0-P1
    channel 3 → address[1], P2-P3

Conversion matches the simple example: linear mV → psi.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# Default calibration (same as simple_examples/ads1115_pressure.py).
_MV_LO, _PSI_LO = -14.858, -11.5
_MV_HI, _PSI_HI = 96.9, 75.0

# Differential pin pairs on one ADS1115.
_DIFF_PAIRS = (
    (0, 1),  # P0 - P1
    (2, 3),  # P2 - P3
)


def mv_to_psi(
    mv: float,
    mv_lo: float = _MV_LO,
    psi_lo: float = _PSI_LO,
    mv_hi: float = _MV_HI,
    psi_hi: float = _PSI_HI,
) -> float:
    """Linear convert millivolts to psi between two calibration points."""
    return psi_lo + (mv - mv_lo) * (psi_hi - psi_lo) / (mv_hi - mv_lo)


class ADS1115PressureReader:
    """Read up to four differential pressure channels as psi."""

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        self.i2c_addresses = self._parse_addresses(ps_cfg)
        self.channels = [int(ch) for ch in ps_cfg.get("channels", [0, 1, 2, 3])]
        self.channel_configs = ps_cfg.get("channel_configs", {}) or {}
        self.gain = int(ps_cfg.get("gain", 16))
        self.data_rate = int(ps_cfg.get("data_rate", 860))
        self.last_error: Optional[str] = None
        self.is_initialized = False

        cal = ps_cfg.get("calibration", {}) or {}
        self._mv_lo = float(cal.get("mv_lo", _MV_LO))
        self._psi_lo = float(cal.get("psi_lo", _PSI_LO))
        self._mv_hi = float(cal.get("mv_hi", _MV_HI))
        self._psi_hi = float(cal.get("psi_hi", _PSI_HI))

        self._i2c = None
        self._analog_inputs: Dict[int, object] = {}

        if not self.enabled:
            self.last_error = "ADS1115 pressure reader disabled by config"
            return

        try:
            import board  # type: ignore
            import busio  # type: ignore
            import adafruit_ads1x15.ads1115 as ADS  # type: ignore
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore

            try:
                from adafruit_ads1x15.ads1x15 import Mode  # type: ignore
            except Exception:  # pragma: no cover
                from adafruit_ads1x15.ads1115 import Mode  # type: ignore

            pins = (
                getattr(ADS, "P0", 0),
                getattr(ADS, "P1", 1),
                getattr(ADS, "P2", 2),
                getattr(ADS, "P3", 3),
            )

            self._i2c = busio.I2C(board.SCL, board.SDA)
            ads_by_address: Dict[int, object] = {}

            for address in self.i2c_addresses:
                ads = ADS.ADS1115(self._i2c, address=address)
                ads.gain = self.gain
                ads.data_rate = self.data_rate
                ads.mode = Mode.SINGLE
                ads_by_address[address] = ads

            for channel in self.channels:
                if channel < 0 or channel >= 4:
                    continue
                address = self._address_for_channel(channel)
                ads = ads_by_address.get(address)
                if ads is None:
                    continue
                pos_idx, neg_idx = _DIFF_PAIRS[channel % 2]
                self._analog_inputs[channel] = AnalogIn(
                    ads, pins[pos_idx], pins[neg_idx]
                )

            self.is_initialized = bool(self._analog_inputs)
            if not self.is_initialized:
                self.last_error = "No valid ADS1115 differential pressure channels configured"
        except Exception as exc:
            self.last_error = f"ADS1115 pressure initialization failed: {exc}"

    @staticmethod
    def _parse_addresses(ps_cfg: dict) -> List[int]:
        raw = ps_cfg.get("i2c_addresses")
        if raw is None:
            single = ps_cfg.get("i2c_address")
            raw = [single] if single is not None else [74, 75]
        addresses: List[int] = []
        for item in raw:
            try:
                addresses.append(int(item))
            except (TypeError, ValueError):
                continue
        return addresses or [74, 75]

    def _address_for_channel(self, channel: int) -> int:
        chip_index = channel // 2
        if chip_index >= len(self.i2c_addresses):
            return self.i2c_addresses[-1]
        return self.i2c_addresses[chip_index]

    def _channel_label(self, channel: int) -> str:
        cfg = self.channel_configs.get(
            str(channel), self.channel_configs.get(channel, {})
        )
        if isinstance(cfg, dict) and cfg.get("label"):
            return str(cfg["label"])
        return f"Pressure {channel + 1}"

    def read_pressures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        values: Dict[str, float] = {}
        for channel, analog in self._analog_inputs.items():
            label = self._channel_label(channel)
            try:
                mv = float(analog.voltage) * 1000.0
                values[label] = mv_to_psi(
                    mv, self._mv_lo, self._psi_lo, self._mv_hi, self._psi_hi
                )
            except Exception as exc:
                self.last_error = f"Pressure read failed on channel {channel}: {exc}"
                values[label] = float("nan")
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._i2c = None
        self.is_initialized = False
