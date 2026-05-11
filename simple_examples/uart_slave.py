"""Minimal UART slave: answers the master from uart_simple.py.

Wire two USB–serial adapters: TX of each side to RX of the other, GND common.

Usage:
    python uart_slave.py [PORT]
"""

import sys

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = "/dev/serial0"
BAUDRATE = 1200


def main() -> None:
    with serial.Serial(PORT, BAUDRATE, timeout=1.0) as ser:
        print(f"Slave on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")
        while True:
            line = ser.readline()
            if not line:
                continue
            if line.strip() == b"ping":
                ser.write(b"pong\n")
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
