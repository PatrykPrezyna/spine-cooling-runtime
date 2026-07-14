"""ADS1115-based differential pressure sensor reader.

Each pressure sensor is differential and consumes two analog inputs.
One ADS1115 therefore serves at most two sensors:

    sensor N → chip ``i2c_addresses[N // 2]``
               pins (P0, P1) when N % 2 == 0
               pins (P2, P3) when N % 2 == 1

Four sensors need two chips (the third and fourth ADS1115 on the bus).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Lazy hardware imports so --sim / unit tests work off-Pi.


class ADS1115PressureReader:
    """Read differential pressure channels from one or more ADS1115 ADCs."""

    _GAIN_MAP = {
        "2/3": 2 / 3,
        "1": 1,
        "2": 2,
        "4": 4,
        "8": 8,
        "16": 16,
    }
    _MAX_SENSORS = 4
    # (positive_pin_index, negative_pin_index) per sensor slot on a chip.
    _DIFF_PAIRS = (
        (0, 1),
        (2, 3),
    )

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        # Defaults: third + fourth ADS1115 (thermistors use 0x48 / 0x49).
        self.i2c_addresses = self._parse_addresses(ps_cfg)
        self.channels = [int(ch) for ch in ps_cfg.get("channels", [0, 1, 2, 3])]
        self.channel_configs = ps_cfg.get("channel_configs", {}) or {}
        self.last_error: Optional[str] = None
        self.is_initialized = False

        self._i2c = None
        self._ads_by_address: Dict[int, object] = {}
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

            pin_map = {
                0: getattr(ADS, "P0", 0),
                1: getattr(ADS, "P1", 1),
                2: getattr(ADS, "P2", 2),
                3: getattr(ADS, "P3", 3),
            }

            self._i2c = busio.I2C(board.SCL, board.SDA)
            gain_key = str(ps_cfg.get("gain", "1"))
            data_rate = int(ps_cfg.get("data_rate", 128))
            gain = self._GAIN_MAP.get(gain_key, 1)

            for address in self.i2c_addresses:
                ads = ADS.ADS1115(self._i2c, address=address)
                ads.gain = gain
                ads.data_rate = data_rate
                ads.mode = Mode.SINGLE
                self._ads_by_address[address] = ads

            for channel in self.channels:
                ch = int(channel)
                if ch < 0 or ch >= self._MAX_SENSORS:
                    continue
                address = self._address_for_channel(ch)
                ads = self._ads_by_address.get(address)
                pos_idx, neg_idx = self._pins_for_channel(ch)
                pos = pin_map.get(pos_idx)
                neg = pin_map.get(neg_idx)
                if ads is None or pos is None or neg is None:
                    continue
                self._analog_inputs[ch] = AnalogIn(ads, pos, neg)

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
            raw = [single] if single is not None else [50, 51]
        addresses: List[int] = []
        for item in raw:
            try:
                addresses.append(int(item))
            except (TypeError, ValueError):
                continue
        return addresses or [50, 51]

    def _address_for_channel(self, channel: int) -> int:
        chip_index = int(channel) // 2
        if chip_index >= len(self.i2c_addresses):
            return self.i2c_addresses[-1]
        return self.i2c_addresses[chip_index]

    def _pins_for_channel(self, channel: int) -> Tuple[int, int]:
        cfg = self.channel_configs.get(
            str(channel), self.channel_configs.get(channel, {})
        )
        if isinstance(cfg, dict):
            try:
                if "positive_pin" in cfg and "negative_pin" in cfg:
                    return int(cfg["positive_pin"]), int(cfg["negative_pin"])
            except (TypeError, ValueError):
                pass
        return self._DIFF_PAIRS[int(channel) % 2]

    def _channel_label(self, channel: int) -> str:
        cfg = self.channel_configs.get(
            str(channel), self.channel_configs.get(channel, {})
        )
        if isinstance(cfg, dict):
            label = cfg.get("label")
            if label:
                return str(label)
        return f"Pressure {channel + 1}"

    def _channel_limits(self, channel: int) -> tuple[float, float, float, float]:
        cfg = self.channel_configs.get(
            str(channel), self.channel_configs.get(channel, {})
        )
        if not isinstance(cfg, dict):
            cfg = {}
        v_min = float(cfg.get("voltage_min", 0.5))
        v_max = float(cfg.get("voltage_max", 4.5))
        p_min = float(cfg.get("pressure_min", 0.0))
        p_max = float(cfg.get("pressure_max", 300.0))
        return v_min, v_max, p_min, p_max

    @staticmethod
    def _convert_voltage_to_pressure(
        voltage: float,
        voltage_min: float,
        voltage_max: float,
        pressure_min: float,
        pressure_max: float,
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
                values[self._channel_label(channel)] = self._convert_voltage_to_pressure(
                    voltage, v_min, v_max, p_min, p_max
                )
            except Exception as exc:
                self.last_error = f"Pressure read failed on channel {channel}: {exc}"
                values[self._channel_label(channel)] = float("nan")
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._ads_by_address = {}
        self._i2c = None
        self.is_initialized = False
