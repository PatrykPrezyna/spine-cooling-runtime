"""UART baud rate scanner for RX2309-COMP compressor controller.

Sends a compressor command frame at every common baud rate and waits
long enough for a reply. Tells you which baud rate actually works.

Usage:
    python3 uart_scan.py [port]
    python3 uart_scan.py /dev/serial0
"""

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"

BAUD_RATES = [300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

# At 300 baud a 16-byte frame takes ~530 ms to transmit.
# We wait 2x that after sending so even the slowest rate has time to reply.
WAIT_AFTER_SEND = 2.0   # seconds


def checksum(frame: bytearray) -> int:
    return (-sum(frame[1:14])) & 0xFF


def build_frame(on: bool = True, rpm: int = 2400) -> bytes:
    f = bytearray(16)
    f[0]  = 0xAA
    f[1]  = 0x00
    f[2]  = 0x01 if on else 0x00
    f[3]  = rpm & 0xFF
    f[4]  = (rpm >> 8) & 0xFF
    f[14] = checksum(f)
    f[15] = 0x55
    return bytes(f)


def try_baud(port: str, baudrate: int, tx: bytes) -> bytes:
    """Open port, flush, send frame, wait, read everything back."""
    with serial.Serial(port, baudrate, timeout=0.5) as ser:
        ser.reset_input_buffer()
        ser.write(tx)
        ser.flush()

        # Wait long enough for the frame to transmit + slave to respond
        time.sleep(WAIT_AFTER_SEND)

        # Read whatever arrived
        rx = b""
        while ser.in_waiting:
            rx += ser.read(ser.in_waiting)
            time.sleep(0.05)    # small pause in case more bytes are still arriving
        return rx


def show_hex(data: bytes) -> None:
    for i in range(0, len(data), 16):
        row = data[i:i+16]
        hex_part = " ".join(f"{b:02X}" for b in row)
        asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"    {i:04X}  {hex_part:<48}  {asc_part}")


def check_reply(rx: bytes) -> str:
    if len(rx) < 16:
        return f"too short ({len(rx)} bytes)"
    if rx[0] != 0xAA:
        return f"bad start byte 0x{rx[0]:02X}"
    if rx[15] != 0x55:
        return f"bad end byte 0x{rx[15]:02X}"
    expected = (-sum(rx[1:14])) & 0xFF
    if rx[14] != expected:
        return f"bad checksum (got 0x{rx[14]:02X}, expected 0x{expected:02X})"
    return "OK"


def decode_reply(rx: bytes) -> None:
    rpm   = rx[2] | (rx[3] << 8)
    amps  = (rx[4] | (rx[5] << 8)) * 0.1
    volts = (rx[6] | (rx[7] << 8)) * 0.1
    faults = rx[9]
    names = {0:"Overcurrent",1:"Overvoltage",2:"Undervoltage",
             3:"Phase loss",4:"Stall",5:"HW overcurrent",6:"Bad phase"}
    active = [names[b] for b in range(7) if faults & (1 << b)]
    print(f"    Speed:   {rpm} RPM")
    print(f"    Current: {amps:.1f} A")
    print(f"    Voltage: {volts:.1f} V")
    if active:
        print(f"    FAULTS:  {', '.join(active)}")


# ── Main ──────────────────────────────────────────────────────────────────────

tx = build_frame(on=True, rpm=2400)

print(f"Port : {PORT}")
print(f"Frame: {tx.hex(' ').upper()}")
print(f"Waiting {WAIT_AFTER_SEND}s after each send for a reply.")
print("─" * 60)

results = {}   # baud → rx bytes

for baud in BAUD_RATES:
    print(f"\n→ Trying {baud} baud ...")
    print(f"  TX: {tx.hex(' ').upper()}")

    try:
        rx = try_baud(PORT, baud, tx)
    except serial.SerialException as e:
        print(f"  Port error: {e}")
        continue

    if not rx:
        print("  RX: <nothing>")
        continue

    print(f"  RX: {rx.hex(' ').upper()}")
    show_hex(rx)

    status = check_reply(rx)
    print(f"  Status: {status}")

    if status == "OK":
        decode_reply(rx)
        results[baud] = rx

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n" + "─" * 60)
if results:
    print(f"✓ Valid reply received at: {', '.join(str(b) for b in results)} baud")
    print(f"  Use baud rate: {list(results.keys())[0]}")
else:
    print("✗ No valid reply at any baud rate.")
    print()
    print("  Check:")
    print("  1. Board is powered (24V/48V on power terminals)")
    print("  2. Pi TX (Pin 8)  → Board RX")
    print("     Pi RX (Pin 10) → Board TX")
    print("     Pi GND (Pin 6) → Board GND (signal GND, not power GND)")
    print("  3. UART enabled:  sudo raspi-config → Interface → Serial Port")
    print("     Login shell: NO  |  Hardware serial: YES  → reboot")
    print("  4. Try port /dev/ttyAMA0 if /dev/serial0 gives nothing")