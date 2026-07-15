"""CSV data logger for temperature, actuators, and pressure readings."""

import csv
import math
from datetime import datetime
from pathlib import Path
from typing import Optional


class CSVLogger:
    """Append sensor + temperature + pressure samples to a timestamped CSV file."""

    def __init__(self, config: dict):
        self.csv_directory = config['logging']['csv_directory']
        self.filename_format = config['logging']['filename_format']
        self.thermocouple_columns = self._thermocouple_columns_from_config(config)
        self.pressure_columns = self._pressure_columns_from_config(config)
        # Linear pump model: flow_ml_per_s = rpm * slope / 60.
        self.pump_flow_ml_per_min_per_rpm = float(
            config.get('pump_flow_ml_per_min_per_rpm', 0.7823)
        )
        self.header = self._build_header(
            self.thermocouple_columns, self.pressure_columns
        )

        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False

        Path(self.csv_directory).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _thermocouple_columns_from_config(config: dict) -> list[str]:
        from sensor_injection import thermocouple_labels_from_config

        return thermocouple_labels_from_config(config)

    @staticmethod
    def _pressure_columns_from_config(config: dict) -> list[str]:
        from sensor_injection import pressure_labels_from_config

        return pressure_labels_from_config(config)

    @staticmethod
    def _csv_slug(label: str) -> str:
        slug = "".join(c.lower() if c.isalnum() else "_" for c in label).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug or "temp"

    def _build_header(
        self, thermocouple_columns: list[str], pressure_columns: list[str]
    ) -> list[str]:
        header = ['timestamp']
        for name in thermocouple_columns:
            header.append(f"{self._csv_slug(name)}_c")
        header.append('set_temperature_c')
        header.append('peristaltic_pump_set_speed_rpm')
        header.append('pump_flow_ml_per_s')
        header.append('compressor_cooling')
        for name in pressure_columns:
            header.append(f"{self._csv_slug(name)}_psi")
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

    def log(
        self,
        sensor_states: dict,
        temperatures: Optional[dict] = None,
        peristaltic_pump_set_speed_rpm: Optional[float] = None,
        set_temperature_c: Optional[float] = None,
        compressor_cooling: Optional[int] = None,
        thermistor_temperatures: Optional[dict] = None,
        pressures: Optional[dict] = None,
    ):
        """Append a single row with temperature, actuators, and pressures.

        ``sensor_states`` is accepted for backwards compatibility but is no
        longer logged — the cartridge level digital sensors are tracked in
        the conditions registry instead.
        ``peristaltic_pump_set_speed_rpm`` is the latest stepper setpoint
        (the peristaltic pump is driven by the stepper).
        ``set_temperature_c`` is the user-selected target temperature.
        ``compressor_cooling`` is 1 when the compressor relay is on (cooling),
        0 when off (idle).
        Thermistors are accepted for API compatibility but not logged yet.
        ``pressures`` maps label → psi (logged to two decimal places).
        """
        del sensor_states  # not logged anymore; kept for API compatibility
        del thermistor_temperatures  # not logged yet
        if not self.is_logging:
            return

        try:
            timestamp = datetime.now().isoformat()
            temperatures = temperatures or {}
            pressures = pressures or {}
            row: list = [timestamp]
            for column in self.thermocouple_columns:
                value = temperatures.get(column)
                row.append(f"{float(value):.3f}" if value is not None else "")
            row.append(
                f"{float(set_temperature_c):.3f}"
                if set_temperature_c is not None
                else ""
            )
            row.append(
                f"{float(peristaltic_pump_set_speed_rpm):.2f}"
                if peristaltic_pump_set_speed_rpm is not None
                else ""
            )
            if peristaltic_pump_set_speed_rpm is not None:
                flow_ml_per_s = (
                    float(peristaltic_pump_set_speed_rpm)
                    * self.pump_flow_ml_per_min_per_rpm
                    / 60.0
                )
                row.append(f"{flow_ml_per_s:.4f}")
            else:
                row.append("")
            row.append(
                int(compressor_cooling)
                if compressor_cooling is not None
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
        sample_temps = {}
        for idx, name in enumerate(logger.thermocouple_columns):
            sample_temps[name] = 22.0 + i * 0.1 + idx
        sample_pressures = {
            name: 10.0 + i + idx * 0.1
            for idx, name in enumerate(logger.pressure_columns)
        }
        logger.log(
            sensor_states={},
            temperatures=sample_temps,
            peristaltic_pump_set_speed_rpm=30 + i,
            set_temperature_c=33.0,
            compressor_cooling=i % 2,
            pressures=sample_pressures,
        )
        time.sleep(0.1)

    print(f"Log file size: {logger.get_log_file_size()} bytes")
    logger.stop_logging()
    print("Test complete!")
