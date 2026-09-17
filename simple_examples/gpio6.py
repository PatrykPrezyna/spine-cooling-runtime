"""Interactive BCM GPIO 6 switch (pigpio).

Requires the pigpio daemon:
  sudo pigpiod

Run:
  python gpio6.py

Then type 1 for HIGH or 0 for LOW. Ctrl+C or q to quit.
GPIO 6 is header pin 31.
"""

import sys

import pigpio

PIN = 6


def _print_level(pi: pigpio.pi) -> None:
    level = pi.read(PIN)
    word = "HIGH" if level else "LOW"
    volts = "3.3 V" if level else "0 V"
    print(f"GPIO {PIN}: {word} ({volts})")


def main() -> int:
    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio daemon is not running. Start it with: sudo pigpiod", file=sys.stderr)
        return 1

    try:
        pi.set_mode(PIN, pigpio.OUTPUT)
        print(f"GPIO {PIN} — type 1 for HIGH, 0 for LOW, q to quit")
        _print_level(pi)
        while True:
            try:
                line = input("> ").strip().lower()
            except EOFError:
                print()
                break
            if line in ("q", "quit", "exit"):
                break
            if line == "1":
                pi.write(PIN, 1)
                _print_level(pi)
            elif line == "0":
                pi.write(PIN, 0)
                _print_level(pi)
            elif line:
                print("use 1 or 0")
        return 0
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        pi.stop()


if __name__ == "__main__":
    sys.exit(main())
