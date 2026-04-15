import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

THERMAL_ZONE_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
REFRESH_MS = 3000


def read_cpu_temperature() -> tuple[float | None, str]:
    """Read Raspberry Pi CPU temperature in degrees Celsius."""
    if THERMAL_ZONE_PATH.exists():
        try:
            raw_value = THERMAL_ZONE_PATH.read_text().strip()
            return int(raw_value) / 1000.0, "Read from /sys/class/thermal/thermal_zone0/temp"
        except (ValueError, OSError):
            return None, "Unable to parse CPU temperature"

    return None, "Thermal sensor file not found"


class CpuTempWindow(QMainWindow):
    """Main window showing Raspberry Pi CPU temperature."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Raspberry Pi CPU Temperature")
        self.setMinimumSize(360, 160)
        self._build_ui()
        self._refresh_temperature()

    def _build_ui(self) -> None:
        self.temperature_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.temperature_label.setStyleSheet("font-size: 42px; font-weight: bold;")

        self.status_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: gray;")

        layout = QVBoxLayout()
        layout.addWidget(self.temperature_label)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        timer = QTimer(self)
        timer.timeout.connect(self._refresh_temperature)
        timer.start(REFRESH_MS)

    def _refresh_temperature(self) -> None:
        temp_c, message = read_cpu_temperature()
        if temp_c is None:
            self.temperature_label.setText("CPU temperature unavailable")
            self.temperature_label.setStyleSheet("font-size: 24px; color: red;")
        else:
            self.temperature_label.setText(f"{temp_c:.1f} °C")
            self.temperature_label.setStyleSheet(
                "font-size: 48px; font-weight: bold; color: darkgreen;"
            )

        self.status_label.setText(f"{datetime.now():%Y-%m-%d %H:%M:%S} · {message}")


def main() -> int:
    app = QApplication(sys.argv)
    window = CpuTempWindow()
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
