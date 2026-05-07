"""Simple UART master example for Raspberry Pi.

Sends a compressor ON command at a target RPM and prints the reply.

Usage:
    python3 uart_master.py
"""

import serial
import time

PORT     = "/dev/serial0"
BAUDRATE = 600


def checksum(frame: bytearray) -> int:
    return (-sum(frame[1:14])) & 0xFF


def build_command(on: bool, rpm: int) -> bytes:
    f = bytearray(16)
    f[0]  = 0xAA
    f[1]  = 0x00
    f[2]  = 0x01 if on else 0x00
    f[3]  = rpm & 0xFF
    f[4]  = (rpm >> 8) & 0xFF
    f[14] = checksum(f)
    f[15] = 0x55
    return bytes(f)


def send_and_receive(ser: serial.Serial, frame: bytes) -> bytes:
    ser.write(frame)
    ser.flush()
    time.sleep(0.05)        # give slave 50 ms to respond
    return ser.read(16)


def print_reply(rx: bytes) -> None:
    if not rx:
        print("  No reply received")
        return

    print("  Raw:", rx.hex(" ").upper())

    if len(rx) != 16 or rx[0] != 0xAA or rx[15] != 0x55:
        print("  Bad frame")
        return

    rpm     = rx[2] | (rx[3] << 8)
    amps    = (rx[4] | (rx[5] << 8)) * 0.1
    volts   = (rx[6] | (rx[7] << 8)) * 0.1
    faults  = rx[9]

    print(f"  Speed:   {rpm} RPM")
    print(f"  Current: {amps:.1f} A")
    print(f"  Voltage: {volts:.1f} V")

    if faults:
        names = {0:"Overcurrent",1:"Overvoltage",2:"Undervoltage",
                 3:"Phase loss",4:"Stall",5:"HW overcurrent",6:"Bad phase"}
        active = [names[b] for b in range(7) if faults & (1 << b)]
        print("  FAULTS:", ", ".join(active))


# ── main ──────────────────────────────────────────────────────────────────────

with serial.Serial(PORT, BAUDRATE, timeout=0.5) as ser:
    print(f"Opened {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")

    while True:
        tx = build_command(on=True, rpm=3000)
        print("TX:", tx.hex(" ").upper())

        rx = send_and_receive(ser, tx)
        print_reply(rx)
        print()

        time.sleep(3.0)