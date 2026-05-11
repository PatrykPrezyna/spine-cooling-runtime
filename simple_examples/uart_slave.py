"""UART slave simulator — counterpart to uart_simple.py (master).

Listens for 16-byte compressor-style frames (0xAA … 0x55), validates the
checksum, applies the ON/RPM command, and sends a status reply the master
expects (same layout as print_reply in uart_simple).

Wire two USB–serial adapters back-to-back (cross TX/RX, common GND), or use
a null-modem cable: run uart_slave on one COM port and uart_simple on the other.

Usage:
    python uart_slave.py [PORT]
    python uart_slave.py COM5
"""

from __future__ import annotations

import sys
import time

# UART: use PyPI "pyserial" (import serial). PyPI "serial" is a different library.
import serial  # pyright: ignore[reportMissingModuleSource]

PORT     = "/dev/serial0"
#PORT = "COM4"
BAUDRATE = 600
FRAME_LEN = 16


def checksum(frame: bytes | bytearray) -> int:
    return (-sum(frame[1:14])) & 0xFF


def build_reply(
    rpm_feedback: int,
    amps_tenths: int,
    volts_tenths: int,
    faults: int,
) -> bytes:
    f = bytearray(FRAME_LEN)
    f[0] = 0xAA
    f[1] = 0x00
    f[2] = rpm_feedback & 0xFF
    f[3] = (rpm_feedback >> 8) & 0xFF
    f[4] = amps_tenths & 0xFF
    f[5] = (amps_tenths >> 8) & 0xFF
    f[6] = volts_tenths & 0xFF
    f[7] = (volts_tenths >> 8) & 0xFF
    f[8] = 0x00
    f[9] = faults & 0xFF
    f[10] = f[11] = f[12] = f[13] = 0x00
    f[14] = checksum(f)
    f[15] = 0x55
    return bytes(f)


def parse_command(frame: bytes) -> tuple[bool, int]:
    on = frame[2] != 0
    rpm = frame[3] | (frame[4] << 8)
    return on, rpm


def read_one_frame(ser: serial.Serial) -> bytes | None:
    """Block until a valid 16-byte frame is assembled (sync on 0xAA)."""
    while True:
        b = ser.read(1)
        if not b:
            return None
        if b[0] != 0xAA:
            continue
        rest = ser.read(FRAME_LEN - 1)
        if len(rest) < FRAME_LEN - 1:
            continue
        frame = b + rest
        if frame[FRAME_LEN - 1] != 0x55:
            continue
        if frame[14] != checksum(frame):
            print("  [slave] bad checksum, resyncing")
            continue
        return bytes(frame)


class SimulatedDrive:
    """Minimal dynamics so the master sees plausible RPM / current."""

    def __init__(self) -> None:
        self.rpm = 0
        self.target_on = False
        self.target_rpm = 0

    def step(self, on: bool, rpm_cmd: int, dt: float) -> tuple[int, int, int, int]:
        self.target_on = on
        self.target_rpm = max(0, min(rpm_cmd, 6000)) if on else 0

        # Ramp ~800 RPM/s toward target
        ramp = int(800 * dt)
        tgt = self.target_rpm if self.target_on else 0
        if self.rpm < tgt:
            self.rpm = min(tgt, self.rpm + ramp)
        elif self.rpm > tgt:
            self.rpm = max(tgt, self.rpm - ramp)

        # Simple load model: current scales with speed when “on” path
        if self.rpm > 100 and self.target_on:
            amps_tenths = min(350, int(5 + (self.rpm / 3000.0) * 120))
        else:
            amps_tenths = max(0, int(self.rpm / 3000.0 * 8))

        volts_tenths = 480  # 48.0 V bus
        faults = 0
        return self.rpm, amps_tenths, volts_tenths, faults


def main() -> None:
    drive = SimulatedDrive()
    last_t = time.monotonic()

    with serial.Serial(PORT, BAUDRATE, timeout=0.2) as ser:
        ser.reset_input_buffer()
        print(f"Slave listening on {PORT} @ {BAUDRATE} baud (master: uart_simple.py). Ctrl+C to stop.\n")

        while True:
            frame = read_one_frame(ser)
            if frame is None:
                continue

            now = time.monotonic()
            dt = max(0.001, now - last_t)
            last_t = now

            on, rpm_cmd = parse_command(frame)
            print(f"RX: {frame.hex(' ').upper()}  |  ON={on}  RPM_cmd={rpm_cmd}")

            rpm_fb, amps_t, volts_t, faults = drive.step(on, rpm_cmd, dt)
            reply = build_reply(rpm_fb, amps_t, volts_t, faults)

            ser.write(reply)
            ser.flush()
            print(f"TX: {reply.hex(' ').upper()}  |  RPM={rpm_fb}  I={amps_t/10:.1f} A  V={volts_t/10:.1f} V\n")


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
