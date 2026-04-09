import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import RPi.GPIO as GPIO
import spidev

from .config import AppConfig
from .utils import utc_iso_timestamp


@dataclass
class SensorSample:
    timestamp: str
    values: List[Optional[float]]
    errors: List[Optional[str]] = field(default_factory=list)


class SensorManager(threading.Thread):
    """Manage MAX31855 SPI sensor polling and publish live samples."""

    def __init__(
        self,
        config: AppConfig,
        ui_queue: queue.Queue,
        logger_queue: queue.Queue,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="SensorManager")
        self.config = config
        self.ui_queue = ui_queue
        self.logger_queue = logger_queue
        self.stop_event = stop_event
        self._lock = threading.Lock()
        self.latest_sample: Optional[SensorSample] = None
        self.logger = logging.getLogger(__name__)
        self.spi = spidev.SpiDev()
        self.cs_pins = config.sensor_cs_pins
        self._setup_hardware()

    def _setup_hardware(self) -> None:
        GPIO.setmode(GPIO.BCM)
        for pin in self.cs_pins:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)

        self.spi.open(self.config.spi_bus, self.config.spi_device)
        self.spi.max_speed_hz = 500_000
        self.spi.mode = 0
        self.logger.info(
            "SPI initialized bus=%s device=%s cs_pins=%s",
            self.config.spi_bus,
            self.config.spi_device,
            self.cs_pins,
        )

    @staticmethod
    def _parse_max31855_value(raw_bytes: List[int]) -> float:
        raw = (raw_bytes[0] << 24) | (raw_bytes[1] << 16) | (raw_bytes[2] << 8) | raw_bytes[3]
        if raw & 0x7:
            raise ValueError("MAX31855 reported an open-circuit or short-circuit fault")

        raw_temp = raw >> 18
        if raw_temp & 0x2000:
            raw_temp -= 0x4000
        return raw_temp * 0.25

    def _read_sensor(self, sensor_index: int, cs_pin: int) -> Optional[float]:
        try:
            GPIO.output(cs_pin, GPIO.LOW)
            raw_bytes = self.spi.xfer2([0x00, 0x00, 0x00, 0x00])
            GPIO.output(cs_pin, GPIO.HIGH)
            return self._parse_max31855_value(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Sensor %s read error: %s", sensor_index, exc)
            raise

    def _poll_sensors(self) -> SensorSample:
        readings: List[Optional[float]] = []
        errors: List[Optional[str]] = []
        for index, pin in enumerate(self.cs_pins):
            try:
                value = self._read_sensor(index, pin)
                readings.append(value)
                errors.append(None)
            except Exception as exc:
                readings.append(None)
                errors.append(str(exc))
        return SensorSample(timestamp=utc_iso_timestamp(), values=readings, errors=errors)

    def run(self) -> None:
        self.logger.info("Sensor manager starting")
        interval = self.config.sensor_poll_interval
        while not self.stop_event.is_set():
            start = time.monotonic()
            sample = self._poll_sensors()
            with self._lock:
                self.latest_sample = sample

            for target_queue in (self.ui_queue, self.logger_queue):
                try:
                    target_queue.put_nowait(sample)
                except queue.Full:
                    self.logger.warning("Dropping sensor sample because queue is full")

            duration = time.monotonic() - start
            sleep_time = max(0.0, interval - duration)
            time.sleep(sleep_time)

        self._shutdown()

    def get_latest_sample(self) -> Optional[SensorSample]:
        with self._lock:
            return self.latest_sample

    def _shutdown(self) -> None:
        self.logger.info("Sensor manager shutting down")
        try:
            self.spi.close()
        except Exception:
            pass
        try:
            GPIO.cleanup(self.cs_pins)
        except Exception:
            pass
