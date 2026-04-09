import enum
import logging
import threading
import time
from typing import Optional

import serial

from .config import AppConfig
from .sensor_manager import SensorManager


class CompressorState(enum.Enum):
    IDLE = "IDLE"
    COOLING = "COOLING"
    ALARM = "ALARM"
    FAULT = "FAULT"


class CompressorController(threading.Thread):
    """Monitor temperature state and exchange commands with the RS-232 compressor."""

    def __init__(
        self,
        config: AppConfig,
        sensor_manager: SensorManager,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="CompressorController")
        self.config = config
        self.sensor_manager = sensor_manager
        self.stop_event = stop_event
        self.logger = logging.getLogger(__name__)
        self.state = CompressorState.IDLE
        self.last_command: Optional[str] = None
        self.port = config.uart_port
        self.baudrate = config.uart_baudrate
        self.serial: Optional[serial.Serial] = None
        self._open_serial()

    def _open_serial(self) -> None:
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.5)
            self.logger.info("Compressor UART opened on %s at %s", self.port, self.baudrate)
        except serial.SerialException as exc:
            self.logger.exception("Unable to open compressor UART port: %s", exc)
            self.serial = None

    def run(self) -> None:
        self.logger.info("Compressor controller starting")
        while not self.stop_event.is_set():
            self._read_serial()
            self._evaluate_sensor_state()
            time.sleep(self.config.compressor_poll_interval)
        self._shutdown()

    def _read_serial(self) -> None:
        if not self.serial or not self.serial.is_open:
            return
        try:
            raw_data = self.serial.readline()
            if not raw_data:
                return
            message = raw_data.decode("ascii", errors="ignore").strip()
            self.logger.debug("Compressor UART received: %s", message)
            self._parse_message(message)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Compressor UART read failure: %s", exc)

    def _parse_message(self, message: str) -> None:
        lower = message.lower()
        if "fault" in lower or "error" in lower:
            self._transition(CompressorState.FAULT)
        elif "alarm" in lower:
            self._transition(CompressorState.ALARM)
        elif "running" in lower or "ok" in lower:
            if self.state == CompressorState.FAULT:
                self._transition(CompressorState.IDLE)
        self.logger.info("Compressor controller parsed remote message: %s", message)

    def _evaluate_sensor_state(self) -> None:
        sample = self.sensor_manager.get_latest_sample()
        if sample is None or not sample.values:
            return

        max_temp = max((value for value in sample.values if value is not None), default=0.0)
        target_state = self.state
        if max_temp >= self.config.fault_threshold:
            target_state = CompressorState.FAULT
        elif max_temp >= self.config.alarm_threshold:
            target_state = CompressorState.ALARM
        elif max_temp >= self.config.cooling_enable:
            target_state = CompressorState.COOLING
        elif max_temp <= self.config.cooling_disable:
            target_state = CompressorState.IDLE

        if target_state != self.state:
            self._transition(target_state)
            if target_state == CompressorState.COOLING:
                self._send_command("START_COOLING")
            elif target_state in (CompressorState.IDLE,):
                self._send_command("STOP_COOLING")
            elif target_state == CompressorState.ALARM:
                self._send_command("SET_ALARM")
            elif target_state == CompressorState.FAULT:
                self._send_command("SET_FAULT")

    def _transition(self, next_state: CompressorState) -> None:
        if next_state == self.state:
            return
        self.logger.info("Compressor state transition %s -> %s", self.state.value, next_state.value)
        self.state = next_state

    def _send_command(self, command: str) -> None:
        if not self.serial or not self.serial.is_open:
            self.logger.warning("Cannot send compressor command, UART port is unavailable")
            return
        try:
            framed = f"{command}\r\n".encode("ascii")
            self.serial.write(framed)
            self.serial.flush()
            self.last_command = command
            self.logger.info("Sent compressor command: %s", command)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Failed to send compressor command %s: %s", command, exc)

    def _shutdown(self) -> None:
        self.logger.info("Compressor controller shutting down")
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass
