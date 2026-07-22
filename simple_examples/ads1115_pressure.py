"""Standalone differential pressure readout (one sensor).

ADS1115 at address 50, differential input P0-P1.
Hit ENTER to stop.

    python simple_examples/ads1115_pressure.py
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import board  # pyright: ignore[reportMissingImports]
import busio  # pyright: ignore[reportMissingImports]
import adafruit_ads1x15.ads1115 as ADS  # pyright: ignore[reportMissingImports]
from adafruit_ads1x15.analog_in import AnalogIn  # pyright: ignore[reportMissingImports]

try:
    from adafruit_ads1x15.ads1x15 import Mode  # pyright: ignore[reportMissingImports]
except Exception:
    from adafruit_ads1x15.ads1115 import Mode  # pyright: ignore[reportMissingImports]

I2C_ADDRESS = 74
GAIN = 16  # ±0.256 V
SAMPLE_INTERVAL_S = 0.5  # 2 Hz print loop

# Linear calibration: mV -> psi
MV_LO, PSI_LO = -14.858, -11.5
MV_HI, PSI_HI = 96.9, 75.0

keep_going = True


def mv_to_psi(mv: float) -> float:
    return PSI_LO + (mv - MV_LO) * (PSI_HI - PSI_LO) / (MV_HI - MV_LO)


def key_capture_thread() -> None:
    global keep_going
    input()
    keep_going = False


def main() -> None:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, address=I2C_ADDRESS)
    ads.gain = GAIN
    ads.mode = Mode.SINGLE/sigma delta

    # Differential: channel 0 (+) minus channel 1 (-)
    # Newer ads1x15 builds may not export P0/P1; fall back to pin indices.
    p0 = getattr(ADS, "P0", 0)
    p1 = getattr(ADS, "P1", 1)
    sensor = AnalogIn(ads, p0, p1)

    print(
        f"Reading Pressure 1 on ADS1115 0x{I2C_ADDRESS:X} "
        f"(P0-P1 differential, gain={GAIN}, "
        f"{1.0 / SAMPLE_INTERVAL_S:.0f} Hz). Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            mv = sensor.voltage * 1000.0
            psi = mv_to_psi(mv)
            print(f"{now}  Pressure 1 -> {mv:.2f} mV  {psi:.2f} psi  (raw={sensor.value})")
        except Exception as exc:
            print(f"{now}  Pressure 1 -> ERR ({exc})")
        time.sleep(SAMPLE_INTERVAL_S)

    print()


if __name__ == "__main__":
    main()
