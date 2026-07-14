"""ADS1115-based thermistor temperature reader.

Reads single-ended ADC channels and converts millivolts to Celsius using a
piecewise-linear curve. Default calibration points (NTC-style, mV falls as
temperature rises):

    0 °C  -> 616 mV
   37 °C  -> 142 mV
   50 °C  ->  87 mV

Up to 8 channels are supported by spanning multiple ADS1115 chips: channel N
maps to ``i2c_addresses[N // 4]`` and pin ``N % 4``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# (millivolts, celsius) — sorted high-mV → low-mV for NTC-style sensors.
DEFAULT_MV_C_POINTS: Tuple[Tuple[float, float], ...] = (
    (616.0, 0.0),
    (142.0, 37.0),
    (87.0, 50.0),
)


def millivolts_to_celsius(
    millivolts: float,
    points: Sequence[Tuple[float, float]] = DEFAULT_MV_C_POINTS,
) -> float:
    """Piecewise-linear mV → °C conversion with endpoint extrapolation."""
    if not points:
        return float("nan")
    ordered = sorted(((float(mv), float(c)) for mv, c in points), key=lambda p: -p[0])
    mv = float(millivolts)

    if len(ordered) == 1:
        return ordered[0][1]

    # Above the highest-mV point (coldest): extrapolate using the first segment.
    if mv >= ordered[0][0]:
        return _lerp_mv_c(mv, ordered[0], ordered[1])

    # Below the lowest-mV point (hottest): extrapolate using the last segment.
    if mv <= ordered[-1][0]:
        return _lerp_mv_c(mv, ordered[-2], ordered[-1])

    for left, right in zip(ordered, ordered[1:]):
        if right[0] <= mv <= left[0]:
            return _lerp_mv_c(mv, left, right)

    return float("nan")


def _lerp_mv_c(
    mv: float,
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    mv_a, c_a = a
    mv_b, c_b = b
    if abs(mv_b - mv_a) < 1e-9:
        return c_a
    ratio = (mv - mv_a) / (mv_b - mv_a)
    return c_a + ratio * (c_b - c_a)


def _parse_conversion_points(raw) -> Tuple[Tuple[float, float], ...]:
    if not raw:
        return DEFAULT_MV_C_POINTS
    points: List[Tuple[float, float]] = []
    for item in raw:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append((float(item[0]), float(item[1])))
            elif isinstance(item, dict):
                points.append((float(item["mv"]), float(item["c"])))
        except (TypeError, ValueError, KeyError):
            continue
    return tuple(points) if points else DEFAULT_MV_C_POINTS


class ADS1115ThermistorReader:
    """Read thermistor channels from one or more ADS1115 ADCs."""

    _GAIN_MAP = {
        "2/3": 2 / 3,
        "1": 1,
        "2": 2,
        "4": 4,
        "8": 8,
        "16": 16,
    }
    _MAX_CHANNELS = 8

    def __init__(self, config: dict):
        ts_cfg = config.get("thermistor_sensors", {})
        self.enabled = bool(ts_cfg.get("enabled", False))
        self.i2c_addresses = self._parse_addresses(ts_cfg)
        self.channels = [int(ch) for ch in ts_cfg.get("channels", [0, 1, 2, 3])]
        self.channel_labels = self._parse_labels(ts_cfg)
        self.conversion_points = _parse_conversion_points(
            (ts_cfg.get("conversion", {}) or {}).get("points_mv_c")
        )
        self.last_error: Optional[str] = None
        self.is_initialized = False

        self._i2c = None
        self._ads_by_address: Dict[int, object] = {}
        self._analog_inputs: Dict[int, object] = {}

        if not self.enabled:
            self.last_error = "ADS1115 thermistor reader disabled by config"
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
            gain_key = str(ts_cfg.get("gain", "1"))
            data_rate = int(ts_cfg.get("data_rate", 128))
            gain = self._GAIN_MAP.get(gain_key, 1)

            for address in self.i2c_addresses:
                ads = ADS.ADS1115(self._i2c, address=address)
                ads.gain = gain
                ads.data_rate = data_rate
                ads.mode = Mode.SINGLE
                self._ads_by_address[address] = ads

            for channel in self.channels:
                ch = int(channel)
                if ch < 0 or ch >= self._MAX_CHANNELS:
                    continue
                address = self._address_for_channel(ch)
                ads = self._ads_by_address.get(address)
                pin = pin_map.get(ch % 4)
                if ads is None or pin is None:
                    continue
                self._analog_inputs[ch] = AnalogIn(ads, pin)

            self.is_initialized = bool(self._analog_inputs)
            if not self.is_initialized:
                self.last_error = "No valid ADS1115 thermistor channels configured"
        except Exception as exc:
            self.last_error = f"ADS1115 thermistor initialization failed: {exc}"

    @staticmethod
    def _parse_addresses(ts_cfg: dict) -> List[int]:
        raw = ts_cfg.get("i2c_addresses")
        if raw is None:
            raw = [ts_cfg.get("i2c_address", 0x48)]
        addresses: List[int] = []
        for item in raw:
            try:
                addresses.append(int(item))
            except (TypeError, ValueError):
                continue
        return addresses or [0x48]

    @staticmethod
    def _parse_labels(ts_cfg: dict) -> Dict[int, str]:
        raw = ts_cfg.get("labels", {}) or {}
        labels: Dict[int, str] = {}
        for key, value in raw.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        channel_configs = ts_cfg.get("channel_configs", {}) or {}
        for key, cfg in channel_configs.items():
            if not isinstance(cfg, dict) or not cfg.get("label"):
                continue
            try:
                labels[int(key)] = str(cfg["label"])
            except (TypeError, ValueError):
                continue
        return labels

    def _address_for_channel(self, channel: int) -> int:
        chip_index = int(channel) // 4
        if chip_index >= len(self.i2c_addresses):
            return self.i2c_addresses[-1]
        return self.i2c_addresses[chip_index]

    def _channel_label(self, channel: int) -> str:
        return self.channel_labels.get(channel, f"Therm {channel + 1}")

    def read_temperatures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        values: Dict[str, float] = {}
        for channel, analog in self._analog_inputs.items():
            try:
                millivolts = float(analog.voltage) * 1000.0
                values[self._channel_label(channel)] = millivolts_to_celsius(
                    millivolts, self.conversion_points
                )
            except Exception as exc:
                self.last_error = f"Thermistor read failed on channel {channel}: {exc}"
                values[self._channel_label(channel)] = float("nan")
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._ads_by_address = {}
        self._i2c = None
        self.is_initialized = False
