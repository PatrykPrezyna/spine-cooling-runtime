"""Standalone readout of all 8 thermistors.

Two ADS1115 chips: 0x48 (ch 0-3), 0x49 (ch 4-7), single-ended.
Hit ENTER to stop.

    python simple_examples/ads1115_thermistors.py
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

I2C_ADDRESSES = (0x48, 0x49)
GAIN = 1
SAMPLE_INTERVAL_S = 0.5

# Piecewise-linear mV -> °C (NTC-style)
MV_C = ((616.0, 0.0), (142.0, 37.0), (87.0, 50.0))

keep_going = True


def mv_to_c(mv: float) -> float:
    pts = sorted(MV_C, key=lambda p: -p[0])
    if mv >= pts[0][0]:
        a, b = pts[0], pts[1]
    elif mv <= pts[-1][0]:
        a, b = pts[-2], pts[-1]
    else:
        a = b = pts[0]
        for left, right in zip(pts, pts[1:]):
            if right[0] <= mv <= left[0]:
                a, b = left, right
                break
    return a[1] + (mv - a[0]) * (b[1] - a[1]) / (b[0] - a[0])


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
        f"(gain={GAIN}). Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        parts = []
        for i, ch in enumerate(channels):
            try:
                mv = ch.voltage * 1000.0
                parts.append(f"T{i + 1}={mv_to_c(mv):.1f}C({mv:.0f}mV)")
            except Exception as exc:
                parts.append(f"T{i + 1}=ERR({exc})")
        print(f"{now}  " + "  ".join(parts))
        time.sleep(SAMPLE_INTERVAL_S)

    print()


if __name__ == "__main__":
    main()
