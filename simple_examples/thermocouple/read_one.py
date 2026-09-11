"""Read one thermocouple on a Sequent Microsystems SMtc HAT.

Default: stack 0, channel 1, Type T (copper / constantan).
Hit ENTER to stop.

    python simple_examples/thermocouple/read_one.py
    python simple_examples/thermocouple/read_one.py 2          # channel 2
    python simple_examples/thermocouple/read_one.py 1 --type K
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime

try:
    import sm_tc
except ImportError:
    print("Missing package: SMtc. Install with:  pip install SMtc")
    sys.exit(1)

# Sensor-type codes from the SMtc driver.
SENSOR_TYPES = {
    "B": 0,
    "E": 1,
    "J": 2,
    "K": 3,
    "N": 4,
    "R": 5,
    "S": 6,
    "T": 7,
}

STACK = 0
I2C_BUS = 1
SAMPLE_INTERVAL_S = 1.0

keep_going = True


def key_capture_thread() -> None:
    global keep_going
    input()
    keep_going = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read one SMtc thermocouple channel")
    parser.add_argument(
        "channel",
        nargs="?",
        type=int,
        default=1,
        help="Hardware channel 1–8 (default: 1)",
    )
    parser.add_argument(
        "--type",
        dest="sensor_type",
        default="T",
        choices=sorted(SENSOR_TYPES),
        help="Thermocouple type (default: T)",
    )
    parser.add_argument(
        "--stack",
        type=int,
        default=STACK,
        help="HAT stack address 0–7 (default: 0)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    channel = int(args.channel)
    if channel < 1 or channel > 8:
        print("Channel must be 1–8")
        return 1

    type_code = SENSOR_TYPES[args.sensor_type]
    try:
        board = sm_tc.SMtc(args.stack, I2C_BUS)
        board.set_sensor_type(channel, type_code)
    except Exception as exc:
        print(f"SMtc init failed: {exc}")
        print("Check I2C:  ls /dev/i2c-1 && sudo i2cdetect -y 1")
        print("Stack 0 should appear at address 0x16.")
        return 1

    print(
        f"Reading channel {channel} (Type {args.sensor_type}) "
        f"on stack {args.stack}. Hit ENTER to exit."
    )
    threading.Thread(target=key_capture_thread, daemon=True).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S")
        try:
            temp_c = board.get_temp(channel)
            print(f"{now}  ch{channel}  {temp_c:.2f} °C")
        except Exception as exc:
            print(f"{now}  read error: {exc}")
        time.sleep(SAMPLE_INTERVAL_S)

    print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
