"""Compressor UART driver.

Implements the 16-byte command/response protocol from the compressor
specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import serial  # type: ignore


@dataclass
class CompressorTelemetry:
    actual_rpm: int
    current_a: float
    bus_voltage_v: float
    fault_manual: int
    fault_auto: int
    raw_reply: bytes

    def has_fault(self) -> bool:
        return bool(self.fault_manual or self.fault_auto)

    def fault_flags(self) -> Dict[str, bool]:
        bit_names = {
            0: "software_overcurrent",
            1: "overvoltage",
            2: "undervoltage",
            3: "phase_loss",
            4: "stall",
            5: "hardware_overcurrent",
            6: "abnormal_phase_current",
        }
        merged = self.fault_manual | self.fault_auto
        return {name: bool(merged & (1 << bit)) for bit, name in bit_names.items()}


class CompressorUartDriver:
    """UART master driver for compressor board."""

    FRAME_LEN = 16
    START_BYTE = 0xAA
    END_BYTE = 0x55
    MASTER_ADDR = 0x00
    SLAVE_ADDR = 0x01

    def __init__(self, config: dict):
        c_cfg = config.get("compressor", {})
        self.enabled = bool(c_cfg.get("enabled", False))
        self.port = str(c_cfg.get("port", "/dev/ttyS0"))
        self.baudrate = int(c_cfg.get("baudrate", 600))
        self.timeout_s = float(c_cfg.get("timeout_s", 0.08))
        self.max_speed_rpm = int(c_cfg.get("max_speed_rpm", 6000))

        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._serial = None

        if not self.enabled:
            self.last_error = "Compressor UART disabled by config"
            return

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout_s,
                write_timeout=self.timeout_s,
            )
            self.is_initialized = True
        except Exception as exc:
            self.last_error = f"Compressor UART init failed: {exc}"

    @staticmethod
    def _checksum(frame: bytes) -> int:
        """
        Checksum rule from spec:
        reverse + 1 over sum(byte1..byte13) == two's complement.
        """
        if len(frame) < 14:
            return 0
        sum_1_to_13 = sum(frame[1:14]) & 0xFF
        return (-sum_1_to_13) & 0xFF

    def _build_command_frame(self, on: bool, set_speed_rpm: int) -> bytes:
        speed = max(0, min(int(set_speed_rpm), self.max_speed_rpm))
        frame = bytearray(self.FRAME_LEN)
        frame[0] = self.START_BYTE
        frame[1] = self.MASTER_ADDR
        frame[2] = 0x01 if on else 0x00
        frame[3] = speed & 0xFF          # low byte
        frame[4] = (speed >> 8) & 0xFF   # high byte
        for idx in range(5, 14):
            frame[idx] = 0x00
        frame[14] = self._checksum(frame)
        frame[15] = self.END_BYTE
        return bytes(frame)

    def _parse_reply(self, reply: bytes) -> CompressorTelemetry:
        if len(reply) != self.FRAME_LEN:
            raise ValueError(f"Invalid reply length: {len(reply)}")
        if reply[0] != self.START_BYTE or reply[15] != self.END_BYTE:
            raise ValueError("Invalid reply frame markers")
        if reply[1] != self.SLAVE_ADDR:
            raise ValueError(f"Invalid slave address byte: 0x{reply[1]:02X}")

        expected_checksum = self._checksum(reply)
        if reply[14] != expected_checksum:
            raise ValueError(
                f"Reply checksum mismatch: got 0x{reply[14]:02X}, expected 0x{expected_checksum:02X}"
            )

        actual_rpm = int(reply[2] | (reply[3] << 8))
        current_raw = int(reply[4] | (reply[5] << 8))
        voltage_raw = int(reply[6] | (reply[7] << 8))
        fault_manual = int(reply[9])
        fault_auto = int(reply[13])

        return CompressorTelemetry(
            actual_rpm=actual_rpm,
            current_a=current_raw / 10.0,
            bus_voltage_v=voltage_raw / 10.0,
            fault_manual=fault_manual,
            fault_auto=fault_auto,
            raw_reply=reply,
        )

    def exchange(self, on: bool, set_speed_rpm: int) -> Optional[CompressorTelemetry]:
        """Send one command frame and parse one 16-byte reply frame."""
        if not self.is_initialized:
            return None

        command = self._build_command_frame(on, set_speed_rpm)

        try:
            assert self._serial is not None
            self._serial.reset_input_buffer()
            self._serial.write(command)
            self._serial.flush()
            reply = self._serial.read(self.FRAME_LEN)
            telemetry = self._parse_reply(reply)
            self.last_error = None
            return telemetry
        except Exception as exc:
            self.last_error = f"Compressor UART exchange failed: {exc}"
            return None

    def cleanup(self):
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self.is_initialized = False
