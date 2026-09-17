"""Switch BCM GPIO 16 on or off from the command line (pigpio).

Requires the pigpio daemon:
  sudo pigpiod

Examples (from this folder):
  python gpio16.py on
  python gpio16.py off
  python gpio16.py          # show current level
"""

import argparse
import sys

import pigpio

PIN = 16


def _level_from_arg(value: str) -> int:
    key = value.strip().lower()
    if key in ("on", "1", "high", "hi"):
        return 1
    if key in ("off", "0", "low", "lo"):
        return 0
    raise argparse.ArgumentTypeError(f"expected on/off (got {value!r})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set BCM GPIO 16 HIGH or LOW")
    parser.add_argument(
        "state",
        nargs="?",
        type=_level_from_arg,
        help="on / off (omit to read the current level)",
    )
    args = parser.parse_args()

    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio daemon is not running. Start it with: sudo pigpiod", file=sys.stderr)
        return 1

    try:
        pi.set_mode(PIN, pigpio.OUTPUT)
        if args.state is None:
            level = pi.read(PIN)
        else:
            pi.write(PIN, args.state)
            level = pi.read(PIN)
        word = "on" if level else "off"
        volts = "3.3 V" if level else "0 V"
        print(f"GPIO {PIN}: {word} ({volts}, level={level})")
        return 0
    finally:
        pi.stop()


if __name__ == "__main__":
    sys.exit(main())
