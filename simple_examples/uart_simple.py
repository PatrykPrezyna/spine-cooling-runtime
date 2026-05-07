"""Simplest UART communication example using pyserial.

Usage:
  python uart_simple.py /dev/ttyS0 600
"""

from __future__ import annotations

import sys
import time

import serial  # type: ignore

FRAME_LEN = 16
MASTER_ADDR = 0x00
SLAVE_ADDR = 0x01
FRAME_PERIOD_S = 1.0
REPLY_DELAY_S = 0.020


def checksum(frame: bytes) -> int:
    return (-sum(frame[1:14])) & 0xFF


def build_frame() -> bytes:
    """Build a minimal 16-byte compressor command frame."""
    frame = bytearray(FRAME_LEN)
    frame[0] = 0xAA  # start
    frame[1] = MASTER_ADDR  # master addr
    frame[2] = 0x01  # ON command
    frame[3] = 0xDC  # speed low byte (1500 RPM -> 0x05DC)
    frame[4] = 0x05  # speed high byte
    # bytes 5..13 remain 0x00

    frame[14] = checksum(frame)
    frame[15] = 0x55  # end
    return bytes(frame)


def validate_reply(frame: bytes) -> str:
    if len(frame) != FRAME_LEN:
        return f"BAD length={len(frame)}"
    if frame[0] != 0xAA:
        return f"BAD start=0x{frame[0]:02X}"
    if frame[1] != SLAVE_ADDR:
        return f"BAD addr=0x{frame[1]:02X}"
    if frame[14] != checksum(frame):
        return f"BAD checksum=0x{frame[14]:02X}"
    if frame[15] != 0x55:
        return f"BAD end=0x{frame[15]:02X}"
    return "OK"


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 600

    tx = build_frame()
    print(f"Opening {port} @ {baudrate} (8N1, frame={FRAME_LEN} bytes)...")

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
            print("Sending one frame every 1000 ms. Press Ctrl+C to stop.")
            while True:
                cycle_start = time.monotonic()
                ser.reset_input_buffer()
                ser.write(tx)
                ser.flush()
                time.sleep(REPLY_DELAY_S)  # slave replies ~20 ms after request
                rx = ser.read(FRAME_LEN)
                status = validate_reply(rx)

                print("TX:", " ".join(f"{b:02X}" for b in tx))
                print("RX:", " ".join(f"{b:02X}" for b in rx) if rx else "<no data>")
                print("RX status:", status)
                print("-")

                elapsed = time.monotonic() - cycle_start
                sleep_left = FRAME_PERIOD_S - elapsed
                if sleep_left > 0:
                    time.sleep(sleep_left)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    except Exception as exc:
        print(f"UART error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
