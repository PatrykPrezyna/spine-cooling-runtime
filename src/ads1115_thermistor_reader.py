"""ADS1115 thermistor reader.

Hardware is fixed (not config):

- 12 single-ended channels on three chips
- 0–3:  i2c-1 0x48
- 4–7:  i2c-1 0x49
- 8–11: i2c-6 0x48
- gain 1 (±4.096 V), 128 SPS, single-shot

Conversion is fixed: 2.5 V / 100 kΩ divider. MA300TA103C for every
channel except 0 (Tip), which uses the AB6N2 table.

Only ``thermistor_sensors.labels`` is read from config (channel → name).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from thermistor_conversion import (
    DEFAULT_RS_OHM,
    DEFAULT_VREF_V,
    load_rt_table,
    millivolts_to_celsius,
)

ChipKey = Tuple[int, int]
RtPoint = Tuple[float, float]

_CHIPS: Tuple[ChipKey, ...] = (
    (1, 0x48),
    (1, 0x49),
    (6, 0x48),
)
_CHANNEL_COUNT = 12
_GAIN = 1
_DATA_RATE = 128
_TIP_CHANNEL = 0
_TIP_TABLE_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "calibration"
    / "Thermistor_AB6N2-GC14KA143E_37C.csv"
)
_TIP_R_COL = "Resistance_Ohm"


def chip_key_for_channel(channel: int) -> ChipKey:
    return _CHIPS[int(channel) // 4]


def labels_from_config(config: dict) -> Dict[int, str]:
    raw = (config.get("thermistor_sensors") or {}).get("labels") or {}
    labels: Dict[int, str] = {}
    for key, value in raw.items():
        try:
            labels[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return labels


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
    """Read the 12 thermistor channels and convert voltage to °C."""

    def __init__(self, config: dict):
        self.channel_labels = labels_from_config(config)
        self.rt_table: Sequence[RtPoint] = load_rt_table()
        self._tip_table: Sequence[RtPoint] = load_rt_table(
            _TIP_TABLE_CSV, r_col=_TIP_R_COL
        )
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._i2c_by_bus: Dict[int, object] = {}
        self._ads_by_chip: Dict[ChipKey, object] = {}
        self._analog_inputs: Dict[int, object] = {}

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

        pins = (
            getattr(ADS, "P0", 0),
            getattr(ADS, "P1", 1),
            getattr(ADS, "P2", 2),
            getattr(ADS, "P3", 3),
        )
        errors: list[str] = []
        for bus_id, address in _CHIPS:
            try:
                ads = ADS.ADS1115(self._i2c_for(bus_id), address=address)
                ads.gain = _GAIN
                ads.data_rate = _DATA_RATE
                ads.mode = Mode.SINGLE
                self._ads_by_chip[(bus_id, address)] = ads
            except Exception as exc:
                errors.append(f"0x{address:X} on i2c-{bus_id}: {exc}")

        for channel in range(_CHANNEL_COUNT):
            ads = self._ads_by_chip.get(chip_key_for_channel(channel))
            if ads is None:
                continue
            self._analog_inputs[channel] = AnalogIn(ads, pins[channel % 4])

        self.is_initialized = bool(self._analog_inputs)
        if errors:
            self.last_error = "; ".join(errors)
        if not self.is_initialized:
            self.last_error = (
                self.last_error or "No ADS1115 thermistor channels opened"
            )

    def _i2c_for(self, bus_id: int):
        if bus_id not in self._i2c_by_bus:
            self._i2c_by_bus[bus_id] = _open_i2c_bus(bus_id)
        return self._i2c_by_bus[bus_id]

    def _label(self, channel: int) -> str:
        return self.channel_labels.get(channel, f"Therm {channel + 1}")

    def _table_for(self, channel: int) -> Sequence[RtPoint]:
        if int(channel) == _TIP_CHANNEL:
            return self._tip_table
        return self.rt_table

    def read_temperatures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        values: Dict[str, float] = {}
        for channel, analog in self._analog_inputs.items():
            try:
                millivolts = float(analog.voltage) * 1000.0
                values[self._label(channel)] = millivolts_to_celsius(
                    millivolts,
                    self._table_for(channel),
                    vref_v=DEFAULT_VREF_V,
                    rs_ohm=DEFAULT_RS_OHM,
                )
            except Exception as exc:
                self.last_error = f"Thermistor read failed on channel {channel}: {exc}"
                values[self._label(channel)] = float("nan")
        return values

    def cleanup(self) -> None:
        self._analog_inputs = {}
        self._ads_by_chip = {}
        self._i2c_by_bus = {}
        self.is_initialized = False
