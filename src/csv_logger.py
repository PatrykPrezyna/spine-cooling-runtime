"""CSV data logger for digital sensor states and thermocouple readings."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional


class CSVLogger:
    """Append sensor + thermocouple samples to a timestamped CSV file."""

    def __init__(self, config: dict):
        self.csv_directory = config['logging']['csv_directory']
        self.filename_format = config['logging']['filename_format']
        self.temperature_columns = self._temperature_columns_from_config(config)
        self.header = self._build_header(self.temperature_columns)

        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False

        Path(self.csv_directory).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _temperature_columns_from_config(config: dict) -> list[str]:
        tc_cfg = config.get("thermocouples", {})
        channels = tc_cfg.get("channels", [])
        raw_labels = tc_cfg.get("labels", {})
        labels = {}
        for key, value in raw_labels.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        columns: list[str] = []
        for channel in channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            columns.append(str(labels.get(ch, f"Temp {ch}")))
        return columns

    @staticmethod
    def _csv_slug(label: str) -> str:
        slug = "".join(c.lower() if c.isalnum() else "_" for c in label).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug or "temp"

    def _build_header(self, temperature_columns: list[str]) -> list[str]:
        header = [
            'timestamp',
            'level_low',
            'level_critical',
            'cartridge_in_place',
        ]
        for name in temperature_columns:
            header.append(f"{self._csv_slug(name)}_c")
        return header

    def start_logging(self) -> bool:
        """Start logging to a new CSV file. Returns True on success."""
        if self.is_logging:
            print("Warning: Logging already active")
            return False

        try:
            timestamp = datetime.now().strftime(self.filename_format)
            self.csv_file = Path(self.csv_directory) / timestamp

            self.file_handle = open(self.csv_file, 'w', newline='')
            self.csv_writer = csv.writer(self.file_handle)
            self.csv_writer.writerow(self.header)
            self.file_handle.flush()

            self.is_logging = True
            print(f"Started logging to: {self.csv_file}")
            return True
        except Exception as e:
            print(f"Error starting logging: {e}")
            self.is_logging = False
            return False

    def log(self, sensor_states: dict, temperatures: Optional[dict] = None):
        """Append a single row with the current sensor + temperature state."""
        if not self.is_logging:
            return

        try:
            timestamp = datetime.now().isoformat()
            level_low = 1 if sensor_states.get('Level Low', False) else 0
            level_critical = 1 if sensor_states.get('Level Critical', False) else 0
            cartridge = 1 if sensor_states.get('Cartridge In Place', False) else 0

            temperatures = temperatures or {}
            row = [timestamp, level_low, level_critical, cartridge]
            for column in self.temperature_columns:
                value = temperatures.get(column)
                row.append(f"{float(value):.3f}" if value is not None else "")

            self.csv_writer.writerow(row)
            self.file_handle.flush()
        except Exception as e:
            print(f"Error logging data: {e}")

    def stop_logging(self):
        """Close the active CSV file (no-op if not logging)."""
        if not self.is_logging:
            return

        try:
            if self.file_handle:
                self.file_handle.close()
                print(f"Stopped logging. File saved: {self.csv_file}")
        except Exception as e:
            print(f"Error stopping logging: {e}")
        finally:
            self.is_logging = False
            self.csv_writer = None
            self.file_handle = None

    def get_log_file_path(self) -> Optional[str]:
        return str(self.csv_file) if self.csv_file else None

    def get_log_file_size(self) -> int:
        if self.csv_file and self.csv_file.exists():
            return self.csv_file.stat().st_size
        return 0

    def __del__(self):
        try:
            self.stop_logging()
        except Exception:
            # Avoid destructor-time exceptions during interpreter shutdown.
            pass


if __name__ == "__main__":
    import time
    import yaml

    print("Testing CSVLogger...")
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    logger = CSVLogger(config)
    logger.start_logging()
    print(f"Log file: {logger.get_log_file_path()}")

    for i in range(10):
        state = i % 2 == 0
        sample_temps = {}
        for idx, name in enumerate(logger.temperature_columns):
            sample_temps[name] = 22.0 + i * 0.1 + idx
        logger.log(
            {
                "Level Low": state,
                "Level Critical": not state,
                "Cartridge In Place": True,
            },
            sample_temps,
        )
        time.sleep(0.5)

    print(f"Log file size: {logger.get_log_file_size()} bytes")
    logger.stop_logging()
    print("Test complete!")
