"""UART slave: answers uart_simple.py with a 16-byte status frame.

  python uart_slave.py [PORT [BAUDRATE]]
"""

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 600
N = 16


def chk(b: bytes | bytearray) -> int:
    return (-sum(b[1:14])) & 0xFF


def reply(rpm: int, i_x10: int, v_x10: int) -> bytes:
    f = bytearray(N)
    f[0], f[1] = 0xAA, 0x01
    f[2], f[3] = rpm & 0xFF, (rpm >> 8) & 0xFF
    f[4], f[5] = i_x10 & 0xFF, (i_x10 >> 8) & 0xFF
    f[6], f[7] = v_x10 & 0xFF, (v_x10 >> 8) & 0xFF
    # f[8], f[10..12] stay 0; f[9], f[13] fault bytes stay 0
    f[14], f[15] = chk(f), 0x55
    return bytes(f)


def read_cmd(ser: serial.Serial, t: float) -> bytes:
    end = time.monotonic() + t
    while time.monotonic() < end:
        if ser.read(1) == b"\xaa":
            rest = ser.read(N - 1)
            if len(rest) == N - 1:
                return b"\xaa" + rest
    return b""


def main() -> None:
    with serial.Serial(PORT, BAUD, timeout=0.05) as ser:
        ser.reset_input_buffer()
        print(f"{PORT} @ {BAUD} baud  Ctrl+C stop\n")

        while True:
            rx = read_cmd(ser, 2.0)
            if len(rx) < N or rx[-1] != 0x55 or rx[-2] != chk(rx):
                continue

            on = bool(rx[2] & 1)
            rpm_cmd = rx[3] | (rx[4] << 8)
            print("RX:", rx.hex(" ").upper(), "| on=", on, "rpm=", rpm_cmd)

            rpm = rpm_cmd if on else 0
            tx = reply(rpm, 120 if on else 0, 480)  # 12 A / 48 V when on
            ser.write(tx)
            ser.flush()
            print("TX:", tx.hex(" ").upper(), "\n")


if __name__ == "__main__":
    try:
        main()
    except (serial.SerialException, KeyboardInterrupt) as e:
        if isinstance(e, serial.SerialException):
            print(e, file=sys.stderr)
            sys.exit(1)
        print("\nStopped.")
