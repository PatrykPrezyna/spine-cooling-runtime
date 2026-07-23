"""Standalone readout of all 8 thermistors.

Two ADS1115 chips: 0x48 (ch 0-3), 0x49 (ch 4-7), single-ended.
Hit ENTER to stop.

    python simple_examples/ads1115_thermistors.py
"""

from __future__ import annotations

import csv
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

I2C_ADDRESSES = (0x48, 0x49)
GAIN = 1
SAMPLE_INTERVAL_S = 0.5

# Voltage divider: V = Vref * R / (Rs + R), NTC to ground, Rs pull-up.
VREF_V = 2.5
RS_OHM = 100_000.0
THERMISTOR_CSV = Path(__file__).with_name("Thermistor_MA300TA103C.csv")
R_COL = "10k_Ohm"

keep_going = True


def load_rt_table(path: Path) -> list[tuple[float, float]]:
    """Return (R_ohm, T_C) pairs sorted by descending R (NTC)."""
    rows: list[tuple[float, float]] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append((float(row[R_COL]), float(row["Temperature_C"])))
    rows.sort(key=lambda p: -p[0])
    return rows


RT_TABLE = load_rt_table(THERMISTOR_CSV)


def voltage_to_r(v: float) -> float:
    """Invert V = Vref * R / (Rs + R)."""
    if v <= 0.0:
        return 0.0
    if v >= VREF_V:
        return float("inf")
    return RS_OHM * v / (VREF_V - v)


def r_to_c(r: float) -> float:
    """Linear interpolate °C from resistance using the MA300TA103C 10k table."""
    pts = RT_TABLE
    if r >= pts[0][0]:
        a, b = pts[0], pts[1]
    elif r <= pts[-1][0]:
        a, b = pts[-2], pts[-1]
    else:
        a = b = pts[0]
        for left, right in zip(pts, pts[1:]):
            if right[0] <= r <= left[0]:
                a, b = left, right
                break
    return a[1] + (r - a[0]) * (b[1] - a[1]) / (b[0] - a[0])


def voltage_to_c(v: float) -> float:
    return r_to_c(voltage_to_r(v))


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
