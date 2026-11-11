"""Scan every ADS1115 on I2C bus 1 and bus 6 as a thermistor.

Eight chips (0x48–0x4B on each bus), four pins each. Every pin is converted
with the thermistor table so a sensor plugged into a pressure or flow chip
still shows a temperature. A reading from 20 °C to 40 °C is marked so it
stands out while you find the right probe.

Hit ENTER to stop. Pass a bus number to read only that bus:

    python examples/ads1115_thermistors.py
    python examples/ads1115_thermistors.py 1
    python examples/ads1115_thermistors.py 6

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

# All four ADS1115 addresses on both buses. Pressure and flow chips are
# included so a thermistor on the wrong converter still shows up.
BUSES = (1, 6)
ADDRESSES = (0x48, 0x49, 0x4A, 0x4B)
CHIPS = tuple((bus_id, address) for bus_id in BUSES for address in ADDRESSES)
# Bus-1 temperature addresses only; ads1115_thermistor_calibrate.py still imports this.
I2C_ADDRESSES = (0x4A, 0x4B)
GAIN = 1
SAMPLE_INTERVAL_S = 0.5
VREF_V = DEFAULT_VREF_V
RS_OHM = DEFAULT_RS_OHM
WARM_LO_C = 20.0
WARM_HI_C = 40.0
_MARK_ON = "\033[1;30;103m"
_MARK_OFF = "\033[0m"

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


def in_warm_range(temp_c: float) -> bool:
    return WARM_LO_C <= temp_c <= WARM_HI_C


def mark(text: str) -> str:
    """Yellow highlight on a terminal; asterisks if color is not available."""
    if sys.stdout.isatty():
        return f"{_MARK_ON} {text} {_MARK_OFF}"
    return f"** {text} **"


def format_chip(
    bus_id: int, address: int, channels: list[AnalogIn]
) -> tuple[str, list[str]]:
    parts: list[str] = []
    warm: list[str] = []
    for pin, ch in enumerate(channels):
        label = f"AIN{pin}"
        try:
            volts = ch.voltage
            temp_c = voltage_to_c(volts)
            text = f"{label}={temp_c:.1f}C({volts * 1000.0:.0f}mV)"
            if in_warm_range(temp_c):
                text = mark(text)
                warm.append(f"i2c-{bus_id} 0x{address:X} {label}={temp_c:.1f}C")
            parts.append(text)
        except Exception as exc:
            parts.append(f"{label}=ERR({exc})")
    line = f"  i2c-{bus_id} 0x{address:X}  " + "  ".join(parts)
    return line, warm


def main() -> None:
    wanted = parse_buses(sys.argv[1:])
    opened, errors = open_chips(wanted)
    for message in errors:
        print(message)
    if not opened:
        raise SystemExit("No ADS1115 chips opened.")

    n_channels = sum(len(channels) for _, _, channels in opened)
    print(
        f"Reading {n_channels} pins on {len(opened)} ADS1115s as thermistors "
        f"(gain={GAIN}, Vref={VREF_V}V, Rs={RS_OHM:.0f}Ω). "
        f"{WARM_LO_C:.0f}–{WARM_HI_C:.0f}°C is highlighted. Hit ENTER to exit."
    )
    threading.Thread(
        target=key_capture_thread, name="key_capture_thread", daemon=True
    ).start()

    while keep_going:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        lines = [now]
        warm: list[str] = []
        for bus_id, address, channels in opened:
            line, hits = format_chip(bus_id, address, channels)
            lines.append(line)
            warm.extend(hits)
        if warm:
            lines.append("  " + mark("20–40°C: " + " | ".join(warm)))
        print("\n".join(lines))
        print()
        time.sleep(SAMPLE_INTERVAL_S)

    print()


if __name__ == "__main__":
    main()
