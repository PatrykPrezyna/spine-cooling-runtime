"""Minimal UART master: sends a line and prints the reply.

Pair with uart_slave.py on another COM port. Cross TX↔RX, common GND.

Usage:
    python uart_simple.py [PORT]
"""

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
BAUDRATE = 600
LINE = b"ping\n"


def main() -> None:
    with serial.Serial(PORT, BAUDRATE, timeout=1.0) as ser:
        print(f"Master on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")
        while True:
            ser.reset_input_buffer()
            ser.write(LINE)
            ser.flush()
            rx = ser.readline()
            print(f"TX {LINE!r}  ->  RX {rx!r}")
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
