"""Standalone differential pressure readout (one sensor).

ADS1115 at address 50, differential input P0-P1.
Hit ENTER to stop.

    python simple_examples/ads1115_pressure.py
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

try:
    from adafruit_ads1x15.ads1x15 import Mode
except Exception:
    from adafruit_ads1x15.ads1115 import Mode

I2C_ADDRESS = 48
GAIN = 16  # ±0.256 V

keep_going = True


def key_capture_thread() -> None:
    global keep_going
    input()
    keep_going = False


def main() -> None:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, address=I2C_ADDRESS)
    ads.gain = GAIN
    ads.mode = Mode.SINGLE

    # Differential: channel 0 (+) minus channel 1 (-)
    sensor = AnalogIn(ads, ADS.P0, ADS.P1)

    print(
        f"Reading Pressure 1 on ADS1115 0x{I2C_ADDRESS:X} "
        f"(P0-P1 differential, gain={GAIN}). Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S")
        try:
            mv = sensor.voltage * 1000.0
            print(f"{now}  Pressure 1 -> {mv:.2f} mV  (raw={sensor.value})")
        except Exception as exc:
            print(f"{now}  Pressure 1 -> ERR ({exc})")
        time.sleep(1.0)

    print()


if __name__ == "__main__":
    main()
