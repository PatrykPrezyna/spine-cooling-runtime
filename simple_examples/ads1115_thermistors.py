"""Standalone readout of thermistors on I2C bus 1 and bus 6.

Bus 1: ADS1115 0x48 (T1-T4), 0x49 (T5-T8); pressure is 0x4A/0x4B
Bus 6: ADS1115 0x48 (T9-T12); 0x49 AIN0 = 4-20 mA flow (220 Ω)

Hit ENTER to stop. Pass a bus number to read only that bus:

    python simple_examples/ads1115_thermistors.py
    python simple_examples/ads1115_thermistors.py 1
    python simple_examples/ads1115_thermistors.py 6

Uses the shared MA300TA103C table from ``data/calibration/``.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

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
from ads1115_flow_reader import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    voltage_to_flow_ml_per_min,
    voltage_to_ma,
)

# (bus, address) — same layout as config.yaml thermistor_sensors.
CHIPS = (
    (1, 0x48),  # T1-T4
    (1, 0x49),  # T5-T8
    (6, 0x48),  # T9-T12
    (6, 0x49),  # FLOW on AIN0
)
# Bus-1 addresses only; ads1115_thermistor_calibrate.py still imports this.
I2C_ADDRESSES = (0x48, 0x49)
GAIN = 1
FLOW_GAIN = 2 / 3  # 20 mA × 220 Ω = 4.40 V needs ±6.144 V
FLOW_SHUNT_OHM = 220.0
FLOW_CHIP = (6, 0x49)
FLOW_PIN_INDEX = 0
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


def open_i2c(bus_id: int):
    """Open Blinka I2C for ``/dev/i2c-<bus_id>``. Bus 1 uses the default pins."""
    if int(bus_id) == 1:
        import board  # pyright: ignore[reportMissingImports]
        import busio  # pyright: ignore[reportMissingImports]

        return busio.I2C(board.SCL, board.SDA)
    from adafruit_extended_bus import ExtendedI2C  # pyright: ignore[reportMissingImports]

    return ExtendedI2C(int(bus_id))


def parse_buses(argv: list[str]) -> set[int] | None:
    """None means all chips. Otherwise a set of bus numbers from argv."""
    if not argv:
        return None
    buses: set[int] = set()
    for arg in argv:
        try:
            buses.add(int(arg))
        except ValueError:
            raise SystemExit(f"Usage: {Path(__file__).name} [bus ...]") from None
    return buses


def open_chips(
    wanted_buses: set[int] | None = None,
) -> tuple[list[tuple[int, int, list[AnalogIn]]], list[str]]:
    """Open each configured chip. Failed buses/chips are reported, not fatal."""
    pins = [getattr(ADS, f"P{i}", i) for i in range(4)]
    i2c_by_bus: dict[int, object] = {}
    opened: list[tuple[int, int, list[AnalogIn]]] = []
    errors: list[str] = []

    for bus_id, address in CHIPS:
        if wanted_buses is not None and bus_id not in wanted_buses:
            continue
        try:
            if bus_id not in i2c_by_bus:
                i2c_by_bus[bus_id] = open_i2c(bus_id)
            ads = ADS.ADS1115(i2c_by_bus[bus_id], address=address)
            ads.gain = GAIN
            ads.mode = Mode.SINGLE
            channels = [AnalogIn(ads, pin) for pin in pins]
            opened.append((bus_id, address, channels))
        except Exception as exc:
            errors.append(f"i2c-{bus_id} 0x{address:X}: {exc}")
    return opened, errors


def format_chip(bus_id: int, address: int, channels: list[AnalogIn], start: int) -> str:
    parts = []
    for i, ch in enumerate(channels):
        is_flow = (bus_id, address) == FLOW_CHIP and i == FLOW_PIN_INDEX
        if (bus_id, address) == FLOW_CHIP and not is_flow:
            continue
        try:
            if is_flow:
                ads = getattr(ch, "ads", None)
                previous_gain = getattr(ads, "gain", None) if ads is not None else None
                if ads is not None:
                    ads.gain = FLOW_GAIN
                v = ch.voltage
                if ads is not None and previous_gain is not None:
                    ads.gain = previous_gain
                ma = voltage_to_ma(v, FLOW_SHUNT_OHM)
                flow = voltage_to_flow_ml_per_min(v, shunt_ohm=FLOW_SHUNT_OHM)
                parts.append(f"FLOW={flow:.1f}ml/min({ma:.1f}mA,{v * 1000.0:.0f}mV)")
            else:
                label = f"T{start + i}"
                v = ch.voltage
                parts.append(f"{label}={voltage_to_c(v):.1f}C({v * 1000.0:.0f}mV)")
        except Exception as exc:
            label = "FLOW" if is_flow else f"T{start + i}"
            parts.append(f"{label}=ERR({exc})")
    return f"  i2c-{bus_id} 0x{address:X}  " + "  ".join(parts)


def main() -> None:
    wanted = parse_buses(sys.argv[1:])
    opened, errors = open_chips(wanted)
    for message in errors:
        print(message)
    if not opened:
        raise SystemExit("No ADS1115 chips opened.")

    n_channels = sum(len(channels) for _, _, channels in opened)
    print(
        f"Reading {n_channels} thermistors "
        f"(gain={GAIN}, Vref={VREF_V}V, Rs={RS_OHM:.0f}Ω). Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    index_of = {chip: 1 + 4 * CHIPS.index(chip) for chip in CHIPS}

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        lines = [now]
        for bus_id, address, channels in opened:
            start = index_of[(bus_id, address)]
            lines.append(format_chip(bus_id, address, channels, start))
        print("\n".join(lines))
        time.sleep(SAMPLE_INTERVAL_S)

    print()


if __name__ == "__main__":
    main()
