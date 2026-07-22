"""Fast pressure-only CSV logger.

Writes timestamp + psi columns with buffered I/O (no per-row flush) so the
10 Hz IO tick is not blocked by disk sync. A new timestamped file is created
on every ``start_logging()`` call.
"""

from __future__ import annotations

import csv
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class PressureCSVLogger:
    """Append pressure samples to a dedicated CSV file while capture is on."""

    # Flush every N rows so a crash loses at most a short burst, without
    # paying fsync cost on every 10 Hz sample.
    _FLUSH_EVERY_N_ROWS = 10

    def __init__(self, config: dict):
        logging_cfg = config.get("logging", {})
        self.csv_directory = str(
            logging_cfg.get(
                "pressure_csv_directory",
                logging_cfg.get("csv_directory", "data/csv"),
            )
        )
        self.filename_format = str(
            logging_cfg.get(
                "pressure_filename_format",
                "pressure_log_%Y%m%d_%H%M%S.csv",
            )
        )
        self.pressure_columns = self._pressure_columns_from_config(config)
        self.header = self._build_header(self.pressure_columns)

        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False
        self._rows_since_flush = 0
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
        header = ["timestamp"]
        for name in pressure_columns:
            header.append(f"{self._csv_slug(name)}_psi")
        return header

    def _next_csv_path(self) -> Path:
        """Return a unique path under ``csv_directory`` for a new capture file."""
        candidate = Path(self.csv_directory) / datetime.now().strftime(
            self.filename_format
        )
        if not candidate.exists():
            return candidate
        # Same-second restarts: keep the format stem and add a numeric suffix.
        stem = candidate.stem
        suffix = candidate.suffix
        for index in range(1, 1000):
            alt = candidate.with_name(f"{stem}_{index}{suffix}")
            if not alt.exists():
                return alt
        return Path(self.csv_directory) / (
            f"{stem}_{datetime.now().strftime('%f')}{suffix}"
        )

    def start_logging(self) -> bool:
        """Start logging to a new CSV file. Returns True on success.

        If logging is already active, the current file is closed first so each
        ON toggle always creates a fresh file.
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
                print(f"Started pressure logging to: {self.csv_file}")
                return True
            except Exception as e:
                print(f"Error starting pressure logging: {e}")
                self._reset_unlocked()
                return False

    def log(self, pressures: Optional[dict] = None) -> None:
        """Append one pressure row (no-op when capture is off)."""
        with self._lock:
            if not self.is_logging or self.csv_writer is None or self.file_handle is None:
                return

            try:
                pressures = pressures or {}
                row: list = [datetime.now().isoformat()]
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
