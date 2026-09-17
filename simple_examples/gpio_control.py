"""Interactive BCM GPIO switch (pigpio).

Requires the pigpio daemon:
  sudo pigpiod

Run:
  python gpio6.py

Then type pin + on/off, for example:
  6on
  16off
  q to quit
"""

import re
import sys

import pigpio

_CMD = re.compile(r"^(\d+)\s*(on|off|high|low|hi|lo)$")


def _level_from_word(word: str) -> int:
    return 0 if word in ("off", "low", "lo") else 1


def _print_level(pi: pigpio.pi, pin: int) -> None:
    level = pi.read(pin)
    word = "HIGH" if level else "LOW"
    volts = "3.3 V" if level else "0 V"
    print(f"GPIO {pin}: {word} ({volts})")


def _set_pin(pi: pigpio.pi, pin: int, level: int) -> None:
    if pin < 0 or pin > 27:
        print(f"GPIO {pin} is out of range (0-27)")
        return
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.write(pin, level)
    _print_level(pi, pin)


def main() -> int:
    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio daemon is not running. Start it with: sudo pigpiod", file=sys.stderr)
        return 1

    try:
        print("type 6on / 16off (BCM pin + on|off), q to quit")
        while True:
            try:
                line = input("> ").strip().lower()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line in ("q", "quit", "exit"):
                break
            match = _CMD.fullmatch(line.replace(" ", ""))
            if match is None:
                print("use e.g. 6on or 16off")
                continue
            pin = int(match.group(1))
            level = _level_from_word(match.group(2))
            _set_pin(pi, pin, level)
        return 0
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        pi.stop()


if __name__ == "__main__":
    sys.exit(main())
