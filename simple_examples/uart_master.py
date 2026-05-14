"""UART master: 16-byte compressor command and decode of slave reply.

  python uart_simple.py [PORT [BAUDRATE]]
"""

import sys
import time

import serial  # pyright: ignore[reportMissingModuleSource]

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 600
N = 16


def chk(b: bytearray) -> int:
    return (-sum(b[1:14])) & 0xFF


def cmd(on: bool, rpm: int) -> bytes:
    f = bytearray(N)
    f[0], f[1], f[2] = 0xAA, 0x00, 1 if on else 0
    f[3], f[4] = rpm & 0xFF, (rpm >> 8) & 0xFF
    f[14], f[15] = chk(f), 0x55
    return bytes(f)


def read_n(ser: serial.Serial, n: int, t: float) -> bytes:
    out, end = b"", time.monotonic() + t
    while len(out) < n and time.monotonic() < end:
        c = ser.read(n - len(out))
        if c:
            out += c
        else:
            time.sleep(0.001)
    return out


def u16(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8)


def faults(mask: int) -> str:
    names = (
        "SW overcurrent",
        "overvoltage",
        "undervoltage",
        "phase loss",
        "stall",
        "HW overcurrent",
        "bad phase",
    )
    return ", ".join(names[i] for i in range(7) if mask & (1 << i))


def main() -> None:
    pause = (10.0 / BAUD) * (2 * N + 4)  # TX + RX time + margin

    with serial.Serial(PORT, BAUD, timeout=0.05) as ser:
        print(f"{PORT} @ {BAUD} baud  Ctrl+C stop\n")

        while True:
            ser.reset_input_buffer()
            tx = cmd(True, 3000)
            ser.write(tx)
            ser.flush()
            print("TX:", tx.hex(" ").upper())

            time.sleep(pause)
            rx = read_n(ser, N, 2.0)

            ok = (
                len(rx) == N
                and rx[0] == 0xAA
                and rx[1] == 0x01
                and rx[15] == 0x55
            )
            if ok:
                print("RX:", rx.hex(" ").upper())
                print(f"  {u16(rx, 2)} RPM  {u16(rx, 4) * 0.1:.1f} A  {u16(rx, 6) * 0.1:.1f} V")
                if rx[9]:
                    print("  faults:", faults(rx[9]))
                if rx[13]:
                    print("  autoclr:", faults(rx[13]))
            elif rx:
                print("RX bad:", rx.hex(" ").upper())
            else:
                print("RX: (nothing)")

            print()
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except (serial.SerialException, KeyboardInterrupt) as e:
        if isinstance(e, serial.SerialException):
            print(e, file=sys.stderr)
            sys.exit(1)
        print("\nStopped.")
