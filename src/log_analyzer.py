"""Expert-view log analyzer for spine-cooling session CSVs.

Open a ``*_sensors.csv`` (or the folder that contains the three session
files) to replay Temperature, Pressure and Flow, Power, and Status using
the same widgets as the runtime expert page.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui import (
    DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM,
    PowerGraphTab,
    PressureServiceTab,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    ServiceTab,
    TemperatureGraphTab,
    _HEADER_ICON_BUTTON_STYLE,
    _PAGE_TAB_BAR_STYLE,
    _header_fullscreen_icon,
    _header_restore_window_icon,
)
from session_logs import SessionData, load_session, series_stats

_HISTORY_SEC = 48 * 3600
_DEFAULT_TEMP_NAMES = [
    "Tip",
    "Cartrige Out",
    "Catheter In",
    "Catheter Out",
    "Cartrige In",
    "Plate 1",
    "Plate 2",
    "Body Temp",
    "Hot bath1",
    "Hot bath2",
    "Ice Water",
    "Probe 4",
]
_DEFAULT_PRESSURE_NAMES = ["Pump In", "Pump Out", "Catheter In", "Catheter Out"]


def _header_folder_icon(size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#51606c"))
    tab = QRectF(size * 0.14, size * 0.18, size * 0.32, size * 0.16)
    painter.drawRoundedRect(tab, size * 0.04, size * 0.04)
    painter.drawRoundedRect(
        QRectF(size * 0.12, size * 0.30, size * 0.76, size * 0.54),
        size * 0.08,
        size * 0.08,
    )
    painter.setPen(QPen(QColor("#eef2f5"), max(1.0, size * 0.07)))
    painter.drawLine(
        int(size * 0.22), int(size * 0.52), int(size * 0.78), int(size * 0.52)
    )
    painter.end()
    return QIcon(pixmap)


def _status_chip_style(bg_color: str, border_color: str, text_color: str) -> str:
    return f"""
        QLabel {{
            background-color: {bg_color};
            color: {text_color};
            font-size: 12px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 10px;
            border: 1px solid {border_color};
        }}
    """


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_default_session() -> Optional[Path]:
    roots = [
        application_dir(),
        application_dir() / "evaluation tool",
        Path.cwd(),
        Path.cwd() / "evaluation tool",
    ]
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        matches = sorted(resolved.glob("*_sensors.csv"))
        if matches:
            return matches[-1]
    return None


def _format_clock(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _format_number(value: float, fmt: str) -> str:
    if value is None or math.isnan(value):
        return "--"
    return fmt.format(value)


class SessionStatusTab(QWidget):
    """Status tab: session summary, min/max, and the event log."""

    def __init__(self):
        super().__init__()
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self.summary_group = QGroupBox("Session")
        self.summary_group.setStyleSheet(
            ServiceTab._group_box_style("#0e6a76", "10px", margin_top=6)
        )
        self.duration_label = QLabel("Duration: --")
        self.samples_label = QLabel("Samples: --")
        self.setpoint_label = QLabel("Set temperature: --")
        self.flow_label = QLabel("Peak flow: --")
        for label in (
            self.duration_label,
            self.samples_label,
            self.setpoint_label,
            self.flow_label,
        ):
            label.setStyleSheet(
                "font-size: 12px; padding: 6px; color: #245962; font-weight: 600;"
            )

        self.stats_group = QGroupBox("Min / max")
        self.stats_group.setStyleSheet(
            ServiceTab._group_box_style("#3b82f6", "10px", margin_top=6)
        )
        self.stats_table = QTableWidget(0, 4)
        self.stats_table.setHorizontalHeaderLabels(["Signal", "Min", "Max", "Mean"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3):
            self.stats_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

        self.events_group = QGroupBox("Events")
        self.events_group.setStyleSheet(
            ServiceTab._group_box_style("#3b82f6", "10px", margin_top=6)
        )
        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels(
            ["Time", "Event", "State", "Message"]
        )
        self.events_table.verticalHeader().setVisible(False)
        self.events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.events_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.events_table.setAlternatingRowColors(True)
        self.events_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        for column in (0, 1, 2):
            self.events_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

    def _setup_layout(self) -> None:
        summary_row = QHBoxLayout()
        summary_row.addWidget(self.duration_label)
        summary_row.addWidget(self.samples_label)
        summary_row.addWidget(self.setpoint_label)
        summary_row.addWidget(self.flow_label)
        self.summary_group.setLayout(summary_row)

        stats_layout = QVBoxLayout()
        stats_layout.setContentsMargins(8, 10, 8, 8)
        stats_layout.addWidget(self.stats_table)
        self.stats_group.setLayout(stats_layout)

        events_layout = QVBoxLayout()
        events_layout.setContentsMargins(8, 10, 8, 8)
        events_layout.addWidget(self.events_table)
        self.events_group.setLayout(events_layout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self.summary_group)
        layout.addWidget(self.stats_group, 1)
        layout.addWidget(self.events_group, 1)

    def show_session(self, session: SessionData) -> None:
        minutes = session.duration_minutes
        self.duration_label.setText(f"Duration: {minutes:.1f} min")
        self.samples_label.setText(
            f"Samples: {len(session.temperature_samples)} temp  ·  "
            f"{len(session.pressure_samples)} pressure"
        )
        self.setpoint_label.setText(
            "Set temperature: "
            + (
                f"{session.set_temperature_c:.1f} °C"
                if session.set_temperature_c is not None
                else "--"
            )
        )
        flow_stats = series_stats(session.pressure_samples, "Flow")
        self.flow_label.setText(
            f"Peak flow: {_format_number(flow_stats['max'], '{:.0f}')} ml/min"
        )

        rows: list[tuple[str, dict[str, float], str]] = []
        for name in session.temperature_names:
            rows.append((name, series_stats(session.temperature_samples, name), "{:.1f}"))
        for name in session.pressure_names:
            rows.append((name, series_stats(session.pressure_samples, name), "{:.2f}"))
        rows.append(("Flow", series_stats(session.pressure_samples, "Flow"), "{:.0f}"))
        rows.append(("Catheter", series_stats(session.power_samples, "Catheter"), "{:.1f}"))
        rows.append(("Cartridge", series_stats(session.power_samples, "Cartridge"), "{:.1f}"))

        self.stats_table.setRowCount(len(rows))
        for index, (name, stats, fmt) in enumerate(rows):
            unit = "°C" if name in session.temperature_names else (
                "ml/min" if name == "Flow" else ("W" if name in ("Catheter", "Cartridge") else "bar")
            )
            self.stats_table.setItem(index, 0, QTableWidgetItem(f"{name} ({unit})"))
            self.stats_table.setItem(
                index, 1, QTableWidgetItem(_format_number(stats["min"], fmt))
            )
            self.stats_table.setItem(
                index, 2, QTableWidgetItem(_format_number(stats["max"], fmt))
            )
            self.stats_table.setItem(
                index, 3, QTableWidgetItem(_format_number(stats["mean"], fmt))
            )

        self.events_table.setRowCount(len(session.events))
        for index, event in enumerate(session.events):
            self.events_table.setItem(index, 0, QTableWidgetItem(_format_clock(event.timestamp)))
            self.events_table.setItem(index, 1, QTableWidgetItem(event.event))
            self.events_table.setItem(index, 2, QTableWidgetItem(event.state))
            self.events_table.setItem(index, 3, QTableWidgetItem(event.message))


class LogAnalyzerWindow(QMainWindow):
    """Desktop viewer that mirrors the runtime expert page."""

    def __init__(self):
        super().__init__()
        self.session: Optional[SessionData] = None
        self.setWindowTitle("Spine Cooling — Log Viewer")
        self.setMinimumSize(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.resize(960, 620)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #eef2f5;
                color: #1b2430;
                font-family: "Segoe UI";
                font-size: 12px;
            }
            QGroupBox {
                font-weight: 600;
                font-size: 12px;
                border: 1px solid #d7dfe6;
                border-radius: 14px;
                margin-top: 12px;
                padding-top: 12px;
                background: #f8fafb;
            }
            QTableWidget {
                background: white;
                border: 1px solid #d8e0e7;
                border-radius: 8px;
                gridline-color: #e5ebf0;
            }
            QHeaderView::section {
                background: #e5ebf0;
                color: #40505d;
                font-weight: 600;
                padding: 4px 8px;
                border: none;
            }
        """)
        self._create_widgets()
        self._setup_layout()
        self._show_empty_state()

    def _create_widgets(self) -> None:
        self.state_label = QLabel("State: Log")
        self.state_label.setMinimumHeight(32)
        self.state_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.state_label.setStyleSheet(
            _status_chip_style("#e9eef2", "#d6dde3", "#2f3b47")
        )

        self.hint_label = QLabel("Open a session CSV to review the experiment")
        self.hint_label.setMinimumHeight(32)
        self.hint_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.hint_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.hint_label.setStyleSheet(
            _status_chip_style("#e8f5e9", "#16a34a", "#166534")
        )

        self.session_timer_label = QLabel("0 min")
        self.session_timer_label.setMinimumHeight(32)
        self.session_timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.session_timer_label.setStyleSheet(
            _status_chip_style("#e9eef2", "#d6dde3", "#2f3b47")
        )

        self.open_button = QPushButton()
        self.open_button.setFixedSize(34, 34)
        self.open_button.setIcon(_header_folder_icon(20))
        self.open_button.setIconSize(QSize(20, 20))
        self.open_button.setToolTip("Open session CSV or folder")
        self.open_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)
        self.open_button.clicked.connect(self._choose_session)

        self.window_mode_toggle_button = QPushButton()
        self.window_mode_toggle_button.setFixedSize(34, 34)
        self.window_mode_toggle_button.setIconSize(QSize(20, 20))
        self.window_mode_toggle_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)
        self.window_mode_toggle_button.clicked.connect(self._toggle_window_mode)
        self._update_window_mode_toggle_button()

        self.temperature_tab = TemperatureGraphTab(list(_DEFAULT_TEMP_NAMES))
        self.pressure_tab = PressureServiceTab(
            pressure_sensor_names=list(_DEFAULT_PRESSURE_NAMES)
        )
        self.pressure_tab.pump_flow_ml_per_min_per_rpm = (
            DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        )
        self.power_tab = PowerGraphTab({})
        self.status_tab = SessionStatusTab()
        self._prepare_graph(self.temperature_tab)
        self._prepare_graph(self.pressure_tab)
        self._prepare_graph(self.power_tab)

        self.tab_selector = QTabBar()
        self.tab_selector.setExpanding(False)
        self.tab_selector.setStyleSheet(_PAGE_TAB_BAR_STYLE)
        self.content_stack = QStackedWidget()
        for title, widget in (
            ("Temperature", self.temperature_tab),
            ("Pressure and Flow", self.pressure_tab),
            ("Power", self.power_tab),
            ("Status", self.status_tab),
        ):
            self.tab_selector.addTab(title)
            self.content_stack.addWidget(widget)
        self.tab_selector.currentChanged.connect(self.content_stack.setCurrentIndex)

    def _setup_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        header.addWidget(self.state_label, 3)
        header.addWidget(self.hint_label, 7)
        header.addWidget(self.session_timer_label, 0)
        header.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignRight)
        header.addWidget(self.window_mode_toggle_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        expert = QWidget()
        expert_layout = QVBoxLayout(expert)
        expert_layout.setContentsMargins(0, 0, 0, 0)
        expert_layout.setSpacing(8)
        tab_row = QHBoxLayout()
        tab_row.addWidget(self.tab_selector, 1)
        expert_layout.addLayout(tab_row)
        expert_layout.addWidget(self.content_stack, 1)
        layout.addWidget(expert, 1)

    def _prepare_graph(self, tab: TemperatureGraphTab) -> None:
        tab.graph_widget.use_history_end_as_now = True
        tab.graph_widget._MAX_HISTORY_SEC = _HISTORY_SEC

    def _show_empty_state(self) -> None:
        self.state_label.setText("State: Log")
        self.state_label.setStyleSheet(
            _status_chip_style("#e9eef2", "#d6dde3", "#2f3b47")
        )
        self.hint_label.setText("Open a session CSV to review the experiment")
        self.session_timer_label.setText("0 min")

    def _choose_session(self) -> None:
        start = application_dir()
        sample = find_default_session()
        if sample is not None:
            start = sample.parent
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Open session log",
            str(start),
            "Session logs (*_sensors.csv *_pressure_100Hz.csv *_status_and_errors.csv);;CSV files (*.csv);;All files (*.*)",
        )
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path) -> None:
        try:
            session = load_session(path)
        except Exception as exc:
            QMessageBox.warning(self, "Could not open session", str(exc))
            return
        self._apply_session(session)

    def _apply_session(self, session: SessionData) -> None:
        self.session = session
        temp_names = session.temperature_names or list(_DEFAULT_TEMP_NAMES)
        pressure_names = session.pressure_names or list(_DEFAULT_PRESSURE_NAMES)

        self.temperature_tab = TemperatureGraphTab(temp_names)
        self.pressure_tab = PressureServiceTab(pressure_sensor_names=pressure_names)
        self.pressure_tab.pump_flow_ml_per_min_per_rpm = (
            DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        )
        self.power_tab = PowerGraphTab({"cooling_power": {}})
        self._prepare_graph(self.temperature_tab)
        self._prepare_graph(self.pressure_tab)
        self._prepare_graph(self.power_tab)

        self._replace_stack_widget(0, self.temperature_tab)
        self._replace_stack_widget(1, self.pressure_tab)
        self._replace_stack_widget(2, self.power_tab)
        self.content_stack.setCurrentIndex(self.tab_selector.currentIndex())

        self._load_graph(
            self.temperature_tab, session.temperature_samples, session.duration_s
        )
        self._load_pressure(session)
        self._load_graph(self.power_tab, session.power_samples, session.duration_s)
        self.status_tab.show_session(session)
        self._update_header(session)

    def _replace_stack_widget(self, index: int, widget: QWidget) -> None:
        old = self.content_stack.widget(index)
        self.content_stack.removeWidget(old)
        old.deleteLater()
        self.content_stack.insertWidget(index, widget)

    def _load_graph(
        self,
        tab: TemperatureGraphTab,
        samples: list[tuple[float, dict]],
        duration_s: float,
    ) -> None:
        tab.graph_widget.replace_history(samples)
        if samples:
            tab._update_checkbox_labels(samples[-1][1])
        self._fit_time_window(tab, duration_s)
        tab._update_nav_states()

    def _load_pressure(self, session: SessionData) -> None:
        tab = self.pressure_tab
        tab._samples.clear()
        for timestamp, values in session.pressure_samples:
            tab._samples.append((timestamp, dict(values)))
        tab._rebuild_graph()
        self._fit_time_window(tab, session.duration_s)

    def _fit_time_window(self, tab: TemperatureGraphTab, duration_s: float) -> None:
        options = list(tab.graph_widget._x_window_minutes_options)
        chosen = next(
            (option for option in options if option * 60 >= duration_s),
            options[-1],
        )
        tab.graph_window_combo.setCurrentIndex(options.index(chosen))

    def _update_header(self, session: SessionData) -> None:
        state = session.last_state
        self.state_label.setText(f"State: {state}")
        if state == "Error":
            colors = ("#f8e5db", "#d06a45", "#7e3f26")
        elif state in ("Init", "Ready", "Log"):
            colors = ("#e9eef2", "#d6dde3", "#2f3b47")
        else:
            colors = ("#dff0f2", "#8fc8cf", "#245962")
        self.state_label.setStyleSheet(_status_chip_style(*colors))

        started = ""
        if session.start_ts is not None:
            started = datetime.fromtimestamp(session.start_ts).strftime("%Y-%m-%d %H:%M")
        self.hint_label.setText(f"{session.stamp}   {started}".strip())
        self.hint_label.setStyleSheet(
            _status_chip_style("#e8f5e9", "#16a34a", "#166534")
        )
        self.session_timer_label.setText(f"{session.duration_minutes:.0f} min")

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._update_window_mode_toggle_button()

    def _update_window_mode_toggle_button(self) -> None:
        if self.isFullScreen():
            self.window_mode_toggle_button.setIcon(_header_restore_window_icon(20))
            self.window_mode_toggle_button.setToolTip("Exit fullscreen")
        else:
            self.window_mode_toggle_button.setIcon(_header_fullscreen_icon(20))
            self.window_mode_toggle_button.setToolTip("Enter fullscreen")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        self.load_path(Path(urls[0].toLocalFile()))


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication(args)
    app.setApplicationName("Spine Cooling Log Viewer")
    window = LogAnalyzerWindow()
    requested = Path(args[1]) if len(args) > 1 else find_default_session()
    if requested is not None:
        window.load_path(requested)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
