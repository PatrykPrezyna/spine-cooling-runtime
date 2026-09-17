"""Unit tests for pigpio digital GPIO (sensors and compressor relay)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compressor_relay import CompressorRelay  # noqa: E402
from multi_sensor_reader import MultiSensorReader  # noqa: E402
from pigpio_gpio import (  # noqa: E402
    INPUT,
    OUTPUT,
    PUD_DOWN,
    PUD_OFF,
    PUD_UP,
    PigpioUnavailableError,
    connect_pigpio,
)


class FakePi:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.stopped = False
        self.modes: dict[int, int] = {}
        self.pulls: dict[int, int] = {}
        self.levels: dict[int, int] = {}

    def set_mode(self, pin: int, mode: int) -> None:
        self.modes[pin] = mode

    def set_pull_up_down(self, pin: int, pud: int) -> None:
        self.pulls[pin] = pud

    def write(self, pin: int, level: int) -> None:
        self.levels[pin] = int(level)

    def read(self, pin: int) -> int:
        return int(self.levels.get(pin, 0))

    def stop(self) -> None:
        self.stopped = True


class ConnectPigpioTests(unittest.TestCase):
    def test_raises_when_module_missing(self) -> None:
        with patch("pigpio_gpio.pigpio", None):
            with self.assertRaises(PigpioUnavailableError) as ctx:
                connect_pigpio("test")
        self.assertIn("not installed", str(ctx.exception))

    def test_raises_when_daemon_disconnected(self) -> None:
        fake = FakePi(connected=False)
        pigpio_mod = Mock()
        pigpio_mod.pi.return_value = fake
        with patch("pigpio_gpio.pigpio", pigpio_mod):
            with self.assertRaises(PigpioUnavailableError):
                connect_pigpio("test")
        self.assertTrue(fake.stopped)

    def test_returns_connected_client(self) -> None:
        fake = FakePi(connected=True)
        pigpio_mod = Mock()
        pigpio_mod.pi.return_value = fake
        with patch("pigpio_gpio.pigpio", pigpio_mod):
            self.assertIs(connect_pigpio("test"), fake)


class CompressorRelayTests(unittest.TestCase):
    def test_active_high_off_is_gpio_low(self) -> None:
        pi = FakePi()
        relay = CompressorRelay(6, pi=pi)
        self.assertEqual(pi.modes[6], OUTPUT)
        self.assertEqual(pi.pulls[6], PUD_OFF)
        self.assertEqual(pi.levels[6], 0)

        relay.set_running(True)
        self.assertEqual(pi.levels[6], 1)

        relay.set_running(False)
        self.assertEqual(pi.levels[6], 0)

        relay.cleanup()
        self.assertEqual(pi.levels[6], 0)
        self.assertFalse(pi.stopped)

    def test_active_low_on_is_gpio_low(self) -> None:
        pi = FakePi()
        relay = CompressorRelay(6, pi=pi, active_low=True)
        self.assertEqual(pi.levels[6], 1)

        relay.set_running(True)
        self.assertEqual(pi.levels[6], 0)

        relay.set_running(False)
        self.assertEqual(pi.levels[6], 1)


class MultiSensorReaderTests(unittest.TestCase):
    def _config(self) -> dict:
        return {
            "sample_rate_hz": 1.0,
            "sensors": [
                {
                    "name": "Level Low",
                    "gpio_pin": 12,
                    "active_high": True,
                    "pull_up": True,
                },
                {
                    "name": "Leak Sensor",
                    "gpio_pin": 26,
                    "active_high": False,
                    "pull_up": False,
                },
            ],
        }

    def test_configures_inputs_and_reads_levels(self) -> None:
        pi = FakePi()
        pi.levels[12] = 1
        pi.levels[26] = 0
        reader = MultiSensorReader(self._config(), pi=pi)

        self.assertEqual(pi.modes[12], INPUT)
        self.assertEqual(pi.pulls[12], PUD_UP)
        self.assertEqual(pi.modes[26], INPUT)
        self.assertEqual(pi.pulls[26], PUD_DOWN)

        states = reader.read_all()
        self.assertTrue(states["Level Low"])
        # active_low: GPIO 0 → reported True
        self.assertTrue(states["Leak Sensor"])

        reader.cleanup()
        self.assertFalse(pi.stopped)
        self.assertFalse(reader.is_initialized)


if __name__ == "__main__":
    unittest.main()
