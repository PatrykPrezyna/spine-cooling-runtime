"""
PyQt6 user interface for the Spine Cooling runtime.

Contains the main application window (`MainScreen`) and its primary
visualization/control widget (`MainScreenWidget`), plus auxiliary tab
widgets (`ServiceTab`, `Service2Tab`).
"""

import math
import sys
import time
from collections import deque
from typing import Optional, Callable

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QGridLayout, QGroupBox, QSlider, QComboBox, QStackedWidget, QCheckBox,
    QSizePolicy, QTabBar, QTabWidget, QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QLinearGradient,
    QFont, QPainterPath,
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
        font-size: 12px;
        font-weight: bold;
        border: 1px solid #334155;
        border-radius: 5px;
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
        font-size: 10px;
        font-weight: bold;
        color: #1f2937;
        background-color: white;
        border: 1px solid #94a3b8;
        border-radius: 5px;
        padding: 2px 6px;
    }
    QComboBox::drop-down { width: 14px; }
"""


class MainScreenWidget(QWidget):
    """Composite main-screen widget.

    Renders one or more of:
      - temperature history graph (with legend + x-axis controls),
      - vertical setpoint gauge with touch +/- buttons,
      - cartridge level visualization with threshold indicators.
    """

    def __init__(self, show_cartridge: bool = True, show_graph: bool = True, show_temp_controls: bool = True):
        super().__init__()
        self.show_cartridge = show_cartridge
        self.show_graph = show_graph
        self.show_temp_controls = show_temp_controls
        self.primary_temperature_label = "Temperature"
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
        self._temp_gauge_rect = QRectF()  # Updated during paint, used for hit testing
        self._dragging_temp = False
        self.on_temperature_change_callback: Optional[Callable[[float], None]] = None

        # Graph history: (timestamp, set_temp, temp1, temp2)
        self._temp_history: deque = deque()
        self._x_window_minutes_options = [5, 15, 60]
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
            # Reserve only the space needed for local graph controls so the
            # plotted graph can use more of the available height.
            bottom_safe = 76
            graph_width = self.width() - (2 * margin)
            if self.show_temp_controls:
                # Keep room for the right-side gauge and +/- controls.
                graph_width -= 200
            self._draw_temperature_graph(
                painter,
                graph_x=margin,
                graph_y=margin,
                graph_width=max(220, graph_width),
                graph_height=max(330, self.height() - (2 * margin) - bottom_safe),
            )
            if self.show_temp_controls:
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
            # Draw set temperature gauge on the right side
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
        (1, "Set Tmp", "#0ea5e9"),
        (2, "", "#16a34a"),
    )
    
    def add_temperature_sample(self, temp1: float, temp2: float):
        """Record a new sample of (set temperature, primary temp, secondary temp)."""
        now = time.monotonic()
        self._temp_history.append((now, self.set_temperature, float(temp1), float(temp2)))
        
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
        
        # Plot area (inside with padding for legend / axes)
        plot_left = graph_x + 36
        plot_right = graph_x + graph_width - 10
        plot_top = graph_y + 12
        plot_bottom = graph_y + graph_height - 42
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top
        
        now = time.monotonic()
        window_sec = float(self._x_window_minutes) * 60.0
        end_ts = now - (self._x_pan_windows * window_sec)
        start_ts = end_ts - window_sec
        visible_entries = [entry for entry in self._temp_history if start_ts <= entry[0] <= end_ts]
        y_min, y_max = self._compute_visible_y_range(visible_entries)

        # Y-axis grid lines and labels
        y_ticks = self._build_y_ticks(y_min, y_max, count=4)
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        for t in y_ticks:
            ratio = (t - y_min) / max(0.001, (y_max - y_min))
            py = int(plot_bottom - ratio * plot_height)
            painter.setPen(QPen(QColor("#cbd5e1"), 2))
            painter.drawLine(plot_left, py, plot_right, py)
            painter.setPen(QColor("#475569"))
            label_text = f"{t:.1f}" if (y_max - y_min) < 10 else f"{t:.0f}"
            painter.drawText(
                QRectF(graph_x + 2, py - 8, 30, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label_text
            )
        
        # X-axis labels (minutes ago)
        painter.setPen(QColor("#334155"))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        for i in range(6):
            ratio = i / 5.0
            px = int(plot_left + ratio * plot_width)
            ts = start_ts + ratio * window_sec
            mins_ago = int(round((now - ts) / 60.0))
            label = "now" if mins_ago == 0 else f"-{mins_ago}m"
            painter.drawText(
                QRectF(px - 20, plot_bottom + 4, 40, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label
            )

        # Legend with live values (moved to bottom footer).
        self._draw_graph_legend(painter, graph_x, graph_y + graph_height - 20, graph_width)
        
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

    def _compute_visible_y_range(self, visible_entries):
        # Y axis is intentionally locked to a fixed range so the visual
        # baseline does not shift as samples come in. Values outside the
        # range are clamped/clipped at draw time.
        del visible_entries
        return self._GRAPH_TEMP_MIN, self._GRAPH_TEMP_MAX

    @staticmethod
    def _build_y_ticks(y_min: float, y_max: float, count: int = 4):
        if count < 2:
            return [y_min, y_max]
        step = (y_max - y_min) / float(count - 1)
        return [y_min + i * step for i in range(count)]
    
    def _draw_graph_legend(self, painter: QPainter, graph_x: int, y: int, graph_width: int):
        """Draw legend entries for the graph series"""
        entries = (
            self._GRAPH_SERIES[0],
            (2, self.primary_temperature_label, self._GRAPH_SERIES[1][2]),
        )
        # Compact, right-aligned legend to avoid overlapping graph nav controls.
        entry_width = 92
        legend_total_width = entry_width * len(entries)
        start_x = max(graph_x + 112, graph_x + graph_width - legend_total_width - 8)

        font = QFont("Arial", 8, QFont.Weight.DemiBold)
        painter.setFont(font)
        latest = self._temp_history[-1] if self._temp_history else None
        
        for i, (series_index, label, color_hex) in enumerate(entries):
            ex = start_x + i * entry_width
            
            # Color line swatch
            pen = QPen(QColor(color_hex), 3)
            if series_index == 1:
                pen.setDashPattern([3, 2])
            painter.setPen(pen)
            painter.drawLine(ex, y + 8, ex + 14, y + 8)
            
            # Label
            painter.setPen(QColor("#334155"))
            label_text = label
            if latest is not None:
                label_text = f"{label}: {latest[series_index]:.1f}°C"
            painter.drawText(
                QRectF(ex + 18, y, entry_width - 20, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label_text
            )
    
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
    
    # Touch-friendly gauge geometry
    _GAUGE_WIDTH = 55
    _GAUGE_HEIGHT = 240
    _GAUGE_TOP = 50
    _GAUGE_RIGHT_MARGIN = 140  # gauge_x = self.width() - _GAUGE_RIGHT_MARGIN
    _TEMP_BUTTON_SIZE = 48
    _TEMP_BUTTON_GAP = 10
    
    def _gauge_geometry(self):
        """Return the gauge track rectangle dimensions based on widget size"""
        gauge_x = self.width() - self._GAUGE_RIGHT_MARGIN
        return gauge_x, self._GAUGE_TOP, self._GAUGE_WIDTH, self._GAUGE_HEIGHT
    
    def _draw_temperature_gauge(self, painter: QPainter):
        """Draw vertical set temperature gauge on the right side"""
        gauge_x, gauge_y, gauge_width, gauge_height = self._gauge_geometry()
        
        # Store gauge track rectangle for hit testing
        self._temp_gauge_rect = QRectF(gauge_x, gauge_y, gauge_width, gauge_height)
        
        # Current value display
        painter.setPen(QColor("#1f4f57"))
        font = QFont("Arial", 18, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(gauge_x - 18, gauge_y - 24, gauge_width + 36, 22),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            f"{self.set_temperature:.1f}\u00b0C"
        )
        
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
        handle_overhang = 12
        
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
        if not self.show_temp_controls:
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

    # Compact size used for graph X-axis nav controls (fits inside main graph).
    _GRAPH_NAV_BTN_W = 26
    _GRAPH_NAV_BTN_H = 24
    _GRAPH_NAV_COMBO_W = 64
    _GRAPH_NAV_GAP = 4

    def _create_graph_nav_controls(self):
        """Create graph X-axis controls (window size and panning)."""
        def make_nav(text: str, on_click) -> QPushButton:
            btn = QPushButton(text, self)
            btn.setFixedSize(self._GRAPH_NAV_BTN_W, self._GRAPH_NAV_BTN_H)
            btn.setStyleSheet(_GRAPH_NAV_BUTTON_STYLE)
            btn.clicked.connect(on_click)
            return btn

        self.graph_nav_left_button = make_nav("<", self._on_graph_nav_left)
        self.graph_nav_right_button = make_nav(">", self._on_graph_nav_right)

        self.graph_window_combo = QComboBox(self)
        for minutes in self._x_window_minutes_options:
            self.graph_window_combo.addItem(f"{minutes}m", minutes)
        self.graph_window_combo.setCurrentIndex(
            self._x_window_minutes_options.index(self._x_window_minutes)
        )
        self.graph_window_combo.currentIndexChanged.connect(self._on_graph_window_changed)
        self.graph_window_combo.setStyleSheet(_GRAPH_WINDOW_COMBO_STYLE)
        self.graph_window_combo.setFixedSize(self._GRAPH_NAV_COMBO_W, self._GRAPH_NAV_BTN_H)
    
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
        
        gauge_x, gauge_y, gauge_width, gauge_height = self._gauge_geometry()
        gauge_center_x = gauge_x + gauge_width // 2
        
        buttons_total_width = 2 * self._TEMP_BUTTON_SIZE + self._TEMP_BUTTON_GAP
        buttons_left = gauge_center_x - buttons_total_width // 2
        # Anchor +/- buttons just above the bottom edge of this widget, so they
        # sit immediately above the acknowledge button row in the main window.
        buttons_top = self.height() - self._TEMP_BUTTON_SIZE - 4
        # Don't let them overlap the gauge if the widget is unusually short.
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
        if not hasattr(self, "graph_window_combo"):
            return
        btn_w = self._GRAPH_NAV_BTN_W
        btn_h = self._GRAPH_NAV_BTN_H
        combo_w = self._GRAPH_NAV_COMBO_W
        gap = self._GRAPH_NAV_GAP

        # Anchor time controls to the bottom-left corner of the drawn graph.
        if self.show_graph and not self.show_cartridge:
            margin = 10
            bottom_safe = 76
            graph_x = margin
            graph_y = margin
            graph_width = self.width() - (2 * margin)
            if self.show_temp_controls:
                graph_width -= 200
            graph_width = max(220, graph_width)
            graph_height = max(330, self.height() - (2 * margin) - bottom_safe)
            left = graph_x + 6
            top = graph_y + graph_height - btn_h - 6
        else:
            top = max(10, self.height() - 116)
            left = 12

        self.graph_nav_left_button.move(left, top)
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
    _LABEL_NEUTRAL_STYLE = "font-size: 12px; padding: 6px; color: #5c6b79;"
    _LABEL_STRONG_TEMPLATE = "font-size: 12px; padding: 6px; color: {color}; font-weight: 600;"
    _CONTROL_LABEL_STYLE = "font-size: 12px; padding: 3px 6px; color: #2f3b47;"
    _JOG_BUTTON_STYLE = """
            QPushButton {
                background-color: #e7edf2;
                border: 1px solid #cfd8e0;
                font-size: 15px;
                color: #23303b;
                font-weight: 600;
                border-radius: 16px;
                padding: 12px 16px;
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
    
    def __init__(self, stepper_config: Optional[dict] = None, compressor_config: Optional[dict] = None):
        super().__init__()

        stepper_cfg = stepper_config or {}
        compressor_cfg = compressor_config or {}

        # Sensor + output state
        self.sensor_states: dict = {}
        self.compressor_on = False
        self.compressor_command_on = False
        self.compressor_manual_on = False
        self.compressor_manual_io6_high = True
        self.compressor_manual_on_time_s = 20
        self.compressor_manual_off_time_s = 40
        self.compressor_speed_rpm = int(compressor_cfg.get("default_speed_rpm", 3000))
        self.compressor_max_speed_rpm = max(100, int(compressor_cfg.get("max_speed_rpm", 6000)))
        self.stepper_speed_rpm = int(stepper_cfg.get("default_speed_rpm", 30))
        self.stepper_max_speed_rpm = max(5, int(stepper_cfg.get("max_speed_rpm", 60)))
        self.stepper_continuous_on: bool = False

        # Callbacks (set by the host window).
        self.on_compressor_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_manual_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_manual_timing_change_callback: Optional[Callable[[int, int], None]] = None
        self.on_compressor_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None

        self._create_widgets()
        self._setup_layout()
    
    def _create_widgets(self):
        """Create service tab widgets"""
        # Sensors group
        self.sensors_group = QGroupBox("Digital Sensors")
        self.sensors_group.setStyleSheet(self._group_box_style("#3b82f6", "12px"))
        
        # Sensor labels
        self.sensor_labels = {}
        sensor_names = ['Level Low', 'Level Critical', 'Cartridge In Place']
        for name in sensor_names:
            label = QLabel(f"{name}: --")
            label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
            self.sensor_labels[name] = label
        
        # Compressor group
        self.compressor_group = QGroupBox("Compressor")
        self.compressor_group.setStyleSheet(self._group_box_style("#16a34a", "12px"))
        
        # Stepper group
        self.outputs_group = QGroupBox("Stepper")
        self.outputs_group.setStyleSheet(self._group_box_style("#0e6a76", "12px"))
        
        # Output labels
        self.compressor_label = QLabel("Compressor: OFF (IO6: HIGH)")
        self.compressor_label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
        self.compressor_manual_button = QPushButton("OFF")
        self.compressor_manual_button.setMinimumHeight(36)
        self.compressor_manual_button.clicked.connect(self._on_compressor_manual_toggle_clicked)
        self._apply_compressor_manual_button_style(False)
        self.compressor_manual_on_time_spin = QSpinBox()
        self.compressor_manual_on_time_spin.setRange(1, 9999)
        self.compressor_manual_on_time_spin.setSingleStep(5)
        self.compressor_manual_on_time_spin.setValue(self.compressor_manual_on_time_s)
        self.compressor_manual_on_time_spin.setFixedWidth(80)
        self.compressor_manual_on_time_spin.setFixedHeight(48)
        self.compressor_manual_on_time_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compressor_manual_on_time_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.compressor_manual_on_time_spin.setStyleSheet("""
            QSpinBox {
                font-size: 18px;
                font-weight: 700;
            }
        """)
        self.compressor_manual_on_time_spin.valueChanged.connect(self._on_manual_timing_changed)
        self.compressor_manual_on_down_button = QPushButton("-")
        self.compressor_manual_on_down_button.setFixedSize(48, 48)
        self.compressor_manual_on_down_button.clicked.connect(
            lambda: self.compressor_manual_on_time_spin.stepBy(-1)
        )
        self.compressor_manual_on_up_button = QPushButton("+")
        self.compressor_manual_on_up_button.setFixedSize(48, 48)
        self.compressor_manual_on_up_button.clicked.connect(
            lambda: self.compressor_manual_on_time_spin.stepBy(1)
        )
        self.compressor_manual_off_time_spin = QSpinBox()
        self.compressor_manual_off_time_spin.setRange(1, 9999)
        self.compressor_manual_off_time_spin.setSingleStep(5)
        self.compressor_manual_off_time_spin.setValue(self.compressor_manual_off_time_s)
        self.compressor_manual_off_time_spin.setFixedWidth(80)
        self.compressor_manual_off_time_spin.setFixedHeight(48)
        self.compressor_manual_off_time_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compressor_manual_off_time_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.compressor_manual_off_time_spin.setStyleSheet("""
            QSpinBox {
                font-size: 18px;
                font-weight: 700;
            }
        """)
        self.compressor_manual_off_time_spin.valueChanged.connect(self._on_manual_timing_changed)
        self.compressor_manual_off_down_button = QPushButton("-")
        self.compressor_manual_off_down_button.setFixedSize(48, 48)
        self.compressor_manual_off_down_button.clicked.connect(
            lambda: self.compressor_manual_off_time_spin.stepBy(-1)
        )
        self.compressor_manual_off_up_button = QPushButton("+")
        self.compressor_manual_off_up_button.setFixedSize(48, 48)
        self.compressor_manual_off_up_button.clicked.connect(
            lambda: self.compressor_manual_off_time_spin.stepBy(1)
        )
        self.compressor_manual_off_countdown_label = QLabel("--")
        self.compressor_manual_off_countdown_label.setStyleSheet(self._CONTROL_LABEL_STYLE)
        
        self.stepper_speed_label = QLabel(f"{self.stepper_speed_rpm} RPM")
        self.stepper_speed_label.setStyleSheet(self._CONTROL_LABEL_STYLE)
        self.stepper_speed_label.setFixedHeight(52)
        self.stepper_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.stepper_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.stepper_speed_slider.setRange(5, self.stepper_max_speed_rpm)
        self.stepper_speed_slider.setTickInterval(10)
        self.stepper_speed_slider.setSingleStep(1)
        self.stepper_speed_slider.setPageStep(10)
        self.stepper_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.stepper_speed_slider.setValue(max(5, min(self.stepper_max_speed_rpm, self.stepper_speed_rpm)))
        self.stepper_speed_slider.setMinimumHeight(52)
        self.stepper_speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 16px;
                background: #d8e0e6;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #0e6a76;
                border-radius: 8px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 2px solid #0e6a76;
                width: 30px;
                margin: -9px 0;
                border-radius: 15px;
            }
        """)
        self.stepper_speed_slider.valueChanged.connect(self._on_stepper_speed_changed)

        # Jog controls (hold to move)
        self.jog_reverse_button = QPushButton("JOG REVERSE")
        self.jog_reverse_button.setMinimumHeight(48)
        self.jog_reverse_button.setStyleSheet(self._JOG_BUTTON_STYLE)
        self.jog_reverse_button.pressed.connect(lambda: self._on_jog_pressed(-1))
        self.jog_reverse_button.released.connect(self._on_jog_released)
        
        self.jog_forward_button = QPushButton("JOG FORWARD")
        self.jog_forward_button.setMinimumHeight(48)
        self.jog_forward_button.setStyleSheet(self._JOG_BUTTON_STYLE)
        self.jog_forward_button.pressed.connect(lambda: self._on_jog_pressed(1))
        self.jog_forward_button.released.connect(self._on_jog_released)

        self.stepper_continuous_button = QPushButton("RUN OFF")
        self.stepper_continuous_button.setMinimumHeight(48)
        self.stepper_continuous_button.clicked.connect(self._on_stepper_continuous_toggle_clicked)
        self._apply_continuous_button_style(False)
        
    def _setup_layout(self):
        """Setup service tab layout"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(1)
        
        # Sensors layout - horizontal arrangement
        sensors_layout = QHBoxLayout()
        for name in ['Level Low', 'Level Critical', 'Cartridge In Place']:
            sensors_layout.addWidget(self.sensor_labels[name])
        self.sensors_group.setLayout(sensors_layout)
        main_layout.addWidget(self.sensors_group)
        
        # Compressor layout
        compressor_layout = QVBoxLayout()
        compressor_layout.setContentsMargins(2, 1, 2, 1)
        compressor_layout.setSpacing(1)
        compressor_layout.addWidget(self.compressor_label)
        compressor_layout.addWidget(self.compressor_manual_button)
        manual_timing_row = QHBoxLayout()
        manual_timing_row.setContentsMargins(0, 0, 0, 0)
        manual_timing_row.setSpacing(6)
        manual_timing_row.addWidget(QLabel("On time (s):"))
        manual_timing_row.addWidget(self.compressor_manual_on_time_spin)
        manual_timing_row.addWidget(self.compressor_manual_on_down_button)
        manual_timing_row.addWidget(self.compressor_manual_on_up_button)
        manual_timing_row.addWidget(QLabel("Off time (s):"))
        manual_timing_row.addWidget(self.compressor_manual_off_time_spin)
        manual_timing_row.addWidget(self.compressor_manual_off_down_button)
        manual_timing_row.addWidget(self.compressor_manual_off_up_button)
        manual_timing_row.addWidget(self.compressor_manual_off_countdown_label)
        manual_timing_row.addStretch()
        compressor_layout.addLayout(manual_timing_row)
        self.compressor_group.setLayout(compressor_layout)
        main_layout.addWidget(self.compressor_group)

        # Stepper layout
        outputs_layout = QVBoxLayout()
        outputs_layout.setContentsMargins(2, 1, 2, 1)
        outputs_layout.setSpacing(1)
        speed_row_layout = QHBoxLayout()
        speed_row_layout.setContentsMargins(0, 0, 0, 0)
        speed_row_layout.setSpacing(6)
        speed_row_layout.addWidget(self.stepper_speed_slider, 1)
        speed_row_layout.addWidget(self.stepper_speed_label, 0, Qt.AlignmentFlag.AlignVCenter)
        outputs_layout.addLayout(speed_row_layout)
        jog_layout = QHBoxLayout()
        jog_layout.setContentsMargins(0, 0, 0, 0)
        jog_layout.setSpacing(1)
        jog_layout.addWidget(self.jog_reverse_button)
        jog_layout.addWidget(self.jog_forward_button)
        jog_layout.addWidget(self.stepper_continuous_button)
        outputs_layout.addLayout(jog_layout)
        self.outputs_group.setLayout(outputs_layout)
        main_layout.addWidget(self.outputs_group)
        
        # Add stretch to push everything to top
        main_layout.addStretch()
        
        self.setLayout(main_layout)
    
    def update_sensors(self, sensor_states: dict):
        """Update sensor display"""
        self.sensor_states = sensor_states
        for name, state in sensor_states.items():
            if name in self.sensor_labels:
                status = "HIGH" if state else "LOW"
                color = "#16a34a" if state else "#dc2626"
                self.sensor_labels[name].setText(f"{name}: {status}")
                self.sensor_labels[name].setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=color))
    
    def update_outputs(
        self,
        compressor_on: bool = None,
        compressor_speed_rpm: int = None,
        compressor_command_on: bool = None,
        compressor_manual_on: bool = None,
        compressor_manual_io6_high: bool = None,
        compressor_manual_off_countdown_s: int = None,
        compressor_manual_on_time_s: int = None,
        compressor_manual_off_time_s: int = None,
        stepper_speed_rpm: int = None,
    ):
        """Update output display"""
        if compressor_on is not None:
            self.compressor_on = compressor_on
        if compressor_speed_rpm is not None:
            self.compressor_speed_rpm = int(compressor_speed_rpm)
        if compressor_command_on is not None:
            self.compressor_command_on = bool(compressor_command_on)
        if compressor_manual_on is not None:
            self.compressor_manual_on = bool(compressor_manual_on)
            self._apply_compressor_manual_button_style(self.compressor_manual_on)
        if compressor_manual_io6_high is not None:
            self.compressor_manual_io6_high = bool(compressor_manual_io6_high)
        if compressor_manual_on_time_s is not None:
            self.compressor_manual_on_time_s = max(1, int(compressor_manual_on_time_s))
            if self.compressor_manual_on_time_spin.value() != self.compressor_manual_on_time_s:
                self.compressor_manual_on_time_spin.setValue(self.compressor_manual_on_time_s)
        if compressor_manual_off_time_s is not None:
            self.compressor_manual_off_time_s = max(1, int(compressor_manual_off_time_s))
            if self.compressor_manual_off_time_spin.value() != self.compressor_manual_off_time_s:
                self.compressor_manual_off_time_spin.setValue(self.compressor_manual_off_time_s)
        if compressor_manual_off_countdown_s is not None:
            phase_name = "OFF" if self.compressor_manual_io6_high else "ON"
            self.compressor_manual_off_countdown_label.setText(
                f"{phase_name}: {max(0, int(compressor_manual_off_countdown_s))}s"
            )
        elif compressor_manual_on is False:
            self.compressor_manual_off_countdown_label.setText("--")
        if stepper_speed_rpm is not None:
            self.stepper_speed_rpm = int(stepper_speed_rpm)
            if self.stepper_speed_slider.value() != self.stepper_speed_rpm:
                self.stepper_speed_slider.setValue(self.stepper_speed_rpm)
        
        # Update compressor label
        comp_status = "ON" if self.compressor_on else "OFF"
        comp_color = "#16a34a" if self.compressor_on else "#6b7280"
        io6_state = "HIGH" if self.compressor_manual_io6_high else "LOW"
        self.compressor_label.setText(f"Compressor: {comp_status} (IO6: {io6_state})")
        self.compressor_label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=comp_color))
        self.stepper_speed_label.setText(f"{self.stepper_speed_rpm} RPM")
        self._update_stepper_control_enabled_state()
        self.stepper_continuous_button.setEnabled(True)

    def _on_stepper_speed_changed(self, value: int):
        """Handle speed slider changes."""
        self.stepper_speed_rpm = int(value)
        self.stepper_speed_label.setText(f"{self.stepper_speed_rpm} RPM")
        if self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(self.stepper_speed_rpm)

    def _on_compressor_manual_toggle_clicked(self):
        self.compressor_manual_on = not self.compressor_manual_on
        self._apply_compressor_manual_button_style(self.compressor_manual_on)
        if self.on_compressor_manual_toggle_callback:
            self.on_compressor_manual_toggle_callback(self.compressor_manual_on)

    def _on_manual_timing_changed(self, _value: Optional[int] = None):
        on_time_s = max(1, int(self.compressor_manual_on_time_spin.value()))
        off_time_s = max(1, int(self.compressor_manual_off_time_spin.value()))
        self.compressor_manual_on_time_s = on_time_s
        self.compressor_manual_off_time_s = off_time_s
        if self.compressor_manual_on_time_spin.value() != on_time_s:
            self.compressor_manual_on_time_spin.setValue(on_time_s)
        if self.compressor_manual_off_time_spin.value() != off_time_s:
            self.compressor_manual_off_time_spin.setValue(off_time_s)
        if self.on_compressor_manual_timing_change_callback:
            self.on_compressor_manual_timing_change_callback(on_time_s, off_time_s)

    def _apply_compressor_manual_button_style(self, is_on: bool):
        if is_on:
            text = "ON"
            bg = "#22c55e"
            hover = "#16a34a"
            border = "#15803d"
        else:
            text = "OFF"
            bg = "#6b7280"
            hover = "#4b5563"
            border = "#4b5563"
        self.compressor_manual_button.setText(text)
        self.compressor_manual_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 12px;
                font-weight: 700;
                border-radius: 10px;
                padding: 6px 10px;
                border: 2px solid {border};
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

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
        self.stepper_continuous_on = not self.stepper_continuous_on
        self._apply_continuous_button_style(self.stepper_continuous_on)
        self._update_stepper_control_enabled_state()
        if self.on_stepper_continuous_toggle_callback:
            self.on_stepper_continuous_toggle_callback(self.stepper_continuous_on)

    def _apply_continuous_button_style(self, is_on: bool):
        if is_on:
            text = "OFF"
            bg = "#16a34a"
            hover = "#15803d"
        else:
            text = "ON"
            bg = "#6b7280"
            hover = "#4b5563"
        self.stepper_continuous_button.setText(text)
        self.stepper_continuous_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 15px;
                font-weight: 700;
                border-radius: 16px;
                padding: 12px 16px;
                border: 1px solid #cfd8e0;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def _update_stepper_control_enabled_state(self):
        """Disable jog buttons while continuous run is active."""
        jog_enabled = not self.stepper_continuous_on
        self.jog_reverse_button.setEnabled(jog_enabled)
        self.jog_forward_button.setEnabled(jog_enabled)

    @staticmethod
    def _group_box_style(border_color: str, font_size: str, bg_color: str = "white", margin_top: int = 10) -> str:
        return f"""
            QGroupBox {{
                font-weight: bold;
                font-size: {font_size};
                border: 2px solid {border_color};
                border-radius: 5px;
                margin-top: {margin_top}px;
                padding-top: 10px;
                background-color: {bg_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1f2937;
            }}
        """


class Service2Tab(QWidget):
    """Animal Study tab showing temperature and pressure channels."""
    _LABEL_NEUTRAL_STYLE = "font-size: 12px; padding: 6px; color: #5c6b79;"
    _LABEL_STRONG_TEMPLATE = "font-size: 12px; padding: 6px; color: {color}; font-weight: 600;"

    _DEFAULT_PRESSURE_SENSOR_NAMES = ("Pressure 1", "Pressure 2")

    def __init__(
        self,
        sensor_names: list[str],
        pressure_sensor_names: Optional[list[str]] = None,
    ):
        super().__init__()
        self.sensor_names = list(sensor_names)
        self.pressure_sensor_names = list(
            pressure_sensor_names
            if pressure_sensor_names is not None
            else self._DEFAULT_PRESSURE_SENSOR_NAMES
        )
        self.temp_values = {name: float("nan") for name in self.sensor_names}
        self.pressure_values = {name: float("nan") for name in self.pressure_sensor_names}
        self.temp_labels = {}
        self.pressure_labels = {}
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        self.temp_group = QGroupBox("Temperature Sensors")
        self.temp_group.setStyleSheet(ServiceTab._group_box_style("#f59e0b", "12px"))
        for name in self.sensor_names:
            label = QLabel(f"{name}: --°C")
            label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
            self.temp_labels[name] = label

        self.pressure_group = QGroupBox("Pressure Sensors")
        self.pressure_group.setStyleSheet(ServiceTab._group_box_style("#8b5cf6", "12px"))
        for name in self.pressure_sensor_names:
            label = QLabel(f"{name}: -- mmHg")
            label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
            self.pressure_labels[name] = label

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        overview_page = QWidget()
        overview_layout = QVBoxLayout()
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)

        temp_layout = QGridLayout()
        for index, name in enumerate(self.sensor_names):
            row = index // 2
            col = index % 2
            temp_layout.addWidget(self.temp_labels[name], row, col)
        self.temp_group.setLayout(temp_layout)
        main_layout.addWidget(self.temp_group)

        pressure_layout = QGridLayout()
        for index, name in enumerate(self.pressure_sensor_names):
            row = index // 2
            col = index % 2
            pressure_layout.addWidget(self.pressure_labels[name], row, col)
        self.pressure_group.setLayout(pressure_layout)
        main_layout.addWidget(self.pressure_group)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_temperatures(self, temps: Optional[dict] = None):
        """Update temperature display with real thermocouple values."""
        if temps:
            self.temp_values.update(temps)

        for name, value in self.temp_values.items():
            label = self.temp_labels.get(name)
            if label is None:
                continue
            if math.isnan(value):
                label.setText(f"{name}: --.-°C")
                label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
                continue
            if value < 20:
                color = "#3b82f6"
            elif value > 25:
                color = "#ef4444"
            else:
                color = "#16a34a"
            label.setText(f"{name}: {value:.1f}°C")
            label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=color))

    def update_pressures(self, pressures: Optional[dict] = None):
        """Update pressure display. Placeholder until real sensors are wired in."""
        if pressures:
            self.pressure_values.update(pressures)

        for name, value in self.pressure_values.items():
            label = self.pressure_labels.get(name)
            if label is None:
                continue
            if math.isnan(value):
                label.setText(f"{name}: --.- mmHg")
                label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
                continue
            label.setText(f"{name}: {value:.1f} mmHg")
            label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color="#8b5cf6"))


class CompressorUartTab(QWidget):
    """Advanced tab showing live UART connection + telemetry diagnostics."""

    _VALUE_STYLE = "font-size: 12px; color: #1f2937; padding: 4px 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;"
    _VALUE_MONO_STYLE = "font-family: Consolas, 'Courier New', monospace; font-size: 11px; color: #0f172a; padding: 4px 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;"
    _VALUE_OK_STYLE = "font-size: 12px; color: #166534; font-weight: 600; padding: 4px 6px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px;"
    _VALUE_WARN_STYLE = "font-size: 12px; color: #9a3412; font-weight: 600; padding: 4px 6px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 6px;"
    _VALUE_ERR_STYLE = "font-size: 12px; color: #991b1b; font-weight: 600; padding: 4px 6px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px;"

    _FAULT_FLAG_NAMES = (
        "software_overcurrent",
        "overvoltage",
        "undervoltage",
        "phase_loss",
        "stall",
        "hardware_overcurrent",
        "abnormal_phase_current",
    )

    def __init__(self, compressor_config: Optional[dict] = None):
        super().__init__()
        cfg = compressor_config or {}
        self._enabled = bool(cfg.get("enabled", False))
        self._port = str(cfg.get("port", "/dev/ttyS0"))
        self._baudrate = int(cfg.get("baudrate", 600))
        self._timeout_s = float(cfg.get("timeout_s", 0.08))
        self._max_speed_rpm = int(cfg.get("max_speed_rpm", 6000))

        self._connection_fields: dict[str, QLabel] = {}
        self._telemetry_fields: dict[str, QLabel] = {}
        self._fault_flag_labels: dict[str, QLabel] = {}

        self._create_widgets()
        self._setup_layout()

    def _add_row(self, layout: QGridLayout, row: int, key: str, label_text: str, mono: bool = False):
        key_label = QLabel(label_text)
        key_label.setStyleSheet("font-size: 12px; color: #475569;")
        value_label = QLabel("--")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setStyleSheet(self._VALUE_MONO_STYLE if mono else self._VALUE_STYLE)
        layout.addWidget(key_label, row, 0)
        layout.addWidget(value_label, row, 1)
        return value_label

    def _create_widgets(self):
        self.connection_group = QGroupBox("UART Connection")
        self.connection_group.setStyleSheet(ServiceTab._group_box_style("#16a34a", "12px"))
        self.telemetry_group = QGroupBox("Compressor Telemetry")
        self.telemetry_group.setStyleSheet(ServiceTab._group_box_style("#0ea5e9", "12px"))
        self.faults_group = QGroupBox("Fault Flags")
        self.faults_group.setStyleSheet(ServiceTab._group_box_style("#f59e0b", "12px"))

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        overview_page = QWidget()
        overview_layout = QVBoxLayout()
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(10)

        conn_layout = QGridLayout()
        conn_layout.setHorizontalSpacing(12)
        conn_layout.setVerticalSpacing(6)
        self._connection_fields["enabled"] = self._add_row(conn_layout, 0, "enabled", "Enabled")
        self._connection_fields["initialized"] = self._add_row(conn_layout, 1, "initialized", "Initialized")
        self._connection_fields["port"] = self._add_row(conn_layout, 2, "port", "Port", mono=True)
        self._connection_fields["baudrate"] = self._add_row(conn_layout, 3, "baudrate", "Baudrate")
        self._connection_fields["timeout_s"] = self._add_row(conn_layout, 4, "timeout_s", "Timeout (s)")
        self._connection_fields["max_speed_rpm"] = self._add_row(conn_layout, 5, "max_speed_rpm", "Max Speed (RPM)")
        self._connection_fields["last_error"] = self._add_row(conn_layout, 6, "last_error", "Last Error", mono=True)
        self.connection_group.setLayout(conn_layout)
        overview_layout.addWidget(self.connection_group)

        telemetry_layout = QGridLayout()
        telemetry_layout.setHorizontalSpacing(12)
        telemetry_layout.setVerticalSpacing(6)
        self._telemetry_fields["command_on"] = self._add_row(telemetry_layout, 0, "command_on", "Command ON")
        self._telemetry_fields["set_speed_rpm"] = self._add_row(telemetry_layout, 1, "set_speed_rpm", "Set Speed (RPM)")
        self._telemetry_fields["actual_rpm"] = self._add_row(telemetry_layout, 2, "actual_rpm", "Actual Speed (RPM)")
        self._telemetry_fields["current_a"] = self._add_row(telemetry_layout, 3, "current_a", "Motor Current (A)")
        self._telemetry_fields["bus_voltage_v"] = self._add_row(telemetry_layout, 4, "bus_voltage_v", "Bus Voltage (V)")
        self._telemetry_fields["fault_manual"] = self._add_row(telemetry_layout, 5, "fault_manual", "Fault Manual (byte)")
        self._telemetry_fields["fault_auto"] = self._add_row(telemetry_layout, 6, "fault_auto", "Fault Auto (byte)")
        self._telemetry_fields["fault_status"] = self._add_row(telemetry_layout, 7, "fault_status", "Fault Status")
        self._telemetry_fields["raw_reply"] = self._add_row(telemetry_layout, 8, "raw_reply", "Raw Reply (hex)", mono=True)
        self.telemetry_group.setLayout(telemetry_layout)
        overview_layout.addWidget(self.telemetry_group)
        overview_layout.addStretch()
        overview_page.setLayout(overview_layout)

        faults_page = QWidget()
        faults_page_layout = QVBoxLayout()
        faults_page_layout.setContentsMargins(0, 0, 0, 0)
        faults_page_layout.setSpacing(10)

        faults_layout = QGridLayout()
        faults_layout.setHorizontalSpacing(10)
        faults_layout.setVerticalSpacing(6)
        for idx, name in enumerate(self._FAULT_FLAG_NAMES):
            row = idx // 2
            col = idx % 2
            label = QLabel(f"{name}: --")
            label.setStyleSheet("font-size: 12px; color: #5c6b79; padding: 3px;")
            faults_layout.addWidget(label, row, col)
            self._fault_flag_labels[name] = label
        self.faults_group.setLayout(faults_layout)
        faults_page_layout.addWidget(self.faults_group)
        faults_page_layout.addStretch()
        faults_page.setLayout(faults_page_layout)

        self.details_tabs = QTabWidget()
        self.details_tabs.addTab(overview_page, "Overview")
        self.details_tabs.addTab(faults_page, "Fault Flags")
        main_layout.addWidget(self.details_tabs)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_telemetry(
        self,
        telemetry: Optional[object] = None,
        compressor_command_on: Optional[bool] = None,
        compressor_set_speed_rpm: Optional[int] = None,
        compressor_last_error: Optional[str] = None,
        compressor_initialized: Optional[bool] = None,
    ):
        initialized = bool(compressor_initialized) if compressor_initialized is not None else bool(telemetry is not None)
        self._connection_fields["enabled"].setText("YES" if self._enabled else "NO")
        self._connection_fields["enabled"].setStyleSheet(self._VALUE_OK_STYLE if self._enabled else self._VALUE_WARN_STYLE)
        self._connection_fields["initialized"].setText("YES" if initialized else "NO")
        self._connection_fields["initialized"].setStyleSheet(self._VALUE_OK_STYLE if initialized else self._VALUE_WARN_STYLE)
        self._connection_fields["port"].setText(self._port)
        self._connection_fields["baudrate"].setText(str(self._baudrate))
        self._connection_fields["timeout_s"].setText(f"{self._timeout_s:.3f}")
        self._connection_fields["max_speed_rpm"].setText(str(self._max_speed_rpm))

        error_text = compressor_last_error if compressor_last_error else "None"
        self._connection_fields["last_error"].setText(error_text)
        self._connection_fields["last_error"].setStyleSheet(
            self._VALUE_ERR_STYLE if compressor_last_error else self._VALUE_STYLE
        )

        if compressor_command_on is None:
            self._telemetry_fields["command_on"].setText("--")
            self._telemetry_fields["command_on"].setStyleSheet(self._VALUE_STYLE)
        else:
            self._telemetry_fields["command_on"].setText("ON" if compressor_command_on else "OFF")
            self._telemetry_fields["command_on"].setStyleSheet(
                self._VALUE_OK_STYLE if compressor_command_on else self._VALUE_WARN_STYLE
            )
        self._telemetry_fields["set_speed_rpm"].setText(
            "--" if compressor_set_speed_rpm is None else str(int(compressor_set_speed_rpm))
        )

        if telemetry is None:
            self._telemetry_fields["actual_rpm"].setText("--")
            self._telemetry_fields["current_a"].setText("--")
            self._telemetry_fields["bus_voltage_v"].setText("--")
            self._telemetry_fields["fault_manual"].setText("--")
            self._telemetry_fields["fault_auto"].setText("--")
            self._telemetry_fields["fault_status"].setText("No telemetry")
            self._telemetry_fields["fault_status"].setStyleSheet(self._VALUE_WARN_STYLE)
            self._telemetry_fields["raw_reply"].setText("--")
            for name, label in self._fault_flag_labels.items():
                label.setText(f"{name}: --")
                label.setStyleSheet("font-size: 12px; color: #5c6b79; padding: 3px;")
            return

        actual_rpm = int(getattr(telemetry, "actual_rpm", 0))
        current_a = float(getattr(telemetry, "current_a", 0.0))
        bus_voltage_v = float(getattr(telemetry, "bus_voltage_v", 0.0))
        fault_manual = int(getattr(telemetry, "fault_manual", 0))
        fault_auto = int(getattr(telemetry, "fault_auto", 0))
        raw_reply = bytes(getattr(telemetry, "raw_reply", b""))

        self._telemetry_fields["actual_rpm"].setText(str(actual_rpm))
        self._telemetry_fields["current_a"].setText(f"{current_a:.1f}")
        self._telemetry_fields["bus_voltage_v"].setText(f"{bus_voltage_v:.1f}")
        self._telemetry_fields["fault_manual"].setText(f"0x{fault_manual:02X}")
        self._telemetry_fields["fault_auto"].setText(f"0x{fault_auto:02X}")
        self._telemetry_fields["raw_reply"].setText(" ".join(f"{b:02X}" for b in raw_reply) if raw_reply else "--")

        has_fault = bool(fault_manual or fault_auto)
        self._telemetry_fields["fault_status"].setText("FAULT ACTIVE" if has_fault else "OK")
        self._telemetry_fields["fault_status"].setStyleSheet(
            self._VALUE_ERR_STYLE if has_fault else self._VALUE_OK_STYLE
        )

        flags = {}
        if hasattr(telemetry, "fault_flags"):
            try:
                flags = dict(telemetry.fault_flags())
            except Exception:
                flags = {}

        for name, label in self._fault_flag_labels.items():
            state = flags.get(name)
            if state is None:
                label.setText(f"{name}: --")
                label.setStyleSheet("font-size: 12px; color: #5c6b79; padding: 3px;")
                continue
            label.setText(f"{name}: {'ON' if state else 'OFF'}")
            label.setStyleSheet(
                "font-size: 12px; color: #991b1b; font-weight: 600; padding: 3px;"
                if state
                else "font-size: 12px; color: #166534; padding: 3px;"
            )


class MultiTemperatureGraphWidget(QWidget):
    """Custom graph widget for plotting multiple temperature channels."""

    _MAX_HISTORY_SEC = 3600  # 60 minutes

    def __init__(self, series_names: list[str]):
        super().__init__()
        self.series_names = list(series_names)
        self._history = deque()
        self._visible = {name: True for name in self.series_names}
        self._x_window_minutes = 10
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

    def set_series_visible(self, name: str, visible: bool):
        if name in self._visible:
            self._visible[name] = bool(visible)
            self.update()

    def add_sample(self, series_values: dict):
        now = time.monotonic()
        normalized = {}
        for name in self.series_names:
            value = series_values.get(name)
            try:
                normalized[name] = float(value)
            except (TypeError, ValueError):
                normalized[name] = float("nan")
        self._history.append((now, normalized))

        cutoff = now - self._MAX_HISTORY_SEC
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()
        self.update()

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

        plot_left = graph_x + 44
        plot_right = graph_x + graph_width - 12
        plot_top = graph_y + 12
        # No footer legend anymore; keep only space for x-axis labels.
        plot_bottom = graph_y + graph_height - 24
        plot_width = max(1, plot_right - plot_left)
        plot_height = max(1, plot_bottom - plot_top)

        now = time.monotonic()
        window_sec = float(self._x_window_minutes) * 60.0
        start_ts = now - window_sec
        visible_entries = [entry for entry in self._history if entry[0] >= start_ts]

        y_min, y_max = self._compute_visible_y_range(visible_entries)

        # Y grid and labels
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        for i in range(4):
            t = y_min + (i / 3.0) * (y_max - y_min)
            ratio = (t - y_min) / max(0.001, (y_max - y_min))
            py = int(plot_bottom - ratio * plot_height)
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawLine(plot_left, py, plot_right, py)
            painter.setPen(QColor("#475569"))
            painter.drawText(
                QRectF(graph_x + 2, py - 8, 38, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{t:.1f}",
            )

        # X labels
        painter.setPen(QColor("#334155"))
        for i in range(6):
            ratio = i / 5.0
            px = int(plot_left + ratio * plot_width)
            mins_ago = int(round((1.0 - ratio) * self._x_window_minutes))
            label = "now" if mins_ago == 0 else f"-{mins_ago}m"
            painter.drawText(
                QRectF(px - 18, plot_bottom + 4, 36, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.drawLine(int(plot_left), int(plot_top), int(plot_left), int(plot_bottom))
        painter.drawLine(int(plot_left), int(plot_bottom), int(plot_right), int(plot_bottom))

        if visible_entries:
            def temp_to_y(t: float) -> float:
                t_clamped = max(y_min, min(y_max, t))
                ratio = (t_clamped - y_min) / max(0.001, (y_max - y_min))
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
                pen = QPen(QColor(self._series_colors[name]), 2)
                path = QPainterPath()
                first = True
                for ts, values in visible_entries:
                    value = values.get(name, float("nan"))
                    if math.isnan(value):
                        continue
                    px = time_to_x(ts)
                    py = temp_to_y(value)
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

    def _compute_visible_y_range(self, visible_entries):
        values = []
        for _ts, series_values in visible_entries:
            for name, value in series_values.items():
                if self._visible.get(name, False) and not math.isnan(value):
                    values.append(value)
        if not values:
            return 20.0, 40.0
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
        return y_min, y_max

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
    """Advanced tab: multi-temperature history graph with series toggles."""

    def __init__(self, series_names: list[str]):
        super().__init__()
        self.series_names = list(series_names)
        self.graph_widget = MultiTemperatureGraphWidget(self.series_names)
        self.checkboxes = {}
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        for name in self.series_names:
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)
            checkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            series_color = self.graph_widget._series_colors.get(name, "#1f2937")
            # Unchecked = neutral gray; checked = series color (matches the
            # plotted line and the label text).
            checkbox.setStyleSheet("""
                QCheckBox {
                    font-size: 18px;
                    font-weight: 600;
                    color: %s;
                    min-height: 44px;
                    padding: 4px 0;
                }
                QCheckBox::indicator {
                    width: 32px;
                    height: 32px;
                    margin-left: 10px;
                    border-radius: 6px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #e5e7eb;
                    border: 2px solid #9ca3af;
                }
                QCheckBox::indicator:checked {
                    background-color: %s;
                    border: 2px solid %s;
                }
            """ % (series_color, series_color, series_color))
            checkbox.stateChanged.connect(
                lambda state, series_name=name: self.graph_widget.set_series_visible(
                    series_name, state == Qt.CheckState.Checked.value
                )
            )
            self.checkboxes[name] = checkbox

    def _setup_layout(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        control_group = QGroupBox("Series Visibility")
        control_group.setStyleSheet(ServiceTab._group_box_style("#0ea5e9", "16px"))
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(12, 14, 12, 12)
        controls_layout.setSpacing(6)
        for name in self.series_names:
            controls_layout.addWidget(self.checkboxes[name])
        controls_layout.addStretch()
        control_group.setLayout(controls_layout)
        # Wide enough to fit the longest configured sensor name (e.g.
        # "Heat Exchanger Temp") at 18px bold next to the 32px indicator.
        control_group.setFixedWidth(210)

        # Maximize graph area (left) while keeping touch-friendly controls (right).
        main_layout.addWidget(self.graph_widget, 1)
        main_layout.addWidget(control_group, 0)
        self.setLayout(main_layout)

    def add_sample(self, series_values: dict):
        self.graph_widget.add_sample(series_values)
        self._update_checkbox_labels(series_values)

    def _update_checkbox_labels(self, series_values: dict) -> None:
        """Show the latest value next to each probe name in the toggles."""
        for name, checkbox in self.checkboxes.items():
            raw = series_values.get(name)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = float("nan")
            if math.isnan(value):
                checkbox.setText(name)
            else:
                checkbox.setText(f"{name}  {value:.1f} \u00b0C")

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
        self.primary_temperature_label = self._pick_primary_temperature_label(
            self.temperature_sensor_names
        )
        self.secondary_temperature_label = self._pick_secondary_temperature_label(
            self.temperature_sensor_names,
            self.primary_temperature_label,
        )

        # Callbacks (set by the host application).
        self.on_start_pumping_callback: Optional[Callable] = None
        self.on_stop_pumping_callback: Optional[Callable] = None
        self.on_acknowledge_callback: Optional[Callable] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_manual_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_manual_timing_change_callback: Optional[Callable[[int, int], None]] = None
        self.on_compressor_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_temperature_calibration_callback: Optional[
            Callable[[str, float, float], tuple[bool, str]]
        ] = None

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
        tc_cfg = config.get("thermocouples", {})
        channels = tc_cfg.get("channels", [])
        raw_labels = tc_cfg.get("labels", {})
        labels = {}
        for key, value in raw_labels.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        names: list[str] = []
        for channel in channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            names.append(str(labels.get(ch, f"Temp {ch}")))
        return names

    @staticmethod
    def _pick_primary_temperature_label(sensor_names: list[str]) -> Optional[str]:
        """Prefer CSF for the main graph; fallback to first configured sensor."""
        for name in sensor_names:
            if "csf" in str(name).lower():
                return name
        return sensor_names[0] if sensor_names else None

    @staticmethod
    def _pick_secondary_temperature_label(
        sensor_names: list[str], primary_label: Optional[str]
    ) -> Optional[str]:
        """Choose a different sensor label for optional secondary usage."""
        for name in sensor_names:
            if name != primary_label:
                return name
        return None

    @staticmethod
    def _pressure_sensor_names_from_config(config: dict) -> list[str]:
        ps_cfg = config.get("pressure_sensors", {})
        channels = ps_cfg.get("channels", [])
        raw_channel_cfg = ps_cfg.get("channel_configs", {})
        names: list[str] = []
        for channel in channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            cfg = raw_channel_cfg.get(str(ch), raw_channel_cfg.get(ch, {}))
            if isinstance(cfg, dict) and cfg.get("label"):
                names.append(str(cfg.get("label")))
            else:
                names.append(f"Pressure {ch + 1}")
        return names
    
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
    
    def _create_widgets(self):
        """Create UI widgets"""
        # Main screen widget: temperature graph + setpoint controls
        self.main_graph_widget = MainScreenWidget(
            show_cartridge=False,
            show_graph=True,
            show_temp_controls=True,
        )
        if self.primary_temperature_label:
            self.main_graph_widget.primary_temperature_label = self.primary_temperature_label
        self.main_graph_widget.setMinimumHeight(280)
        self.main_graph_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Service tab
        self.service_tab = ServiceTab(
            self.config.get('stepper_motor', {}),
            self.config.get('compressor', {}),
        )
        self.service_tab.on_stepper_speed_change_callback = self._on_service_stepper_speed_change
        self.service_tab.on_stepper_jog_start_callback = self._on_service_stepper_jog_start
        self.service_tab.on_stepper_jog_stop_callback = self._on_service_stepper_jog_stop
        self.service_tab.on_stepper_continuous_toggle_callback = self._on_service_stepper_continuous_toggle
        self.service_tab.on_compressor_toggle_callback = self._on_service_compressor_toggle
        self.service_tab.on_compressor_manual_toggle_callback = self._on_service_compressor_manual_toggle
        self.service_tab.on_compressor_manual_timing_change_callback = self._on_service_compressor_manual_timing_change
        self.service_tab.on_compressor_speed_change_callback = self._on_service_compressor_speed_change

        # Service 2 tab (temperature channels)
        pressure_sensor_names = self._pressure_sensor_names_from_config(self.config)
        self.service2_tab = Service2Tab(
            self.temperature_sensor_names,
            pressure_sensor_names=pressure_sensor_names,
        )
        temp_series_names = ["Set Temp", *self.temperature_sensor_names]
        self.temperature_graph_tab = TemperatureGraphTab(temp_series_names)
        self.calibration_tab = CalibrationTab(self.temperature_sensor_names)
        self.compressor_uart_tab = CompressorUartTab(self.config.get("compressor", {}))
        self.calibration_tab.on_apply_calibration_callback = (
            self._on_temperature_graph_calibration_apply
        )

        # In-window advanced area (Service / Animal Study / Temp Graph / Calibration).
        self.advanced_tab_selector = QTabBar()
        self.advanced_tab_selector.addTab("Service")
        self.advanced_tab_selector.addTab("Animal Study")
        self.advanced_tab_selector.addTab("Temp Graph")
        self.advanced_tab_selector.addTab("Calibration")
        self.advanced_tab_selector.addTab("Compressor UART")
        self.advanced_tab_selector.setExpanding(False)

        self.advanced_content_stack = QStackedWidget()
        self.advanced_content_stack.addWidget(self.service_tab)
        self.advanced_content_stack.addWidget(self.service2_tab)
        self.advanced_content_stack.addWidget(self.temperature_graph_tab)
        self.advanced_content_stack.addWidget(self.calibration_tab)
        self.advanced_content_stack.addWidget(self.compressor_uart_tab)
        self.advanced_tab_selector.currentChanged.connect(self.advanced_content_stack.setCurrentIndex)

        self.to_main_menu_button = QPushButton("To Main Menu")
        self.to_main_menu_button.setFixedHeight(34)
        self.to_main_menu_button.clicked.connect(self._show_main_view)
        self.to_main_menu_button.setStyleSheet("""
            QPushButton {
                background: #e8edf2;
                color: #24313d;
                border: 1px solid #d1d8df;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: #dde6ed;
            }
        """)
        self.to_main_menu_button.setVisible(False)

        # Corner control for toggling fullscreen/windowed mode.
        self.window_mode_toggle_button = QPushButton("")
        self.window_mode_toggle_button.setFixedSize(34, 34)
        self.window_mode_toggle_button.clicked.connect(self._toggle_window_mode)
        self.window_mode_toggle_button.setStyleSheet("""
            QPushButton {
                background: #f8fafb;
                color: #51606c;
                border: 1px solid #d5dce3;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #eef3f7;
            }
            QPushButton:pressed {
                background: #e5ebf0;
            }
        """)
        self._update_window_mode_toggle_button()

        self.advanced_page = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_page)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(8)
        advanced_header_row = QHBoxLayout()
        advanced_header_row.setContentsMargins(0, 0, 0, 0)
        advanced_header_row.setSpacing(10)
        advanced_header_row.addWidget(self.advanced_tab_selector)
        advanced_layout.addLayout(advanced_header_row)
        advanced_layout.addWidget(self.advanced_content_stack, 1)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.main_graph_widget)
        self.content_stack.addWidget(self.advanced_page)
        
        # Compact advanced settings launcher
        self.advanced_settings_button = QPushButton("⚙")
        self.advanced_settings_button.setFixedSize(52, 52)
        self.advanced_settings_button.setToolTip("Open advanced settings")
        self.advanced_settings_button.clicked.connect(self._show_advanced_view)
        self.advanced_settings_button.setStyleSheet("""
            QPushButton {
                background: #f8fafb;
                color: #51606c;
                border: 1px solid #d5dce3;
                border-radius: 14px;
                font-size: 20px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #eef3f7;
            }
            QPushButton:pressed {
                background: #e5ebf0;
            }
        """)
        
        # State indicator label (top status line)
        self.state_label = QLabel("State: INIT")
        self.state_label.setMinimumHeight(32)
        self.state_label.setStyleSheet("""
            QLabel {
                background-color: #e9eef2;
                color: #2f3b47;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 10px;
                border: 1px solid #d6dde3;
            }
        """)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Pumping toggle button - acts as "START PUMPING" in Cooling state
        # and "STOP PUMPING" in Pumping state. Disabled in other states.
        self.pumping_toggle_button = QPushButton("START PUMPING")
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
        
        # Error message label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("""
            QLabel {
                background-color: #f8e5db;
                color: #7e3f26;
                font-size: 13px;
                font-weight: 600;
                padding: 10px;
                border-radius: 14px;
                border: 1px solid #edcdbd;
            }
        """)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
    
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
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        # Header row: state indicator + advanced settings button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        header_row.addWidget(self.state_label, 1)
        header_row.addWidget(self.to_main_menu_button)
        header_row.addWidget(self.window_mode_toggle_button, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(header_row)

        # Main content area
        main_layout.addWidget(self.content_stack, 1)
        
        # Error message (only visible in ERROR state)
        main_layout.addWidget(self.error_label)
        
        # State-specific buttons row (visible only on Main tab)
        self.state_buttons_row = QWidget()
        state_button_layout = QHBoxLayout()
        state_button_layout.setContentsMargins(0, 0, 0, 0)
        state_button_layout.setSpacing(10)
        state_button_layout.addWidget(self.pumping_toggle_button)
        state_button_layout.addWidget(self.acknowledge_button)
        state_button_layout.addWidget(self.advanced_settings_button)
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

    def _on_service_compressor_toggle(self, enabled: bool):
        """Forward service-tab compressor on/off toggle to app callback."""
        if self.on_compressor_toggle_callback:
            self.on_compressor_toggle_callback(enabled)

    def _on_service_compressor_manual_toggle(self, enabled: bool):
        """Forward service-tab manual compressor relay toggle to app callback."""
        if self.on_compressor_manual_toggle_callback:
            self.on_compressor_manual_toggle_callback(enabled)

    def _on_service_compressor_manual_timing_change(self, on_time_s: int, off_time_s: int):
        """Forward service-tab manual compressor cycle timing updates."""
        if self.on_compressor_manual_timing_change_callback:
            self.on_compressor_manual_timing_change_callback(on_time_s, off_time_s)

    def _on_service_compressor_speed_change(self, speed_rpm: int):
        """Forward service-tab compressor speed setpoint change."""
        if self.on_compressor_speed_change_callback:
            self.on_compressor_speed_change_callback(speed_rpm)

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
        """Show an intuitive icon for the next window mode action."""
        if self.isFullScreen():
            # Restore down icon when currently fullscreen.
            self.window_mode_toggle_button.setText("❐")
            self.window_mode_toggle_button.setToolTip("Exit fullscreen")
        else:
            # Maximize icon when currently windowed.
            self.window_mode_toggle_button.setText("□")
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
        current_state = self.state_label.text().replace("State: ", "")
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

    def _show_advanced_view(self):
        """Switch to in-window advanced settings page."""
        self.content_stack.setCurrentWidget(self.advanced_page)
        self._set_main_action_buttons_visible(False)
        self.to_main_menu_button.setVisible(True)
        self.state_label.setFixedWidth(self._ADVANCED_STATE_LABEL_WIDTH)

    def _show_main_view(self):
        """Return to main screen from advanced settings page."""
        self.content_stack.setCurrentWidget(self.main_graph_widget)
        self._set_main_action_buttons_visible(True)
        self.to_main_menu_button.setVisible(False)
        self.state_label.setMinimumWidth(0)
        self.state_label.setMaximumWidth(16777215)
        self.state_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _set_main_action_buttons_visible(self, visible: bool):
        """Show or hide the bottom action row (children follow the parent)."""
        self.state_buttons_row.setVisible(visible)

    def update_state_display(self, state_name: str, error_message: Optional[str] = None):
        """
        Update state display and button visibility
        
        Args:
            state_name: Current state name
            error_message: Error message if in ERROR state
        """
        # Update state label
        self.state_label.setText(f"State: {state_name}")
        
        # Error state -> red, otherwise green.
        if state_name == "Error":
            bg_color = "#f8e5db"
            border_color = "#d06a45"
            text_color = "#7e3f26"
        else:
            bg_color = "#dff0f2"
            border_color = "#8fc8cf"
            text_color = "#245962"
        
        self.state_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                font-size: 12px;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 10px;
                border: 1px solid {border_color};
            }}
        """)
        
        # Update unified pumping toggle button (label + style + enabled state)
        if state_name in ("Pumping", "Pumping Slowly"):
            self.pumping_toggle_button.setText("STOP PUMPING")
            self._apply_pumping_button_style(active=True)
            self.pumping_toggle_button.setEnabled(True)
        else:
            self.pumping_toggle_button.setText("START PUMPING")
            self._apply_pumping_button_style(active=False)
            self.pumping_toggle_button.setEnabled(state_name == "Cooling")
        
        self.acknowledge_button.setEnabled(state_name == "Error")
        
        # Show/hide error message
        if state_name == "Error" and error_message:
            self.error_label.setText(f"⚠️ {error_message}")
            self.error_label.setVisible(True)
        else:
            self.error_label.setVisible(False)
    
    def update_sensor_display(
        self,
        sensor_states: dict,
        temperatures: Optional[dict] = None,
        raw_temperatures: Optional[dict] = None,
        pressures: Optional[dict] = None,
        telemetry: Optional[object] = None,
        compressor_command_on: Optional[bool] = None,
        compressor_set_speed_rpm: Optional[int] = None,
        compressor_last_error: Optional[str] = None,
        compressor_initialized: Optional[bool] = None,
    ):
        """Update sensor display"""
        self.service_tab.update_sensors(sensor_states)
        self.service2_tab.update_temperatures(temperatures)
        self.service2_tab.update_pressures(pressures)
        self.calibration_tab.update_current_temperatures(raw_temperatures, temperatures)
        self.compressor_uart_tab.update_telemetry(
            telemetry=telemetry,
            compressor_command_on=compressor_command_on,
            compressor_set_speed_rpm=compressor_set_speed_rpm,
            compressor_last_error=compressor_last_error,
            compressor_initialized=compressor_initialized,
        )
        
        # Feed first two configured thermocouple channels into the main trend graph.
        temp1 = (
            self.service2_tab.temp_values.get(self.primary_temperature_label, 0.0)
            if self.primary_temperature_label
            else 0.0
        )
        temp2 = (
            self.service2_tab.temp_values.get(self.secondary_temperature_label, 0.0)
            if self.secondary_temperature_label
            else 0.0
        )
        if temp1 == temp1 and temp2 == temp2:  # skip NaN values
            self.main_graph_widget.add_temperature_sample(temp1, temp2)

        # Feed full temperature set into advanced multi-series graph tab.
        series_values = {"Set Temp": float(self.main_graph_widget.set_temperature)}
        for name in self.temperature_sensor_names:
            series_values[name] = self.service2_tab.temp_values.get(name, float("nan"))
        self.temperature_graph_tab.add_sample(series_values)

        # Keep compressor display stable unless updated by app logic.
        self.service_tab.update_outputs()
    
    def set_status_message(self, message: str, is_error: bool = False):
        """No-op kept for API compatibility (status shown visually elsewhere)."""

    # Width of the state indicator on the advanced page (half of usable width).
    _ADVANCED_STATE_LABEL_WIDTH = max(260, (SCREEN_WIDTH - 20) // 2)
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


