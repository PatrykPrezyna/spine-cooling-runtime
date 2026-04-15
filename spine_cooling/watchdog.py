import logging
import threading
import time
from pathlib import Path

import RPi.GPIO as GPIO


class WatchdogThread(threading.Thread):
    """Kick the Linux watchdog device and perform hardware reset on failure."""

    def __init__(
        self,
        dev_path: Path,
        reset_pin: int,
        interval: float,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="WatchdogThread")
        self.dev_path = dev_path
        self.reset_pin = reset_pin
        self.interval = interval
        self.stop_event = stop_event
        self.watchdog_file = None
        self.logger = logging.getLogger(__name__)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.reset_pin, GPIO.OUT, initial=GPIO.HIGH)

    def run(self) -> None:
        self.logger.info("Watchdog thread starting, device=%s", self.dev_path)
        try:
            with open(self.dev_path, "wb", buffering=0) as handle:
                self.watchdog_file = handle
                while not self.stop_event.is_set():
                    try:
                        self.watchdog_file.write(b"\0")
                        self.watchdog_file.flush()
                        self.logger.debug("Watchdog kicked")
                    except Exception as exc:  # noqa: BLE001
                        self.logger.exception("Watchdog write failed: %s", exc)
                        self._hardware_reset()
                        self.stop_event.set()
                        break
                    time.sleep(self.interval)
        except FileNotFoundError:
            self.logger.error("Watchdog device not found: %s", self.dev_path)
            self._hardware_reset()
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Unexpected watchdog failure: %s", exc)
            self._hardware_reset()
        finally:
            self.logger.info("Watchdog thread exiting")

    def _hardware_reset(self) -> None:
        self.logger.warning("Attempting BCM hardware reset on pin %s", self.reset_pin)
        try:
            GPIO.output(self.reset_pin, GPIO.LOW)
            time.sleep(0.5)
            GPIO.output(self.reset_pin, GPIO.HIGH)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Hardware reset failed: %s", exc)
