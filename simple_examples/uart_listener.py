"""UART listener — scans every common baud rate looking for data.

Connect only RX (Pi Pin 10) and GND. TX is unused.

Usage:
    python3 uart_listen.py [port]
    python3 uart_listen.py /dev/serial0
"""

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/serial0"

BAUD_RATES = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

LISTEN_SECONDS = 3      # how long to listen at each baud rate


def listen(port: str, baudrate: int, duration: float) -> bytes:
    """Open port at baudrate, collect bytes for `duration` seconds."""
    try:
        with serial.Serial(port, baudrate, timeout=0.2) as ser:
            ser.reset_input_buffer()
            deadline = time.monotonic() + duration
            buf = b""
            while time.monotonic() < deadline:
                chunk = ser.read(64)
                if chunk:
                    buf += chunk
            return buf
    except serial.SerialException as e:
        print(f"  Error: {e}")
        return b""


def show(data: bytes, baudrate: int) -> None:
    print(f"  Received {len(data)} bytes at {baudrate} baud:")
    # hex view
    for i in range(0, len(data), 16):
        row = data[i:i+16]
        hex_part = " ".join(f"{b:02X}" for b in row)
        asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"    {i:04X}  {hex_part:<48}  {asc_part}")


print(f"Listening on {PORT}. Trying each baud rate for {LISTEN_SECONDS}s.\n")
print("─" * 60)

found = {}

for baud in BAUD_RATES:
    print(f"→ {baud} baud ... ", end="", flush=True)
    data = listen(PORT, baud, LISTEN_SECONDS)

    if data:
        print(f"GOT DATA ({len(data)} bytes)")
        show(data, baud)
        found[baud] = data
    else:
        print("nothing")

    print()

# ── Summary ───────────────────────────────────────────────────────────────────
print("─" * 60)
if found:
    print("✓ Got data at baud rates:", ", ".join(str(b) for b in found))
    best = max(found, key=lambda b: len(found[b]))
    print(f"  Most data received at: {best} baud  ← likely the correct rate")
else:
    print("✗ No data received at any baud rate.")
    print("  Check: is the board powered? Is RX wired to the board's TX?")