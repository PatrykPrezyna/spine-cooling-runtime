import csv
import logging
import queue
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import AppConfig
from .sensor_manager import SensorSample


class DataLogger(threading.Thread):
    """Persist sensor samples to SQLite and rotating CSV files."""

    def __init__(
        self,
        config: AppConfig,
        record_queue: queue.Queue,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="DataLogger")
        self.config = config
        self.record_queue = record_queue
        self.stop_event = stop_event
        self.db_path = config.db_path
        self.csv_folder = config.csv_folder
        self.rotate_size = int(config.app.get("csv_rotate_size_mb", 5)) * 1024 * 1024
        self.rotate_count = int(config.app.get("csv_rotate_count", 5))
        self.csv_file: Optional[Path] = None
        self.csv_handle = None
        self.csv_writer = None
        self.logger = logging.getLogger(__name__)
        self._initialize_storage()

    def _initialize_storage(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_folder.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
        self._open_csv_file()

    def _initialize_database(self) -> None:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS temperature_log (
                    timestamp TEXT PRIMARY KEY,
                    sensor0 REAL,
                    sensor1 REAL,
                    sensor2 REAL,
                    sensor3 REAL,
                    sensor4 REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_temperature_timestamp ON temperature_log(timestamp)"
            )
            conn.commit()
        finally:
            conn.close()

    def _open_csv_file(self) -> None:
        self.csv_file = self.csv_folder / f"temps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.csv_handle = self.csv_file.open("w", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(
            self.csv_handle,
            fieldnames=["timestamp", "sensor0", "sensor1", "sensor2", "sensor3", "sensor4"],
        )
        self.csv_writer.writeheader()
        self.csv_handle.flush()
        self.logger.info("Opened CSV log file %s", self.csv_file)

    def _maybe_rotate_csv(self) -> None:
        if self.csv_file is None:
            return
        if self.csv_file.stat().st_size < self.rotate_size:
            return
        self.logger.info("Rotating CSV file %s", self.csv_file)
        self.csv_handle.close()
        archived = self.csv_file.with_suffix(".old.csv")
        self.csv_file.rename(archived)
        self._prune_csv_files()
        self._open_csv_file()

    def _prune_csv_files(self) -> None:
        candidates = sorted(self.csv_folder.glob("temps_*.csv"), reverse=True)
        for old_file in candidates[self.rotate_count :]:
            try:
                old_file.unlink()
            except OSError:
                self.logger.warning("Unable to remove old CSV file %s", old_file)

    def run(self) -> None:
        self.logger.info("Data logger starting")
        while not self.stop_event.is_set():
            try:
                sample = self.record_queue.get(timeout=self.config.logger_poll_interval)
            except queue.Empty:
                continue
            self._record_sample(sample)
        self._shutdown()

    def _record_sample(self, sample: SensorSample) -> None:
        self._write_database(sample)
        self._write_csv(sample)

    def _write_database(self, sample: SensorSample) -> None:
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                "INSERT OR REPLACE INTO temperature_log (timestamp, sensor0, sensor1, sensor2, sensor3, sensor4)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sample.timestamp,
                    sample.values[0],
                    sample.values[1],
                    sample.values[2],
                    sample.values[3],
                    sample.values[4],
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            self.logger.exception("Failed to write sample to SQLite: %s", exc)
        finally:
            conn.close()

    def _write_csv(self, sample: SensorSample) -> None:
        try:
            self.csv_writer.writerow(
                {
                    "timestamp": sample.timestamp,
                    "sensor0": sample.values[0],
                    "sensor1": sample.values[1],
                    "sensor2": sample.values[2],
                    "sensor3": sample.values[3],
                    "sensor4": sample.values[4],
                }
            )
            self.csv_handle.flush()
            self._maybe_rotate_csv()
        except Exception as exc:
            self.logger.exception("Failed to write sample to CSV: %s", exc)

    def query_history(self, start_iso: str, end_iso: str) -> list[tuple[str, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            cursor = conn.execute(
                "SELECT timestamp, sensor0, sensor1, sensor2, sensor3, sensor4 "
                "FROM temperature_log WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
                (start_iso, end_iso),
            )
            return cursor.fetchall()
        except sqlite3.Error as exc:
            self.logger.exception("History query failed: %s", exc)
            return []
        finally:
            conn.close()

    def _shutdown(self) -> None:
        self.logger.info("Data logger shutting down")
        try:
            if self.csv_handle:
                self.csv_handle.close()
        except Exception:
            pass
