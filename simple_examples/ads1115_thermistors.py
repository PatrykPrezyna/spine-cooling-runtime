"""Standalone readout of all 8 thermistors.

Two ADS1115 chips: 0x48 (ch 0-3), 0x49 (ch 4-7), single-ended.
Hit ENTER to stop.

Uses the shared MA300TA103C table from ``data/calibration/``.

    python simple_examples/ads1115_thermistors.py
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import board  # pyright: ignore[reportMissingImports]
import busio  # pyright: ignore[reportMissingImports]
import adafruit_ads1x15.ads1115 as ADS  # pyright: ignore[reportMissingImports]
from adafruit_ads1x15.analog_in import AnalogIn  # pyright: ignore[reportMissingImports]

try:
    from adafruit_ads1x15.ads1x15 import Mode  # pyright: ignore[reportMissingImports]
except Exception:
    from adafruit_ads1x15.ads1115 import Mode  # pyright: ignore[reportMissingImports]

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
from thermistor_conversion import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    DEFAULT_RS_OHM,
    DEFAULT_VREF_V,
    voltage_to_celsius,
)

I2C_ADDRESSES = (0x48, 0x49)
GAIN = 1
SAMPLE_INTERVAL_S = 0.5
VREF_V = DEFAULT_VREF_V
RS_OHM = DEFAULT_RS_OHM

# Re-export for calibrate script / callers that import voltage_to_c.
voltage_to_c = voltage_to_celsius

keep_going = True


def key_capture_thread() -> None:
    global keep_going
    input()
    keep_going = False


def main() -> None:
    i2c = busio.I2C(board.SCL, board.SDA)
    pins = [getattr(ADS, f"P{i}", i) for i in range(4)]
    channels: list[AnalogIn] = []

    for address in I2C_ADDRESSES:
        ads = ADS.ADS1115(i2c, address=address)
        ads.gain = GAIN
        ads.mode = Mode.SINGLE
        for pin in pins:
            channels.append(AnalogIn(ads, pin))

    print(
        f"Reading 8 thermistors on ADS1115 "
        f"{', '.join(f'0x{a:X}' for a in I2C_ADDRESSES)} "
        f"(gain={GAIN}, Vref={VREF_V}V, Rs={RS_OHM:.0f}Ω). Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        parts = []
        for i, ch in enumerate(channels):
            try:
                v = ch.voltage
                parts.append(f"T{i + 1}={voltage_to_c(v):.1f}C({v * 1000.0:.0f}mV)")
            except Exception as exc:
                parts.append(f"T{i + 1}=ERR({exc})")
        print(f"{now}\n" + "  ".join(parts))
        time.sleep(SAMPLE_INTERVAL_S)

    print()


if __name__ == "__main__":
    main()
