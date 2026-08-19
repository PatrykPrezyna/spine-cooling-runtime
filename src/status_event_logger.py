"""CSV logger for state-machine changes, errors, and warnings.

Unlike the sensor/pressure files this is event-based: one row per
transition or fault edge, not a periodic sample.
"""

from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from session_log_paths import log_directory, status_filename_format


class StatusEventLogger:
    """Append status, error, and warning events to a session CSV."""

    HEADER = (
        "timestamp",
        "event",
        "severity",
        "previous_state",
        "state",
        "fault_code",
        "message",
    )

    def __init__(self, config: dict, session_start: Optional[datetime] = None):
        self.csv_directory = log_directory(config)
        self.filename_format = status_filename_format(config)
        self.session_start = session_start or datetime.now()

        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False
        self._lock = threading.Lock()

        Path(self.csv_directory).mkdir(parents=True, exist_ok=True)

    def start_logging(self) -> bool:
        """Open the session status file and write a session_start row."""
        with self._lock:
            if self.is_logging:
                print("Warning: Status logging already active")
                return False

            try:
                self.csv_file = Path(self.csv_directory) / self.session_start.strftime(
                    self.filename_format
                )
                self.file_handle = open(self.csv_file, "w", newline="", encoding="utf-8")
                self.csv_writer = csv.writer(self.file_handle)
                self.csv_writer.writerow(self.HEADER)
                self.is_logging = True
                self._write_unlocked(
                    event="session_start",
                    severity="info",
                    message="Logging started",
                )
                print(f"Started status logging to: {self.csv_file}")
                return True
            except Exception as e:
                print(f"Error starting status logging: {e}")
                self._reset_unlocked()
                return False

    def log(
        self,
        event: str,
        *,
        severity: str = "info",
        previous_state: Any = None,
        state: Any = None,
        fault_code: Any = None,
        message: str = "",
    ) -> None:
        """Append one event row (no-op when logging is not active)."""
        with self._lock:
            self._write_unlocked(
                event=event,
                severity=severity,
                previous_state=previous_state,
                state=state,
                fault_code=fault_code,
                message=message,
            )

    def log_state_change(
        self,
        previous_state: Any,
        state: Any,
        reason: str = "",
        *,
        fault_code: Any = None,
    ) -> None:
        """Log a state-machine transition; ERROR entries are tagged as errors."""
        is_error = self._state_value(state).lower() == "error"
        self.log(
            event="error" if is_error else "state_change",
            severity="stop" if is_error else "info",
            previous_state=previous_state,
            state=state,
            fault_code=fault_code,
            message=reason,
        )

    def log_warning(
        self,
        fault_code: Any,
        message: str,
        *,
        state: Any = None,
        cleared: bool = False,
    ) -> None:
        self.log(
            event="warning_cleared" if cleared else "warning",
            severity="message",
            state=state,
            fault_code=fault_code,
            message=message,
        )

    def log_session_stop(self, *, state: Any = None, message: str = "Session ended") -> None:
        self.log(
            event="session_stop",
            severity="info",
            state=state,
            previous_state=state,
            message=message,
        )

    def stop_logging(self) -> None:
        """Close the active CSV file (no-op if not logging)."""
        with self._lock:
            if not self.is_logging:
                return
            try:
                if self.file_handle:
                    self.file_handle.flush()
                    self.file_handle.close()
                    print(f"Stopped status logging. File saved: {self.csv_file}")
            except Exception as e:
                print(f"Error stopping status logging: {e}")
            finally:
                self._reset_unlocked()

    def get_log_file_path(self) -> Optional[str]:
        with self._lock:
            return str(self.csv_file) if self.csv_file else None

    def _write_unlocked(
        self,
        *,
        event: str,
        severity: str = "info",
        previous_state: Any = None,
        state: Any = None,
        fault_code: Any = None,
        message: str = "",
    ) -> None:
        if not self.is_logging or self.csv_writer is None or self.file_handle is None:
            return
        try:
            self.csv_writer.writerow(
                [
                    datetime.now().isoformat(),
                    event,
                    severity,
                    self._state_value(previous_state),
                    self._state_value(state),
                    self._code_value(fault_code),
                    message or "",
                ]
            )
            self.file_handle.flush()
        except Exception as e:
            print(f"Error logging status event: {e}")

    def _reset_unlocked(self) -> None:
        self.is_logging = False
        self.csv_writer = None
        self.file_handle = None

    @staticmethod
    def _state_value(state: Any) -> str:
        if state is None:
            return ""
        return str(getattr(state, "value", state))

    @staticmethod
    def _code_value(code: Any) -> str:
        if code is None:
            return ""
        return str(getattr(code, "value", code))

    def __del__(self):
        try:
            self.stop_logging()
        except Exception:
            pass
