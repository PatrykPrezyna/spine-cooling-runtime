"""Own one run's session CSVs and the USB copy of those files.

``SensorMonitorApp`` decides when a row or event is worth recording.
This class opens the files, writes them, and closes them. It does not
read sensors or update the screen.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from csv_logger import CSVLogger
from fault_catalog import FaultCode, get_fault
from pressure_csv_logger import PressureCSVLogger, PressureCaptureLoop
from safety_rules import TelemetrySnapshot
from session_log_paths import log_directory
from status_event_logger import StatusEventLogger, warning_log_edges
from usb_log_mirror import (
    STATE_CATCHING_UP,
    STATE_DISABLED,
    STATE_EJECTING,
    STATE_ERROR,
    STATE_MIRRORING,
    STATE_SAFE_TO_REMOVE,
    STATE_WAITING,
    UsbLogMirror,
    disk_free_bytes,
)


class SessionRecorder:
    """Sensor, pressure, and status CSVs for a single session stamp."""

    def __init__(
        self,
        config: dict,
        session_start: datetime,
        *,
        simulation: bool = False,
    ):
        self.config = config
        self.session_start = session_start
        self.simulation = bool(simulation)
        self.csv_logger = CSVLogger(config, session_start=session_start)
        self.pressure_csv_logger = PressureCSVLogger(
            config, session_start=session_start
        )
        self.status_event_logger = StatusEventLogger(
            config, session_start=session_start
        )
        self._usb_mirror: Optional[UsbLogMirror] = None
        self._pressure_capture_loop: Optional[PressureCaptureLoop] = None
        self._logged_setpoints: dict[str, str] = {}
        self._logged_warning_codes: set[FaultCode] = set()
        # USB absence is logged once per session. Presence checks flicker when
        # the mount comes and goes, and a stop fault clears the warning set,
        # which was appending a new row on almost every tick.
        self._once_logged_warnings: set[FaultCode] = set()

    def start_status_log(self) -> None:
        """Create the log folder and open the status CSV.

        A failed status file is not fatal. Sensor logging is started later,
        after hardware init, and that failure still stops the session.
        """
        Path(log_directory(self.config)).mkdir(parents=True, exist_ok=True)
        if not self.status_event_logger.start_logging():
            print("Warning: status logging failed to start; continuing without it")

    def start_sensor_log(self) -> bool:
        """Open the UI-rate sensor CSV. False means the session cannot start."""
        return self.csv_logger.start_logging()

    def record_sensors(
        self,
        sensor_states: dict,
        temperatures: Optional[dict] = None,
        *,
        peristaltic_pump_set_speed_rpm: Optional[float] = None,
        set_temperature_c: Optional[float] = None,
        compressor_cooling: Optional[int] = None,
        pressures: Optional[dict] = None,
        flow_sensor_ml_per_min: Optional[float] = None,
    ) -> None:
        """Append one sensor-CSV row. The I/O worker calls this on its own thread."""
        self.csv_logger.log(
            sensor_states,
            temperatures,
            peristaltic_pump_set_speed_rpm=peristaltic_pump_set_speed_rpm,
            set_temperature_c=set_temperature_c,
            compressor_cooling=compressor_cooling,
            pressures=pressures,
            flow_sensor_ml_per_min=flow_sensor_ml_per_min,
        )

    def start_pressure_capture(
        self,
        pressure_reader: Any,
        pump_set_speed_rpm_getter: Callable[[], float],
    ) -> None:
        """Begin the 100 Hz pressure file for the whole session.

        Skipped when the reader is unavailable, which would otherwise fill
        the file with blank rows. Capture failure is not fatal: the sensor
        CSV still carries pressures at the UI tick rate.
        """
        if pressure_reader is None or not pressure_reader.is_initialized:
            print("Pressure CSV start skipped: pressure reader unavailable")
            return
        self._stop_pressure_capture()
        if not self.pressure_csv_logger.start_logging():
            print("Warning: pressure CSV start failed; continuing without it")
            return
        self._pressure_capture_loop = PressureCaptureLoop(
            pressure_reader,
            self.pressure_csv_logger,
            pump_set_speed_rpm_getter=pump_set_speed_rpm_getter,
        )
        self._pressure_capture_loop.start()

    def start_usb_mirror(self) -> None:
        """Copy new log bytes to a USB stick, if that copy is enabled."""
        self._usb_mirror = UsbLogMirror(
            self.config,
            source_directory=Path(log_directory(self.config)),
            on_event=self._on_usb_mirror_event,
            flush_sources=self.flush,
        )
        if not self._usb_mirror.enabled:
            print("USB log copy disabled")
            return
        self._usb_mirror.start()
        print(
            f"USB log copy started (label {self._usb_mirror.volume_label}, "
            f"every {self._usb_mirror.interval_s:.1f}s)"
        )

    def flush(self) -> None:
        """Flush buffered pressure and status rows before a USB copy.

        The sensor CSV already flushes every row.
        """
        if self.pressure_csv_logger is not None:
            self.pressure_csv_logger.flush()
        if self.status_event_logger is not None:
            self.status_event_logger.flush()

    def log_state_change(
        self,
        old_state: Any,
        new_state: Any,
        reason: str = "",
        *,
        fault_code: Any = None,
    ) -> None:
        self.status_event_logger.log_state_change(
            old_state,
            new_state,
            reason,
            fault_code=fault_code,
        )

    def sync_warnings(self, message_codes: list[FaultCode], state: Any) -> None:
        """Log warning appear/clear edges, not every 10 Hz tick.

        ``USB_NOT_PRESENT`` is written once per session. It stays active for
        the whole run when no stick is inserted, and mount detection plus
        stop-fault clears were re-logging it on every flicker.
        """
        cleared, raised, logged, once_logged = warning_log_edges(
            self._logged_warning_codes,
            set(message_codes),
            once_codes={FaultCode.USB_NOT_PRESENT},
            once_logged=self._once_logged_warnings,
        )
        if not cleared and not raised:
            self._logged_warning_codes = logged
            self._once_logged_warnings = once_logged
            return
        for code in cleared:
            self._log_warning(code, state, cleared=True)
        for code in raised:
            self._log_warning(code, state, cleared=False)
        self._logged_warning_codes = logged
        self._once_logged_warnings = once_logged

    def log_setpoint_if_changed(self, name: str, value: str) -> None:
        """Append a setpoint row when the commanded value differs from the last one."""
        if self._logged_setpoints.get(name) == value:
            return
        self._logged_setpoints[name] = value
        self.status_event_logger.log_setpoint(name, value)

    def storage_telemetry(self) -> TelemetrySnapshot:
        """USB presence and free space for MESSAGE-severity storage warnings."""
        local_free = disk_free_bytes(Path(log_directory(self.config)))
        # --sim has no physical SPINELOGS stick; skip presence/storage faults.
        if self.simulation:
            return TelemetrySnapshot(
                usb_logging_enabled=False,
                local_free_bytes=local_free,
            )
        mirror = self._usb_mirror
        if mirror is None or not mirror.enabled:
            return TelemetrySnapshot(
                usb_logging_enabled=False,
                local_free_bytes=local_free,
            )
        status = mirror.status()
        ejected = status.state in (STATE_EJECTING, STATE_SAFE_TO_REMOVE)
        present = status.state in (
            STATE_MIRRORING,
            STATE_CATCHING_UP,
            STATE_ERROR,
        ) and bool(status.mount_path)
        if status.state == STATE_WAITING:
            present = False
        if status.state == STATE_DISABLED:
            return TelemetrySnapshot(
                usb_logging_enabled=False,
                local_free_bytes=local_free,
            )
        return TelemetrySnapshot(
            usb_logging_enabled=True,
            usb_present=present if not ejected else False,
            usb_ejected=ejected,
            usb_free_bytes=status.free_bytes if present and not ejected else None,
            local_free_bytes=local_free,
        )

    def usb_ui_status(self) -> Optional[tuple[str, str, bool]]:
        """Return ``(state, message, can_eject)``, or None before the mirror exists."""
        mirror = self._usb_mirror
        if mirror is None:
            return None
        status = mirror.status()
        return status.state, status.message, status.can_eject

    def request_usb_eject(self) -> None:
        if self._usb_mirror is None:
            return
        self._usb_mirror.request_eject()

    def stop(self, state: Any = None, message: str = "Session ended") -> None:
        """Close every session file. The caller stops the I/O worker first."""
        if self.csv_logger:
            self.csv_logger.stop_logging()
            print("CSV logging stopped")
        self._stop_pressure_capture()
        if self.pressure_csv_logger is not None:
            self.pressure_csv_logger.stop_logging()
        self._stop_status_logging(state, message)
        self._stop_usb_mirror()

    def _log_warning(self, code: FaultCode, state: Any, *, cleared: bool) -> None:
        self.status_event_logger.log_warning(
            code,
            get_fault(code).message,
            state=state,
            cleared=cleared,
        )

    def _on_usb_mirror_event(self, event: str, message: str) -> None:
        self.status_event_logger.log(event=event, severity="info", message=message)

    def _stop_pressure_capture(self) -> None:
        if self._pressure_capture_loop is not None:
            self._pressure_capture_loop.stop()
            self._pressure_capture_loop = None

    def _stop_status_logging(self, state: Any, message: str) -> None:
        logger = self.status_event_logger
        if logger is None or not logger.is_logging:
            return
        logger.log_session_stop(state=state, message=message)
        logger.stop_logging()

    def _stop_usb_mirror(self) -> None:
        if self._usb_mirror is None:
            return
        self._usb_mirror.stop()
        self._usb_mirror = None
