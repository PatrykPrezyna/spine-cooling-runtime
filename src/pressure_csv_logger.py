"""Fast pressure-only CSV logger with a dedicated capture thread.

A background loop reads pressures and appends CSV rows at
``pressure_sensors.capture_rate_hz`` (default 100 Hz) for the whole session.

``start_logging()`` opens ``<session>_pressure_100Hz.csv`` in the shared
``logs`` folder. If capture is restarted in the same session, later files
are ``<session>_pressure_100Hz_run02.csv``, ``_run03``, … Pairing with the
sensor and status files is a string match on the shared session stamp.
"""

from __future__ import annotations

import csv
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from session_log_paths import log_directory, pressure_filename_format


class PressureCSVLogger:
    """Append pressure samples to a dedicated CSV file while capture is on."""

    # Flush every N rows so a crash loses at most a short burst, without
    # paying fsync cost on every high-rate sample.
    _FLUSH_EVERY_N_ROWS = 50

    def __init__(self, config: dict, session_start: Optional[datetime] = None):
        ps_cfg = config.get("pressure_sensors", {}) or {}
        self.csv_directory = log_directory(config, "pressure_csv_directory")
        self.filename_format = pressure_filename_format(config)
        self.capture_rate_hz = max(
            1.0, float(ps_cfg.get("capture_rate_hz", 100.0))
        )
        self.pressure_columns = self._pressure_columns_from_config(config)
        self.header = self._build_header(self.pressure_columns)
        # Shared with CSVLogger so every capture is traceable to its session.
        self.session_start = session_start or datetime.now()

        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False
        self._rows_since_flush = 0
        self._run_index = 0
        self._lock = threading.Lock()

        Path(self.csv_directory).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _pressure_columns_from_config(config: dict) -> list[str]:
        from sensor_injection import pressure_labels_from_config

        return pressure_labels_from_config(config)

    @staticmethod
    def _csv_slug(label: str) -> str:
        slug = "".join(c.lower() if c.isalnum() else "_" for c in label).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug or "pressure"

    def _build_header(self, pressure_columns: list[str]) -> list[str]:
        header = ["timestamp", "peristaltic_pump_set_speed_rpm"]
        for name in pressure_columns:
            header.append(f"{self._csv_slug(name)}_bar")
        return header

    def _next_csv_path(self) -> Path:
        """Return the next path for the current session.

        The first capture of a session uses ``<stamp>_pressure_100Hz.csv``.
        Later restarts add ``_run02``, ``_run03``, … so earlier files are kept
        and still pair with the sensor/status CSVs by stamp.
        """
        base = Path(self.csv_directory) / self.session_start.strftime(
            self.filename_format
        )
        if self._run_index == 0 and not base.exists():
            self._run_index = 1
            return base
        start = 2 if self._run_index < 2 else self._run_index + 1
        for index in range(start, 1000):
            candidate = base.with_name(f"{base.stem}_run{index:02d}{base.suffix}")
            if not candidate.exists():
                self._run_index = index
                return candidate
        # Exhausted the run counter; fall back to a unique time-based suffix.
        return base.with_name(
            f"{base.stem}_run{datetime.now().strftime('%H%M%S%f')}{base.suffix}"
        )

    def start_logging(self) -> bool:
        """Start logging to a new CSV file. Returns True on success.

        If logging is already active, the current file is closed first so a
        restart always creates a fresh file.
        """
        with self._lock:
            if self.is_logging:
                self._stop_unlocked()

            try:
                self.csv_file = self._next_csv_path()
                # Large buffer; we flush periodically / on stop.
                self.file_handle = open(
                    self.csv_file, "w", newline="", buffering=64 * 1024
                )
                self.csv_writer = csv.writer(self.file_handle)
                self.csv_writer.writerow(self.header)
                self.file_handle.flush()
                self._rows_since_flush = 0
                self.is_logging = True
                print(
                    f"Started pressure logging "
                    f"({self.capture_rate_hz:.0f} Hz) to: {self.csv_file}"
                )
                return True
            except Exception as e:
                print(f"Error starting pressure logging: {e}")
                self._reset_unlocked()
                return False

    def log(
        self,
        pressures: Optional[dict] = None,
        peristaltic_pump_set_speed_rpm: Optional[float] = None,
    ) -> None:
        """Append one pressure row (no-op when capture is not running).

        ``peristaltic_pump_set_speed_rpm`` is the latest stepper setpoint
        (0 when the pump is not running), matching the session CSV column.
        """
        with self._lock:
            if not self.is_logging or self.csv_writer is None or self.file_handle is None:
                return

            try:
                pressures = pressures or {}
                row: list = [datetime.now().isoformat()]
                row.append(
                    f"{float(peristaltic_pump_set_speed_rpm):.2f}"
                    if peristaltic_pump_set_speed_rpm is not None
                    else ""
                )
                for column in self.pressure_columns:
                    value = pressures.get(column)
                    if value is None or (
                        isinstance(value, float) and math.isnan(value)
                    ):
                        row.append("")
                    else:
                        row.append(f"{float(value):.2f}")
                self.csv_writer.writerow(row)
                self._rows_since_flush += 1
                if self._rows_since_flush >= self._FLUSH_EVERY_N_ROWS:
                    self.file_handle.flush()
                    self._rows_since_flush = 0
            except Exception as e:
                print(f"Error logging pressure data: {e}")

    def stop_logging(self) -> None:
        """Close the active CSV file (no-op if not logging)."""
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        if not self.is_logging:
            return
        try:
            if self.file_handle:
                self.file_handle.flush()
                self.file_handle.close()
                print(f"Stopped pressure logging. File saved: {self.csv_file}")
        except Exception as e:
            print(f"Error stopping pressure logging: {e}")
        finally:
            self._reset_unlocked()

    def _reset_unlocked(self) -> None:
        self.is_logging = False
        self.csv_writer = None
        self.file_handle = None
        self._rows_since_flush = 0

    def get_log_file_path(self) -> Optional[str]:
        with self._lock:
            return str(self.csv_file) if self.csv_file else None

    def __del__(self):
        try:
            self.stop_logging()
        except Exception:
            pass


class PressureCaptureLoop:
    """Background read+log loop at ``capture_rate_hz`` for the session."""

    def __init__(
        self,
        pressure_reader: Any,
        logger: PressureCSVLogger,
        rate_hz: Optional[float] = None,
        pump_set_speed_rpm_getter: Optional[Callable[[], float]] = None,
    ):
        self._pressure_reader = pressure_reader
        self._logger = logger
        self._pump_set_speed_rpm_getter = pump_set_speed_rpm_getter
        self._rate_hz = max(
            1.0, float(rate_hz if rate_hz is not None else logger.capture_rate_hz)
        )
        self._interval_s = 1.0 / self._rate_hz
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the capture thread (no-op if already running)."""
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="pressure_capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the capture thread and wait briefly for it to exit."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        next_t = time.perf_counter()
        while not self._stop.is_set():
            try:
                if self._pressure_reader is not None:
                    pressures = self._pressure_reader.read_pressures()
                else:
                    pressures = {}
                pump_speed: Optional[float] = None
                if self._pump_set_speed_rpm_getter is not None:
                    pump_speed = float(self._pump_set_speed_rpm_getter())
                self._logger.log(
                    pressures,
                    peristaltic_pump_set_speed_rpm=pump_speed,
                )
            except Exception as exc:
                print(f"Pressure capture loop error: {exc}")

            next_t += self._interval_s
            delay = next_t - time.perf_counter()
            if delay > 0:
                if self._stop.wait(delay):
                    break
            else:
                # Fell behind (I2C / disk); resync so we don't busy-spin catch-up.
                next_t = time.perf_counter()
