"""Thermocouple reader for Sequent SMtc boards (I2C).

Uses ``sm_tc`` only to program the sensor type at init time; runtime reads
go through a persistent ``smbus2.SMBus`` handle and a single block read so
the GIL is not held for repeated bus open/close cycles every second.
"""

from __future__ import annotations

import struct
from typing import Dict, Optional

import smbus2  # type: ignore
import sm_tc  # type: ignore
from temperature_calibration import (
    IDENTITY_CALIBRATION,
    apply_linear_calibration,
    build_two_point_calibration,
)


class ThermocoupleReader:
    """Read thermocouple channels from Sequent SMtc board."""

    _TYPE_MAP = {
        "B": 0,
        "E": 1,
        "J": 2,
        "K": 3,
        "N": 4,
        "R": 5,
        "S": 6,
        "T": 7,
    }

    # Layout from upstream sm_tc/__init__.py.
    _CARD_BASE_ADDRESS = 0x16
    _TCP_VAL1_ADD = 0
    _TEMP_SCALE_FACTOR = 10.0
    _IN_CH_COUNT = 8
    _TEMP_BLOCK_BYTES = _IN_CH_COUNT * 2  # 8 channels x int16

    def __init__(self, config: dict):
        tc_cfg = config.get("thermocouples", {})
        self.enabled = bool(tc_cfg.get("enabled", True))
        self.stack = int(tc_cfg.get("stack", 0))
        self.i2c_bus = int(tc_cfg.get("i2c_bus", 1))
        # Hardware input 1 on the HAT is broken; defaults skip it.
        self.channels = tc_cfg.get("channels", [2, 3, 4, 5, 6, 7])
        self._default_sensor_type_name = str(tc_cfg.get("sensor_type", "T")).upper()
        self._channel_sensor_type_codes = self._build_channel_sensor_type_codes(tc_cfg)
        configured_labels = tc_cfg.get(
            "labels",
            {
                2: "CSF Temp",
                3: "Heat Exchanger Temp",
                4: "Temp 3",
                5: "Temp 4",
                6: "Temp 5",
                7: "Temp 6",
            },
        )
        # Normalize keys so either "2" or 2 works in config.
        self.channel_labels = {}
        for key, value in configured_labels.items():
            try:
                self.channel_labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue

        self.is_initialized = False
        self.last_error: Optional[str] = None
        self._device = None
        self._bus: Optional[smbus2.SMBus] = None
        self._hw_address = self._CARD_BASE_ADDRESS + self.stack
        self._channel_calibration = self._build_calibration(tc_cfg)
        self._last_raw_temperatures: Dict[str, float] = {}

        if not self.enabled:
            self.last_error = "Thermocouple reader disabled by config"
            return

        try:
            self._device = sm_tc.SMtc(self.stack, self.i2c_bus)
            self._apply_sensor_type()
            # Persistent SMBus handle reused for every read; this avoids the
            # open/close churn the upstream lib does on every get_temp().
            self._bus = smbus2.SMBus(self.i2c_bus)
            self.is_initialized = True
        except Exception as exc:
            self.last_error = f"SMtc initialization failed: {exc}"

    def _build_calibration(self, tc_cfg: dict) -> Dict[int, tuple[float, float]]:
        """Build linear calibration params (gain, offset) for each channel."""
        calibration_cfg = tc_cfg.get("calibration", {})
        if not calibration_cfg:
            return {}

        default_gain, default_offset = IDENTITY_CALIBRATION
        if isinstance(calibration_cfg, dict):
            default_cfg = calibration_cfg.get("default", {})
            if isinstance(default_cfg, dict):
                default_gain, default_offset = self._compute_two_point_params(
                    default_cfg,
                    channel_name="default",
                )

        channels_cfg = calibration_cfg.get("channels", {}) if isinstance(calibration_cfg, dict) else {}
        params: Dict[int, tuple[float, float]] = {}
        for channel in self.channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue

            gain = default_gain
            offset = default_offset
            if isinstance(channels_cfg, dict):
                point_cfg = channels_cfg.get(str(ch), channels_cfg.get(ch))
                if isinstance(point_cfg, dict):
                    gain, offset = self._compute_two_point_params(
                        point_cfg,
                        channel_name=f"channel {ch}",
                    )
            params[ch] = (gain, offset)
        return params

    def _compute_two_point_params(
        self, point_cfg: dict, channel_name: str
    ) -> tuple[float, float]:
        """Calculate gain/offset from measured values at 0C and 100C."""
        calibration, error = build_two_point_calibration(
            point_cfg.get("measured_at_0c"),
            point_cfg.get("measured_at_100c"),
        )
        if error:
            self.last_error = f"Invalid calibration for {channel_name}: {error}"
        return calibration

    def _apply_calibration(self, channel: int, raw_temperature_c: float) -> float:
        """Apply per-channel linear calibration."""
        gain, offset = self._channel_calibration.get(int(channel), IDENTITY_CALIBRATION)
        return apply_linear_calibration(raw_temperature_c, gain, offset)

    def set_channel_two_point_calibration(
        self,
        channel: int,
        measured_at_0c: float,
        measured_at_100c: float,
    ) -> tuple[bool, str]:
        """Set runtime two-point calibration for one hardware channel."""
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            return False, f"Invalid channel: {channel}"
        if ch < 1 or ch > self._IN_CH_COUNT:
            return False, f"Channel out of range: {ch}"

        calibration, error = build_two_point_calibration(measured_at_0c, measured_at_100c)
        if error:
            msg = f"Invalid calibration for channel {ch}: {error}"
            self.last_error = msg
            return False, msg

        self._channel_calibration[ch] = calibration
        self.last_error = None
        return True, f"Calibration updated for channel {ch}"

    def _apply_sensor_type(self) -> None:
        """Set configured thermocouple type on all active channels."""
        if not self._device:
            return
        for channel in self.channels:
            ch = int(channel)
            type_code = self._channel_sensor_type_codes.get(ch, self._TYPE_MAP["T"])
            self._device.set_sensor_type(ch, type_code)

    def _build_channel_sensor_type_codes(self, tc_cfg: dict) -> Dict[int, int]:
        """Build per-channel thermocouple type codes from config."""
        default_code = self._TYPE_MAP.get(self._default_sensor_type_name, self._TYPE_MAP["T"])
        configured_map = tc_cfg.get("sensor_types", {})
        channel_codes: Dict[int, int] = {}
        for channel in self.channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            type_name = self._default_sensor_type_name
            if isinstance(configured_map, dict):
                override = configured_map.get(str(ch), configured_map.get(ch))
                if override is not None:
                    type_name = str(override).upper()
            channel_codes[ch] = self._TYPE_MAP.get(type_name, default_code)
        return channel_codes

    def set_channel_sensor_type(self, channel: int, sensor_type_name: str) -> tuple[bool, str]:
        """Set per-channel thermocouple type at runtime."""
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            return False, f"Invalid channel: {channel}"
        if ch < 1 or ch > self._IN_CH_COUNT:
            return False, f"Channel out of range: {ch}"

        type_name = str(sensor_type_name).upper().strip()
        if type_name not in self._TYPE_MAP:
            return False, f"Unsupported sensor type: {sensor_type_name}"
        type_code = self._TYPE_MAP[type_name]

        try:
            if self._device is not None:
                self._device.set_sensor_type(ch, type_code)
        except Exception as exc:
            msg = f"Failed setting sensor type for channel {ch}: {exc}"
            self.last_error = msg
            return False, msg

        self._channel_sensor_type_codes[ch] = type_code
        self.last_error = None
        return True, f"Sensor type {type_name} set on channel {ch}"

    def read_temperatures(self) -> Dict[str, float]:
        """
        Read configured thermocouple channels.

        Returns:
            dict[str, float]: mapping from label to temperature in Celsius.
            Returns empty dict when not initialized.
        """
        if not self.is_initialized or self._bus is None:
            return {}

        try:
            block = self._bus.read_i2c_block_data(
                self._hw_address, self._TCP_VAL1_ADD, self._TEMP_BLOCK_BYTES
            )
        except Exception as exc:
            # Block read may fail if the bus is busy or disconnected. Fall
            # back to per-channel reads so a single failure doesn't kill
            # the rest of the cycle.
            return self._read_temperatures_per_channel(exc)

        values: Dict[str, float] = {}
        raw_values: Dict[str, float] = {}
        for channel in self.channels:
            try:
                ch = int(channel)
                if ch < 1 or ch > self._IN_CH_COUNT:
                    continue
                offset = (ch - 1) * 2
                raw = struct.unpack(
                    "h", bytes(block[offset:offset + 2])
                )[0]
                label = self.channel_labels.get(ch, f"Temp {ch}")
                raw_temperature_c = raw / self._TEMP_SCALE_FACTOR
                raw_values[label] = raw_temperature_c
                values[label] = self._apply_calibration(ch, raw_temperature_c)
            except Exception as exc:
                self.last_error = f"Failed parsing thermocouple channel {channel}: {exc}"
        self._last_raw_temperatures = raw_values
        return values

    def _read_temperatures_per_channel(self, block_error: Exception) -> Dict[str, float]:
        """Slow-path fallback used when the block read fails."""
        values: Dict[str, float] = {}
        raw_values: Dict[str, float] = {}
        if self._bus is None:
            self.last_error = f"Block read failed: {block_error}"
            return values
        for channel in self.channels:
            try:
                ch = int(channel)
                offset = self._TCP_VAL1_ADD + (ch - 1) * 2
                pair = self._bus.read_i2c_block_data(self._hw_address, offset, 2)
                raw = struct.unpack("h", bytes(pair))[0]
                label = self.channel_labels.get(ch, f"Temp {ch}")
                raw_temperature_c = raw / self._TEMP_SCALE_FACTOR
                raw_values[label] = raw_temperature_c
                values[label] = self._apply_calibration(ch, raw_temperature_c)
            except Exception as exc:
                self.last_error = f"Failed reading thermocouple channel {channel}: {exc}"
        self._last_raw_temperatures = raw_values
        return values

    def get_last_raw_temperatures(self) -> Dict[str, float]:
        """Return latest raw (uncalibrated) readings keyed by sensor label."""
        return dict(self._last_raw_temperatures)

    def cleanup(self) -> None:
        """Close the persistent I2C bus handle."""
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self.is_initialized = False
