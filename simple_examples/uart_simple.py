"""Minimal UART master: sends a fixed message and reads a fixed-length reply.

Pair with uart_slave.py on another COM port. Cross TX↔RX, common GND.

At low baud (e.g. 600), readline() often returns too early; this example uses
exact byte counts instead.

Usage:
    python uart_simple.py [PORT]
"""

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
BAUDRATE = 600

TX_MSG = b"ping\n"      # 5 bytes
RX_LEN = 6              # b"pong\n"


def read_exact(ser: serial.Serial, n: int, total_timeout: float) -> bytes:
    """Read n bytes even when they trickle in slowly (low baud)."""
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
    # One character time ≈ 10 bits / baud (8N1).
    char_time = 10.0 / BAUDRATE
    # Wait for our TX on the wire + slave reply (RX_LEN chars) + margin.
    post_tx_pause = char_time * (len(TX_MSG) + RX_LEN + 4)

    with serial.Serial(PORT, BAUDRATE, timeout=0.05) as ser:
        print(f"Master on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")
        while True:
            ser.reset_input_buffer()
            ser.write(TX_MSG)
            ser.flush()
            time.sleep(post_tx_pause)
            rx = read_exact(ser, RX_LEN, total_timeout=2.0)
            print(f"TX {TX_MSG!r}  ->  RX {rx!r}")
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
