"""Simplest UART communication example using pyserial.

Usage:
  python uart_simple.py /dev/ttyS0 600
"""

from __future__ import annotations

import sys

import serial  # type: ignore


def build_frame() -> bytes:
    """Build a minimal 16-byte compressor command frame."""
    frame = bytearray(16)
    frame[0] = 0xAA  # start
    frame[1] = 0x00  # master addr
    frame[2] = 0x01  # ON command
    frame[3] = 0xDC  # speed low byte (1500 RPM -> 0x05DC)
    frame[4] = 0x05  # speed high byte
    # bytes 5..13 remain 0x00

    checksum = (-sum(frame[1:14])) & 0xFF
    frame[14] = checksum
    frame[15] = 0x55  # end
    return bytes(frame)


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 600

    tx = build_frame()
    print(f"Opening {port} @ {baudrate}...")

    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
            write_timeout=0.2,
        ) as ser:
            ser.reset_input_buffer()
            ser.write(tx)
            ser.flush()
            rx = ser.read(16)
    except Exception as exc:
        print(f"UART error: {exc}")
        return 1

    print("TX:", " ".join(f"{b:02X}" for b in tx))
    print("RX:", " ".join(f"{b:02X}" for b in rx) if rx else "<no data>")
    print(f"RX length: {len(rx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
