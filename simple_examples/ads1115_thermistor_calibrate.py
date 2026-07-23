"""Interactive 2-point bath check for all 8 thermistors.

For each sensor T1..T8:
  1. Put the sensor in ice water (~0°C), press ENTER
  2. Put the same sensor in 37°C water, press ENTER

Saves measured voltage and calculated temperature to a timestamped CSV.

    python simple_examples/ads1115_thermistor_calibrate.py
"""

from __future__ import annotations

import csv
import statistics
import sys
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ads1115_thermistors import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    GAIN,
    I2C_ADDRESSES,
    voltage_to_c,
)

NUM_SENSORS = 8
NUM_SAMPLES = 10
SAMPLE_GAP_S = 0.1
SETTLE_S = 1.0

BATHS = (
    ("ice_water", 0.0, "ice water (~0°C)"),
    ("water_37c", 37.0, "37°C water"),
)

OUT_DIR = Path(__file__).resolve().parent


def open_channels() -> list[AnalogIn]:
    i2c = busio.I2C(board.SCL, board.SDA)
    pins = [getattr(ADS, f"P{i}", i) for i in range(4)]
    channels: list[AnalogIn] = []
    for address in I2C_ADDRESSES:
        ads = ADS.ADS1115(i2c, address=address)
        ads.gain = GAIN
        ads.mode = Mode.SINGLE
        for pin in pins:
            channels.append(AnalogIn(ads, pin))
    return channels


def wait_confirm(prompt: str) -> None:
    input(f"{prompt}\nPress ENTER when ready (or Ctrl+C to abort)... ")


def measure(channel: AnalogIn) -> tuple[float, float]:
    """Average several readings; return (voltage_v, temp_c)."""
    time.sleep(SETTLE_S)
    voltages: list[float] = []
    for _ in range(NUM_SAMPLES):
        voltages.append(channel.voltage)
        time.sleep(SAMPLE_GAP_S)
    v = statistics.mean(voltages)
    return v, voltage_to_c(v)


def main() -> None:
    channels = open_channels()
    if len(channels) < NUM_SENSORS:
        raise SystemExit(f"Expected {NUM_SENSORS} channels, got {len(channels)}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"thermistor_bath_check_{stamp}.csv"

    print(
        "Thermistor bath check\n"
        f"Sensors T1..T{NUM_SENSORS} on ADS1115 "
        f"{', '.join(f'0x{a:X}' for a in I2C_ADDRESSES)}\n"
        f"Results will be saved to:\n  {out_path}\n"
    )

    fieldnames = (
        "sensor",
        "bath",
        "expected_temp_c",
        "voltage_v",
        "voltage_mv",
        "measured_temp_c",
        "temp_error_c",
        "timestamp",
    )
    rows: list[dict[str, object]] = []

    try:
        for i in range(NUM_SENSORS):
            sensor = f"T{i + 1}"
            ch = channels[i]
            print(f"\n===== {sensor} =====")
            for bath_id, expected_c, bath_label in BATHS:
                wait_confirm(f"Put {sensor} into {bath_label}.")
                print(f"Measuring {sensor} in {bath_label}...")
                v, t_c = measure(ch)
                row = {
                    "sensor": sensor,
                    "bath": bath_id,
                    "expected_temp_c": expected_c,
                    "voltage_v": round(v, 6),
                    "voltage_mv": round(v * 1000.0, 3),
                    "measured_temp_c": round(t_c, 3),
                    "temp_error_c": round(t_c - expected_c, 3),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
                rows.append(row)
                print(
                    f"  {sensor} {bath_id}: "
                    f"{v * 1000.0:.1f} mV -> {t_c:.2f}°C "
                    f"(expected {expected_c:.0f}°C, "
                    f"error {t_c - expected_c:+.2f}°C)"
                )
    except KeyboardInterrupt:
        print("\nAborted by user.")

    if not rows:
        print("No measurements taken; CSV not written.")
        return

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} rows to:\n  {out_path}")


if __name__ == "__main__":
    main()
