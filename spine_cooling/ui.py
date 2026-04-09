import logging
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtCore import QDate, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .sensor_manager import SensorSample


class LiveChartWidget(QWidget):
    """Live chart display for real-time sensor values."""

    def __init__(
        self,
        sensor_count: int,
        data_queue,
        update_interval_ms: int,
        status_callback: Optional[Callable[["SensorSample"], None]] = None,
    ) -> None:
        super().__init__()
        self.sensor_count = sensor_count
        self.data_queue = data_queue
        self.update_interval_ms = update_interval_ms
        self.status_callback = status_callback
        self.logger = logging.getLogger(__name__)
        self.series: List[QLineSeries] = []
        self.points: List[deque[tuple[float, float]]] = [deque(maxlen=200) for _ in range(sensor_count)]
        self.x_counter = 0.0

        self._build_ui()
        self._start_timer()

    def _build_ui(self) -> None:
        self.chart = QChart()
        self.chart.setTitle("Live Thermocouple Temperatures")
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        for index in range(self.sensor_count):
            series = QLineSeries()
            series.setName(f"Sensor {index}")
            self.chart.addSeries(series)
            self.series.append(series)

        self.x_axis = QValueAxis()
        self.x_axis.setLabelFormat("%g")
        self.x_axis.setTitleText("Samples")
        self.x_axis.setRange(0, 200)
        self.chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)

        self.y_axis = QValueAxis()
        self.y_axis.setLabelFormat("%.1f")
        self.y_axis.setTitleText("Temperature (°C)")
        self.y_axis.setRange(0, 120)
        self.chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)

        for series in self.series:
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(self.chart_view.renderHints())

        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        self.setLayout(layout)

    def _start_timer(self) -> None:
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(self.update_interval_ms)

    def _refresh(self) -> None:
        updated = False
        while not self.data_queue.empty():
            try:
                sample: SensorSample = self.data_queue.get_nowait()
            except Exception:
                break
            self._append_sample(sample)
            updated = True

        if updated:
            self._update_series()

    def _append_sample(self, sample: SensorSample) -> None:
        self.x_counter += 1.0
        for index, value in enumerate(sample.values):
            self.points[index].append((self.x_counter, value if value is not None else 0.0))

        if self.status_callback is not None:
            self.status_callback(sample)

    def _update_series(self) -> None:
        min_y = 0.0
        max_y = 1.0
        for index, series in enumerate(self.series):
            series.clear()
            points = self.points[index]
            for x, y in points:
                series.append(x, y)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
        self.y_axis.setRange(max(0.0, min_y - 5.0), max(120.0, max_y + 5.0))
        self.x_axis.setRange(max(0.0, self.x_counter - 200), self.x_counter)


class MainWindow(QMainWindow):
    """Main application window with live chart and history explorer."""

    def __init__(self, db_path: Path, live_queue, update_interval_ms: int) -> None:
        super().__init__()
        self.db_path = db_path
        self.live_queue = live_queue
        self.update_interval_ms = update_interval_ms
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Spine Cooling DAQ")
        self.setMinimumSize(1024, 600)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout()

        self.chart_widget = LiveChartWidget(
            sensor_count=5,
            data_queue=self.live_queue,
            update_interval_ms=self.update_interval_ms,
            status_callback=self.update_sensor_status,
        )
        root_layout.addWidget(self.chart_widget, stretch=4)

        indicator_layout = QHBoxLayout()
        self.status_labels = [QLabel(f"Sensor {i}: Unknown") for i in range(5)]
        for label in self.status_labels:
            label.setFont(QFont("Sans", 12))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            indicator_layout.addWidget(label)
        root_layout.addLayout(indicator_layout)

        history_layout = QGridLayout()
        history_layout.addWidget(QLabel("Start date"), 0, 0)
        history_layout.addWidget(QLabel("End date"), 0, 1)

        self.start_date = QDateEdit(QDate.currentDate().addDays(-1))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        history_layout.addWidget(self.start_date, 1, 0)
        history_layout.addWidget(self.end_date, 1, 1)

        self.query_button = QPushButton("Query History")
        self.query_button.clicked.connect(self._load_history)
        history_layout.addWidget(self.query_button, 1, 2)

        root_layout.addLayout(history_layout)

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["Timestamp", "Sensor0", "Sensor1", "Sensor2", "Sensor3", "Sensor4"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        root_layout.addWidget(self.history_table, stretch=2)

        root.setLayout(root_layout)
        self.setCentralWidget(root)

        self._connect_history_refresh()

    def _connect_history_refresh(self) -> None:
        refresh_timer = QTimer(self)
        refresh_timer.timeout.connect(self._load_history)
        refresh_timer.start(30_000)

    def _load_history(self) -> None:
        start_iso = datetime.combine(self.start_date.date().toPython(), datetime.min.time()).isoformat()
        end_iso = datetime.combine(self.end_date.date().toPython(), datetime.max.time()).isoformat()
        rows = self._query_history(start_iso, end_iso)
        self._populate_history(rows)

    def _query_history(self, start_iso: str, end_iso: str):
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
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

    def _populate_history(self, rows) -> None:
        self.history_table.clearContents()
        self.history_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.history_table.setItem(row_index, col_index, item)

    def update_sensor_status(self, sample: SensorSample) -> None:
        for index, value in enumerate(sample.values):
            label = self.status_labels[index]
            if value is None:
                label.setText(f"Sensor {index}: Error")
                label.setStyleSheet("color: red")
            else:
                label.setText(f"Sensor {index}: {value:.1f} °C")
                label.setStyleSheet("color: green")
