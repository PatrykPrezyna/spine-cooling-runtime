"""UART master ? compressor command frame.

Command frame (master ? slave):
  Byte  0    : 0xAA  (start)
  Byte  1    : 0x00
  Byte  2    : instructions  bit0: 1=on, 0=off
  Byte  3    : set speed low  byte
  Byte  4    : set speed high byte
  Byte  5-13 : 0x00
  Byte  14   : checksum = (-sum(bytes[1:14])) & 0xFF
  Byte  15   : 0x55  (end)

Reply frame (slave ? master):
  Byte  0    : 0xAA
  Byte  1    : 0x01
  Byte  2-3  : actual speed (low, high)
  Byte  4-5  : current x0.1 A (low, high)
  Byte  6-7  : busbar voltage x0.1 V (low, high)
  Byte  8    : 0x00
  Byte  9    : persistent error code (bits 0-6)
  Byte 10    : ambient temperature (reserved)
  Byte 11    : ventilate (reserved)
  Byte 12    : 0x00
  Byte 13    : auto-clear fault bits (cleared in 120 s)
  Byte 14    : checksum
  Byte 15    : 0x55

Example command (on, 3000 rpm):
  AA 00 01 B8 0B 00 00 00 00 00 00 00 00 00 3C 55

Usage:
    python uart_simple.py [PORT [BAUDRATE]]
"""

from __future__ import annotations

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT     = sys.argv[1] if len(sys.argv) > 1 else "COM4"
BAUDRATE = 9600
FRAME    = 16


def checksum(frame: bytearray) -> int:
    return (-sum(frame[1:14])) & 0xFF


def build_frame(on: bool, rpm: int) -> bytes:
    f = bytearray(FRAME)
    f[0]  = 0xAA
    f[1]  = 0x00
    f[2]  = 0x01 if on else 0x00
    f[3]  = rpm & 0xFF
    f[4]  = (rpm >> 8) & 0xFF
    # bytes 5-13 remain 0x00
    f[14] = checksum(f)
    f[15] = 0x55
    return bytes(f)


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
    char_time      = 10.0 / BAUDRATE          # seconds per byte at 8N1
    post_tx_pause  = char_time * (FRAME * 2 + 4)   # TX + reply + margin

    with serial.Serial(
        PORT, BAUDRATE, timeout=0.05,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
    ) as ser:
        print(f"Master on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")

        while True:
            ser.reset_input_buffer()
            tx = build_frame(on=True, rpm=3000)
            ser.write(tx)
            ser.flush()
            print(f"TX: {tx.hex(' ').upper()}")

            time.sleep(post_tx_pause)
            rx = read_exact(ser, FRAME, total_timeout=2.0)

            if len(rx) == FRAME and rx[0] == 0xAA and rx[1] == 0x01 and rx[15] == 0x55:
                rpm_fb   = rx[2] | (rx[3] << 8)
                amps     = (rx[4] | (rx[5] << 8)) * 0.1
                volts    = (rx[6] | (rx[7] << 8)) * 0.1
                err      = rx[9]
                autocl   = rx[13]

                FAULT_NAMES = {
                    0: "software overcurrent", 1: "overvoltage",
                    2: "undervoltage",         3: "phase loss",
                    4: "stall",                5: "HW overcurrent",
                    6: "abnormal phase",
                }
                faults = [FAULT_NAMES[b] for b in range(7) if err & (1 << b)]

                print(f"RX: {rx.hex(' ').upper()}")
                print(f"  Speed:   {rpm_fb} RPM")
                print(f"  Current: {amps:.1f} A")
                print(f"  Voltage: {volts:.1f} V")
                if faults:
                    print(f"  FAULTS:  {', '.join(faults)}")
                if autocl:
                    acl = [FAULT_NAMES[b] for b in range(7) if autocl & (1 << b)]
                    print(f"  AutoClr: {', '.join(acl)}")
            elif rx:
                print(f"RX (bad frame): {rx.hex(' ').upper()}")
            else:
                print("RX: <no reply>")

            print()
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
