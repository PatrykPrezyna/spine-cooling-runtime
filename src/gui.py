"""
PyQt6 user interface for the Spine Cooling runtime.

Contains the main application window (`MainScreen`) and its primary
visualization/control widget (`MainScreenWidget`), plus the tab widgets used
by the two sub-pages.

`MainScreen` shows exactly one of three pages:

- Main: trend graph, CSF/setpoint readouts and the cooling action buttons
  (`MainScreenWidget`). Its only exit is the expert page.
- Expert: monitoring only — Temperature (`TemperatureGraphTab`), Pressure and
  Flow (`PressureServiceTab`), Power (`PowerGraphTab`), Status (`Service2Tab`).
- Service: acts on the hardware — Manual Operation (`ServiceTab`), Calibration
  (`CalibrationTab`). Only the expert tab row links to it, so it stays one
  step away from the main page.
"""

import math
import sys
import time
from collections import deque
from html import escape as _html_escape
from typing import Optional, Callable

from cooling_power import (
    CoolingPowerConfig,
    cartridge_cooling_power_w,
    catheter_cooling_power_w,
)
from fault_catalog import FaultCode, operator_help

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QGridLayout, QGroupBox, QSlider, QComboBox, QStackedWidget, QCheckBox,
    QSizePolicy, QTabBar, QTabWidget, QLineEdit, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QScrollArea, QFrame,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QLinearGradient,
    QFont, QPainterPath, QIcon, QPixmap,
)


# Target hardware: Raspberry Pi 800x480 touchscreen. The whole UI is laid out
# for this exact resolution so layout never shifts between windowed and
# fullscreen/frameless modes.
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480


# ---------------------------------------------------------------------------
# Shared style sheets (kept at module level so they can be tweaked once).
# ---------------------------------------------------------------------------
_TEMP_BUTTON_STYLE = """
    QPushButton {
        background-color: #0e6a76;
        color: white;
        font-size: 22px;
        font-weight: 600;
        border: 1px solid #0b565f;
        border-radius: 12px;
    }
    QPushButton:pressed { background-color: #0b565f; }
    QPushButton:hover   { background-color: #0d616c; }
    QPushButton:disabled {
        background-color: #d9e0e6;
        border-color: #c8d1d8;
        color: #8b98a5;
    }
"""

_GRAPH_NAV_BUTTON_STYLE = """
    QPushButton {
        background-color: #475569;
        color: white;
        font-size: 18px;
        font-weight: bold;
        border: 1px solid #334155;
        border-radius: 10px;
    }
    QPushButton:pressed { background-color: #334155; }
    QPushButton:disabled {
        background-color: #cbd5e1;
        border-color: #94a3b8;
        color: #64748b;
    }
"""

_GRAPH_WINDOW_COMBO_STYLE = """
    QComboBox {
        font-size: 13px;
        font-weight: bold;
        color: #1f2937;
        background-color: white;
        border: 1px solid #94a3b8;
        border-radius: 10px;
        padding: 4px 6px;
    }
    QComboBox::drop-down { width: 18px; }
"""

_SMOOTHING_TOGGLE_STYLE = """
    QPushButton {
        font-size: 12px;
        font-weight: 700;
        color: #475569;
        min-height: 26px;
        padding: 2px 4px;
        border: 2px solid #cbd5e1;
        border-radius: 8px;
        background-color: #f1f5f9;
    }
    QPushButton:checked {
        color: #ffffff;
        border: 2px solid #0e6a76;
        background-color: #0e6a76;
    }
"""

# Graph X-axis nav row: [<] [time window] [>]. The main page and the advanced
# graph tabs share these metrics so the block sits in the same spot on every
# page, at the top of a control column of _GRAPH_NAV_COLUMN_W pixels.
_GRAPH_NAV_BTN_W = 30
_GRAPH_NAV_BTN_H = 34
_GRAPH_NAV_GAP = 4
_GRAPH_NAV_COLUMN_W = 150
_SPINE_COLUMN_W = _GRAPH_NAV_COLUMN_W
_SPINE_NAV_GAP = 6
_SPINE_BUTTON_GAP = 8

_PAGE_TAB_BAR_STYLE = """
    QTabBar::tab {
        background: #e5ebf0;
        color: #40505d;
        padding: 9px 12px;
        margin-right: 4px;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        font-weight: 600;
    }
    QTabBar::tab:selected {
        background: #0e6a76;
        color: white;
    }
    QTabBar::tab:hover:!selected {
        background: #d8e1e8;
    }
"""

_HEADER_ICON_BUTTON_STYLE = """
    QPushButton {
        background: #f8fafb;
        color: #51606c;
        border: 1px solid #d5dce3;
        border-radius: 10px;
        font-size: 18px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: #eef3f7;
    }
    QPushButton:pressed {
        background: #e5ebf0;
    }
"""


def _header_house_icon(size: int = 20) -> QIcon:
    """Simple house silhouette for the back-to-main header button."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#51606c"))

    roof = QPainterPath()
    roof.moveTo(size * 0.50, size * 0.08)
    roof.lineTo(size * 0.96, size * 0.50)
    roof.lineTo(size * 0.04, size * 0.50)
    roof.closeSubpath()
    painter.drawPath(roof)

    painter.drawRect(QRectF(size * 0.22, size * 0.46, size * 0.56, size * 0.46))

    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.drawRect(QRectF(size * 0.42, size * 0.64, size * 0.16, size * 0.28))
    painter.end()
    return QIcon(pixmap)


def _header_gear_icon(size: int = 20) -> QIcon:
    """Cog for the service header button, drawn to match the other icons."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#51606c"))
    painter.translate(size / 2.0, size / 2.0)

    tooth_width = size * 0.22
    for _ in range(8):
        painter.drawRoundedRect(
            QRectF(-tooth_width / 2.0, -size * 0.48, tooth_width, size * 0.30),
            size * 0.05,
            size * 0.05,
        )
        painter.rotate(45)
    painter.drawEllipse(QRectF(-size * 0.30, -size * 0.30, size * 0.60, size * 0.60))

    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.drawEllipse(QRectF(-size * 0.13, -size * 0.13, size * 0.26, size * 0.26))
    painter.end()
    return QIcon(pixmap)


def _header_fullscreen_icon(size: int = 20) -> QIcon:
    """Four corner brackets: the action is 'grow to fullscreen'."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#51606c"), max(1.0, size * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    inset = size * 0.17
    arm = size * 0.24
    for x, y, dx, dy in (
        (inset, inset, 1, 1),
        (size - inset, inset, -1, 1),
        (inset, size - inset, 1, -1),
        (size - inset, size - inset, -1, -1),
    ):
        painter.drawLine(QPointF(x, y), QPointF(x + dx * arm, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + dy * arm))
    painter.end()
    return QIcon(pixmap)


def _header_restore_window_icon(size: int = 20) -> QIcon:
    """Two offset frames (restore down): the action is 'shrink to a window'."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#51606c"), max(1.0, size * 0.10))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.drawRoundedRect(
        QRectF(size * 0.36, size * 0.10, size * 0.54, size * 0.44),
        size * 0.08,
        size * 0.08,
    )

    front = QRectF(size * 0.10, size * 0.40, size * 0.54, size * 0.50)
    # Punch a gap around the front frame so the two frames stay readable.
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#000000"))
    painter.drawRoundedRect(
        front.adjusted(-size * 0.07, -size * 0.07, size * 0.07, size * 0.07),
        size * 0.10,
        size * 0.10,
    )

    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(front, size * 0.08, size * 0.08)
    painter.end()
    return QIcon(pixmap)


def _header_chart_icon(size: int = 20) -> QIcon:
    """Axes with a trend line, for the expert (plots and status) header button."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setPen(QPen(QColor("#51606c"), max(1.0, size * 0.09)))
    painter.drawLine(
        QPointF(size * 0.12, size * 0.10), QPointF(size * 0.12, size * 0.88)
    )
    painter.drawLine(
        QPointF(size * 0.12, size * 0.88), QPointF(size * 0.92, size * 0.88)
    )

    trend = QPainterPath()
    trend.moveTo(size * 0.26, size * 0.66)
    trend.lineTo(size * 0.45, size * 0.40)
    trend.lineTo(size * 0.62, size * 0.55)
    trend.lineTo(size * 0.84, size * 0.22)
    painter.strokePath(trend, QPen(QColor("#0e6a76"), max(1.0, size * 0.11)))
    painter.end()
    return QIcon(pixmap)


class ClickableLabel(QLabel):
    """QLabel that can emit ``clicked`` when tap/click is enabled."""

    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._click_enabled = False
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_click_enabled(self, enabled: bool) -> None:
        self._click_enabled = bool(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._click_enabled
            else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event):
        if (
            self._click_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FaultHelpDialog(QDialog):
    """Modal help sheet: probable causes and step-by-step recovery."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        causes: tuple[str, ...],
        steps: tuple[str, ...],
    ):
        super().__init__(parent)
        self.setWindowTitle("Error help")
        self.setModal(True)
        self.setFixedSize(720, 400)
        self.setStyleSheet("""
            QDialog {
                background: #f8fafb;
            }
            QLabel#faultTitle {
                color: #7e3f26;
                font-size: 18px;
                font-weight: 700;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("faultTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        body = QLabel(self._help_html(causes, steps))
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.setStyleSheet("QLabel { background: transparent; color: #1b2430; }")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        close_button = QPushButton("Close")
        close_button.setMinimumHeight(48)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #0e6a76;
                color: white;
                font-size: 16px;
                font-weight: 600;
                border: 1px solid #0b565f;
                border-radius: 12px;
            }
            QPushButton:pressed { background-color: #0b565f; }
        """)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    @staticmethod
    def _help_html(causes: tuple[str, ...], steps: tuple[str, ...]) -> str:
        cause_items = "".join(
            f"<li style='margin-bottom:6px;'>{_html_escape(item)}</li>"
            for item in causes
        )
        step_items = "".join(
            f"<li style='margin-bottom:6px;'>{_html_escape(item)}</li>"
            for item in steps
        )
        return (
            "<p style='font-size:15px;font-weight:700;color:#7e3f26;margin:4px 0 8px 0;'>"
            "Probable causes</p>"
            f"<ul style='font-size:14px;line-height:1.35;'>{cause_items}</ul>"
            "<p style='font-size:15px;font-weight:700;color:#245962;margin:14px 0 8px 0;'>"
            "What to do</p>"
            f"<ol style='font-size:14px;line-height:1.35;'>{step_items}</ol>"
        )


# Default linear pump model (overridden from config): flow_ml_min = rpm * slope.
DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM = 0.5862
# Discrete setpoints on the service-tab flow slider (10, 20, 30, ... ml/min).
PUMP_FLOW_SLIDER_STEP_ML_PER_MIN = 10
# Service-tab flow ramp test: start at 10 ml/min, +10 every 2 minutes.
FLOW_RAMP_TEST_START_ML_PER_MIN = 10
FLOW_RAMP_TEST_STEP_ML_PER_MIN = 10
FLOW_RAMP_TEST_INTERVAL_MS = 2 * 60 * 1000
# RPM→flow calibration: run pump at the selected RPM for a fixed window
# so volume can be measured and converted to ml/min.
RPM_FLOW_CALIBRATION_DURATION_S = 5 * 60
RPM_FLOW_CALIBRATION_TICK_MS = 1000


def _pump_flow_ml_per_min(rpm: float, slope: float) -> float:
    return max(0.0, float(rpm)) * float(slope)


def _aggregate_series(samples: list[dict], names: list[str], reduce) -> dict:
    """Reduce finite values for each name across ``samples`` (mean, max, …)."""
    result = {}
    for name in names:
        values = []
        for sample in samples:
            raw = sample.get(name)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isnan(value):
                values.append(value)
        result[name] = reduce(values) if values else float("nan")
    return result


def _mean_series(samples: list[dict], names: list[str]) -> dict:
    """Mean of finite values for each name across ``samples``."""
    return _aggregate_series(samples, names, lambda values: sum(values) / len(values))


def _max_series(samples: list[dict], names: list[str]) -> dict:
    """Maximum of finite values for each name across ``samples``."""
    return _aggregate_series(samples, names, max)


def _snap_ml_per_min_setpoint(ml_per_min: float, step: int = PUMP_FLOW_SLIDER_STEP_ML_PER_MIN) -> int:
    """Snap a flow value to the nearest discrete ml/min setpoint."""
    step = max(1, int(step))
    return int(round(float(ml_per_min) / step) * step)


class MainScreenWidget(QWidget):
    """Composite main-screen widget.

    Renders one or more of:
      - temperature history graph (with x-axis controls),
      - prominent CSF + setpoint readouts in the upper-right,
      - vertical setpoint gauge with touch +/- buttons,
      - cartridge level visualization with threshold indicators.
    """

    def __init__(
        self,
        show_cartridge: bool = True,
        show_graph: bool = True,
        show_temp_controls: bool = True,
        show_spine_diagram: bool = False,
    ):
        super().__init__()
        self.show_cartridge = show_cartridge
        self.show_graph = show_graph
        self.show_temp_controls = show_temp_controls
        self.show_spine_diagram = show_spine_diagram
        self.primary_temperature_label = "Temperature"
        self.catheter_in_temperature_label = "Catheter In"
        self.catheter_out_temperature_label = "Catheter Out"
        # Compact enough for Pi screens, still grows with the main layout.
        self.setMinimumSize(640, 280)

        # Cartridge sensor state
        self.level_low = False
        self.level_critical = False
        self.cartridge_present = False
        self.liquid_level = 0.7
        self.low_threshold = 0.4
        self.critical_threshold = 0.2

        # Setpoint configuration
        self.temp_min = 30.0
        self.temp_max = 35.0
        self.temp_step = 0.2
        self.set_temperature = 32.0
        self.current_csf_temperature = float("nan")
        self.current_catheter_in_temperature = float("nan")
        self.current_catheter_out_temperature = float("nan")
        self._temp_gauge_rect = QRectF()  # Updated during paint, used for hit testing
        self._dragging_temp = False
        self.on_temperature_change_callback: Optional[Callable[[float], None]] = None

        # Graph history: (timestamp, set_temp, csf_temp, catheter_in_temp)
        self._temp_history: deque = deque()
        self._x_window_minutes_options = [1, 2, 5, 15, 60]
        self._x_window_minutes = 5
        self._x_pan_windows = 0

        if self.show_temp_controls:
            self._create_temp_buttons()
            self._create_graph_nav_controls()

    # ------------------------------------------------------------------
    # Setpoint helpers
    # ------------------------------------------------------------------
    def _snap_to_step(self, value: float) -> float:
        """Clamp `value` to [temp_min, temp_max] and snap to `temp_step`."""
        clamped = max(self.temp_min, min(self.temp_max, value))
        num_steps = round((clamped - self.temp_min) / self.temp_step)
        return round(self.temp_min + num_steps * self.temp_step, 1)

    def _commit_setpoint(self, new_temp: float) -> None:
        """Apply a new setpoint, repaint, and notify the callback if changed."""
        new_temp = self._snap_to_step(new_temp)
        if abs(new_temp - self.set_temperature) <= 1e-6:
            return
        self.set_temperature = new_temp
        self._update_temp_button_enabled_state()
        self.update()
        if self.on_temperature_change_callback:
            self.on_temperature_change_callback(self.set_temperature)
    
    def set_sensor_states(self, states: dict):
        """Update sensor states and trigger repaint"""
        self.level_low = states.get('Level Low', False)
        self.level_critical = states.get('Level Critical', False)
        self.cartridge_present = states.get('Cartridge In Place', False)
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        """Paint the cartridge visualization"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background gradient
        self._draw_background(painter)

        if self.show_graph and not self.show_cartridge:
            margin = 10
            graph_height = max(180, self.height() - (2 * margin))
            if self.show_spine_diagram:
                right_w = self._right_controls_reserved_width()
                graph_width = self.width() - (2 * margin) - right_w - self._CONTROLS_GRAPH_GAP
                self._draw_temperature_graph(
                    painter,
                    graph_x=margin,
                    graph_y=margin,
                    graph_width=max(200, graph_width),
                    graph_height=graph_height,
                )
                spine_x, spine_y, spine_w, spine_h = self._spine_diagram_geometry()
                self._draw_spine_diagram(painter, spine_x, spine_y, spine_w, spine_h)
            else:
                graph_width = self.width() - (2 * margin)
                if self.show_temp_controls:
                    graph_width -= self._right_controls_reserved_width()
                # Graph fills the full available height; the time controls live in
                # the reserved right-hand column (see _position_graph_nav_controls).
                self._draw_temperature_graph(
                    painter,
                    graph_x=margin,
                    graph_y=margin,
                    graph_width=max(220, graph_width),
                    graph_height=graph_height,
                )
            if self.show_temp_controls:
                if not self.show_spine_diagram:
                    self._draw_csf_readout(painter)
                    self._draw_temperature_gauge(painter)
            return
        
        if self.show_graph:
            # Draw temperature history graph on the left
            self._draw_temperature_graph(painter)
        if self.show_cartridge:
            # Draw single chamber with liquid and threshold levels
            self._draw_single_chamber(painter)
            # Draw present sensor indicator below the chamber
            self._draw_present_sensor(painter)
        if self.show_temp_controls:
            self._draw_csf_readout(painter)
            self._draw_temperature_gauge(painter)
    
    def _draw_background(self, painter: QPainter):
        """Draw gradient background"""
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#f8fbff"))
        gradient.setColorAt(1, QColor("#eaf2ff"))
        painter.fillRect(self.rect(), gradient)
    
    # Temperature history graph configuration
    _MAX_HISTORY_SEC = 3600  # Keep up to 60 minutes for panning
    # Fixed temperature (Y) axis range for the main-screen graph.
    _GRAPH_TEMP_MIN = 20.0
    _GRAPH_TEMP_MAX = 40.0
    _GRAPH_SERIES = (
        # (history tuple index, label, color)
        (1, "Set Temp", "#0ea5e9"),
        (2, "CSF", "#1B7A7B"),
        (3, "Input", "#2E86C1"),
    )
    _SETPOINT_COLOR = "#0ea5e9"
    _CSF_COLOR = "#1B7A7B"
    _INPUT_COLOR = "#2E86C1"
    
    def add_temperature_sample(self, csf_temp: float, catheter_in_temp: float):
        """Record setpoint, CSF, and catheter-input temps for the main trace."""
        now = time.monotonic()
        self.current_csf_temperature = float(csf_temp)
        self.current_catheter_in_temperature = float(catheter_in_temp)
        self._temp_history.append(
            (now, self.set_temperature, float(csf_temp), float(catheter_in_temp))
        )
        
        # Drop samples older than retained history window
        cutoff = now - self._MAX_HISTORY_SEC
        while self._temp_history and self._temp_history[0][0] < cutoff:
            self._temp_history.popleft()
        
        self.update()
    
    def _draw_temperature_graph(
        self,
        painter: QPainter,
        graph_x: int = 15,
        graph_y: int = 40,
        graph_width: int = 270,
        graph_height: int = 280,
    ):
        """Draw the temperature history graph on the left side of the chamber"""
        # Background
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#cbd5e1"), 3))
        painter.drawRoundedRect(graph_x, graph_y, graph_width, graph_height, 10, 10)
        
        # Plot area. Top padding holds the one-line legend; bottom holds x labels.
        plot_left = graph_x + 42
        plot_right = graph_x + graph_width - 10
        plot_top = graph_y + 24
        plot_bottom = graph_y + graph_height - 26
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top
        
        now = time.monotonic()
        window_sec = float(self._x_window_minutes) * 60.0
        end_ts = now - (self._x_pan_windows * window_sec)
        start_ts = end_ts - window_sec
        visible_entries = [entry for entry in self._temp_history if start_ts <= entry[0] <= end_ts]
        y_min, y_max = self._compute_visible_y_range(visible_entries)

        minor_pen = QPen(QColor("#e2e8f0"), 1)
        minor_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(minor_pen)
        for i in range(6):
            ratio = (i + 0.5) / 6.0
            py = int(plot_bottom - ratio * plot_height)
            painter.drawLine(plot_left, py, plot_right, py)
        for i in range(10):
            ratio = (i + 0.5) / 10.0
            px = int(plot_left + ratio * plot_width)
            painter.drawLine(px, plot_top, px, plot_bottom)

        # Y-axis grid lines and labels (same 7 major ticks as expert pages).
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        for i in range(7):
            t = y_min + (i / 6.0) * (y_max - y_min)
            ratio = (t - y_min) / max(0.001, (y_max - y_min))
            py = int(plot_bottom - ratio * plot_height)
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(plot_left, py, plot_right, py)
            painter.setPen(QColor("#475569"))
            painter.drawText(
                QRectF(graph_x + 2, py - 8, 38, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{t:.0f}°C",
            )

        # X-axis labels and vertical time gridlines
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        for i in range(11):
            ratio = i / 10.0
            px = int(plot_left + ratio * plot_width)
            ts = start_ts + ratio * window_sec
            mins_ago = int(round((now - ts) / 60.0))
            label = "now" if mins_ago == 0 else f"-{mins_ago} min"
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(px, plot_top, px, plot_bottom)
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(px - 26, plot_bottom + 4, 52, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        # Plot axes
        painter.setPen(QPen(QColor("#64748b"), 2))
        painter.drawLine(int(plot_left), int(plot_top), int(plot_left), int(plot_bottom))
        painter.drawLine(int(plot_left), int(plot_bottom), int(plot_right), int(plot_bottom))
        
        # Plot data series
        if len(visible_entries) >= 1:
            def temp_to_y(t: float) -> float:
                t_clamped = max(y_min, min(y_max, t))
                ratio = (t_clamped - y_min) / max(0.001, (y_max - y_min))
                return plot_bottom - ratio * plot_height
            
            def time_to_x(ts: float) -> float:
                ratio = (ts - start_ts) / max(0.001, window_sec)
                ratio = max(0.0, min(1.0, ratio))
                return plot_left + ratio * plot_width
            
            # Clip drawing to the plot area to avoid overshoot
            painter.save()
            painter.setClipRect(QRectF(plot_left, plot_top, plot_width, plot_height))
            
            for series_index, _label, color_hex in self._GRAPH_SERIES:
                pen = QPen(QColor(color_hex), 4)
                if series_index == 1:  # Set temperature: dashed line
                    pen.setDashPattern([6, 3])

                path = QPainterPath()
                first = True
                for entry in visible_entries:
                    ts = entry[0]
                    value = entry[series_index]
                    px = time_to_x(ts)
                    py = temp_to_y(value)
                    if first:
                        path.moveTo(px, py)
                        first = False
                    else:
                        path.lineTo(px, py)
                # strokePath ignores the active brush, so crossing lines
                # don't clobber each other with the background fill.
                painter.strokePath(path, pen)
            
            painter.restore()
        else:
            # Empty-state message
            painter.setPen(QColor("#94a3b8"))
            font = QFont("Arial", 10)
            painter.setFont(font)
            painter.drawText(
                QRectF(plot_left, plot_top, plot_width, plot_height),
                Qt.AlignmentFlag.AlignCenter,
                "Waiting for data..."
            )

        # Color legend inside the graph, top-right corner (Set Temp vs CSF).
        self._draw_graph_legend(painter, graph_x, graph_width, graph_y)

    def _draw_graph_legend(self, painter: QPainter, graph_x: int, graph_width: int, top_y: int):
        """One-line Set / CSF / Input legend in the graph top-right."""
        latest = self._temp_history[-1] if self._temp_history else None
        set_text = f"Set {latest[1]:.1f}°C" if latest else "Set --.-°C"
        csf_text = f"CSF {latest[2]:.1f}°C" if latest else "CSF --.-°C"
        input_text = f"In {latest[3]:.1f}°C" if latest else "In --.-°C"
        entries = (
            (self._SETPOINT_COLOR, set_text, True),
            (self._CSF_COLOR, csf_text, False),
            (self._INPUT_COLOR, input_text, False),
        )

        painter.setFont(QFont("Arial", 9, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        swatch_w, swatch_gap, item_gap = 16, 5, 14
        widths = [
            swatch_w + swatch_gap + metrics.horizontalAdvance(text)
            for _color, text, _dashed in entries
        ]
        total = sum(widths) + item_gap * (len(entries) - 1)
        x = graph_x + graph_width - total - 12
        y = top_y + 4

        for (color, text, dashed), width in zip(entries, widths):
            pen = QPen(QColor(color), 3)
            if dashed:
                pen.setDashPattern([3, 2])
            painter.setPen(pen)
            painter.drawLine(int(x), int(y + 8), int(x + swatch_w), int(y + 8))
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(x + swatch_w + swatch_gap, y, width - swatch_w - swatch_gap, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            x += width + item_gap

    def _compute_visible_y_range(self, visible_entries):
        # Y axis is intentionally locked to a fixed range so the visual
        # baseline does not shift as samples come in. Values outside the
        # range are clamped/clipped at draw time.
        del visible_entries
        return self._GRAPH_TEMP_MIN, self._GRAPH_TEMP_MAX
 
    # Touch-friendly gauge geometry
    _GAUGE_WIDTH = 55
    _GAUGE_MIN_HEIGHT = 80
    # Leaves room for the graph nav row plus the CSF / setpoint readouts.
    _GAUGE_TOP = 127
    _GAUGE_HANDLE_OVERHANG = 12
    _GAUGE_TICK_LABEL_LEFT = 48
    # Wide enough for the [<] [window] [>] nav row, matching the advanced tabs.
    _READOUT_MIN_WIDTH = _GRAPH_NAV_COLUMN_W
    # Mirrors the graph's left inset so the controls column is symmetric.
    _RIGHT_MARGIN = 10
    _CONTROLS_GRAPH_GAP = 8
    _TEMP_BUTTON_SIZE = 48
    _TEMP_BUTTON_GAP = 10

    def _right_controls_reserved_width(self) -> int:
        """Horizontal space reserved for the right-side gauge column."""
        if self.show_spine_diagram:
            return _SPINE_COLUMN_W + self._RIGHT_MARGIN + self._CONTROLS_GRAPH_GAP
        gauge_extent = (
            self._GAUGE_TICK_LABEL_LEFT
            + self._GAUGE_WIDTH
            + self._GAUGE_HANDLE_OVERHANG
        )
        return (
            max(self._READOUT_MIN_WIDTH, gauge_extent)
            + self._RIGHT_MARGIN
            + self._CONTROLS_GRAPH_GAP
        )

    def _controls_column_right(self) -> float:
        """Right edge shared by readouts and gauge handle."""
        return self.width() - self._RIGHT_MARGIN

    def _temp_buttons_top(self) -> int:
        """Natural Y anchor for +/- buttons (must stay in sync with _position_temp_buttons)."""
        return self.height() - self._TEMP_BUTTON_SIZE - 4

    def _gauge_geometry(self):
        """Return the gauge track rectangle dimensions based on widget size."""
        column_left, column_width = self._readout_column_geometry()
        gauge_x = column_left + (column_width - self._GAUGE_WIDTH) / 2
        gauge_y = self._GAUGE_TOP
        # Extend the track down toward the +/- buttons without moving them.
        buttons_top = self._temp_buttons_top()
        gauge_height = max(self._GAUGE_MIN_HEIGHT, buttons_top - gauge_y - 8)
        return int(gauge_x), gauge_y, self._GAUGE_WIDTH, gauge_height

    def _spine_diagram_geometry(self) -> tuple[int, int, int, int]:
        """Right-column rect for the catheter graphic (between nav row and +/-)."""
        column_left, column_width = self._readout_column_geometry()
        nav_bottom = self._GRAPH_NAV_TOP + _GRAPH_NAV_BTN_H
        spine_top = nav_bottom + _SPINE_NAV_GAP
        buttons_top = self._temp_buttons_top()
        spine_height = max(60, buttons_top - _SPINE_BUTTON_GAP - spine_top)
        return int(column_left), spine_top, int(column_width), spine_height

    def _readout_column_geometry(self) -> tuple[float, float]:
        """Left edge and width for controls column (readouts and/or +/- buttons)."""
        column_right = self._controls_column_right()
        if self.show_spine_diagram:
            column_width = float(_SPINE_COLUMN_W)
        else:
            column_width = max(
                self._READOUT_MIN_WIDTH,
                self._GAUGE_WIDTH + 2 * self._GAUGE_HANDLE_OVERHANG,
            )
        return column_right - column_width, column_width

    def _draw_csf_readout(self, painter: QPainter):
        """Draw CSF and set-temperature readouts above the right-side controls."""
        column_left, column_width = self._readout_column_geometry()

        csf_top = self._GRAPH_NAV_TOP + _GRAPH_NAV_BTN_H + 8
        csf_height = 38
        if math.isnan(self.current_csf_temperature):
            csf_text = "--.-°C"
        else:
            csf_text = f"{self.current_csf_temperature:.1f}°C"
        painter.setPen(QColor(self._CSF_COLOR))
        csf_font_size = 22 if self.show_spine_diagram else 30
        painter.setFont(QFont("Arial", csf_font_size, QFont.Weight.Bold))
        painter.drawText(
            QRectF(column_left, csf_top, column_width, csf_height),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            csf_text,
        )

        set_font_size = 22 if self.show_spine_diagram else 18
        set_height = 30 if self.show_spine_diagram else 24
        if self.show_spine_diagram:
            set_top = csf_top + csf_height + 6
        else:
            _, gauge_y, _, _ = self._gauge_geometry()
            set_top = csf_top + csf_height + (
                (gauge_y - (csf_top + csf_height) - set_height) / 2
            )
        set_text = f"{self.set_temperature:.1f}°C"
        painter.setPen(QColor(self._SETPOINT_COLOR))
        painter.setFont(QFont("Arial", set_font_size, QFont.Weight.Bold))
        painter.drawText(
            QRectF(column_left, set_top, column_width, set_height),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            set_text,
        )

        if self.show_spine_diagram:
            label_top = set_top + set_height + 2
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.drawText(
                QRectF(column_left, label_top, column_width, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Setpoint",
            )
    
    def _draw_spine_diagram(
        self, painter: QPainter, x: int, y: int, width: int, height: int
    ) -> None:
        """Catheter schematic sized for the right column between nav and +/-."""
        top_label_band = 34
        bottom_label_band = 34
        art_y = y + top_label_band
        art_h = max(40, height - top_label_band - bottom_label_band)

        lbl_font = QFont("Segoe UI", 9)
        val_font = QFont("Segoe UI", 10, QFont.Weight.Bold)

        csf_val = (
            f"{self.current_csf_temperature:.1f}°C"
            if not math.isnan(self.current_csf_temperature)
            else "--.-°C"
        )
        in_val = (
            f"{self.current_catheter_in_temperature:.1f}°C"
            if not math.isnan(self.current_catheter_in_temperature)
            else "--.-°C"
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        def draw_name_value_row(row_y: float, name: str, value: str, value_color: str) -> None:
            painter.setFont(lbl_font)
            name_w = painter.fontMetrics().horizontalAdvance(name)
            painter.setFont(val_font)
            value_w = painter.fontMetrics().horizontalAdvance(value)
            row_left = x + (width - (name_w + label_gap + value_w)) / 2
            painter.setPen(QColor("#2A2A2A"))
            painter.setFont(lbl_font)
            painter.drawText(
                QRectF(row_left, row_y, name_w, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                name,
            )
            painter.setPen(QColor(value_color))
            painter.setFont(val_font)
            painter.drawText(
                QRectF(row_left + name_w + label_gap, row_y, value_w, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                value,
            )

        label_gap = 4
        draw_name_value_row(
            y + (top_label_band - 16) / 2,
            "CSF (Tip)",
            csf_val,
            "#1B7A7B",
        )
        draw_name_value_row(
            y + height - bottom_label_band + (bottom_label_band - 16) / 2,
            self.catheter_in_temperature_label,
            in_val,
            "#2E86C1",
        )

        # Artwork viewBox includes both sensors so they are never clipped.
        vb_w = 148.0
        vb_y0, vb_y1 = 82.0, 552.0
        vb_h = vb_y1 - vb_y0
        scale = min(width / vb_w, art_h / vb_h)
        ox = x + (width - vb_w * scale) / 2.0
        oy = art_y + (art_h - vb_h * scale) / 2.0

        def pt(sx: float, sy: float) -> QPointF:
            return QPointF(ox + sx * scale, oy + (sy - vb_y0) * scale)

        def sw(v: float) -> float:
            return max(1.0, v * scale)

        def draw_temp_sensor(cx: float, cy: float, radius: float) -> None:
            painter.setBrush(QColor("#1B7A7B"))
            painter.setPen(QPen(QColor("#124F50"), sw(2.4)))
            painter.drawEllipse(pt(cx, cy), sw(radius), sw(radius))
            painter.setPen(
                QPen(QColor("#FFFFFF"), sw(2.8), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawLine(pt(cx, cy - radius * 0.38), pt(cx, cy + radius * 0.12))
            painter.setBrush(QColor("#FF5252"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt(cx, cy + radius * 0.32), sw(radius * 0.22), sw(radius * 0.22))

        def draw_chevron(cx: float, cy: float, pointing_up: bool, color: str) -> None:
            half = 6.5
            tip = cy - 10 if pointing_up else cy + 10
            base = cy + 2 if pointing_up else cy - 2
            arrow = QPainterPath()
            arrow.moveTo(pt(cx - half, base))
            arrow.lineTo(pt(cx, tip))
            arrow.lineTo(pt(cx + half, base))
            arrow.closeSubpath()
            painter.fillPath(arrow, QColor(color))

        blue = QColor("#2E86C1")
        red = QColor("#E53935")
        center_x = 74.0
        cath_left, cath_right = 28.0, 120.0
        tip_r = 24.0
        tip_sensor_y = 108.0
        cath_top = tip_sensor_y + tip_r * 0.45
        cath_bottom = 428.0
        in_x = center_x - 18.0
        out_x = center_x + 18.0
        lumen_bottom = cath_bottom - 8.0
        # Compact U-turn centered at 80% of catheter height (from the bottom).
        turn_y = cath_bottom - 0.80 * (cath_bottom - cath_top)
        turn_r = abs(out_x - in_x) * 0.55
        apex_y = turn_y - turn_r
        inlet_r = 20.0
        inlet_sensor_x, inlet_sensor_y = 20.0, 522.0
        inlet_port_x, inlet_port_y = 40.0, 512.0
        return_port_x, return_port_y = 128.0, 512.0

        painter.setClipRect(QRectF(x, art_y, width, art_h))

        cath_p1 = pt(cath_left, cath_top)
        cath_p2 = pt(cath_right, cath_bottom)
        cath_rect = QRectF(
            cath_p1.x(), cath_p1.y(), cath_p2.x() - cath_p1.x(), cath_p2.y() - cath_p1.y()
        )
        cath_grad = QLinearGradient(cath_rect.topLeft(), cath_rect.topRight())
        cath_grad.setColorAt(0, QColor("#8FA9B5"))
        cath_grad.setColorAt(0.5, QColor("#E8EFF2"))
        cath_grad.setColorAt(1, QColor("#8FA9B5"))
        painter.setPen(QPen(QColor("#6B8794"), sw(2)))
        painter.setBrush(cath_grad)
        painter.drawRoundedRect(cath_rect, sw(10), sw(10))

        painter.setPen(QPen(QColor("#6B8794"), sw(1.2), Qt.PenStyle.DashLine))
        painter.drawLine(pt(center_x, cath_top + 22), pt(center_x, cath_bottom - 8))

        left_branch = QPainterPath()
        left_branch.moveTo(pt(in_x, cath_bottom - 4))
        left_branch.cubicTo(
            pt(in_x - 8, 452), pt(inlet_port_x + 8, 498), pt(inlet_port_x, inlet_port_y)
        )
        painter.setPen(
            QPen(blue, sw(9), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(left_branch)
        painter.setPen(
            QPen(QColor("#7EC8E8"), sw(4.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(left_branch)

        right_branch = QPainterPath()
        right_branch.moveTo(pt(out_x, cath_bottom - 4))
        right_branch.cubicTo(
            pt(out_x + 8, 452),
            pt(return_port_x - 10, 498),
            pt(return_port_x, return_port_y),
        )
        painter.setPen(
            QPen(QColor("#8FA9B5"), sw(8), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(right_branch)
        painter.setPen(
            QPen(QColor("#E8EFF2"), sw(4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(right_branch)

        flow_pen = QPen(blue, sw(5.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(flow_pen)
        painter.drawLine(
            pt(inlet_sensor_x + inlet_r + 1, inlet_port_y),
            pt(inlet_port_x, inlet_port_y),
        )
        painter.drawPath(left_branch)
        painter.drawLine(pt(in_x, lumen_bottom), pt(in_x, turn_y))
        blue_turn = QPainterPath()
        blue_turn.moveTo(pt(in_x, turn_y))
        blue_turn.cubicTo(
            pt(in_x, apex_y), pt(center_x, apex_y), pt(center_x, apex_y + 1)
        )
        painter.drawPath(blue_turn)
        draw_chevron(in_x, turn_y + 16, pointing_up=True, color="#2E86C1")
        feed_arrow = QPainterPath()
        feed_arrow.moveTo(pt(inlet_port_x - 11, inlet_port_y - 6))
        feed_arrow.lineTo(pt(inlet_port_x, inlet_port_y))
        feed_arrow.lineTo(pt(inlet_port_x - 11, inlet_port_y + 6))
        feed_arrow.closeSubpath()
        painter.fillPath(feed_arrow, blue)

        flow_pen.setColor(red)
        painter.setPen(flow_pen)
        red_turn = QPainterPath()
        red_turn.moveTo(pt(center_x, apex_y + 1))
        red_turn.cubicTo(pt(out_x, apex_y), pt(out_x, turn_y), pt(out_x, turn_y))
        painter.drawPath(red_turn)
        painter.drawLine(pt(out_x, turn_y), pt(out_x, lumen_bottom))
        red_to_return = QPainterPath()
        red_to_return.moveTo(pt(out_x, lumen_bottom))
        red_to_return.cubicTo(
            pt(out_x + 6, 448),
            pt(return_port_x - 16, 490),
            pt(return_port_x - 6, return_port_y - 2),
        )
        painter.drawPath(red_to_return)
        draw_chevron(out_x, (turn_y + lumen_bottom) / 2, pointing_up=False, color="#E53935")

        painter.setPen(
            QPen(QColor("#8FA9B5"), sw(5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawLine(pt(return_port_x, return_port_y), pt(return_port_x + 14, return_port_y))

        draw_temp_sensor(center_x, tip_sensor_y, tip_r)
        draw_temp_sensor(inlet_sensor_x, inlet_sensor_y, inlet_r)

        painter.restore()

    def _draw_single_chamber(self, painter: QPainter):
        """Draw single chamber with liquid level and threshold markers"""
        # Chamber dimensions - centered in widget
        chamber_x = (self.width() - 200) // 2
        chamber_y = 40
        chamber_width = 200
        chamber_height = 280
        
        # Draw chamber outline (container)
        painter.setBrush(QColor("#f1f5f9"))
        painter.setPen(QPen(QColor("#334155"), 3))
        painter.drawRoundedRect(chamber_x, chamber_y, chamber_width, chamber_height, 12, 12)
        
        # Draw liquid fill
        if self.cartridge_present:
            liquid_height = int(chamber_height * self.liquid_level)
            liquid_y = chamber_y + chamber_height - liquid_height
            
            # Liquid gradient
            liquid_gradient = QLinearGradient(chamber_x, liquid_y, chamber_x, chamber_y + chamber_height)
            liquid_gradient.setColorAt(0, QColor("#38bdf8"))
            liquid_gradient.setColorAt(1, QColor("#0284c7"))
            
            painter.setBrush(liquid_gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            
            # Draw liquid with rounded bottom
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(chamber_x + 4, liquid_y, chamber_width - 8, liquid_height - 4),
                10, 10
            )
            painter.drawPath(path)
        
        # Draw threshold lines
        self._draw_threshold_line(
            painter, chamber_x, chamber_y, chamber_width, chamber_height,
            self.low_threshold, "LOW", self.level_low, QColor("#f59e0b")
        )
        self._draw_threshold_line(
            painter, chamber_x, chamber_y, chamber_width, chamber_height,
            self.critical_threshold, "CRITICAL", self.level_critical, QColor("#ef4444")
        )
        
        # Draw chamber label
        painter.setPen(QColor("#1e293b"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(chamber_x, chamber_y + chamber_height + 5, chamber_width, 25),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Cartridge Level"
        )
    
    def _draw_threshold_line(self, painter: QPainter, chamber_x: int, chamber_y: int,
                              chamber_width: int, chamber_height: int,
                              threshold: float, label: str, is_triggered: bool, color: QColor):
        """Draw a single threshold line with label"""
        line_y = int(chamber_y + chamber_height * (1 - threshold))
        
        # Draw dashed threshold line
        pen = QPen(color, 2)
        pen.setDashPattern([8, 4])
        painter.setPen(pen)
        painter.drawLine(chamber_x + 10, line_y, chamber_x + chamber_width - 10, line_y)
        
        # Draw label on the right side
        label_x = chamber_x + chamber_width + 10
        
        # Draw indicator circle
        if is_triggered:
            painter.setBrush(color)
        else:
            painter.setBrush(QColor("#94a3b8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(label_x + 8, line_y), 6, 6)
        
        # Draw label text
        if is_triggered:
            painter.setPen(color)
        else:
            painter.setPen(QColor("#64748b"))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(label_x + 20, line_y - 10, 80, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label
        )
    
    def _draw_present_sensor(self, painter: QPainter):
        """Draw cartridge present sensor indicator below the chamber"""
        # Position below the chamber
        indicator_x = (self.width() - 250) // 2
        indicator_y = 360
        indicator_width = 250
        indicator_height = 50
        
        # Draw indicator background
        if self.cartridge_present:
            bg_color = QColor("#dcfce7")
            border_color = QColor("#16a34a")
            circle_color = QColor("#22c55e")
            text_color = QColor("#15803d")
            status_text = "Cartridge Present"
        else:
            bg_color = QColor("#fee2e2")
            border_color = QColor("#ef4444")
            circle_color = QColor("#dc2626")
            text_color = QColor("#991b1b")
            status_text = "No Cartridge"
        
        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(indicator_x, indicator_y, indicator_width, indicator_height, 10, 10)
        
        # Draw status circle
        circle_x = indicator_x + 30
        circle_y = indicator_y + indicator_height // 2
        painter.setBrush(circle_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(circle_x, circle_y), 12, 12)
        
        # Draw checkmark or X inside circle
        painter.setPen(QPen(QColor("white"), 2))
        if self.cartridge_present:
            # Draw checkmark
            painter.drawLine(circle_x - 5, circle_y, circle_x - 1, circle_y + 4)
            painter.drawLine(circle_x - 1, circle_y + 4, circle_x + 6, circle_y - 5)
        else:
            # Draw X
            painter.drawLine(circle_x - 5, circle_y - 5, circle_x + 5, circle_y + 5)
            painter.drawLine(circle_x + 5, circle_y - 5, circle_x - 5, circle_y + 5)
        
        # Draw status text
        painter.setPen(text_color)
        font = QFont("Arial", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(circle_x + 25, indicator_y, indicator_width - 60, indicator_height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            status_text
        )
    
    def _draw_temperature_gauge(self, painter: QPainter):
        """Draw vertical set temperature gauge on the right side"""
        gauge_x, gauge_y, gauge_width, gauge_height = self._gauge_geometry()
        
        # Store gauge track rectangle for hit testing
        self._temp_gauge_rect = QRectF(gauge_x, gauge_y, gauge_width, gauge_height)
        # The setpoint value is shown between the CSF readout and the gauge;
        # the gauge handle + tick numbers indicate position on the track.
        
        # Draw gauge track
        track_gradient = QLinearGradient(gauge_x, gauge_y, gauge_x, gauge_y + gauge_height)
        track_gradient.setColorAt(0, QColor("#e9ecef"))  # neutral top
        track_gradient.setColorAt(1, QColor("#d6e4e7"))  # cool bottom
        painter.setBrush(track_gradient)
        painter.setPen(QPen(QColor("#a0afb8"), 2))
        painter.drawRoundedRect(gauge_x, gauge_y, gauge_width, gauge_height, 10, 10)
        
        # Draw tick marks every 0.2 degrees
        num_steps = int(round((self.temp_max - self.temp_min) / self.temp_step))
        for i in range(num_steps + 1):
            temp_value = self.temp_min + i * self.temp_step
            ratio = (temp_value - self.temp_min) / (self.temp_max - self.temp_min)
            # Higher temperature at top, lower at bottom
            tick_y = int(gauge_y + gauge_height - ratio * gauge_height)
            
            # Major tick (every 1.0 deg) vs minor tick (every 0.2 deg)
            is_major = abs(temp_value - round(temp_value)) < 0.01
            
            if is_major:
                tick_length = 12
                painter.setPen(QPen(QColor("#3b4652"), 2))
            else:
                tick_length = 6
                painter.setPen(QPen(QColor("#6b7885"), 1))
            
            # Tick marks on both sides of the track
            painter.drawLine(gauge_x - tick_length, tick_y, gauge_x, tick_y)
            painter.drawLine(
                gauge_x + gauge_width, tick_y,
                gauge_x + gauge_width + tick_length, tick_y
            )
            
            # Major tick labels
            if is_major:
                painter.setPen(QColor("#3f4b57"))
                font = QFont("Arial", 9, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(
                    QRectF(gauge_x - 48, tick_y - 8, 30, 16),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{int(round(temp_value))}"
                )
        
        # Draw handle at current setpoint (bigger for touch)
        handle_ratio = (self.set_temperature - self.temp_min) / (self.temp_max - self.temp_min)
        handle_y = int(gauge_y + gauge_height - handle_ratio * gauge_height)
        handle_half_height = 14
        handle_overhang = self._GAUGE_HANDLE_OVERHANG
        
        # Handle shadow
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(gauge_x - handle_overhang, handle_y - handle_half_height + 2,
                   gauge_width + 2 * handle_overhang, 2 * handle_half_height),
            8, 8
        )
        
        # Handle body
        handle_gradient = QLinearGradient(
            gauge_x, handle_y - handle_half_height,
            gauge_x, handle_y + handle_half_height
        )
        handle_gradient.setColorAt(0, QColor("#2d6f79"))
        handle_gradient.setColorAt(1, QColor("#1f5962"))
        painter.setBrush(handle_gradient)
        painter.setPen(QPen(QColor("#184a52"), 2))
        painter.drawRoundedRect(
            QRectF(gauge_x - handle_overhang, handle_y - handle_half_height,
                   gauge_width + 2 * handle_overhang, 2 * handle_half_height),
            8, 8
        )
        
        # Handle centerline indicator
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawLine(
            int(gauge_x - handle_overhang + 4), handle_y,
            int(gauge_x + gauge_width + handle_overhang - 4), handle_y
        )
        
    def _y_to_temperature(self, y: float) -> float:
        """Convert a y-coordinate to a temperature value, snapped to the step."""
        if self._temp_gauge_rect.height() <= 0:
            return self.set_temperature
        gauge_top = self._temp_gauge_rect.top()
        gauge_height = self._temp_gauge_rect.height()
        y_clamped = max(gauge_top, min(gauge_top + gauge_height, y))
        # Top = max temp, bottom = min temp.
        ratio = 1.0 - (y_clamped - gauge_top) / gauge_height
        return self._snap_to_step(self.temp_min + ratio * (self.temp_max - self.temp_min))
    
    def _is_near_temp_gauge(self, pos: QPointF) -> bool:
        """Check if a mouse position is within/near the gauge track"""
        if not self.show_temp_controls or self.show_spine_diagram:
            return False
        # Extend hit area slightly beyond the track for easier interaction
        hit_rect = self._temp_gauge_rect.adjusted(-15, -10, 15, 10)
        return hit_rect.contains(pos)
    
    def _update_temperature_from_mouse(self, y: float):
        """Update set temperature from mouse y-position and notify callback"""
        self._commit_setpoint(self._y_to_temperature(y))
    
    def mousePressEvent(self, event):
        """Handle mouse press for temperature gauge interaction"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self._is_near_temp_gauge(pos):
                self._dragging_temp = True
                self._update_temperature_from_mouse(pos.y())
                event.accept()
                return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse drag for temperature gauge interaction"""
        if self._dragging_temp:
            self._update_temperature_from_mouse(event.position().y())
            event.accept()
            return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to end temperature drag"""
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_temp:
            self._dragging_temp = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
    
    def set_temperature_value(self, temperature: float):
        """Programmatically set the temperature value (snapped, no callback)."""
        self.set_temperature = self._snap_to_step(temperature)
        self._update_temp_button_enabled_state()
        self.update()
    
    def _create_temp_buttons(self):
        """Create touch-friendly +/- buttons for temperature adjustment."""
        def make(text: str, on_click) -> QPushButton:
            btn = QPushButton(text, self)
            btn.setFixedSize(self._TEMP_BUTTON_SIZE, self._TEMP_BUTTON_SIZE)
            btn.setStyleSheet(_TEMP_BUTTON_STYLE)
            btn.clicked.connect(on_click)
            # Auto-repeat: holding the button steps continuously.
            btn.setAutoRepeat(True)
            btn.setAutoRepeatDelay(400)
            btn.setAutoRepeatInterval(120)
            return btn

        self.temp_minus_button = make("-", self._on_temp_decrement)
        self.temp_plus_button = make("+", self._on_temp_increment)

    # Top edge of the nav row inside the right-hand controls column.
    _GRAPH_NAV_TOP = 6

    def _create_graph_nav_controls(self):
        """Create graph X-axis controls (window size and panning)."""
        def make_nav(text: str, on_click) -> QPushButton:
            btn = QPushButton(text, self)
            btn.setFixedSize(_GRAPH_NAV_BTN_W, _GRAPH_NAV_BTN_H)
            btn.setStyleSheet(_GRAPH_NAV_BUTTON_STYLE)
            btn.clicked.connect(on_click)
            return btn

        self.graph_nav_left_button = make_nav("<", self._on_graph_nav_left)
        self.graph_nav_right_button = make_nav(">", self._on_graph_nav_right)

        self.graph_window_combo = QComboBox(self)
        for minutes in self._x_window_minutes_options:
            self.graph_window_combo.addItem(f"{minutes} min", minutes)
        self.graph_window_combo.setCurrentIndex(
            self._x_window_minutes_options.index(self._x_window_minutes)
        )
        self.graph_window_combo.currentIndexChanged.connect(self._on_graph_window_changed)
        self.graph_window_combo.setStyleSheet(_GRAPH_WINDOW_COMBO_STYLE)
        self.graph_window_combo.setFixedHeight(_GRAPH_NAV_BTN_H)
    
    def _position_temp_buttons(self):
        """Position +/- buttons below the gauge"""
        if not hasattr(self, "temp_minus_button"):
            return
        if not self.show_temp_controls:
            self.temp_minus_button.hide()
            self.temp_plus_button.hide()
            if hasattr(self, "graph_nav_left_button"):
                self.graph_nav_left_button.hide()
                self.graph_window_combo.hide()
                self.graph_nav_right_button.hide()
            return
        self.temp_minus_button.show()
        self.temp_plus_button.show()
        if hasattr(self, "graph_nav_left_button"):
            self.graph_nav_left_button.show()
            self.graph_window_combo.show()
            self.graph_nav_right_button.show()
        
        column_left, column_width = self._readout_column_geometry()
        controls_center_x = int(column_left + column_width / 2)
        
        buttons_total_width = 2 * self._TEMP_BUTTON_SIZE + self._TEMP_BUTTON_GAP
        buttons_left = controls_center_x - buttons_total_width // 2
        buttons_top = self._temp_buttons_top()
        if not self.show_spine_diagram:
            gauge_x, gauge_y, gauge_width, gauge_height = self._gauge_geometry()
            controls_center_x = gauge_x + gauge_width // 2
            buttons_left = controls_center_x - buttons_total_width // 2
            min_top = gauge_y + gauge_height + 8
            buttons_top = max(min_top, buttons_top)
        
        self.temp_minus_button.move(buttons_left, buttons_top)
        self.temp_plus_button.move(
            buttons_left + self._TEMP_BUTTON_SIZE + self._TEMP_BUTTON_GAP,
            buttons_top,
        )
        self._position_graph_nav_controls()
        self._update_graph_nav_button_states()

    def _position_graph_nav_controls(self):
        """Lay out [<] [window] [>] across the top of the controls column."""
        if not hasattr(self, "graph_window_combo"):
            return
        btn_w = _GRAPH_NAV_BTN_W
        gap = _GRAPH_NAV_GAP

        column_left, column_width = self._readout_column_geometry()
        combo_w = max(40, int(column_width) - 2 * (btn_w + gap))
        left = int(column_left)
        top = self._GRAPH_NAV_TOP

        self.graph_nav_left_button.move(left, top)
        self.graph_window_combo.setFixedWidth(combo_w)
        self.graph_window_combo.move(left + btn_w + gap, top)
        self.graph_nav_right_button.move(left + btn_w + gap + combo_w + gap, top)

    def _on_graph_window_changed(self, index: int):
        self._x_window_minutes = int(self.graph_window_combo.itemData(index))
        self._x_pan_windows = 0
        self._update_graph_nav_button_states()
        self.update()

    def _on_graph_nav_left(self):
        self._x_pan_windows += 1
        self._update_graph_nav_button_states()
        self.update()

    def _on_graph_nav_right(self):
        self._x_pan_windows = max(0, self._x_pan_windows - 1)
        self._update_graph_nav_button_states()
        self.update()

    def _update_graph_nav_button_states(self):
        if not hasattr(self, "graph_nav_left_button"):
            return
        self.graph_nav_right_button.setEnabled(self._x_pan_windows > 0)
        if not self._temp_history:
            self.graph_nav_left_button.setEnabled(False)
            return
        oldest_ts = self._temp_history[0][0]
        now = time.monotonic()
        window_sec = float(self._x_window_minutes) * 60.0
        max_pan = int(max(0.0, (now - oldest_ts) // window_sec))
        self.graph_nav_left_button.setEnabled(self._x_pan_windows < max_pan)
    
    def _step_temperature(self, direction: int):
        """Step the set temperature by `direction` steps (snapped and clamped)."""
        self._commit_setpoint(self.set_temperature + direction * self.temp_step)

    def _on_temp_increment(self):
        self._step_temperature(1)

    def _on_temp_decrement(self):
        self._step_temperature(-1)
    
    def _update_temp_button_enabled_state(self):
        """Disable buttons at range limits"""
        if hasattr(self, "temp_minus_button"):
            self.temp_minus_button.setEnabled(self.set_temperature > self.temp_min + 1e-6)
            self.temp_plus_button.setEnabled(self.set_temperature < self.temp_max - 1e-6)
    
    def resizeEvent(self, event):
        """Reposition touch buttons when the widget is resized"""
        super().resizeEvent(event)
        self._position_temp_buttons()
    
    def showEvent(self, event):
        """Ensure buttons are positioned and enabled state is correct when shown"""
        super().showEvent(event)
        self._position_temp_buttons()
        self._update_temp_button_enabled_state()
        self._update_graph_nav_button_states()


class ServiceTab(QWidget):
    """Service tab showing all sensors and outputs"""
    _LABEL_NEUTRAL_STYLE = "font-size: 13px; padding: 4px 2px; color: #5c6b79;"
    _LABEL_STRONG_TEMPLATE = "font-size: 13px; padding: 4px 2px; color: {color}; font-weight: 600;"
    _CONTROL_LABEL_STYLE = (
        "font-size: 12px; font-weight: 700; padding: 4px 8px; color: #0e6a76;"
        "background: #eef7f8; border: 1px solid #b7d6db; border-radius: 10px;"
    )
    _SLIDER_UNIT_LABEL_STYLE = (
        "font-size: 12px; font-weight: 700; color: #475569; padding: 0 4px;"
    )
    _TEMP_STEP_BUTTON_STYLE = """
            QPushButton {
                background-color: #e8eef3;
                border: 1px solid #c5d0d9;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
                color: #1f2937;
            }
            QPushButton:pressed { background-color: #d5dee6; }
        """
    _COMPACT_PUMP_BUTTON_HEIGHT = 32
    _JOG_BUTTON_STYLE = """
            QPushButton {
                background-color: #e7edf2;
                border: 1px solid #cfd8e0;
                font-size: 11px;
                color: #23303b;
                font-weight: 600;
                border-radius: 8px;
                padding: 4px 6px;
            }
            QPushButton:hover {
                background-color: #dde6ed;
            }
            QPushButton:disabled {
                background-color: #eef2f6;
                border-color: #dbe3ea;
                color: #93a0ac;
            }
        """
    _SLIDER_STYLE = """
            QSlider {
                min-height: 36px;
                max-height: 40px;
            }
            QSlider::groove:horizontal {
                height: 12px;
                background: #d8e0e6;
                border-radius: 6px;
                margin: 0 8px;
            }
            QSlider::sub-page:horizontal {
                background: #0e6a76;
                border-radius: 6px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 2px solid #0e6a76;
                width: 26px;
                height: 26px;
                margin: -8px 0;
                border-radius: 13px;
            }
        """
    
    def __init__(self, stepper_config: Optional[dict] = None, compressor_config: Optional[dict] = None):
        super().__init__()

        stepper_cfg = stepper_config or {}
        compressor_cfg = compressor_config or {}

        # Output state
        self.pump_flow_ml_per_min_per_rpm = DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        self.compressor_on = False
        self.compressor_control_enabled = False
        self.compressor_off_temp_c = float(compressor_cfg.get("off_below_temp_c", 5))
        self.compressor_on_temp_c = float(compressor_cfg.get("on_above_temp_c", 10))
        self.heat_ex_temp_c: Optional[float] = None
        self.stepper_speed_rpm = int(stepper_cfg.get("default_speed_rpm", 30))
        self.stepper_max_speed_rpm = max(5, int(stepper_cfg.get("max_speed_rpm", 60)))
        # Manual (service tab) slider floor. Independent of ``min_pump_speed_rpm``,
        # which is only the minimum enforced during automatic workflow pumping.
        self.stepper_min_speed_rpm = max(
            1,
            int(stepper_cfg.get("min_speed_rpm", 1) or 1),
        )
        self.stepper_continuous_on: bool = False
        # Exact ml/min setpoint when speed is set via the flow slider / ramp test.
        # Integer RPM cannot hit every setpoint exactly with the linear pump model,
        # so the UI shows this commanded value instead of rpm * slope.
        self._commanded_flow_ml_per_min: Optional[int] = None
        self.flow_ramp_test_active: bool = False
        self._flow_ramp_test_ml_per_min: int = FLOW_RAMP_TEST_START_ML_PER_MIN
        self._flow_ramp_test_remaining_s: int = FLOW_RAMP_TEST_INTERVAL_MS // 1000
        self._flow_ramp_test_timer = QTimer(self)
        self._flow_ramp_test_timer.setInterval(1000)
        self._flow_ramp_test_timer.timeout.connect(self._on_flow_ramp_test_tick)
        self.rpm_flow_calibration_active: bool = False
        self._rpm_flow_calibration_rpm: int = self.stepper_speed_rpm
        self._rpm_flow_calibration_remaining_s: int = RPM_FLOW_CALIBRATION_DURATION_S
        self._rpm_flow_calibration_timer = QTimer(self)
        self._rpm_flow_calibration_timer.setInterval(RPM_FLOW_CALIBRATION_TICK_MS)
        self._rpm_flow_calibration_timer.timeout.connect(self._on_rpm_flow_calibration_tick)
        self.pid_run_active: bool = False

        # Callbacks (set by the host window).
        self.on_compressor_control_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_thresholds_change_callback: Optional[Callable[[float, float], None]] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_pid_run_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_usb_eject_callback: Optional[Callable[[], None]] = None

        self._create_widgets()
        self._setup_layout()
    
    def _create_widgets(self):
        """Create service tab widgets"""
        # Compressor group
        self.compressor_group = QGroupBox("Compressor")
        self.compressor_group.setStyleSheet(self._group_box_style("#16a34a", "13px", margin_top=8))
        
        # Stepper group
        self.outputs_group = QGroupBox("Stepper")
        self.outputs_group.setStyleSheet(self._group_box_style("#0e6a76", "13px", margin_top=8))
        
        # Output labels
        self.compressor_label = QLabel("OFF  HX --")
        self.compressor_label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
        self.compressor_label.setMinimumWidth(88)
        self.compressor_control_button = QPushButton("Run")
        self.compressor_control_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.compressor_control_button.setFixedWidth(56)
        self.compressor_control_button.setToolTip("Enable compressor temperature control")
        self.compressor_control_button.clicked.connect(self._on_compressor_control_toggle_clicked)
        self._apply_compressor_control_button_style(False)

        spin_style = """
            QDoubleSpinBox {
                font-size: 14px;
                font-weight: 700;
                background: white;
                border: 1px solid #c5d0d9;
                border-radius: 8px;
                padding: 1px 2px;
            }
        """
        compact_h = self._COMPACT_PUMP_BUTTON_HEIGHT
        self.compressor_off_temp_spin = QDoubleSpinBox()
        self.compressor_off_temp_spin.setRange(-20.0, 80.0)
        self.compressor_off_temp_spin.setDecimals(1)
        self.compressor_off_temp_spin.setSingleStep(0.1)
        self.compressor_off_temp_spin.setValue(self.compressor_off_temp_c)
        self.compressor_off_temp_spin.setFixedWidth(56)
        self.compressor_off_temp_spin.setFixedHeight(compact_h)
        self.compressor_off_temp_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compressor_off_temp_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.compressor_off_temp_spin.setStyleSheet(spin_style)
        self.compressor_off_temp_spin.valueChanged.connect(self._on_compressor_thresholds_changed)
        self.compressor_off_temp_down = QPushButton("-")
        self.compressor_off_temp_down.setFixedSize(compact_h, compact_h)
        self.compressor_off_temp_down.setStyleSheet(self._TEMP_STEP_BUTTON_STYLE)
        self.compressor_off_temp_down.clicked.connect(lambda: self.compressor_off_temp_spin.stepBy(-1))
        self.compressor_off_temp_up = QPushButton("+")
        self.compressor_off_temp_up.setFixedSize(compact_h, compact_h)
        self.compressor_off_temp_up.setStyleSheet(self._TEMP_STEP_BUTTON_STYLE)
        self.compressor_off_temp_up.clicked.connect(lambda: self.compressor_off_temp_spin.stepBy(1))

        self.compressor_on_temp_spin = QDoubleSpinBox()
        self.compressor_on_temp_spin.setRange(-20.0, 80.0)
        self.compressor_on_temp_spin.setDecimals(1)
        self.compressor_on_temp_spin.setSingleStep(0.1)
        self.compressor_on_temp_spin.setValue(self.compressor_on_temp_c)
        self.compressor_on_temp_spin.setFixedWidth(56)
        self.compressor_on_temp_spin.setFixedHeight(compact_h)
        self.compressor_on_temp_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compressor_on_temp_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.compressor_on_temp_spin.setStyleSheet(spin_style)
        self.compressor_on_temp_spin.valueChanged.connect(self._on_compressor_thresholds_changed)
        self.compressor_on_temp_down = QPushButton("-")
        self.compressor_on_temp_down.setFixedSize(compact_h, compact_h)
        self.compressor_on_temp_down.setStyleSheet(self._TEMP_STEP_BUTTON_STYLE)
        self.compressor_on_temp_down.clicked.connect(lambda: self.compressor_on_temp_spin.stepBy(-1))
        self.compressor_on_temp_up = QPushButton("+")
        self.compressor_on_temp_up.setFixedSize(compact_h, compact_h)
        self.compressor_on_temp_up.setStyleSheet(self._TEMP_STEP_BUTTON_STYLE)
        self.compressor_on_temp_up.clicked.connect(lambda: self.compressor_on_temp_spin.stepBy(1))

        self.stepper_speed_label = QLabel(self._format_speed_text(self.stepper_speed_rpm))
        self.stepper_speed_label.setStyleSheet(self._CONTROL_LABEL_STYLE)
        self.stepper_speed_label.setMinimumWidth(108)
        self.stepper_speed_label.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.stepper_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stepper_rpm_unit_label = QLabel("RPM")
        self.stepper_rpm_unit_label.setStyleSheet(self._SLIDER_UNIT_LABEL_STYLE)
        self.stepper_rpm_unit_label.setFixedWidth(52)
        self.stepper_rpm_unit_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.stepper_flow_unit_label = QLabel("ml/min")
        self.stepper_flow_unit_label.setStyleSheet(self._SLIDER_UNIT_LABEL_STYLE)
        self.stepper_flow_unit_label.setFixedWidth(52)
        self.stepper_flow_unit_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.stepper_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.stepper_speed_slider.setRange(
            min(self.stepper_min_speed_rpm, self.stepper_max_speed_rpm),
            self.stepper_max_speed_rpm,
        )
        self.stepper_speed_slider.setTickInterval(10)
        self.stepper_speed_slider.setSingleStep(1)
        self.stepper_speed_slider.setPageStep(10)
        self.stepper_speed_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.stepper_speed_slider.setValue(
            max(
                min(self.stepper_min_speed_rpm, self.stepper_max_speed_rpm),
                min(self.stepper_max_speed_rpm, self.stepper_speed_rpm),
            )
        )
        self.stepper_speed_slider.setStyleSheet(self._SLIDER_STYLE)
        self.stepper_speed_slider.valueChanged.connect(self._on_stepper_speed_changed)

        # Flow slider uses step indices (1 => 10 ml/min, 2 => 20 ml/min, ...).
        self.stepper_flow_slider = QSlider(Qt.Orientation.Horizontal)
        self.stepper_flow_slider.setTickInterval(1)
        self.stepper_flow_slider.setSingleStep(1)
        self.stepper_flow_slider.setPageStep(1)
        self.stepper_flow_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.stepper_flow_slider.setStyleSheet(self._SLIDER_STYLE)
        self._configure_flow_slider_range()
        self.stepper_flow_slider.valueChanged.connect(self._on_stepper_flow_changed)

        # Jog controls (hold to move)
        self.jog_reverse_button = QPushButton("Jog Rev")
        self.jog_reverse_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.jog_reverse_button.setStyleSheet(self._JOG_BUTTON_STYLE)
        self.jog_reverse_button.pressed.connect(lambda: self._on_jog_pressed(-1))
        self.jog_reverse_button.released.connect(self._on_jog_released)

        self.jog_forward_button = QPushButton("Jog Fwd")
        self.jog_forward_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.jog_forward_button.setStyleSheet(self._JOG_BUTTON_STYLE)
        self.jog_forward_button.pressed.connect(lambda: self._on_jog_pressed(1))
        self.jog_forward_button.released.connect(self._on_jog_released)

        self.stepper_continuous_button = QPushButton("Run")
        self.stepper_continuous_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.stepper_continuous_button.clicked.connect(self._on_stepper_continuous_toggle_clicked)
        self._apply_continuous_button_style(False)

        self.flow_ramp_test_button = QPushButton("Start Test")
        self.flow_ramp_test_button.setMinimumHeight(44)
        self.flow_ramp_test_button.clicked.connect(self._on_flow_ramp_test_clicked)
        self._apply_flow_ramp_test_button_style(False)

        self.rpm_flow_calibration_button = QPushButton("Run for 5 min")
        self.rpm_flow_calibration_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.rpm_flow_calibration_button.clicked.connect(
            self._on_rpm_flow_calibration_clicked
        )
        self._apply_rpm_flow_calibration_button_style(False)

        self.pid_run_button = QPushButton("Run with PID")
        self.pid_run_button.setFixedHeight(self._COMPACT_PUMP_BUTTON_HEIGHT)
        self.pid_run_button.setToolTip(
            "Closed-loop pump: control sensor vs the main-screen setpoint "
            "(same PID as Start Pumping)."
        )
        self.pid_run_button.clicked.connect(self._on_pid_run_clicked)
        self._apply_pid_run_button_style(False)

        self.usb_group = QGroupBox("USB logging")
        self.usb_group.setStyleSheet(self._group_box_style("#2563eb", "13px", margin_top=8))
        self.usb_status_label = QLabel("Waiting for USB")
        self.usb_status_label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
        self.usb_status_label.setWordWrap(True)
        self.usb_eject_button = QPushButton("Eject")
        self.usb_eject_button.setMinimumHeight(40)
        self.usb_eject_button.setMaximumWidth(140)
        self.usb_eject_button.setEnabled(False)
        self.usb_eject_button.clicked.connect(self._on_usb_eject_clicked)
        self._apply_usb_eject_button_style(enabled=False)

    def _make_temp_control_row(
        self,
        caption: str,
        spin: QDoubleSpinBox,
        down: QPushButton,
        up: QPushButton,
        tooltip: str = "",
    ) -> QHBoxLayout:
        """Build a compact threshold cluster: label | − value +."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        label = QLabel(caption)
        label.setStyleSheet("font-size: 11px; font-weight: 700; color: #2f3b47;")
        label.setToolTip(tooltip or caption)
        row.addWidget(label)
        row.addWidget(down)
        row.addWidget(spin)
        row.addWidget(up)
        return row

    def _make_slider_row(self, unit_label: QLabel, slider: QSlider) -> QHBoxLayout:
        """Build a labeled slider row with enough handle clearance."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)
        row.addWidget(unit_label)
        row.addWidget(slider, 1)
        return row

    def _setup_layout(self):
        """Setup service tab layout for the 800x480 touchscreen."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(6)

        # Compressor: status, run, and both setpoints on one row.
        compressor_layout = QVBoxLayout()
        compressor_layout.setContentsMargins(8, 6, 8, 6)
        compressor_layout.setSpacing(4)
        compressor_row = QHBoxLayout()
        compressor_row.setContentsMargins(0, 0, 0, 0)
        compressor_row.setSpacing(6)
        compressor_row.addWidget(self.compressor_label, 1)
        compressor_row.addWidget(self.compressor_control_button, 0)
        compressor_row.addLayout(
            self._make_temp_control_row(
                "Off",
                self.compressor_off_temp_spin,
                self.compressor_off_temp_down,
                self.compressor_off_temp_up,
                tooltip="Off below (°C)",
            )
        )
        compressor_row.addLayout(
            self._make_temp_control_row(
                "On",
                self.compressor_on_temp_spin,
                self.compressor_on_temp_down,
                self.compressor_on_temp_up,
                tooltip="On above (°C)",
            )
        )
        compressor_layout.addLayout(compressor_row)
        self.compressor_group.setLayout(compressor_layout)
        main_layout.addWidget(self.compressor_group)

        usb_layout = QHBoxLayout()
        usb_layout.setContentsMargins(8, 6, 8, 6)
        usb_layout.setSpacing(8)
        usb_layout.addWidget(self.usb_status_label, 1)
        usb_layout.addWidget(self.usb_eject_button, 0)
        self.usb_group.setLayout(usb_layout)
        main_layout.addWidget(self.usb_group)

        # Stepper: labeled sliders, readout, compact pump buttons, ramp test.
        outputs_layout = QVBoxLayout()
        outputs_layout.setContentsMargins(8, 6, 8, 6)
        outputs_layout.setSpacing(8)

        outputs_layout.addLayout(
            self._make_slider_row(self.stepper_rpm_unit_label, self.stepper_speed_slider)
        )
        outputs_layout.addLayout(
            self._make_slider_row(self.stepper_flow_unit_label, self.stepper_flow_slider)
        )

        pump_buttons = QHBoxLayout()
        pump_buttons.setContentsMargins(0, 0, 0, 0)
        pump_buttons.setSpacing(4)
        pump_buttons.addWidget(self.rpm_flow_calibration_button, 1)
        pump_buttons.addWidget(self.jog_reverse_button, 1)
        pump_buttons.addWidget(self.jog_forward_button, 1)
        pump_buttons.addWidget(self.stepper_continuous_button, 1)
        pump_buttons.addWidget(self.pid_run_button, 1)
        pump_buttons.addWidget(self.stepper_speed_label, 0)
        outputs_layout.addLayout(pump_buttons)
        outputs_layout.addWidget(self.flow_ramp_test_button)
        self.outputs_group.setLayout(outputs_layout)
        main_layout.addWidget(self.outputs_group, 1)

        self.setLayout(main_layout)

    def update_outputs(
        self,
        compressor_on: bool = None,
        compressor_control_enabled: bool = None,
        compressor_off_temp_c: float = None,
        compressor_on_temp_c: float = None,
        heat_ex_temp_c: Optional[float] = None,
        refresh_heat_ex: bool = False,
        stepper_speed_rpm: int = None,
    ):
        """Update output display"""
        if compressor_on is not None:
            self.compressor_on = compressor_on
        if compressor_control_enabled is not None:
            self.compressor_control_enabled = bool(compressor_control_enabled)
            self._apply_compressor_control_button_style(self.compressor_control_enabled)
        if compressor_off_temp_c is not None:
            self.compressor_off_temp_c = float(compressor_off_temp_c)
            if abs(self.compressor_off_temp_spin.value() - self.compressor_off_temp_c) > 0.05:
                self.compressor_off_temp_spin.setValue(self.compressor_off_temp_c)
        if compressor_on_temp_c is not None:
            self.compressor_on_temp_c = float(compressor_on_temp_c)
            if abs(self.compressor_on_temp_spin.value() - self.compressor_on_temp_c) > 0.05:
                self.compressor_on_temp_spin.setValue(self.compressor_on_temp_c)
        if refresh_heat_ex:
            self.heat_ex_temp_c = float(heat_ex_temp_c) if heat_ex_temp_c is not None else None
        if stepper_speed_rpm is not None:
            self._set_stepper_speed_rpm(int(stepper_speed_rpm), emit_callback=False)

        comp_status = "ON" if self.compressor_on else "OFF"
        comp_color = "#16a34a" if self.compressor_on else "#6b7280"
        if self.heat_ex_temp_c is not None:
            heat_text = f"HX {self.heat_ex_temp_c:.1f}°"
        else:
            heat_text = "HX --"
        self.compressor_label.setText(f"{comp_status}  {heat_text}")
        self.compressor_label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=comp_color))
        self.stepper_speed_label.setText(self._format_speed_text(self.stepper_speed_rpm))
        self._update_stepper_control_enabled_state()

    def update_usb_status(
        self,
        state: str = "waiting",
        message: str = "",
        can_eject: bool = False,
    ) -> None:
        """Update USB mirror status and eject-button enablement."""
        colors = {
            "mirroring": "#16a34a",
            "catching_up": "#0e6a76",
            "error": "#dc2626",
            "ejecting": "#d97706",
            "safe_to_remove": "#2563eb",
            "waiting": "#6b7280",
            "disabled": "#6b7280",
        }
        color = colors.get(state, "#6b7280")
        text = message or "USB logging"
        self.usb_status_label.setText(text)
        self.usb_status_label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=color))
        ejecting = state == "ejecting"
        self.usb_eject_button.setEnabled(bool(can_eject) and not ejecting)
        self.usb_eject_button.setText("Ejecting…" if ejecting else "Eject")
        self._apply_usb_eject_button_style(
            enabled=bool(can_eject) and not ejecting,
            ejecting=ejecting,
        )

    def _format_speed_text(self, rpm: int) -> str:
        if self._commanded_flow_ml_per_min is not None:
            return f"{rpm} RPM  {self._commanded_flow_ml_per_min:d} ml/min"
        ml_per_min = _pump_flow_ml_per_min(rpm, self.pump_flow_ml_per_min_per_rpm)
        return f"{rpm} RPM  {ml_per_min:.0f} ml/min"

    def _flow_setpoint_bounds(self) -> tuple[int, int]:
        """Return min/max discrete ml/min setpoints for the current RPM range."""
        slope = float(self.pump_flow_ml_per_min_per_rpm) or DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        step = PUMP_FLOW_SLIDER_STEP_ML_PER_MIN
        min_rpm = min(self.stepper_min_speed_rpm, self.stepper_max_speed_rpm)
        max_flow = _pump_flow_ml_per_min(self.stepper_max_speed_rpm, slope)
        min_flow = _pump_flow_ml_per_min(min_rpm, slope)
        lo = max(step, int(math.ceil(min_flow / step) * step))
        hi = int(math.floor(max_flow / step) * step)
        if hi < lo:
            hi = lo
        return lo, hi

    def _rpm_to_flow_setpoint(self, rpm: int) -> int:
        lo, hi = self._flow_setpoint_bounds()
        ml_per_min = _pump_flow_ml_per_min(rpm, self.pump_flow_ml_per_min_per_rpm)
        return max(lo, min(hi, _snap_ml_per_min_setpoint(ml_per_min)))

    def _flow_setpoint_to_rpm(self, ml_per_min: int) -> int:
        """Pick the integer RPM closest to the requested ml/min setpoint."""
        slope = float(self.pump_flow_ml_per_min_per_rpm) or DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        min_rpm = min(self.stepper_min_speed_rpm, self.stepper_max_speed_rpm)
        max_rpm = self.stepper_max_speed_rpm
        target = float(ml_per_min)
        exact = target / slope
        candidates = {
            max(min_rpm, min(max_rpm, int(math.floor(exact)))),
            max(min_rpm, min(max_rpm, int(math.ceil(exact)))),
            max(min_rpm, min(max_rpm, int(round(exact)))),
        }
        return min(
            candidates,
            key=lambda rpm: (
                abs(_pump_flow_ml_per_min(rpm, slope) - target),
                abs(rpm - exact),
            ),
        )

    def _flow_ml_to_slider_step(self, ml_per_min: int) -> int:
        return max(1, int(ml_per_min) // PUMP_FLOW_SLIDER_STEP_ML_PER_MIN)

    def _flow_slider_step_to_ml(self, step: int) -> int:
        return max(PUMP_FLOW_SLIDER_STEP_ML_PER_MIN, int(step) * PUMP_FLOW_SLIDER_STEP_ML_PER_MIN)

    def _configure_flow_slider_range(self):
        """Configure the ml/min slider range/value from the current RPM/slope."""
        lo, hi = self._flow_setpoint_bounds()
        if self._commanded_flow_ml_per_min is not None:
            setpoint = max(lo, min(hi, int(self._commanded_flow_ml_per_min)))
        else:
            setpoint = self._rpm_to_flow_setpoint(self.stepper_speed_rpm)
        blocked = self.stepper_flow_slider.blockSignals(True)
        try:
            self.stepper_flow_slider.setRange(
                self._flow_ml_to_slider_step(lo),
                self._flow_ml_to_slider_step(hi),
            )
            self.stepper_flow_slider.setValue(self._flow_ml_to_slider_step(setpoint))
        finally:
            self.stepper_flow_slider.blockSignals(blocked)

    def _sync_linked_speed_sliders(self, rpm: int):
        """Keep RPM and ml/min sliders aligned without re-entering handlers."""
        rpm = int(rpm)
        if self._commanded_flow_ml_per_min is not None:
            flow_setpoint = int(self._commanded_flow_ml_per_min)
        else:
            flow_setpoint = self._rpm_to_flow_setpoint(rpm)
        flow_step = self._flow_ml_to_slider_step(flow_setpoint)

        blocked_rpm = self.stepper_speed_slider.blockSignals(True)
        try:
            if self.stepper_speed_slider.value() != rpm:
                self.stepper_speed_slider.setValue(rpm)
        finally:
            self.stepper_speed_slider.blockSignals(blocked_rpm)

        blocked_flow = self.stepper_flow_slider.blockSignals(True)
        try:
            if self.stepper_flow_slider.value() != flow_step:
                self.stepper_flow_slider.setValue(flow_step)
        finally:
            self.stepper_flow_slider.blockSignals(blocked_flow)

    def _set_stepper_speed_rpm(
        self,
        rpm: int,
        *,
        emit_callback: bool = True,
        flow_setpoint_ml_per_min: Optional[int] = None,
        clear_flow_setpoint: bool = False,
    ):
        """Apply a stepper speed and keep both speed sliders in sync."""
        min_rpm = min(self.stepper_min_speed_rpm, self.stepper_max_speed_rpm)
        rpm = max(min_rpm, min(self.stepper_max_speed_rpm, int(rpm)))
        if flow_setpoint_ml_per_min is not None:
            self._commanded_flow_ml_per_min = int(flow_setpoint_ml_per_min)
        elif clear_flow_setpoint:
            self._commanded_flow_ml_per_min = None
        elif (
            self._commanded_flow_ml_per_min is not None
            and self._flow_setpoint_to_rpm(self._commanded_flow_ml_per_min) != rpm
        ):
            # External RPM no longer matches the commanded flow setpoint.
            self._commanded_flow_ml_per_min = None
        self.stepper_speed_rpm = rpm
        self._sync_linked_speed_sliders(rpm)
        self.stepper_speed_label.setText(self._format_speed_text(self.stepper_speed_rpm))
        if emit_callback and self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(self.stepper_speed_rpm)

    def _on_stepper_speed_changed(self, value: int):
        """Handle RPM slider changes; keep the ml/min slider in sync."""
        self._set_stepper_speed_rpm(
            int(value),
            emit_callback=True,
            clear_flow_setpoint=True,
        )

    def _on_stepper_flow_changed(self, value: int):
        """Handle ml/min slider changes; convert setpoint to RPM and sync."""
        ml_per_min = self._flow_slider_step_to_ml(int(value))
        lo, hi = self._flow_setpoint_bounds()
        ml_per_min = max(lo, min(hi, ml_per_min))
        self._set_stepper_speed_rpm(
            self._flow_setpoint_to_rpm(ml_per_min),
            emit_callback=True,
            flow_setpoint_ml_per_min=ml_per_min,
        )

    def _on_compressor_control_toggle_clicked(self):
        self.compressor_control_enabled = not self.compressor_control_enabled
        self._apply_compressor_control_button_style(self.compressor_control_enabled)
        if self.on_compressor_control_toggle_callback:
            self.on_compressor_control_toggle_callback(self.compressor_control_enabled)

    def _on_compressor_thresholds_changed(self, _value: Optional[float] = None):
        off_c = round(float(self.compressor_off_temp_spin.value()), 1)
        on_c = round(float(self.compressor_on_temp_spin.value()), 1)
        if on_c <= off_c:
            on_c = round(off_c + 0.1, 1)
            if abs(self.compressor_on_temp_spin.value() - on_c) > 0.05:
                self.compressor_on_temp_spin.setValue(on_c)
        self.compressor_off_temp_c = off_c
        self.compressor_on_temp_c = on_c
        if self.on_compressor_thresholds_change_callback:
            self.on_compressor_thresholds_change_callback(off_c, on_c)

    def _apply_compressor_control_button_style(self, control_enabled: bool):
        # Label reflects current state; color matches state (green = active).
        if control_enabled:
            text = "Stop"
            bg = "#16a34a"
            hover = "#15803d"
            border = "#15803d"
        else:
            text = "Run"
            bg = "#6b7280"
            hover = "#4b5563"
            border = "#4b5563"
        self.compressor_control_button.setText(text)
        self.compressor_control_button.setToolTip(
            "Disable compressor temperature control"
            if control_enabled
            else "Enable compressor temperature control"
        )
        self.compressor_control_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 11px;
                font-weight: 700;
                border-radius: 8px;
                padding: 4px 6px;
                border: 1px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def _apply_usb_eject_button_style(self, enabled: bool, ejecting: bool = False) -> None:
        if ejecting:
            bg, hover, border = "#d97706", "#b45309", "#b45309"
        elif enabled:
            bg, hover, border = "#2563eb", "#1d4ed8", "#1d4ed8"
        else:
            bg, hover, border = "#9ca3af", "#9ca3af", "#6b7280"
        self.usb_eject_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 13px;
                font-weight: 700;
                border-radius: 10px;
                padding: 8px 12px;
                border: 2px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #9ca3af;
                border-color: #6b7280;
                color: #f9fafb;
            }}
        """)

    def _on_usb_eject_clicked(self) -> None:
        if self.on_usb_eject_callback:
            self.on_usb_eject_callback()

    def _on_jog_pressed(self, direction: int):
        """Start jog in the given direction (-1 reverse, +1 forward)."""
        if self.on_stepper_jog_start_callback:
            self.on_stepper_jog_start_callback(direction)

    def _on_jog_released(self):
        """Stop jog movement when the jog button is released."""
        if self.on_stepper_jog_stop_callback:
            self.on_stepper_jog_stop_callback()

    def _on_stepper_continuous_toggle_clicked(self):
        """Toggle continuous forward motion ON/OFF."""
        self._set_continuous_run(not self.stepper_continuous_on)

    def _set_continuous_run(self, enabled: bool):
        """Set continuous run state and notify the host if it changed."""
        enabled = bool(enabled)
        if enabled:
            self.stop_pid_run()
        if self.stepper_continuous_on == enabled:
            return
        self.stepper_continuous_on = enabled
        self._apply_continuous_button_style(self.stepper_continuous_on)
        self._update_stepper_control_enabled_state()
        if self.on_stepper_continuous_toggle_callback:
            self.on_stepper_continuous_toggle_callback(self.stepper_continuous_on)

    def _apply_continuous_button_style(self, is_on: bool):
        # Action-oriented labels: tap RUN to start, STOP to halt.
        if is_on:
            text = "Stop"
            bg = "#dc2626"
            hover = "#b91c1c"
            border = "#991b1b"
        else:
            text = "Run"
            bg = "#0e6a76"
            hover = "#0b565f"
            border = "#0b565f"
        self.stepper_continuous_button.setText(text)
        self.stepper_continuous_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 11px;
                font-weight: 700;
                border-radius: 8px;
                padding: 4px 6px;
                border: 1px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def _update_stepper_control_enabled_state(self):
        """Disable jog / open-loop controls while a motor mode is active."""
        jog_enabled = not self.stepper_continuous_on and not self.pid_run_active
        self.jog_reverse_button.setEnabled(jog_enabled)
        self.jog_forward_button.setEnabled(jog_enabled)
        self.stepper_continuous_button.setEnabled(not self.pid_run_active)
        self.rpm_flow_calibration_button.setEnabled(not self.pid_run_active)
        self.flow_ramp_test_button.setEnabled(not self.pid_run_active)
        sliders_enabled = not self.pid_run_active
        self.stepper_speed_slider.setEnabled(sliders_enabled)
        self.stepper_flow_slider.setEnabled(sliders_enabled)

    def _on_flow_ramp_test_clicked(self):
        """Toggle the timed flow-ramp test."""
        if self.flow_ramp_test_active:
            self.stop_flow_ramp_test()
        else:
            self.start_flow_ramp_test()

    def start_flow_ramp_test(self):
        """Start at 10 ml/min, run pump, ramp +10 every 2 min."""
        if self.flow_ramp_test_active:
            return
        self.stop_pid_run()
        self.stop_rpm_flow_calibration()
        lo, hi = self._flow_setpoint_bounds()
        start_ml = max(lo, min(hi, FLOW_RAMP_TEST_START_ML_PER_MIN))
        self.flow_ramp_test_active = True
        self._flow_ramp_test_ml_per_min = start_ml
        self._flow_ramp_test_remaining_s = FLOW_RAMP_TEST_INTERVAL_MS // 1000
        self._apply_flow_ramp_test_button_style(True)
        self._set_stepper_speed_rpm(
            self._flow_setpoint_to_rpm(start_ml),
            emit_callback=True,
            flow_setpoint_ml_per_min=start_ml,
        )
        self._set_continuous_run(True)
        self._flow_ramp_test_timer.start()

    def stop_flow_ramp_test(self):
        """Stop the ramp timer and continuous pump run."""
        if not self.flow_ramp_test_active and not self._flow_ramp_test_timer.isActive():
            return
        self.flow_ramp_test_active = False
        self._flow_ramp_test_timer.stop()
        self._flow_ramp_test_remaining_s = FLOW_RAMP_TEST_INTERVAL_MS // 1000
        self._apply_flow_ramp_test_button_style(False)
        self._set_continuous_run(False)

    def _on_flow_ramp_test_tick(self):
        """Count down to the next +10 ml/min step; stop at the max setpoint."""
        if not self.flow_ramp_test_active:
            return
        self._flow_ramp_test_remaining_s -= 1
        if self._flow_ramp_test_remaining_s > 0:
            self._apply_flow_ramp_test_button_style(True)
            return
        _lo, hi = self._flow_setpoint_bounds()
        next_ml = self._flow_ramp_test_ml_per_min + FLOW_RAMP_TEST_STEP_ML_PER_MIN
        if next_ml > hi:
            self.stop_flow_ramp_test()
            return
        self._flow_ramp_test_ml_per_min = next_ml
        self._flow_ramp_test_remaining_s = FLOW_RAMP_TEST_INTERVAL_MS // 1000
        self._set_stepper_speed_rpm(
            self._flow_setpoint_to_rpm(next_ml),
            emit_callback=True,
            flow_setpoint_ml_per_min=next_ml,
        )
        self._apply_flow_ramp_test_button_style(True)

    def _apply_flow_ramp_test_button_style(self, active: bool):
        if active:
            remaining = max(0, int(self._flow_ramp_test_remaining_s))
            minutes, seconds = divmod(remaining, 60)
            text = (
                f"Stop Test ({self._flow_ramp_test_ml_per_min} ml/min "
                f"{minutes}:{seconds:02d})"
            )
            bg = "#dc2626"
            hover = "#b91c1c"
            border = "#991b1b"
        else:
            text = "Start Flow Ramp Test"
            bg = "#0e6a76"
            hover = "#0b565f"
            border = "#0b565f"
        self.flow_ramp_test_button.setText(text)
        self.flow_ramp_test_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 12px;
                font-weight: 700;
                border-radius: 12px;
                padding: 10px 14px;
                border: 1px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def _on_rpm_flow_calibration_clicked(self):
        """Toggle a fixed-RPM pump run used for RPM→flow volume calibration."""
        if self.rpm_flow_calibration_active:
            self.stop_rpm_flow_calibration()
        else:
            self.start_rpm_flow_calibration()

    def start_rpm_flow_calibration(self):
        """Run the pump at the current slider RPM for 5 minutes, then stop."""
        if self.rpm_flow_calibration_active:
            return
        self.stop_pid_run()
        self.stop_flow_ramp_test()
        self._rpm_flow_calibration_rpm = int(self.stepper_speed_rpm)
        self._rpm_flow_calibration_remaining_s = RPM_FLOW_CALIBRATION_DURATION_S
        self.rpm_flow_calibration_active = True
        self._apply_rpm_flow_calibration_button_style(True)
        self._set_stepper_speed_rpm(
            self._rpm_flow_calibration_rpm,
            emit_callback=True,
            clear_flow_setpoint=True,
        )
        self._set_continuous_run(True)
        self._rpm_flow_calibration_timer.start()

    def stop_rpm_flow_calibration(self):
        """Stop the calibration timer and continuous pump run."""
        if (
            not self.rpm_flow_calibration_active
            and not self._rpm_flow_calibration_timer.isActive()
        ):
            return
        self.rpm_flow_calibration_active = False
        self._rpm_flow_calibration_timer.stop()
        self._rpm_flow_calibration_remaining_s = RPM_FLOW_CALIBRATION_DURATION_S
        self._apply_rpm_flow_calibration_button_style(False)
        self._set_continuous_run(False)

    def _on_rpm_flow_calibration_tick(self):
        """Count down the calibration window; stop the pump at zero."""
        if not self.rpm_flow_calibration_active:
            return
        self._rpm_flow_calibration_remaining_s -= 1
        if self._rpm_flow_calibration_remaining_s <= 0:
            self.stop_rpm_flow_calibration()
            return
        self._apply_rpm_flow_calibration_button_style(True)

    def _apply_rpm_flow_calibration_button_style(self, active: bool):
        if active:
            remaining = max(0, int(self._rpm_flow_calibration_remaining_s))
            minutes, seconds = divmod(remaining, 60)
            text = f"Stop {minutes}:{seconds:02d}"
            bg = "#dc2626"
            hover = "#b91c1c"
            border = "#991b1b"
        else:
            text = "Run for 5 min"
            bg = "#0e6a76"
            hover = "#0b565f"
            border = "#0b565f"
        self.rpm_flow_calibration_button.setText(text)
        self.rpm_flow_calibration_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 11px;
                font-weight: 700;
                border-radius: 8px;
                padding: 4px 6px;
                border: 1px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def _on_pid_run_clicked(self):
        """Toggle closed-loop PID pump run (same controller as Start Pumping)."""
        if self.pid_run_active:
            self.stop_pid_run()
        else:
            self.start_pid_run()

    def start_pid_run(self):
        """Start the pump under PID control vs the main-screen setpoint."""
        if self.pid_run_active:
            return
        self.stop_flow_ramp_test()
        self.stop_rpm_flow_calibration()
        if self.stepper_continuous_on:
            self.stepper_continuous_on = False
            self._apply_continuous_button_style(False)
        self.pid_run_active = True
        self._apply_pid_run_button_style(True)
        self._update_stepper_control_enabled_state()
        if self.on_pid_run_toggle_callback:
            self.on_pid_run_toggle_callback(True)

    def stop_pid_run(self, *, notify: bool = True):
        """Stop a service-page PID run and restore open-loop controls."""
        if not self.pid_run_active:
            return
        self.pid_run_active = False
        self._apply_pid_run_button_style(False)
        self._update_stepper_control_enabled_state()
        if notify and self.on_pid_run_toggle_callback:
            self.on_pid_run_toggle_callback(False)

    def _apply_pid_run_button_style(self, active: bool):
        if active:
            text = "Stop PID"
            bg = "#dc2626"
            hover = "#b91c1c"
            border = "#991b1b"
        else:
            text = "Run with PID"
            bg = "#0e6a76"
            hover = "#0b565f"
            border = "#0b565f"
        self.pid_run_button.setText(text)
        self.pid_run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 11px;
                font-weight: 700;
                border-radius: 8px;
                padding: 4px 6px;
                border: 1px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #9ca3af;
                border-color: #6b7280;
                color: #f9fafb;
            }}
        """)

    @staticmethod
    def _group_box_style(border_color: str, font_size: str, bg_color: str = "white", margin_top: int = 10) -> str:
        return f"""
            QGroupBox {{
                font-weight: bold;
                font-size: {font_size};
                border: 2px solid {border_color};
                border-radius: 8px;
                margin-top: {margin_top}px;
                padding-top: 12px;
                background-color: {bg_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #1f2937;
            }}
        """


class Service2Tab(QWidget):
    """Status tab showing digital inputs. Also caches temperatures for the graphs."""
    _LABEL_NEUTRAL_STYLE = "font-size: 12px; padding: 6px; color: #5c6b79;"
    _LABEL_STRONG_TEMPLATE = "font-size: 12px; padding: 6px; color: {color}; font-weight: 600;"

    _DEFAULT_DIGITAL_SENSOR_NAMES = ("Level Low", "Level Critical", "Cartridge In Place")

    def __init__(
        self,
        sensor_names: list[str],
        pressure_sensor_names: Optional[list[str]] = None,
        digital_sensor_names: Optional[list[str]] = None,
    ):
        super().__init__()
        self.sensor_names = list(sensor_names)
        self.digital_sensor_names = list(
            digital_sensor_names
            if digital_sensor_names is not None
            else self._DEFAULT_DIGITAL_SENSOR_NAMES
        )
        self.sensor_states: dict = {}
        self.temp_values = {name: float("nan") for name in self.sensor_names}
        self.digital_labels = {}
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        self.digital_group = QGroupBox("Digital Status")
        self.digital_group.setStyleSheet(ServiceTab._group_box_style("#3b82f6", "10px", margin_top=6))
        for name in self.digital_sensor_names:
            label = QLabel(f"{name}: --")
            label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
            self.digital_labels[name] = label

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(4)

        digital_layout = QHBoxLayout()
        for name in self.digital_sensor_names:
            digital_layout.addWidget(self.digital_labels[name])
        self.digital_group.setLayout(digital_layout)
        main_layout.addWidget(self.digital_group)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_actuators(self, *args, **kwargs):
        """Kept for API compatibility; actuators are not shown on this tab."""

    def update_sensors(self, sensor_states: dict):
        """Update digital sensor display."""
        self.sensor_states = sensor_states
        for name, state in sensor_states.items():
            label = self.digital_labels.get(name)
            if label is None:
                continue
            status = "HIGH" if state else "LOW"
            color = "#16a34a" if state else "#dc2626"
            label.setText(f"{name}: {status}")
            label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=color))

    def update_temperatures(self, temps: Optional[dict] = None):
        """Cache logical temperatures for the main and advanced graphs."""
        temps = temps or {}
        for name in self.sensor_names:
            value = temps.get(name, float("nan"))
            try:
                self.temp_values[name] = float(value)
            except (TypeError, ValueError):
                self.temp_values[name] = float("nan")

    def update_pressures(self, pressures: Optional[dict] = None):
        """Kept for API compatibility; pressures are not shown on this tab."""


_Y_TICK_COUNT = 7
_Y_TICK_INTERVALS = _Y_TICK_COUNT - 1


def _tick_decimals(fmt: str) -> int:
    """Decimal places implied by a format string such as ``{:.1f}``."""
    try:
        sample = fmt.format(0.0)
    except (IndexError, ValueError):
        return 1
    if "." not in sample:
        return 0
    return len(sample.split(".", 1)[1])


def _snap_axis_range(
    y_min: float,
    y_max: float,
    decimals: int,
    n_intervals: int = _Y_TICK_INTERVALS,
) -> tuple[float, float]:
    """Expand a Y range so major ticks land on values with ``decimals`` places.

    Graphs draw a fixed number of equally spaced labels. Using the raw data
    range puts those lines at values like 1.173 that then display as 1.2.
    Integer units of ``10**(-decimals)`` keep every tick equal to its label.
    """
    scale = 10 ** max(0, int(decimals))
    lo, hi = (y_min, y_max) if y_min <= y_max else (y_max, y_min)
    i_min = math.floor(lo * scale + 1e-9)
    i_max = math.ceil(hi * scale - 1e-9)
    if i_max <= i_min:
        i_max = i_min + n_intervals
    i_step = max(1, math.ceil((i_max - i_min) / n_intervals))
    i_max = i_min + n_intervals * i_step
    return i_min / scale, i_max / scale


def _axis_tick_values(
    y_min: float,
    y_max: float,
    decimals: int,
    n_intervals: int = _Y_TICK_INTERVALS,
) -> list[float]:
    """Major-tick values matching ``_snap_axis_range``."""
    scale = 10 ** max(0, int(decimals))
    i_min = int(round(y_min * scale))
    i_max = int(round(y_max * scale))
    i_step = max(1, (i_max - i_min) // n_intervals)
    return [(i_min + i * i_step) / scale for i in range(n_intervals + 1)]


class MultiTemperatureGraphWidget(QWidget):
    """Custom graph widget for plotting multiple time series.

    Left-axis series share ``y_unit`` (temperatures by default). Optional
    ``right_axis_names`` are scaled independently (e.g. pump flow).
    """

    _MAX_HISTORY_SEC = 3600  # 60 minutes

    def __init__(
        self,
        series_names: list[str],
        *,
        y_unit: str = "°C",
        y_tick_format: str = "{:.1f}",
        default_y_range: tuple[float, float] = (20.0, 40.0),
        right_axis_names: Optional[set[str]] = None,
        right_axis_unit: str = "",
        right_tick_format: str = "{:.0f}",
        default_right_y_range: tuple[float, float] = (0.0, 70.0),
    ):
        super().__init__()
        self.series_names = list(series_names)
        self._y_unit = y_unit
        self._y_tick_format = y_tick_format
        self._default_y_range = default_y_range
        self._right_axis_names = set(right_axis_names or ())
        self._right_axis_unit = right_axis_unit
        self._right_tick_format = right_tick_format
        self._default_right_y_range = default_right_y_range
        self._history = deque()
        self._visible = {name: True for name in self.series_names}
        self._x_window_minutes_options = [1, 2, 5, 10, 15, 30, 60]
        self._x_window_minutes = 10
        self._x_pan_windows = 0
        # Log replay sets this so the right edge is the last sample, not wall clock.
        self.use_history_end_as_now = False
        self.setMinimumHeight(260)

        base_colors = [
            "#0ea5e9",  # Set Temp
            "#16a34a",  # CSF Temp
            "#f59e0b",  # Heat Exchanger Temp
            "#8b5cf6",  # Temp 3
            "#ef4444",  # Temp 4
            "#06b6d4",  # Temp 5
            "#84cc16",  # Temp 6
            "#ec4899",
        ]
        self._series_colors = {
            name: base_colors[i % len(base_colors)]
            for i, name in enumerate(self.series_names)
        }

    def _left_axis_names(self) -> list[str]:
        return [name for name in self.series_names if name not in self._right_axis_names]

    def set_series_visible(self, name: str, visible: bool):
        if name in self._visible:
            self._visible[name] = bool(visible)
            self.update()

    def set_window_minutes(self, minutes: int):
        """Set the visible time window (X-axis span) and reset panning."""
        self._x_window_minutes = int(minutes)
        self._x_pan_windows = 0
        self.update()

    def pan_older(self):
        """Shift the visible window one step into the past."""
        self._x_pan_windows = min(self.max_pan_windows(), self._x_pan_windows + 1)
        self.update()

    def pan_newer(self):
        """Shift the visible window one step toward the present."""
        self._x_pan_windows = max(0, self._x_pan_windows - 1)
        self.update()

    def _reference_now(self) -> float:
        """Timestamp used as the right edge of the un-panned window.

        Live expert view uses the wall/monotonic clock. Session replay sets
        ``use_history_end_as_now`` so "now" is the last logged sample.
        """
        if self.use_history_end_as_now and self._history:
            return float(self._history[-1][0])
        return time.monotonic()

    def max_pan_windows(self) -> int:
        """How many full windows back the recorded history allows."""
        if not self._history:
            return 0
        oldest_ts = self._history[0][0]
        now = self._reference_now()
        window_sec = float(self._x_window_minutes) * 60.0
        if window_sec <= 0:
            return 0
        return int(max(0.0, (now - oldest_ts) // window_sec))

    def add_sample(self, series_values: dict, timestamp: Optional[float] = None):
        now = time.monotonic() if timestamp is None else float(timestamp)
        self._history.append((now, self._normalize_series(series_values)))

        cutoff = now - self._MAX_HISTORY_SEC
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        self.update()

    def replace_history(self, entries) -> None:
        """Replace plotted samples (used when toggling raw vs averaged view)."""
        self._history.clear()
        materialized = list(entries)
        if materialized:
            cutoff = materialized[-1][0] - self._MAX_HISTORY_SEC
            materialized = [entry for entry in materialized if entry[0] >= cutoff]
        for ts, values in materialized:
            self._history.append((float(ts), self._normalize_series(values)))
        self.update()

    def _normalize_series(self, series_values: dict) -> dict:
        normalized = {}
        for name in self.series_names:
            value = series_values.get(name)
            try:
                normalized[name] = float(value)
            except (TypeError, ValueError):
                normalized[name] = float("nan")
        return normalized

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 12
        graph_x = margin
        graph_y = margin
        graph_width = max(220, self.width() - 2 * margin)
        graph_height = max(180, self.height() - 2 * margin)

        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#cbd5e1"), 2))
        painter.drawRoundedRect(graph_x, graph_y, graph_width, graph_height, 10, 10)

        has_right_axis = bool(self._right_axis_names)
        plot_left = graph_x + 44
        plot_right = graph_x + graph_width - (56 if has_right_axis else 12)
        plot_top = graph_y + (20 if has_right_axis else 12)
        # No footer legend anymore; keep only space for x-axis labels.
        plot_bottom = graph_y + graph_height - 24
        plot_width = max(1, plot_right - plot_left)
        plot_height = max(1, plot_bottom - plot_top)

        now = self._reference_now()
        window_sec = float(self._x_window_minutes) * 60.0
        end_ts = now - (self._x_pan_windows * window_sec)
        start_ts = end_ts - window_sec
        visible_entries = [
            entry for entry in self._history if start_ts <= entry[0] <= end_ts
        ]

        left_decimals = _tick_decimals(self._y_tick_format)
        right_decimals = _tick_decimals(self._right_tick_format)
        y_min, y_max = self._compute_visible_y_range(
            visible_entries,
            self._left_axis_names(),
            self._default_y_range,
            decimals=left_decimals,
        )
        right_y_min, right_y_max = self._compute_visible_y_range(
            visible_entries,
            list(self._right_axis_names),
            self._default_right_y_range,
            decimals=right_decimals,
        )

        # Dotted minor subdivisions between the major horizontal gridlines.
        minor_pen = QPen(QColor("#e2e8f0"), 1)
        minor_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(minor_pen)
        for i in range(6):
            ratio = (i + 0.5) / 6.0
            py = int(plot_bottom - ratio * plot_height)
            painter.drawLine(plot_left, py, plot_right, py)

        # Y grid and labels. Tick values are snapped to the label precision
        # (e.g. 0.1 for "{:.1f}") so each line sits on the number shown.
        left_ticks = _axis_tick_values(y_min, y_max, left_decimals)
        right_ticks = _axis_tick_values(right_y_min, right_y_max, right_decimals)
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        for i, t in enumerate(left_ticks):
            ratio = (t - y_min) / max(0.001, (y_max - y_min))
            py = int(plot_bottom - ratio * plot_height)
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(plot_left, py, plot_right, py)
            painter.setPen(QColor("#475569"))
            left_label = self._y_tick_format.format(t)
            if not has_right_axis:
                left_label = f"{left_label}{self._y_unit}"
            painter.drawText(
                QRectF(graph_x + 2, py - 8, 42, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                left_label,
            )
            if has_right_axis:
                painter.setPen(QColor("#475569"))
                painter.drawText(
                    QRectF(plot_right + 2, py - 8, 52, 16),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self._right_tick_format.format(right_ticks[i]),
                )

        if has_right_axis:
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#64748b"))
            if self._y_unit:
                painter.drawText(
                    QRectF(graph_x + 2, graph_y + 2, 42, 12),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    self._y_unit,
                )
            if self._right_axis_unit:
                painter.drawText(
                    QRectF(plot_right + 2, graph_y + 2, 52, 12),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self._right_axis_unit,
                )

        # Dotted minor subdivisions between the major vertical gridlines.
        minor_pen = QPen(QColor("#e2e8f0"), 1)
        minor_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(minor_pen)
        for i in range(10):
            ratio = (i + 0.5) / 10.0
            px = int(plot_left + ratio * plot_width)
            painter.drawLine(px, plot_top, px, plot_bottom)

        # X labels (with vertical time gridlines)
        for i in range(11):
            ratio = i / 10.0
            px = int(plot_left + ratio * plot_width)
            ts = start_ts + ratio * window_sec
            mins_ago = int(round((now - ts) / 60.0))
            label = "now" if mins_ago == 0 else f"-{mins_ago} min"
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(px, plot_top, px, plot_bottom)
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(px - 26, plot_bottom + 4, 52, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.drawLine(int(plot_left), int(plot_top), int(plot_left), int(plot_bottom))
        painter.drawLine(int(plot_left), int(plot_bottom), int(plot_right), int(plot_bottom))
        if has_right_axis:
            painter.drawLine(
                int(plot_right), int(plot_top), int(plot_right), int(plot_bottom)
            )

        if visible_entries:
            def value_to_y(value: float, axis_min: float, axis_max: float) -> float:
                t_clamped = max(axis_min, min(axis_max, value))
                ratio = (t_clamped - axis_min) / max(0.001, (axis_max - axis_min))
                return plot_bottom - ratio * plot_height

            def time_to_x(ts: float) -> float:
                ratio = (ts - start_ts) / max(0.001, window_sec)
                ratio = max(0.0, min(1.0, ratio))
                return plot_left + ratio * plot_width

            painter.save()
            painter.setClipRect(QRectF(plot_left, plot_top, plot_width, plot_height))
            for name in self.series_names:
                if not self._visible.get(name, False):
                    continue
                axis_min, axis_max = (
                    (right_y_min, right_y_max)
                    if name in self._right_axis_names
                    else (y_min, y_max)
                )
                pen = QPen(QColor(self._series_colors[name]), 2)
                path = QPainterPath()
                first = True
                for ts, values in visible_entries:
                    value = values.get(name, float("nan"))
                    if math.isnan(value):
                        continue
                    px = time_to_x(ts)
                    py = value_to_y(value, axis_min, axis_max)
                    if first:
                        path.moveTo(px, py)
                        first = False
                    else:
                        path.lineTo(px, py)
                if not first:
                    # strokePath ignores the active brush, so crossing
                    # lines don't fill-clobber each other.
                    painter.strokePath(path, pen)
            painter.restore()

    def _compute_visible_y_range(
        self,
        visible_entries,
        series_names: Optional[list[str]] = None,
        default_range: Optional[tuple[float, float]] = None,
        decimals: int = 1,
    ):
        names = list(series_names) if series_names is not None else list(self.series_names)
        fallback = default_range if default_range is not None else self._default_y_range
        values = []
        for _ts, series_values in visible_entries:
            for name in names:
                if not self._visible.get(name, False):
                    continue
                value = series_values.get(name, float("nan"))
                if not math.isnan(value):
                    values.append(value)
        if not values:
            return _snap_axis_range(fallback[0], fallback[1], decimals)
        data_min = min(values)
        data_max = max(values)
        data_range = max(0.5, data_max - data_min)
        margin = max(0.4, data_range * 0.08)
        y_min = data_min - margin
        y_max = data_max + margin
        if y_max - y_min < 1.0:
            midpoint = (y_min + y_max) / 2.0
            y_min = midpoint - 0.5
            y_max = midpoint + 0.5
        return _snap_axis_range(y_min, y_max, decimals)

    def _draw_legend(self, painter: QPainter, graph_x: int, y: int, graph_width: int):
        font = QFont("Arial", 8, QFont.Weight.DemiBold)
        painter.setFont(font)
        latest = self._history[-1][1] if self._history else {}
        entry_width = 120
        visible_names = [name for name in self.series_names if self._visible.get(name, False)]
        if not visible_names:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(
                QRectF(graph_x + 8, y - 2, graph_width - 16, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "No series selected",
            )
            return
        total_width = entry_width * len(visible_names)
        start_x = max(graph_x + 8, graph_x + graph_width - total_width - 8)
        for i, name in enumerate(visible_names):
            ex = start_x + i * entry_width
            painter.setPen(QPen(QColor(self._series_colors[name]), 3))
            painter.drawLine(ex, y + 8, ex + 14, y + 8)
            value = latest.get(name, float("nan"))
            label_text = name if math.isnan(value) else f"{name}: {value:.1f}C"
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(ex + 18, y, entry_width - 20, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label_text,
            )


class TemperatureGraphTab(QWidget):
    """Advanced tab: multi-series history graph with series toggles."""

    def __init__(
        self,
        series_names: list[str],
        *,
        graph_widget: Optional[MultiTemperatureGraphWidget] = None,
        series_units: Optional[dict[str, str]] = None,
        series_formats: Optional[dict[str, str]] = None,
        default_unit: str = "\u00b0C",
        default_format: str = "{:.1f}",
        right_column_width: int = _GRAPH_NAV_COLUMN_W,
    ):
        super().__init__()
        self.series_names = list(series_names)
        self.graph_widget = graph_widget or MultiTemperatureGraphWidget(self.series_names)
        self._series_units = dict(series_units or {})
        self._series_formats = dict(series_formats or {})
        self._default_unit = default_unit
        self._default_format = default_format
        self._right_column_width = right_column_width
        self.checkboxes = {}
        self._create_time_scale_controls()
        self._create_widgets()
        self._setup_layout()

    def _create_time_scale_controls(self):
        """Build the X-axis time-window selector and pan buttons (like main page)."""
        self.graph_nav_left_button = QPushButton("<")
        self.graph_nav_left_button.setFixedSize(_GRAPH_NAV_BTN_W, _GRAPH_NAV_BTN_H)
        self.graph_nav_left_button.setStyleSheet(_GRAPH_NAV_BUTTON_STYLE)
        self.graph_nav_left_button.clicked.connect(self._on_nav_older)

        self.graph_nav_right_button = QPushButton(">")
        self.graph_nav_right_button.setFixedSize(_GRAPH_NAV_BTN_W, _GRAPH_NAV_BTN_H)
        self.graph_nav_right_button.setStyleSheet(_GRAPH_NAV_BUTTON_STYLE)
        self.graph_nav_right_button.clicked.connect(self._on_nav_newer)

        self.graph_window_combo = QComboBox()
        for minutes in self.graph_widget._x_window_minutes_options:
            self.graph_window_combo.addItem(f"{minutes} min", minutes)
        self.graph_window_combo.setCurrentIndex(
            self.graph_widget._x_window_minutes_options.index(
                self.graph_widget._x_window_minutes
            )
        )
        self.graph_window_combo.setStyleSheet(_GRAPH_WINDOW_COMBO_STYLE)
        self.graph_window_combo.setFixedHeight(_GRAPH_NAV_BTN_H)
        self.graph_window_combo.currentIndexChanged.connect(self._on_window_changed)

    def _on_window_changed(self, index: int):
        self.graph_widget.set_window_minutes(
            int(self.graph_window_combo.itemData(index))
        )
        self._update_nav_states()

    def _on_nav_older(self):
        self.graph_widget.pan_older()
        self._update_nav_states()

    def _on_nav_newer(self):
        self.graph_widget.pan_newer()
        self._update_nav_states()

    def _update_nav_states(self):
        self.graph_nav_right_button.setEnabled(self.graph_widget._x_pan_windows > 0)
        self.graph_nav_left_button.setEnabled(
            self.graph_widget._x_pan_windows < self.graph_widget.max_pan_windows()
        )

    def _create_widgets(self):
        for name in self.series_names:
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)
            series_color = self.graph_widget._series_colors.get(name, "#1f2937")
            # The whole row is a large pressable toggle: tinted with the series
            # colour when enabled, neutral grey when disabled. The tick indicator
            # is hidden since the fill colour conveys the state.
            checkbox.setStyleSheet("""
                QCheckBox {
                    font-size: 12px;
                    font-weight: 700;
                    color: #475569;
                    min-height: 26px;
                    padding: 2px 8px;
                    border: 2px solid #cbd5e1;
                    border-radius: 8px;
                    background-color: #f1f5f9;
                }
                QCheckBox:checked {
                    color: #ffffff;
                    border: 2px solid %s;
                    background-color: %s;
                }
                QCheckBox::indicator {
                    width: 0px;
                    height: 0px;
                    margin: 0px;
                }
            """ % (series_color, series_color))
            checkbox.stateChanged.connect(
                lambda state, series_name=name: self.graph_widget.set_series_visible(
                    series_name, state == Qt.CheckState.Checked.value
                )
            )
            # Expand vertically so the touch targets share the full column height.
            checkbox.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
            )
            self.checkboxes[name] = checkbox

    def _setup_layout(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # Right-hand control column: time-scale selector on top, series toggles below.
        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(4)

        # Time-scale selector (no title label, to save space).
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(4)
        time_layout.addWidget(self.graph_nav_left_button)
        time_layout.addWidget(self.graph_window_combo, 1)
        time_layout.addWidget(self.graph_nav_right_button)
        right_column.addLayout(time_layout)

        extra = self._right_column_extra_widget()
        if extra is not None:
            right_column.addWidget(extra)

        # Series toggles (no title label) expand to fill the column height so
        # each is a large, easy touch target.
        for name in self.series_names:
            right_column.addWidget(self.checkboxes[name], 1)

        right_container = QWidget()
        right_container.setLayout(right_column)
        right_container.setFixedWidth(self._right_column_width)

        # Maximize graph area (left) while keeping touch-friendly controls (right).
        main_layout.addWidget(self.graph_widget, 1)
        main_layout.addWidget(right_container, 0)
        self.setLayout(main_layout)
        self._update_nav_states()

    def _right_column_extra_widget(self) -> Optional[QWidget]:
        """Optional control row above the series toggles (pressure smoothing)."""
        return None

    def add_sample(self, series_values: dict, timestamp: Optional[float] = None):
        self.graph_widget.add_sample(series_values, timestamp=timestamp)
        self._update_checkbox_labels(series_values)
        self._update_nav_states()

    def _update_checkbox_labels(self, series_values: dict) -> None:
        """Show the latest value next to each series name in the toggles."""
        for name, checkbox in self.checkboxes.items():
            raw = series_values.get(name)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = float("nan")
            if math.isnan(value):
                checkbox.setText(name)
            else:
                fmt = self._series_formats.get(name, self._default_format)
                unit = self._series_units.get(name, self._default_unit)
                checkbox.setText(f"{name}  {fmt.format(value)} {unit}")


class PressureServiceTab(TemperatureGraphTab):
    """Pressure and Flow graph: pressure sensors (bar) plus pump flow (ml/min)."""

    # Short enough to fit the shared control column next to its value + unit.
    PUMP_FLOW_SERIES = "Flow"
    MODE_AVG = "avg"
    MODE_MAX = "max"
    MODE_RAW = "raw"
    _WINDOW_S = 1.0
    _DEFAULT_PRESSURE_SENSOR_NAMES = (
        "Pressure 1",
        "Pressure 2",
        "Pressure 3",
        "Pressure 4",
    )

    def __init__(self, pressure_sensor_names: Optional[list[str]] = None):
        self.pressure_sensor_names = list(
            pressure_sensor_names
            if pressure_sensor_names is not None
            else self._DEFAULT_PRESSURE_SENSOR_NAMES
        )
        series_names = list(self.pressure_sensor_names) + [self.PUMP_FLOW_SERIES]
        series_units = {name: "bar" for name in self.pressure_sensor_names}
        series_units[self.PUMP_FLOW_SERIES] = "ml/min"
        series_formats = {name: "{:.2f}" for name in self.pressure_sensor_names}
        series_formats[self.PUMP_FLOW_SERIES] = "{:.0f}"
        graph_widget = MultiTemperatureGraphWidget(
            series_names,
            y_unit="bar",
            y_tick_format="{:.1f}",
            default_y_range=(0.0, 3.0),
            right_axis_names={self.PUMP_FLOW_SERIES},
            right_axis_unit="ml/min",
            right_tick_format="{:.0f}",
            default_right_y_range=(0.0, 70.0),
        )
        graph_widget._series_colors[self.PUMP_FLOW_SERIES] = "#0e6a76"
        self._display_mode = self.MODE_AVG
        self._samples = deque()
        super().__init__(
            series_names,
            graph_widget=graph_widget,
            series_units=series_units,
            series_formats=series_formats,
            default_unit="bar",
            default_format="{:.2f}",
        )
        self.pressure_values = {
            name: float("nan") for name in self.pressure_sensor_names
        }
        self.pump_speed_rpm = 0
        self.pump_flow_ml_per_min_per_rpm = DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        self._flow_ml_per_min = 0.0

    def _create_widgets(self):
        super()._create_widgets()
        self._smoothing_row = QWidget()
        layout = QVBoxLayout(self._smoothing_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        window_row = QHBoxLayout()
        window_row.setContentsMargins(0, 0, 0, 0)
        window_row.setSpacing(3)
        raw_row = QHBoxLayout()
        raw_row.setContentsMargins(0, 0, 0, 0)
        raw_row.setSpacing(3)

        self._mode_buttons = {}
        specs = (
            (self.MODE_AVG, "Avg 1s", "1-second running average of pressure", window_row),
            (self.MODE_MAX, "Max 1s", "Maximum pressure over the last second", window_row),
            (self.MODE_RAW, "Raw", "Unfiltered pressure samples", raw_row),
        )
        for mode, label, tooltip, parent_row in specs:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(mode == self.MODE_AVG)
            button.setToolTip(tooltip)
            button.setStyleSheet(_SMOOTHING_TOGGLE_STYLE)
            button.clicked.connect(lambda _checked=False, m=mode: self._on_smoothing_clicked(m))
            self._mode_buttons[mode] = button
            parent_row.addWidget(button, 1)

        layout.addLayout(window_row)
        layout.addLayout(raw_row)

        self._avg_button = self._mode_buttons[self.MODE_AVG]
        self._max_button = self._mode_buttons[self.MODE_MAX]
        self._raw_button = self._mode_buttons[self.MODE_RAW]

    def _right_column_extra_widget(self) -> Optional[QWidget]:
        return self._smoothing_row

    def _on_smoothing_clicked(self, mode: str) -> None:
        self._display_mode = mode
        for button_mode, button in self._mode_buttons.items():
            button.setChecked(button_mode == mode)
        self._rebuild_graph()

    def update_pressures(self, pressures: Optional[dict] = None):
        """Store the latest pressure readings (bar) for the next graph sample."""
        if pressures:
            self.pressure_values.update(pressures)

    def update_pump_speed(
        self,
        pump_speed_rpm: Optional[int] = None,
        flow_ml_per_min: Optional[float] = None,
    ):
        """Store pump speed / derived flow for the next graph sample."""
        if pump_speed_rpm is not None:
            self.pump_speed_rpm = max(0, int(pump_speed_rpm))
        if flow_ml_per_min is not None:
            self._flow_ml_per_min = max(0.0, float(flow_ml_per_min))
        elif pump_speed_rpm is not None:
            self._flow_ml_per_min = _pump_flow_ml_per_min(
                self.pump_speed_rpm, self.pump_flow_ml_per_min_per_rpm
            )

    def push_latest_sample(self, timestamp: Optional[float] = None) -> None:
        """Append one graph point from the latest pressure and flow values."""
        now = time.monotonic() if timestamp is None else float(timestamp)
        raw = {
            name: self.pressure_values.get(name, float("nan"))
            for name in self.pressure_sensor_names
        }
        raw[self.PUMP_FLOW_SERIES] = self._flow_ml_per_min
        self._samples.append((now, raw))
        cutoff = now - self.graph_widget._MAX_HISTORY_SEC
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
        self.add_sample(self._displayed_values(now, raw), timestamp=now)

    def _displayed_values(self, timestamp: float, raw: dict) -> dict:
        if self._display_mode == self.MODE_RAW:
            return dict(raw)
        displayed = self._window_pressures_at(timestamp)
        displayed[self.PUMP_FLOW_SERIES] = raw.get(
            self.PUMP_FLOW_SERIES, float("nan")
        )
        return displayed

    def _window_samples_at(self, timestamp: float) -> list[dict]:
        cutoff = timestamp - self._WINDOW_S
        window = []
        for ts, values in reversed(self._samples):
            if ts < cutoff:
                break
            window.append(values)
        return window

    def _window_pressures_at(self, timestamp: float) -> dict:
        window = self._window_samples_at(timestamp)
        reducer = _max_series if self._display_mode == self.MODE_MAX else _mean_series
        return reducer(window, self.pressure_sensor_names)

    def _windowed_entries(self) -> list:
        reducer = _max_series if self._display_mode == self.MODE_MAX else _mean_series
        window = deque()
        entries = []
        for ts, raw in self._samples:
            window.append((ts, raw))
            cutoff = ts - self._WINDOW_S
            while window and window[0][0] < cutoff:
                window.popleft()
            displayed = reducer(
                [values for _wts, values in window],
                self.pressure_sensor_names,
            )
            displayed[self.PUMP_FLOW_SERIES] = raw.get(
                self.PUMP_FLOW_SERIES, float("nan")
            )
            entries.append((ts, displayed))
        return entries

    def _rebuild_graph(self) -> None:
        entries = (
            list(self._samples)
            if self._display_mode == self.MODE_RAW
            else self._windowed_entries()
        )
        self.graph_widget.replace_history(entries)
        if entries:
            self._update_checkbox_labels(entries[-1][1])
        else:
            for name, checkbox in self.checkboxes.items():
                checkbox.setText(name)
        self._update_nav_states()


class PowerGraphTab(TemperatureGraphTab):
    """Catheter and cartridge cooling power (W) from ΔT and water mass flow."""

    CATHETER_SERIES = "Catheter"
    CARTRIDGE_SERIES = "Cartridge"

    def __init__(self, config: Optional[dict] = None):
        self.power_config = CoolingPowerConfig.from_config_dict(
            (config or {}).get("cooling_power")
        )
        series_names = [self.CATHETER_SERIES, self.CARTRIDGE_SERIES]
        graph_widget = MultiTemperatureGraphWidget(
            series_names,
            y_unit="W",
            y_tick_format="{:.1f}",
            default_y_range=(0.0, 40.0),
        )
        graph_widget._series_colors[self.CATHETER_SERIES] = "#0ea5e9"
        graph_widget._series_colors[self.CARTRIDGE_SERIES] = "#f59e0b"
        super().__init__(
            series_names,
            graph_widget=graph_widget,
            series_units={name: "W" for name in series_names},
            series_formats={name: "{:.1f}" for name in series_names},
            default_unit="W",
            default_format="{:.1f}",
        )
        self._temperatures: dict = {}
        self.pump_speed_rpm = 0
        self.pump_flow_ml_per_min_per_rpm = DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
        self._flow_ml_per_min = 0.0

    def update_temperatures(self, temperatures: Optional[dict] = None):
        """Store the latest logical temperatures for the next power sample."""
        if temperatures:
            self._temperatures.update(temperatures)

    def update_pump_speed(
        self,
        pump_speed_rpm: Optional[int] = None,
        flow_ml_per_min: Optional[float] = None,
    ):
        """Store pump speed / derived flow for the next power sample."""
        if pump_speed_rpm is not None:
            self.pump_speed_rpm = max(0, int(pump_speed_rpm))
        if flow_ml_per_min is not None:
            self._flow_ml_per_min = max(0.0, float(flow_ml_per_min))
        elif pump_speed_rpm is not None:
            self._flow_ml_per_min = _pump_flow_ml_per_min(
                self.pump_speed_rpm, self.pump_flow_ml_per_min_per_rpm
            )

    def _power_kwargs(self) -> dict:
        cfg = self.power_config
        return {
            "density_kg_per_l": cfg.water_density_kg_per_l,
            "cp_j_per_kg_k": cfg.water_cp_j_per_kg_k,
        }

    def push_latest_sample(self) -> None:
        """Append one graph point from the latest temperatures and flow."""
        cfg = self.power_config
        temps = self._temperatures
        kwargs = self._power_kwargs()
        series_values = {
            self.CATHETER_SERIES: catheter_cooling_power_w(
                temps.get(cfg.catheter_in_label),
                temps.get(cfg.catheter_out_label),
                self._flow_ml_per_min,
                **kwargs,
            ),
            self.CARTRIDGE_SERIES: cartridge_cooling_power_w(
                temps.get(cfg.cartridge_in_label),
                temps.get(cfg.cartridge_out_label),
                self._flow_ml_per_min,
                **kwargs,
            ),
        }
        self.add_sample(series_values)


class CalibrationTab(QWidget):
    """Advanced tab: two-point calibration controls."""

    def __init__(self, sensor_series_names: list[str]):
        super().__init__()
        self.sensor_series_names = list(sensor_series_names)
        self.on_apply_calibration_callback: Optional[Callable[[str, float, float], tuple[bool, str]]] = None
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self.calibration_table = QTableWidget(len(self.sensor_series_names), 5)
        self.calibration_table.setHorizontalHeaderLabels(
            [
                "Sensor",
                "Raw (°C)",
                "Calibrated (°C)",
                "Measured at 0°C",
                "Measured at 100°C",
            ]
        )
        self.calibration_table.verticalHeader().setVisible(False)
        self.calibration_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.calibration_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.calibration_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.calibration_table.setAlternatingRowColors(True)
        self.calibration_table.setMinimumHeight(220)

        header = self.calibration_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        for row, sensor_name in enumerate(self.sensor_series_names):
            sensor_item = QTableWidgetItem(sensor_name)
            sensor_item.setFlags(sensor_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.calibration_table.setItem(row, 0, sensor_item)

            raw_item = QTableWidgetItem("--")
            raw_item.setFlags(raw_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.calibration_table.setItem(row, 1, raw_item)

            calibrated_item = QTableWidgetItem("--")
            calibrated_item.setFlags(calibrated_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.calibration_table.setItem(row, 2, calibrated_item)

            zero_input = QLineEdit()
            zero_input.setPlaceholderText("e.g. 0.2")
            self.calibration_table.setCellWidget(row, 3, zero_input)

            hundred_input = QLineEdit()
            hundred_input.setPlaceholderText("e.g. 99.4")
            self.calibration_table.setCellWidget(row, 4, hundred_input)

        self.calibration_apply_button = QPushButton("Apply All Calibrations")
        self.calibration_apply_button.setMinimumHeight(40)
        self.calibration_apply_button.clicked.connect(self._on_apply_calibration_clicked)

        self.calibration_status_label = QLabel("")
        self.calibration_status_label.setWordWrap(True)
        self._set_calibration_status("", is_error=False)

    def _setup_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        calibration_group = QGroupBox("2-Point Calibration")
        calibration_group.setStyleSheet(ServiceTab._group_box_style("#0ea5e9", "16px"))
        calibration_layout = QVBoxLayout()
        calibration_layout.setContentsMargins(12, 14, 12, 12)
        calibration_layout.setSpacing(8)
        calibration_layout.addWidget(
            QLabel("Enter measured values for each sensor (leave blank to skip a row).")
        )
        calibration_layout.addWidget(self.calibration_table)
        calibration_layout.addWidget(self.calibration_apply_button)
        calibration_layout.addWidget(self.calibration_status_label)
        calibration_layout.addStretch()
        calibration_group.setLayout(calibration_layout)

        root_layout.addWidget(calibration_group)
        root_layout.addStretch()

    def _on_apply_calibration_clicked(self) -> None:
        if not self.sensor_series_names:
            self._set_calibration_status("No temperature sensor configured", is_error=True)
            return

        if self.on_apply_calibration_callback is None:
            self._set_calibration_status("Calibration callback not connected", is_error=True)
            return

        applied_count = 0
        failed_messages: list[str] = []

        for row, sensor_name in enumerate(self.sensor_series_names):
            zero_widget = self.calibration_table.cellWidget(row, 3)
            hundred_widget = self.calibration_table.cellWidget(row, 4)
            if not isinstance(zero_widget, QLineEdit) or not isinstance(hundred_widget, QLineEdit):
                continue

            zero_text = zero_widget.text().strip()
            hundred_text = hundred_widget.text().strip()
            if not zero_text and not hundred_text:
                continue
            if not zero_text or not hundred_text:
                failed_messages.append(f"{sensor_name}: both 0°C and 100°C are required")
                continue

            try:
                measured_at_0c = float(zero_text)
                measured_at_100c = float(hundred_text)
            except ValueError:
                failed_messages.append(f"{sensor_name}: values must be numeric")
                continue

            ok, message = self.on_apply_calibration_callback(
                sensor_name,
                measured_at_0c,
                measured_at_100c,
            )
            if ok:
                applied_count += 1
            else:
                failed_messages.append(message)

        if applied_count == 0 and not failed_messages:
            self._set_calibration_status("No rows filled in", is_error=True)
            return

        if failed_messages:
            summary = f"Applied {applied_count} calibration(s). " if applied_count > 0 else ""
            self._set_calibration_status(summary + " | ".join(failed_messages), is_error=True)
            return

        self._set_calibration_status(f"Applied {applied_count} calibration(s)", is_error=False)

    def update_current_temperatures(
        self,
        raw_temperatures: Optional[dict],
        calibrated_temperatures: Optional[dict],
    ) -> None:
        """Refresh live raw + calibrated values for each sensor row."""
        raw_temperatures = raw_temperatures or {}
        calibrated_temperatures = calibrated_temperatures or {}

        for row, sensor_name in enumerate(self.sensor_series_names):
            raw_value = raw_temperatures.get(sensor_name)
            calibrated_value = calibrated_temperatures.get(sensor_name)

            raw_item = self.calibration_table.item(row, 1)
            if raw_item is not None:
                raw_item.setText(self._format_temperature_value(raw_value))

            calibrated_item = self.calibration_table.item(row, 2)
            if calibrated_item is not None:
                calibrated_item.setText(self._format_temperature_value(calibrated_value))

    @staticmethod
    def _format_temperature_value(value: object) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "--"
        if math.isnan(number):
            return "--"
        return f"{number:.1f}"

    def _set_calibration_status(self, message: str, is_error: bool) -> None:
        color = "#b42318" if is_error else "#166534"
        self.calibration_status_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 12px;
                font-weight: 600;
                padding: 4px 2px;
            }}
        """)
        self.calibration_status_label.setText(message)


class MainScreen(QMainWindow):
    """Top-level window: hosts the main view and the advanced settings page."""

    def __init__(self, config: dict):
        super().__init__()

        self.config = config
        self.temperature_sensor_names = self._temperature_sensor_names_from_config(config)
        self.calibration_sensor_names = self._thermocouple_sensor_names_from_config(config)
        cooling_cfg = CoolingPowerConfig.from_config_dict(config.get("cooling_power"))
        self.catheter_in_temperature_label = cooling_cfg.catheter_in_label
        self.catheter_out_temperature_label = cooling_cfg.catheter_out_label
        self.primary_temperature_label = self._pick_primary_temperature_label(
            self.temperature_sensor_names
        )

        # Callbacks (set by the host application).
        self.on_start_pumping_callback: Optional[Callable] = None
        self.on_stop_pumping_callback: Optional[Callable] = None
        self.on_acknowledge_callback: Optional[Callable] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_pid_run_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_control_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_thresholds_change_callback: Optional[Callable[[float, float], None]] = None
        self.on_temperature_calibration_callback: Optional[
            Callable[[str, float, float], tuple[bool, str]]
        ] = None
        self.on_usb_eject_callback: Optional[Callable[[], None]] = None

        self._setup_window()
        self._create_widgets()
        self._setup_layout()
        self._setup_timer()
        if self._fullscreen_requested:
            # Enter fullscreen only after widgets/layout exist so the inner
            # 800x480 content frame is built before the OS takes over geometry.
            self.showFullScreen()

    @staticmethod
    def _temperature_sensor_names_from_config(config: dict) -> list[str]:
        from sensor_injection import temperature_labels_from_config

        return temperature_labels_from_config(config)

    @staticmethod
    def _thermocouple_sensor_names_from_config(config: dict) -> list[str]:
        from sensor_injection import thermocouple_labels_from_config

        return thermocouple_labels_from_config(config)

    @staticmethod
    def _pick_primary_temperature_label(sensor_names: list[str]) -> Optional[str]:
        """Prefer CSF for the main graph; fallback to first configured sensor."""
        for name in sensor_names:
            if "csf" in str(name).lower():
                return name
        return sensor_names[0] if sensor_names else None

    @staticmethod
    def _digital_sensor_names_from_config(config: dict) -> list[str]:
        return [str(s["name"]) for s in config.get("sensors", []) if s.get("name")]

    @staticmethod
    def _pressure_sensor_names_from_config(config: dict) -> list[str]:
        from sensor_injection import pressure_labels_from_config

        return pressure_labels_from_config(config)

    
    def _setup_window(self):
        """Setup main window properties.

        The UI is laid out inside a fixed ``SCREEN_WIDTH`` x ``SCREEN_HEIGHT``
        content frame (the Pi touchscreen native resolution) so the internal
        layout never reflows on page changes. The outer ``QMainWindow`` is
        either pinned to that same size in windowed mode or expands to the
        full display in fullscreen mode (with the content frame centered).
        """
        self.setWindowTitle("Cartridge Level Monitor")
        ui_config = self.config.get("ui", {})
        self._fullscreen_requested = bool(ui_config.get("fullscreen", False))
        if self._fullscreen_requested:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        else:
            self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #eef2f5;
                color: #1b2430;
                font-family: "Segoe UI";
                font-size: 12px;
            }
            QTabWidget::pane {
                border: 1px solid #d8e0e7;
                border-radius: 14px;
                background: #f8fafb;
                top: -1px;
            }
            QTabBar::tab {
                background: #e5ebf0;
                color: #40505d;
                padding: 9px 20px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #0e6a76;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #d8e1e8;
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
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #34424f;
            }
            QSlider::groove:horizontal {
                height: 10px;
                background: #d8e0e6;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #0e6a76;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 2px solid #0e6a76;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QComboBox {
                background: white;
                border: 1px solid #cfd7df;
                border-radius: 10px;
                padding: 6px 10px;
                color: #24313d;
                font-weight: 600;
            }
        """)
        
        # In windowed mode, center the 800x480 window on the active screen.
        if not self._fullscreen_requested:
            self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = max(0, (screen.width() - SCREEN_WIDTH) // 2)
        y = max(0, (screen.height() - SCREEN_HEIGHT) // 2)
        self.move(x, y)
    
    def _create_tabbed_page(
        self,
        tabs: list[tuple[str, QWidget]],
        *,
        corner_widgets: Optional[list[QWidget]] = None,
    ) -> tuple[QWidget, QTabBar, QStackedWidget]:
        """Build one sub-page: a tab bar above a stack of tab widgets.

        Returns the page plus its selector and stack so callers can query or
        change the active tab later.
        """
        selector = QTabBar()
        selector.setExpanding(False)
        selector.setStyleSheet(_PAGE_TAB_BAR_STYLE)

        stack = QStackedWidget()
        for title, widget in tabs:
            selector.addTab(title)
            stack.addWidget(widget)

        def on_current_changed(index: int) -> None:
            stack.setCurrentIndex(index)

        selector.currentChanged.connect(on_current_changed)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        header_row.addWidget(selector, 1)
        for corner_widget in corner_widgets or []:
            header_row.addWidget(corner_widget, 0, Qt.AlignmentFlag.AlignRight)
        page_layout.addLayout(header_row)
        page_layout.addWidget(stack, 1)
        return page, selector, stack

    def _create_widgets(self):
        """Create UI widgets"""
        # Main screen widget: temperature graph + setpoint controls
        ui_config = self.config.get("ui", {})
        main_view = str(ui_config.get("main_view", "spine")).lower()
        self.main_graph_widget = MainScreenWidget(
            show_cartridge=False,
            show_graph=True,
            show_temp_controls=True,
            show_spine_diagram=(main_view == "spine"),
        )
        self.main_graph_widget.catheter_in_temperature_label = self.catheter_in_temperature_label
        self.main_graph_widget.catheter_out_temperature_label = self.catheter_out_temperature_label
        if self.primary_temperature_label:
            self.main_graph_widget.primary_temperature_label = self.primary_temperature_label
        self.main_graph_widget.setMinimumHeight(280)
        self.main_graph_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Temperature graph tab (logical temps from temperature_sources)
        self.temperature_graph_tab = TemperatureGraphTab(self.temperature_sensor_names)

        # Pump flow model slope (shared with service tabs for RPM -> ml/min display).
        pump_flow_slope = float(
            self.config.get(
                "pump_flow_ml_per_min_per_rpm", DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM
            )
        )

        # Service tab
        self.service_tab = ServiceTab(
            self.config.get('stepper_motor', {}),
            self.config.get('compressor', {}),
        )
        self.service_tab.pump_flow_ml_per_min_per_rpm = pump_flow_slope
        self.service_tab._configure_flow_slider_range()
        self.service_tab.stepper_speed_label.setText(
            self.service_tab._format_speed_text(self.service_tab.stepper_speed_rpm)
        )
        self.service_tab.on_stepper_speed_change_callback = self._on_service_stepper_speed_change
        self.service_tab.on_stepper_jog_start_callback = self._on_service_stepper_jog_start
        self.service_tab.on_stepper_jog_stop_callback = self._on_service_stepper_jog_stop
        self.service_tab.on_stepper_continuous_toggle_callback = self._on_service_stepper_continuous_toggle
        self.service_tab.on_pid_run_toggle_callback = self._on_service_pid_run_toggle
        self.service_tab.on_compressor_control_toggle_callback = self._on_service_compressor_control_toggle
        self.service_tab.on_compressor_thresholds_change_callback = self._on_service_compressor_thresholds_change
        self.service_tab.on_usb_eject_callback = self._on_service_usb_eject

        # Status tab (digital inputs; also caches logical temperatures for graphs)
        pressure_sensor_names = self._pressure_sensor_names_from_config(self.config)
        digital_sensor_names = self._digital_sensor_names_from_config(self.config)
        self.service2_tab = Service2Tab(
            self.temperature_sensor_names,
            digital_sensor_names=digital_sensor_names,
        )
        self.pressure_service_tab = PressureServiceTab(
            pressure_sensor_names=pressure_sensor_names,
        )
        self.pressure_service_tab.pump_flow_ml_per_min_per_rpm = pump_flow_slope
        self.power_graph_tab = PowerGraphTab(self.config)
        self.power_graph_tab.pump_flow_ml_per_min_per_rpm = pump_flow_slope
        self.calibration_tab = CalibrationTab(self.calibration_sensor_names)
        self.calibration_tab.on_apply_calibration_callback = (
            self._on_temperature_graph_calibration_apply
        )

        self.to_main_menu_button = QPushButton()
        self.to_main_menu_button.setFixedSize(34, 34)
        self.to_main_menu_button.setIcon(_header_house_icon(20))
        self.to_main_menu_button.setIconSize(QSize(20, 20))
        self.to_main_menu_button.setToolTip("Back to main")
        self.to_main_menu_button.clicked.connect(self._show_main_view)
        self.to_main_menu_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)
        self.to_main_menu_button.setVisible(False)

        # Service launcher and fullscreen/windowed toggle: both sit in the
        # expert tab row, so they are available on every expert tab and are
        # out of reach from the main page.
        self.service_view_button = QPushButton()
        self.service_view_button.setFixedSize(34, 34)
        self.service_view_button.setIcon(_header_gear_icon(20))
        self.service_view_button.setIconSize(QSize(20, 20))
        self.service_view_button.setToolTip("Open service view")
        self.service_view_button.clicked.connect(self._show_service_view)
        self.service_view_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)

        self.window_mode_toggle_button = QPushButton()
        self.window_mode_toggle_button.setFixedSize(34, 34)
        self.window_mode_toggle_button.setIconSize(QSize(20, 20))
        self.window_mode_toggle_button.clicked.connect(self._toggle_window_mode)
        self.window_mode_toggle_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)
        self._update_window_mode_toggle_button()

        # Expert page: read-only monitoring (plots and sensor status).
        (
            self.expert_page,
            self.expert_tab_selector,
            self.expert_content_stack,
        ) = self._create_tabbed_page(
            [
                ("Temperature", self.temperature_graph_tab),
                ("Pressure and Flow", self.pressure_service_tab),
                ("Power", self.power_graph_tab),
                ("Status", self.service2_tab),
            ],
            corner_widgets=[
                self.service_view_button,
                self.window_mode_toggle_button,
            ],
        )

        # Service page: everything that acts on the hardware or its calibration.
        (
            self.service_page,
            self.service_tab_selector,
            self.service_content_stack,
        ) = self._create_tabbed_page(
            [
                ("Manual Operation", self.service_tab),
                ("Calibration", self.calibration_tab),
            ]
        )

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.main_graph_widget)
        self.content_stack.addWidget(self.expert_page)
        self.content_stack.addWidget(self.service_page)

        # Compact expert-page launcher in the window header (upper-right).
        self.expert_view_button = QPushButton()
        self.expert_view_button.setFixedSize(34, 34)
        self.expert_view_button.setIcon(_header_chart_icon(20))
        self.expert_view_button.setIconSize(QSize(20, 20))
        self.expert_view_button.setToolTip("Open expert view")
        self.expert_view_button.clicked.connect(self._show_expert_view)
        self.expert_view_button.setStyleSheet(_HEADER_ICON_BUTTON_STYLE)
        
        # Top bar: workflow state (left) and hint/error status (right). The same
        # header is used by the main page and the service pages.
        self.state_label = QLabel("State: Init")
        self.state_label.setMinimumHeight(32)
        self.state_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.state_label.setWordWrap(True)
        self.state_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self.error_status_label = ClickableLabel("")
        self.error_status_label.setMinimumHeight(32)
        self.error_status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.error_status_label.setWordWrap(True)
        self.error_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.error_status_label.setVisible(False)
        self.error_status_label.clicked.connect(self._on_error_status_clicked)
        self._latched_fault_code: Optional[FaultCode] = None
        self._latched_error_message = ""
        self._in_error_state = False

        # Session timer chip: elapsed minutes since the session started.
        self._session_start_time = time.monotonic()
        self.session_timer_label = QLabel("0 min")
        self.session_timer_label.setMinimumHeight(32)
        self.session_timer_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.session_timer_label.setStyleSheet(
            self._status_chip_style("#e9eef2", "#d6dde3", "#2f3b47")
        )

        self._workflow_state_name = "Init"

        # Pumping toggle button - acts as "START PUMPING" in Cooling state
        # and "STOP PUMPING" in Pumping state. Disabled in other states.
        self.pumping_toggle_button = QPushButton("START COOLING")#pumping = cooling patient
        self.pumping_toggle_button.setMinimumHeight(52)
        self.pumping_toggle_button.clicked.connect(self._on_pumping_toggle_clicked)
        self.pumping_toggle_button.setEnabled(False)
        self._apply_pumping_button_style(active=False)
        
        # Acknowledge Error button (initially disabled)
        self.acknowledge_button = QPushButton("ACKNOWLEDGE ERROR")
        self.acknowledge_button.setMinimumHeight(52)
        self.acknowledge_button.setStyleSheet("""
            QPushButton {
                background-color: #d06a45;
                color: white;
                font-size: 13px;
                font-weight: 600;
                border-radius: 14px;
            }
            QPushButton:hover {
                background-color: #b95735;
            }
            QPushButton:disabled {
                background-color: #d9e0e6;
                color: #8b98a5;
            }
        """)
        self.acknowledge_button.clicked.connect(self._on_acknowledge_clicked)
        self.acknowledge_button.setEnabled(False)
        # Only shown while a fault is latched (see update_state_display).
        self.acknowledge_button.setVisible(False)

        self.warnings_label = QLabel("")
        self.warnings_label.setStyleSheet("""
            QLabel {
                background-color: #f8f3d8;
                color: #6b5a1e;
                font-size: 12px;
                font-weight: 600;
                padding: 8px;
                border-radius: 10px;
                border: 1px solid #e8dca0;
            }
        """)
        self.warnings_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warnings_label.setVisible(False)
        self.warnings_label.setWordWrap(True)
    
    def _setup_layout(self):
        """Setup widget layout.

        The actual UI lives inside a fixed-size ``content_frame``
        (``SCREEN_WIDTH`` x ``SCREEN_HEIGHT``) centered within the window.
        That guarantees the layout never reflows when the outer window
        toggles between windowed and fullscreen sizes — only the gray
        margins around the frame change.
        """
        outer = QWidget()
        self.setCentralWidget(outer)
        outer_layout = QGridLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.setRowStretch(0, 1)
        outer_layout.setRowStretch(2, 1)
        outer_layout.setColumnStretch(0, 1)
        outer_layout.setColumnStretch(2, 1)

        content_frame = QWidget()
        content_frame.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
        outer_layout.addWidget(content_frame, 1, 1, Qt.AlignmentFlag.AlignCenter)

        main_layout = QVBoxLayout(content_frame)
        main_layout.setContentsMargins(8, 5, 8, 5)
        main_layout.setSpacing(4)
        
        # Header row: state (left), then corner icons (gear on main, house on service).
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        header_row.addWidget(self.state_label, 3)
        header_row.addWidget(self.error_status_label, 7)
        header_row.addWidget(self.session_timer_label, 0)
        header_row.addWidget(self.expert_view_button, 0, Qt.AlignmentFlag.AlignRight)
        header_row.addWidget(self.to_main_menu_button, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(header_row)

        # Main content area
        main_layout.addWidget(self.content_stack, 1)
        
        main_layout.addWidget(self.warnings_label)
        
        # State-specific buttons row (visible only on Main tab)
        self.state_buttons_row = QWidget()
        state_button_layout = QHBoxLayout()
        state_button_layout.setContentsMargins(0, 0, 0, 0)
        state_button_layout.setSpacing(10)
        state_button_layout.addWidget(self.pumping_toggle_button)
        state_button_layout.addWidget(self.acknowledge_button)
        self.state_buttons_row.setLayout(state_button_layout)
        # Fixed-height footer keeps action buttons from clipping on Pi.
        self.state_buttons_row.setFixedHeight(64)
        self.state_buttons_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.state_buttons_row)

        self._show_main_view()
    
    def _setup_timer(self):
        """Setup update timer"""
        self.update_timer = QTimer(self)
        # Timer connection will be set by main app
    
    def set_update_callback(self, callback):
        """Set the callback function for timer updates."""
        try:
            self.update_timer.timeout.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.update_timer.timeout.connect(callback)

    def _on_service_stepper_speed_change(self, speed_rpm: int):
        """Forward service-tab speed slider updates to app callback."""
        if self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(speed_rpm)
    
    def _on_service_stepper_jog_start(self, direction: int):
        """Forward service-tab jog start to app callback."""
        if self.on_stepper_jog_start_callback:
            self.on_stepper_jog_start_callback(direction)
    
    def _on_service_stepper_jog_stop(self):
        """Forward service-tab jog stop to app callback."""
        if self.on_stepper_jog_stop_callback:
            self.on_stepper_jog_stop_callback()

    def _on_service_stepper_continuous_toggle(self, enabled: bool):
        """Forward service-tab continuous run toggle to app callback."""
        if self.on_stepper_continuous_toggle_callback:
            self.on_stepper_continuous_toggle_callback(enabled)

    def _on_service_pid_run_toggle(self, enabled: bool):
        """Forward service-tab PID run toggle to app callback."""
        if self.on_pid_run_toggle_callback:
            self.on_pid_run_toggle_callback(enabled)

    def _on_service_compressor_control_toggle(self, enabled: bool):
        if self.on_compressor_control_toggle_callback:
            self.on_compressor_control_toggle_callback(enabled)

    def _on_service_compressor_thresholds_change(self, off_temp_c: float, on_temp_c: float):
        if self.on_compressor_thresholds_change_callback:
            self.on_compressor_thresholds_change_callback(off_temp_c, on_temp_c)

    def _on_service_usb_eject(self):
        if self.on_usb_eject_callback:
            self.on_usb_eject_callback()

    def _toggle_window_mode(self) -> None:
        """Toggle between fullscreen and fixed-size windowed mode."""
        if self.isFullScreen():
            self.setWindowFlags(Qt.WindowType.Window)
            self.showNormal()
            self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
            self._center_on_screen()
        else:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            self.showFullScreen()
        self._update_window_mode_toggle_button()

    def _update_window_mode_toggle_button(self) -> None:
        """Show an icon for the window mode the button switches to."""
        if self.isFullScreen():
            self.window_mode_toggle_button.setIcon(_header_restore_window_icon(20))
            self.window_mode_toggle_button.setToolTip("Exit fullscreen")
        else:
            self.window_mode_toggle_button.setIcon(_header_fullscreen_icon(20))
            self.window_mode_toggle_button.setToolTip("Enter fullscreen")

    def _on_temperature_graph_calibration_apply(
        self,
        sensor_name: str,
        measured_at_0c: float,
        measured_at_100c: float,
    ) -> tuple[bool, str]:
        """Forward calibration requests from Temp Graph tab to app."""
        if not self.on_temperature_calibration_callback:
            return False, "Calibration handler unavailable"
        return self.on_temperature_calibration_callback(
            sensor_name,
            measured_at_0c,
            measured_at_100c,
        )
    
    def _on_pumping_toggle_clicked(self):
        """Handle the unified pumping toggle click.
        
        Routes to the start or stop callback based on the current state:
        - Cooling state  -> start pumping
        - Pumping state  -> stop pumping
        """
        current_state = self._workflow_state_name
        if current_state in ("Pumping", "Pumping Slowly"):
            if self.on_stop_pumping_callback:
                self.on_stop_pumping_callback()
        elif current_state == "Cooling":
            if self.on_start_pumping_callback:
                self.on_start_pumping_callback()
    
    def _apply_pumping_button_style(self, active: bool):
        """Style the pumping toggle button.
        
        active=False -> "START PUMPING" (blue)
        active=True  -> "STOP PUMPING"  (orange)
        """
        if active:
            bg = "#d89a2d"
            hover = "#be8420"
        else:
            bg = "#0e6a76"
            hover = "#0b565f"
        
        self.pumping_toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 13px;
                font-weight: 600;
                border-radius: 14px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #d9e0e6;
                color: #8b98a5;
            }}
        """)
    
    def _on_acknowledge_clicked(self):
        """Handle acknowledge error button click"""
        if self.on_acknowledge_callback:
            self.on_acknowledge_callback()

    def _show_page(self, page: QWidget) -> None:
        """Show one of the three top-level pages and sync the header icons.

        The main page only offers the expert page; the service page is reached
        from the expert tab row, and both sub-pages offer the way back.
        """
        self.content_stack.setCurrentWidget(page)
        on_main = page is self.main_graph_widget
        self._set_main_action_buttons_visible(on_main)
        if on_main:
            # Acknowledge stays hidden unless a fault is currently latched.
            self.acknowledge_button.setVisible(getattr(self, "_in_error_state", False))
        self.expert_view_button.setVisible(page is not self.expert_page)
        self.to_main_menu_button.setVisible(not on_main)

    def _show_main_view(self):
        """Show the main page: minimal set of numbers plus the action buttons."""
        self._show_page(self.main_graph_widget)

    def _show_expert_view(self):
        """Show the expert page: temperature / pressure plots and status."""
        self._show_page(self.expert_page)

    def _show_service_view(self):
        """Show the service page: manual operation and calibration."""
        self._show_page(self.service_page)

    def _set_main_action_buttons_visible(self, visible: bool):
        """Show or hide the bottom action row (children follow the parent)."""
        self.state_buttons_row.setVisible(visible)

    @staticmethod
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

    @staticmethod
    def _hint_for_state(state_name: str) -> Optional[str]:
        if state_name == "Ready":
            return "Place and fill the cartridge"
        if state_name == "Cooling":
            return "Place the catheter and start cooling"
        if state_name in ("Pumping", "Pumping Slowly"):
            return "Cooling is taking place"
        return None

    def update_state_display(
        self,
        state_name: str,
        error_message: Optional[str] = None,
        workflow_state_name: Optional[str] = None,
        fault_code: Optional[FaultCode] = None,
    ):
        """
        Update state display and button visibility

        Args:
            state_name: Current state machine state
            error_message: Error message if in ERROR state
            workflow_state_name: Pre-error workflow state (kept for API compatibility)
            fault_code: Latched catalog fault, used for the error-help popup
        """
        self._workflow_state_name = state_name
        self.state_label.setText(f"State: {state_name}")

        if state_name == "Error":
            state_bg, state_border, state_text = "#f8e5db", "#d06a45", "#7e3f26"
        elif state_name in ("Init", "Ready"):
            state_bg, state_border, state_text = "#e9eef2", "#d6dde3", "#2f3b47"
        else:
            state_bg, state_border, state_text = "#dff0f2", "#8fc8cf", "#245962"

        self.state_label.setStyleSheet(
            self._status_chip_style(state_bg, state_border, state_text)
        )

        if state_name == "Error" and error_message:
            self._latched_fault_code = fault_code
            self._latched_error_message = error_message
            self.error_status_label.setText(f"{error_message}   ⓘ")
            self.error_status_label.setStyleSheet(
                self._status_chip_style("#f8e5db", "#d06a45", "#7e3f26")
            )
            self.error_status_label.setToolTip("Tap for probable causes and steps")
            self.error_status_label.set_click_enabled(True)
            self.error_status_label.setVisible(True)
            self.warnings_label.setVisible(False)
        else:
            self._latched_fault_code = None
            self._latched_error_message = ""
            self.error_status_label.set_click_enabled(False)
            self.error_status_label.setToolTip("")
            hint = self._hint_for_state(state_name)
            if hint:
                self.error_status_label.setText(hint)
                self.error_status_label.setStyleSheet(
                    self._status_chip_style("#e8f5e9", "#16a34a", "#166534")
                )
                self.error_status_label.setVisible(True)
            else:
                self.error_status_label.setText("")
                self.error_status_label.setVisible(False)
        
        # Update unified pumping toggle button (label + style + enabled state)
        if state_name in ("Pumping", "Pumping Slowly"):
            self.pumping_toggle_button.setText("STOP COOLING")
            self._apply_pumping_button_style(active=True)
            self.pumping_toggle_button.setEnabled(True)
        else:
            self.pumping_toggle_button.setText("START COOLING")
            self._apply_pumping_button_style(active=False)
            self.pumping_toggle_button.setEnabled(state_name == "Cooling")
        
        self._in_error_state = state_name == "Error"
        # The acknowledge button only exists on screen while in Error.
        self.acknowledge_button.setVisible(self._in_error_state)
        if not self._in_error_state:
            self.acknowledge_button.setEnabled(False)

    def _on_error_status_clicked(self) -> None:
        """Open operator help for the latched error (causes + recovery steps)."""
        if not getattr(self, "_in_error_state", False):
            return
        title = self._latched_error_message or "Error"
        causes, steps = operator_help(self._latched_fault_code)
        dialog = FaultHelpDialog(self, title, causes, steps)
        dialog.exec()

    def set_acknowledge_enabled(self, enabled: bool) -> None:
        """Enable ACK only when the latched fault condition has cleared."""
        if getattr(self, "_in_error_state", False):
            self.acknowledge_button.setEnabled(bool(enabled))

    def update_sensor_display(
        self,
        sensor_states: dict,
        temperatures: Optional[dict] = None,
        raw_temperatures: Optional[dict] = None,
        pressures: Optional[dict] = None,
        calibration_temperatures: Optional[dict] = None,
    ):
        """Update sensor display"""
        self._update_session_timer()
        self.service2_tab.update_sensors(sensor_states)
        self.service2_tab.update_temperatures(temperatures)
        self.service2_tab.update_pressures(pressures)
        self.pressure_service_tab.update_pressures(pressures)
        self.calibration_tab.update_current_temperatures(
            raw_temperatures,
            calibration_temperatures if calibration_temperatures is not None else temperatures,
        )
        
        # Feed CSF and catheter-input temps into the main trend graph.
        temp1 = (
            self.service2_tab.temp_values.get(self.primary_temperature_label, 0.0)
            if self.primary_temperature_label
            else 0.0
        )
        catheter_in = self.service2_tab.temp_values.get(
            self.catheter_in_temperature_label, float("nan")
        )
        catheter_out = self.service2_tab.temp_values.get(
            self.catheter_out_temperature_label, float("nan")
        )
        self.main_graph_widget.current_catheter_out_temperature = float(catheter_out)
        if temp1 == temp1 and catheter_in == catheter_in:  # skip NaN values
            self.main_graph_widget.add_temperature_sample(temp1, catheter_in)
        elif self.main_graph_widget.show_spine_diagram:
            self.main_graph_widget.update()

        # Feed selected logical temps into advanced multi-series graph tab.
        series_values = {"Set Temp": float(self.main_graph_widget.set_temperature)}
        for name in self.temperature_sensor_names:
            series_values[name] = self.service2_tab.temp_values.get(name, float("nan"))
        self.temperature_graph_tab.add_sample(series_values)

        # Keep compressor display stable unless updated by app logic.
        self.service_tab.update_outputs()
        self.service2_tab.update_actuators()
        self.pressure_service_tab.update_pump_speed()
        self.pressure_service_tab.push_latest_sample()
        self.power_graph_tab.update_temperatures(self.service2_tab.temp_values)
        self.power_graph_tab.update_pump_speed()
        self.power_graph_tab.push_latest_sample()
    
    def _update_session_timer(self) -> None:
        """Refresh the header session timer (whole minutes since start)."""
        elapsed_min = int((time.monotonic() - self._session_start_time) // 60)
        self.session_timer_label.setText(f"{elapsed_min} min")

    def reset_session_timer(self) -> None:
        """Restart the session timer from zero."""
        self._session_start_time = time.monotonic()
        self._update_session_timer()

    def set_status_message(self, message: str, is_error: bool = False):
        """No-op kept for API compatibility (status shown visually elsewhere)."""

    def update_warnings(self, messages: list[str]) -> None:
        """Show non-blocking MESSAGE-severity alerts."""
        if not messages:
            self.warnings_label.setVisible(False)
            self.warnings_label.setText("")
            return
        lines = [f"⚠ {msg}" for msg in messages]
        self.warnings_label.setText("\n".join(lines))
        self.warnings_label.setVisible(True)

    # Sentinel used to drop a previous setFixedSize(...) constraint.
    _QWIDGET_SIZE_MAX = 16777215

    def keyPressEvent(self, event):
        """Allow toggling fullscreen (F11) and leaving it (Esc)."""
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._set_fullscreen_mode(False)
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            self._set_fullscreen_mode(not self.isFullScreen())
            event.accept()
            return
        super().keyPressEvent(event)

    def _set_fullscreen_mode(self, fullscreen: bool):
        """Toggle between fullscreen frameless and windowed 800x480.

        The inner ``content_frame`` always stays at ``SCREEN_WIDTH`` x
        ``SCREEN_HEIGHT``, so this only changes how much gray padding is
        drawn around it — it does not reflow the UI.
        """
        self._fullscreen_requested = bool(fullscreen)
        if self._fullscreen_requested:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            # Drop the windowed-mode fixed size so the WM can stretch us.
            self.setMinimumSize(0, 0)
            self.setMaximumSize(self._QWIDGET_SIZE_MAX, self._QWIDGET_SIZE_MAX)
            self.showFullScreen()
        else:
            self.setWindowFlags(Qt.WindowType.Window)
            self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)
            self.showNormal()
            self._center_on_screen()
        self._update_window_mode_toggle_button()
    
    def closeEvent(self, event):
        """Handle window close event."""
        self.update_timer.stop()
        if getattr(self, "service_tab", None) is not None:
            self.service_tab.stop_flow_ramp_test()
            self.service_tab.stop_rpm_flow_calibration()
            self.service_tab.stop_pid_run()
        event.accept()


if __name__ == "__main__":
    # Standalone UI smoke test: random sensor toggles drive the display.
    import random
    import yaml

    print("Testing MainScreen...")

    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    app = QApplication(sys.argv)
    window = MainScreen(config)
    window.show()

    def _feed_random_update():
        states = {
            'Level Low': random.choice([True, False]),
            'Level Critical': random.choice([True, False]),
            'Cartridge In Place': random.choice([True, False]),
        }
        window.update_sensor_display(states)

    test_timer = QTimer()
    test_timer.timeout.connect(_feed_random_update)
    test_timer.start(2000)

    sys.exit(app.exec())


