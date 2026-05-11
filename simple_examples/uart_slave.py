"""UART slave ? simulates compressor responding to uart_simple.py master.

Waits for a valid 16-byte command frame (0xAA?0x55), validates the checksum,
then sends a 16-byte status reply per the protocol spec:
  Byte  0    : 0xAA  (start)
  Byte  1    : 0x01
  Byte  2-3  : compressor rotation speed (low, high)
  Byte  4-5  : compressor current x0.1 A (low, high)
  Byte  6-7  : busbar voltage x0.1 V (low, high)
  Byte  8    : 0x00
  Byte  9    : error code (persistent ? cleared only when compressor restarts)
                 bit0 software overcurrent  bit1 overvoltage   bit2 undervoltage
                 bit3 phase loss            bit4 stall         bit5 HW overcurrent
                 bit6 abnormal phase        bit7 ?
  Byte 10    : ambient temperature (reserved)
  Byte 11    : ventilate (reserved)
  Byte 12    : 0x00
  Byte 13    : auto-clear fault bits (same layout as byte 9, cleared in 120 s)
  Byte 14    : checksum = (-sum(bytes[1:14])) & 0xFF
  Byte 15    : 0x55  (end)

Usage:
    python uart_slave.py [PORT [BAUDRATE]]
    python uart_slave.py /dev/serial0 600
"""

from __future__ import annotations

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = "/dev/serial0"
BAUDRATE = 9600
FRAME    = 16


def checksum(frame: bytes | bytearray) -> int:
    return (-sum(frame[1:14])) & 0xFF


def read_frame(ser: serial.Serial, total_timeout: float) -> bytes:
    """Sync on 0xAA then read the remaining 15 bytes."""
    deadline = time.monotonic() + total_timeout
    while time.monotonic() < deadline:
        b = ser.read(1)
        if not b:
            continue
        if b[0] != 0xAA:
            continue
        # got start byte ? read the rest
        buf = b
        while len(buf) < FRAME and time.monotonic() < deadline:
            chunk = ser.read(FRAME - len(buf))
            if chunk:
                buf += chunk
            else:
                time.sleep(0.001)
        return buf
    return b""


def build_reply(
    rpm: int,
    amps_tenths: int,
    volts_tenths: int,
    error_code: int,
    amb_temp: int = 0,
    ventilate: int = 0,
    autoclear_faults: int = 0,
) -> bytes:
    f = bytearray(FRAME)
    f[0]  = 0xAA
    f[1]  = 0x01
    f[2]  = rpm & 0xFF
    f[3]  = (rpm >> 8) & 0xFF
    f[4]  = amps_tenths & 0xFF
    f[5]  = (amps_tenths >> 8) & 0xFF
    f[6]  = volts_tenths & 0xFF
    f[7]  = (volts_tenths >> 8) & 0xFF
    f[8]  = 0x00
    f[9]  = error_code & 0xFF
    f[10] = amb_temp & 0xFF
    f[11] = ventilate & 0xFF
    f[12] = 0x00
    f[13] = autoclear_faults & 0xFF
    f[14] = checksum(f)
    f[15] = 0x55
    return bytes(f)


def main() -> None:
    with serial.Serial(
        PORT, BAUDRATE, timeout=0.05,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
    ) as ser:
        ser.reset_input_buffer()
        print(f"Slave on {PORT} @ {BAUDRATE} baud. Ctrl+C to stop.\n")

        while True:
            rx = read_frame(ser, total_timeout=2.0)
            if len(rx) < FRAME:
                continue

            # Validate end byte and checksum
            if rx[15] != 0x55:
                print(f"RX bad end byte: {rx.hex(' ').upper()}")
                continue
            if rx[14] != checksum(rx):
                print(f"RX bad checksum: {rx.hex(' ').upper()}")
                continue

            on  = bool(rx[2] & 0x01)
            rpm = rx[3] | (rx[4] << 8)
            print(f"RX: {rx.hex(' ').upper()}  |  on={on}  rpm_cmd={rpm}")

            # Simulated feedback
            rpm_fb       = rpm if on else 0
            amps_tenths  = 120 if on else 0   # 12.0 A
            volts_tenths = 480                # 48.0 V
            error_code   = 0
            autoclear    = 0

            reply = build_reply(rpm_fb, amps_tenths, volts_tenths, error_code, autoclear_faults=autoclear)
            ser.write(reply)
            ser.flush()
            print(f"TX: {reply.hex(' ').upper()}\n")


if __name__ == "__main__":
    try:
        main()
    except serial.SerialException as e:
        print(f"Serial error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
