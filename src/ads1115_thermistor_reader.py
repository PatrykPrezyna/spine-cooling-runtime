"""ADS1115-based thermistor temperature reader.

Reads single-ended ADC channels and converts voltage to Celsius using an R–T
table and the divider ``V = Vref * R / (Rs + R)``.

Default conversion uses the MA300TA103C table. Individual channels may override
``table_csv`` / ``resistance_column`` via ``channel_configs``.

Multiple ADS1115 chips: channel N maps to chip ``N // 4`` (address
``i2c_addresses[N // 4]``, bus ``i2c_buses[N // 4]``) and pin ``N % 4``.
The same address may be reused on a different bus (for example 0x48 on
bus 1 and bus 6).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from thermistor_conversion import (
    DEFAULT_RS_OHM,
    DEFAULT_R_COL,
    DEFAULT_TABLE_CSV,
    DEFAULT_VREF_V,
    load_rt_table,
    millivolts_to_celsius,
    resolve_table_path,
)

ChipKey = Tuple[int, int]
RtPoint = Tuple[float, float]


def _open_i2c_bus(bus_id: int):
    """Open Blinka I2C for ``/dev/i2c-<bus_id>``. Bus 1 uses the default pins."""
    bus_id = int(bus_id)
    if bus_id == 1:
        import board  # type: ignore
        import busio  # type: ignore

        return busio.I2C(board.SCL, board.SDA)
    from adafruit_extended_bus import ExtendedI2C  # type: ignore

    return ExtendedI2C(bus_id)


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

    def __init__(self, config: dict):
        ts_cfg = config.get("thermistor_sensors", {})
        self.enabled = bool(ts_cfg.get("enabled", False))
        self.i2c_addresses = self._parse_addresses(ts_cfg)
        self.i2c_buses = self._parse_buses(ts_cfg, len(self.i2c_addresses))
        self.channels = [int(ch) for ch in ts_cfg.get("channels", [0, 1, 2, 3])]
        self.channel_labels = self._parse_labels(ts_cfg)
        conv = ts_cfg.get("conversion", {}) or {}
        self.vref_v = float(conv.get("vref_v", DEFAULT_VREF_V))
        self.rs_ohm = float(conv.get("rs_ohm", DEFAULT_RS_OHM))
        self.rt_table: Sequence[RtPoint] = self._load_conversion_table(conv)
        self._channel_rt_tables: Dict[int, Sequence[RtPoint]] = (
            self._load_channel_tables(ts_cfg, conv)
        )
        self.last_error: Optional[str] = None
        self.is_initialized = False

        self._i2c_by_bus: Dict[int, object] = {}
        self._ads_by_chip: Dict[ChipKey, object] = {}
        self._analog_inputs: Dict[int, object] = {}

        if not self.enabled:
            self.last_error = "ADS1115 thermistor reader disabled by config"
            return

        try:
            import adafruit_ads1x15.ads1115 as ADS  # type: ignore
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore

            try:
                from adafruit_ads1x15.ads1x15 import Mode  # type: ignore
            except Exception:  # pragma: no cover
                from adafruit_ads1x15.ads1115 import Mode  # type: ignore
        except Exception as exc:
            self.last_error = f"ADS1115 thermistor initialization failed: {exc}"
            return

        pin_map = {
            0: getattr(ADS, "P0", 0),
            1: getattr(ADS, "P1", 1),
            2: getattr(ADS, "P2", 2),
            3: getattr(ADS, "P3", 3),
        }
        gain_key = str(ts_cfg.get("gain", "1"))
        data_rate = int(ts_cfg.get("data_rate", 128))
        gain = self._GAIN_MAP.get(gain_key, 1)
        errors: List[str] = []

        for address, bus_id in zip(self.i2c_addresses, self.i2c_buses):
            key = (bus_id, address)
            if key in self._ads_by_chip:
                continue
            try:
                ads = ADS.ADS1115(self._i2c_for(bus_id), address=address)
                ads.gain = gain
                ads.data_rate = data_rate
                ads.mode = Mode.SINGLE
                self._ads_by_chip[key] = ads
            except Exception as exc:
                errors.append(f"0x{address:X} on i2c-{bus_id}: {exc}")

        max_channel = len(self.i2c_addresses) * 4
        for channel in self.channels:
            ch = int(channel)
            if ch < 0 or ch >= max_channel:
                continue
            ads = self._ads_by_chip.get(self._chip_key_for_channel(ch))
            pin = pin_map.get(ch % 4)
            if ads is None or pin is None:
                continue
            self._analog_inputs[ch] = AnalogIn(ads, pin)

        self.is_initialized = bool(self._analog_inputs)
        if errors:
            self.last_error = "; ".join(errors)
        if not self.is_initialized:
            self.last_error = (
                self.last_error or "No valid ADS1115 thermistor channels configured"
            )

    @staticmethod
    def _load_conversion_table(conv: dict) -> Sequence[RtPoint]:
        path = resolve_table_path(conv.get("table_csv", DEFAULT_TABLE_CSV))
        r_col = str(conv.get("resistance_column", DEFAULT_R_COL))
        return load_rt_table(path, r_col=r_col)

    @classmethod
    def _load_channel_tables(
        cls, ts_cfg: dict, default_conv: dict
    ) -> Dict[int, Sequence[RtPoint]]:
        """Load per-channel R–T overrides from ``channel_configs``."""
        tables: Dict[int, Sequence[RtPoint]] = {}
        channel_configs = ts_cfg.get("channel_configs", {}) or {}
        for key, cfg in channel_configs.items():
            if not isinstance(cfg, dict):
                continue
            if "table_csv" not in cfg and "resistance_column" not in cfg:
                continue
            try:
                channel = int(key)
            except (TypeError, ValueError):
                continue
            override = {
                "table_csv": cfg.get("table_csv", default_conv.get("table_csv")),
                "resistance_column": cfg.get(
                    "resistance_column", default_conv.get("resistance_column")
                ),
            }
            tables[channel] = cls._load_conversion_table(override)
        return tables

    def _rt_table_for_channel(self, channel: int) -> Sequence[RtPoint]:
        return self._channel_rt_tables.get(int(channel), self.rt_table)

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
    def _parse_buses(ts_cfg: dict, n_chips: int) -> List[int]:
        """Parallel to ``i2c_addresses``; missing entries default to bus 1."""
        n_chips = max(int(n_chips), 1)
        default = int(ts_cfg.get("i2c_bus", 1))
        raw = ts_cfg.get("i2c_buses")
        if raw is None:
            return [default] * n_chips
        buses: List[int] = []
        for item in raw:
            try:
                buses.append(int(item))
            except (TypeError, ValueError):
                continue
        if not buses:
            return [default] * n_chips
        if len(buses) < n_chips:
            buses.extend([buses[-1]] * (n_chips - len(buses)))
        return buses[:n_chips]

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

    def _chip_index(self, channel: int) -> int:
        return int(channel) // 4

    def _chip_key_for_channel(self, channel: int) -> ChipKey:
        idx = self._chip_index(channel)
        address = (
            self.i2c_addresses[-1]
            if idx >= len(self.i2c_addresses)
            else self.i2c_addresses[idx]
        )
        bus_id = (
            self.i2c_buses[-1] if idx >= len(self.i2c_buses) else self.i2c_buses[idx]
        )
        return (bus_id, address)

    def _address_for_channel(self, channel: int) -> int:
        return self._chip_key_for_channel(channel)[1]

    def _i2c_for(self, bus_id: int):
        if bus_id not in self._i2c_by_bus:
            self._i2c_by_bus[bus_id] = _open_i2c_bus(bus_id)
        return self._i2c_by_bus[bus_id]

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
                    millivolts,
                    self._rt_table_for_channel(channel),
                    vref_v=self.vref_v,
                    rs_ohm=self.rs_ohm,
                )
            except Exception as exc:
                self.last_error = f"Thermistor read failed on channel {channel}: {exc}"
                values[self._channel_label(channel)] = float("nan")
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._ads_by_chip = {}
        self._i2c_by_bus = {}
        self.is_initialized = False
