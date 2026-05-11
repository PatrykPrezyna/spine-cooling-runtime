"""Minimal UART slave: fixed-length ping / pong for uart_simple.py.

Wire two USB–serial adapters: TX of each side to RX of the other, GND common.

Uses exact byte reads so 600 baud (slow bytes) does not break readline().

Usage:
    python uart_slave.py [PORT]
"""

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
BAUDRATE = 600

RX_LEN = 5   # b"ping\n"
REPLY = b"pong\n"


def read_exact(ser: serial.Serial, n: int, total_timeout: float) -> bytes:
    buf = b""
    deadline = time.monotonic() + total_timeout
    while len(buf) < n and time.monotonic() < deadline:
        chunk = ser.read(n - len(buf))
        if chunk:
            buf += chunk
        else:
            time.sleep(0.001)
    return buf


def main() -> None:
    with serial.Serial(PORT, BAUDRATE, timeout=0.05) as ser:
        print(f"Slave on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")
        while True:
            line = read_exact(ser, RX_LEN, total_timeout=2.0)
            if len(line) < RX_LEN:
                time.sleep(0.05)
                continue
            if line == b"ping\n":
                ser.write(REPLY)
            else:
                ser.write(line)
            ser.flush()
            print(f"RX {line!r}  ->  TX reply")


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
