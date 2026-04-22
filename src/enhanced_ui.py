"""
Enhanced UI Module with Visual Cartridge Representation
PyQt6-based user interface with graphical sensor display
"""

import sys
import time
from collections import deque
from datetime import datetime
from typing import Optional, Callable

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QTabWidget,
    QLabel, QGridLayout, QGroupBox, QFrame, QCheckBox, QSlider
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QLinearGradient,
    QFont, QPainterPath
)


class CartridgeWidget(QWidget):
    """Custom widget to draw the cartridge with levels and sensor"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 420)
        
        # Sensor states
        self.level_low = False
        self.level_critical = False
        self.cartridge_present = False
        
        # Liquid level (0.0 to 1.0, where 1.0 is full)
        self.liquid_level = 0.7  # 70% full
        
        # Threshold positions (as fraction of container height)
        self.low_threshold = 0.4      # Low warning at 40%
        self.critical_threshold = 0.2  # Critical warning at 20%
        
        # Set temperature gauge configuration
        self.temp_min = 30.0
        self.temp_max = 35.0
        self.temp_step = 0.2
        self.set_temperature = 32.0
        self._temp_gauge_rect = QRectF()  # Updated during paint, used for hit testing
        self._dragging_temp = False
        
        # Callback for temperature changes
        self.on_temperature_change_callback: Optional[Callable[[float], None]] = None
        
        # Temperature history for the graph (timestamp, set_temp, temp1, temp2)
        self._temp_history: deque = deque()
        
        # Touch-friendly +/- buttons for fine adjustment
        self._create_temp_buttons()
    
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
        
        # Draw temperature history graph on the left
        self._draw_temperature_graph(painter)
        
        # Draw single chamber with liquid and threshold levels
        self._draw_single_chamber(painter)
        
        # Draw present sensor indicator below the chamber
        self._draw_present_sensor(painter)
        
        # Draw set temperature gauge on the right side
        self._draw_temperature_gauge(painter)
    
    def _draw_background(self, painter: QPainter):
        """Draw gradient background"""
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#f8fbff"))
        gradient.setColorAt(1, QColor("#eaf2ff"))
        painter.fillRect(self.rect(), gradient)
    
    # Temperature history graph configuration
    _HISTORY_DURATION_SEC = 300  # 5 minutes
    _GRAPH_TEMP_MIN = 25.0
    _GRAPH_TEMP_MAX = 40.0
    _GRAPH_SERIES = (
        # (history tuple index, label, color)
        (1, "Set",    "#0ea5e9"),
        (2, "Temp 1", "#16a34a"),
        (3, "Temp 2", "#f59e0b"),
    )
    
    def add_temperature_sample(self, temp1: float, temp2: float):
        """Record a new sample of (set temperature, Temp 1, Temp 2) at current time"""
        now = time.monotonic()
        self._temp_history.append((now, self.set_temperature, float(temp1), float(temp2)))
        
        # Drop samples older than the history window
        cutoff = now - self._HISTORY_DURATION_SEC
        while self._temp_history and self._temp_history[0][0] < cutoff:
            self._temp_history.popleft()
        
        self.update()
    
    def _draw_temperature_graph(self, painter: QPainter):
        """Draw the temperature history graph on the left side of the chamber"""
        # Graph container
        graph_x = 15
        graph_y = 40
        graph_width = 270
        graph_height = 280
        
        # Background
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#cbd5e1"), 2))
        painter.drawRoundedRect(graph_x, graph_y, graph_width, graph_height, 10, 10)
        
        # Title
        painter.setPen(QColor("#1e293b"))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(graph_x, graph_y + 6, graph_width, 16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            "Temperature (last 5 min)"
        )
        
        # Plot area (inside with padding for axes / legend)
        plot_left = graph_x + 36
        plot_right = graph_x + graph_width - 10
        plot_top = graph_y + 48
        plot_bottom = graph_y + graph_height - 22
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top
        
        # Legend (just below the title)
        self._draw_graph_legend(painter, graph_x, graph_y + 24, graph_width)
        
        # Y-axis grid lines and labels
        y_ticks = [25, 30, 35, 40]
        font = QFont("Arial", 8)
        painter.setFont(font)
        for t in y_ticks:
            ratio = (t - self._GRAPH_TEMP_MIN) / (self._GRAPH_TEMP_MAX - self._GRAPH_TEMP_MIN)
            py = int(plot_bottom - ratio * plot_height)
            painter.setPen(QPen(QColor("#e5e7eb"), 1))
            painter.drawLine(plot_left, py, plot_right, py)
            painter.setPen(QColor("#475569"))
            painter.drawText(
                QRectF(graph_x + 2, py - 8, 30, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{t}"
            )
        
        # X-axis labels (minutes ago)
        painter.setPen(QColor("#475569"))
        for mins_ago in [5, 4, 3, 2, 1, 0]:
            ratio = (5 - mins_ago) / 5.0
            px = int(plot_left + ratio * plot_width)
            label = "now" if mins_ago == 0 else f"-{mins_ago}m"
            painter.drawText(
                QRectF(px - 20, plot_bottom + 4, 40, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label
            )
        
        # Plot axes
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.drawLine(plot_left, plot_top, plot_left, plot_bottom)
        painter.drawLine(plot_left, plot_bottom, plot_right, plot_bottom)
        
        # Plot data series
        if len(self._temp_history) >= 1:
            now = time.monotonic()
            
            def temp_to_y(t: float) -> float:
                t_clamped = max(self._GRAPH_TEMP_MIN, min(self._GRAPH_TEMP_MAX, t))
                ratio = (t_clamped - self._GRAPH_TEMP_MIN) / (self._GRAPH_TEMP_MAX - self._GRAPH_TEMP_MIN)
                return plot_bottom - ratio * plot_height
            
            def time_to_x(ts: float) -> float:
                delta = now - ts
                ratio = 1.0 - (delta / self._HISTORY_DURATION_SEC)
                ratio = max(0.0, min(1.0, ratio))
                return plot_left + ratio * plot_width
            
            # Clip drawing to the plot area to avoid overshoot
            painter.save()
            painter.setClipRect(QRectF(plot_left, plot_top, plot_width, plot_height))
            
            for series_index, _label, color_hex in self._GRAPH_SERIES:
                pen = QPen(QColor(color_hex), 2)
                if series_index == 1:  # Set temperature: dashed line
                    pen.setDashPattern([6, 3])
                painter.setPen(pen)
                
                path = QPainterPath()
                first = True
                for entry in self._temp_history:
                    ts = entry[0]
                    value = entry[series_index]
                    px = time_to_x(ts)
                    py = temp_to_y(value)
                    if first:
                        path.moveTo(px, py)
                        first = False
                    else:
                        path.lineTo(px, py)
                painter.drawPath(path)
            
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
    
    def _draw_graph_legend(self, painter: QPainter, graph_x: int, y: int, graph_width: int):
        """Draw legend entries for the graph series"""
        # Calculate entry width based on count
        entries = self._GRAPH_SERIES
        entry_width = graph_width // len(entries)
        font = QFont("Arial", 8, QFont.Weight.Bold)
        painter.setFont(font)
        
        for i, (series_index, label, color_hex) in enumerate(entries):
            ex = graph_x + i * entry_width + 8
            
            # Color line swatch
            pen = QPen(QColor(color_hex), 3)
            if series_index == 1:
                pen.setDashPattern([3, 2])
            painter.setPen(pen)
            painter.drawLine(ex, y + 8, ex + 18, y + 8)
            
            # Label
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(ex + 22, y, entry_width - 30, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label
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
        
        # Title label
        painter.setPen(QColor("#1e293b"))
        font = QFont("Arial", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(gauge_x - 30, gauge_y - 36, gauge_width + 80, 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            "SET TEMP"
        )
        
        # Current value display
        painter.setPen(QColor("#0284c7"))
        font = QFont("Arial", 15, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            QRectF(gauge_x - 30, gauge_y - 18, gauge_width + 80, 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            f"{self.set_temperature:.1f}\u00b0C"
        )
        
        # Draw gauge track
        track_gradient = QLinearGradient(gauge_x, gauge_y, gauge_x, gauge_y + gauge_height)
        track_gradient.setColorAt(0, QColor("#fecaca"))  # Warm at top (high temp)
        track_gradient.setColorAt(1, QColor("#bae6fd"))  # Cool at bottom (low temp)
        painter.setBrush(track_gradient)
        painter.setPen(QPen(QColor("#334155"), 2))
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
                painter.setPen(QPen(QColor("#0f172a"), 2))
            else:
                tick_length = 6
                painter.setPen(QPen(QColor("#475569"), 1))
            
            # Tick marks on both sides of the track
            painter.drawLine(gauge_x - tick_length, tick_y, gauge_x, tick_y)
            painter.drawLine(
                gauge_x + gauge_width, tick_y,
                gauge_x + gauge_width + tick_length, tick_y
            )
            
            # Major tick labels
            if is_major:
                painter.setPen(QColor("#0f172a"))
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
        handle_gradient.setColorAt(0, QColor("#0ea5e9"))
        handle_gradient.setColorAt(1, QColor("#0369a1"))
        painter.setBrush(handle_gradient)
        painter.setPen(QPen(QColor("#0c4a6e"), 2))
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
        
        # Unit label below gauge
        painter.setPen(QColor("#64748b"))
        font = QFont("Arial", 9)
        painter.setFont(font)
        painter.drawText(
            QRectF(gauge_x - 30, gauge_y + gauge_height + 6, gauge_width + 80, 14),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            f"{self.temp_min:.0f}-{self.temp_max:.0f}\u00b0C / 0.2\u00b0 step"
        )
    
    def _y_to_temperature(self, y: float) -> float:
        """Convert a y-coordinate to a temperature value, snapped to the step"""
        if self._temp_gauge_rect.height() <= 0:
            return self.set_temperature
        
        gauge_top = self._temp_gauge_rect.top()
        gauge_height = self._temp_gauge_rect.height()
        
        # Clamp y to the gauge range
        y_clamped = max(gauge_top, min(gauge_top + gauge_height, y))
        
        # Top = max temp, bottom = min temp
        ratio = 1.0 - (y_clamped - gauge_top) / gauge_height
        temp_value = self.temp_min + ratio * (self.temp_max - self.temp_min)
        
        # Snap to nearest step
        num_steps = round((temp_value - self.temp_min) / self.temp_step)
        snapped = self.temp_min + num_steps * self.temp_step
        return max(self.temp_min, min(self.temp_max, round(snapped, 1)))
    
    def _is_near_temp_gauge(self, pos: QPointF) -> bool:
        """Check if a mouse position is within/near the gauge track"""
        # Extend hit area slightly beyond the track for easier interaction
        hit_rect = self._temp_gauge_rect.adjusted(-15, -10, 15, 10)
        return hit_rect.contains(pos)
    
    def _update_temperature_from_mouse(self, y: float):
        """Update set temperature from mouse y-position and notify callback"""
        new_temp = self._y_to_temperature(y)
        if abs(new_temp - self.set_temperature) > 1e-6:
            self.set_temperature = new_temp
            self._update_temp_button_enabled_state()
            self.update()
            if self.on_temperature_change_callback:
                self.on_temperature_change_callback(self.set_temperature)
    
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
        """Programmatically set the temperature value (snapped to step)"""
        clamped = max(self.temp_min, min(self.temp_max, temperature))
        num_steps = round((clamped - self.temp_min) / self.temp_step)
        self.set_temperature = round(self.temp_min + num_steps * self.temp_step, 1)
        self._update_temp_button_enabled_state()
        self.update()
    
    def _create_temp_buttons(self):
        """Create touch-friendly +/- buttons for temperature adjustment"""
        button_style = """
            QPushButton {
                background-color: #0ea5e9;
                color: white;
                font-size: 22px;
                font-weight: bold;
                border: 2px solid #0369a1;
                border-radius: 8px;
            }
            QPushButton:pressed {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #cbd5e1;
                border-color: #94a3b8;
                color: #64748b;
            }
        """
        
        self.temp_minus_button = QPushButton("-", self)
        self.temp_minus_button.setFixedSize(self._TEMP_BUTTON_SIZE, self._TEMP_BUTTON_SIZE)
        self.temp_minus_button.setStyleSheet(button_style)
        self.temp_minus_button.clicked.connect(self._on_temp_decrement)
        
        self.temp_plus_button = QPushButton("+", self)
        self.temp_plus_button.setFixedSize(self._TEMP_BUTTON_SIZE, self._TEMP_BUTTON_SIZE)
        self.temp_plus_button.setStyleSheet(button_style)
        self.temp_plus_button.clicked.connect(self._on_temp_increment)
        
        # Enable auto-repeat so holding the button steps continuously
        for btn in (self.temp_minus_button, self.temp_plus_button):
            btn.setAutoRepeat(True)
            btn.setAutoRepeatDelay(400)
            btn.setAutoRepeatInterval(120)
    
    def _position_temp_buttons(self):
        """Position +/- buttons below the gauge"""
        if not hasattr(self, "temp_minus_button"):
            return
        
        gauge_x, gauge_y, gauge_width, gauge_height = self._gauge_geometry()
        gauge_center_x = gauge_x + gauge_width // 2
        
        buttons_total_width = 2 * self._TEMP_BUTTON_SIZE + self._TEMP_BUTTON_GAP
        buttons_left = gauge_center_x - buttons_total_width // 2
        buttons_top = gauge_y + gauge_height + 26
        
        self.temp_minus_button.move(buttons_left, buttons_top)
        self.temp_plus_button.move(
            buttons_left + self._TEMP_BUTTON_SIZE + self._TEMP_BUTTON_GAP,
            buttons_top,
        )
    
    def _step_temperature(self, direction: int):
        """Step the set temperature by `direction` steps (snapped and clamped)"""
        new_temp = round(self.set_temperature + direction * self.temp_step, 1)
        new_temp = max(self.temp_min, min(self.temp_max, new_temp))
        if abs(new_temp - self.set_temperature) > 1e-6:
            self.set_temperature = new_temp
            self._update_temp_button_enabled_state()
            self.update()
            if self.on_temperature_change_callback:
                self.on_temperature_change_callback(self.set_temperature)
    
    def _on_temp_increment(self):
        """Handle + button click"""
        self._step_temperature(1)
    
    def _on_temp_decrement(self):
        """Handle - button click"""
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


class ServiceTab(QWidget):
    """Service tab showing all sensors and outputs"""
    
    def __init__(self, stepper_config: Optional[dict] = None):
        super().__init__()
        
        # Mock temperature values
        self.temp_values = {
            'Temp 1': 22.5,
            'Temp 2': 23.1,
            'Temp 3': 21.8,
            'Temp 4': 22.9
        }
        
        # Sensor states
        self.sensor_states = {}
        
        # Output states
        self.compressor_on = False
        self.stepper_position = 0
        self.stepper_enabled = False
        self.stepper_fault = False
        self.stepper_microstepping = 1
        self.stepper_driver_name = "STSPIN220"
        self.stepper_speed_rpm = int((stepper_config or {}).get("default_speed_rpm", 30))
        
        self.on_stepper_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        
        self._create_widgets()
        self._setup_layout()
    
    def _create_widgets(self):
        """Create service tab widgets"""
        # Sensors group
        self.sensors_group = QGroupBox("Digital Sensors")
        self.sensors_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #3b82f6;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1f2937;
            }
        """)
        
        # Sensor labels
        self.sensor_labels = {}
        sensor_names = ['Level Low', 'Level Critical', 'Cartridge In Place']
        for name in sensor_names:
            label = QLabel(f"{name}: --")
            label.setStyleSheet("font-size: 11px; padding: 5px; color: #6b7280;")
            self.sensor_labels[name] = label
        
        # Temperature sensors group
        self.temp_group = QGroupBox("Temperature Sensors (Mock)")
        self.temp_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #f59e0b;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1f2937;
            }
        """)
        
        # Temperature labels
        self.temp_labels = {}
        for name in ['Temp 1', 'Temp 2', 'Temp 3', 'Temp 4']:
            label = QLabel(f"{name}: --°C")
            label.setStyleSheet("font-size: 11px; padding: 5px; color: #6b7280;")
            self.temp_labels[name] = label
        
        # Outputs group
        self.outputs_group = QGroupBox("Outputs")
        self.outputs_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #16a34a;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1f2937;
            }
        """)
        
        # Output labels
        self.compressor_label = QLabel("Compressor: OFF")
        self.compressor_label.setStyleSheet("font-size: 11px; padding: 5px; color: #6b7280;")
        
        self.stepper_label = QLabel(
            f"Stepper ({self.stepper_driver_name}): DISABLED - Position 0 - 1/{self.stepper_microstepping} step"
        )
        self.stepper_label.setStyleSheet("font-size: 11px; padding: 5px; color: #6b7280;")
        
        # Stepper controls
        self.stepper_toggle_button = QPushButton("TURN MOTOR ON")
        self.stepper_toggle_button.setMinimumHeight(34)
        self.stepper_toggle_button.clicked.connect(self._on_stepper_toggle_clicked)
        self._apply_stepper_button_style(False)
        
        self.stepper_speed_label = QLabel(f"Stepper Speed: {self.stepper_speed_rpm} RPM")
        self.stepper_speed_label.setStyleSheet("font-size: 11px; padding: 2px 5px; color: #1f2937;")
        
        self.stepper_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.stepper_speed_slider.setRange(5, 120)
        self.stepper_speed_slider.setTickInterval(5)
        self.stepper_speed_slider.setSingleStep(1)
        self.stepper_speed_slider.setPageStep(5)
        self.stepper_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.stepper_speed_slider.setValue(max(5, min(120, self.stepper_speed_rpm)))
        self.stepper_speed_slider.valueChanged.connect(self._on_stepper_speed_changed)
    
    def _setup_layout(self):
        """Setup service tab layout"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Sensors layout - horizontal arrangement
        sensors_layout = QHBoxLayout()
        for name in ['Level Low', 'Level Critical', 'Cartridge In Place']:
            sensors_layout.addWidget(self.sensor_labels[name])
        self.sensors_group.setLayout(sensors_layout)
        main_layout.addWidget(self.sensors_group)
        
        # Temperature sensors layout
        temp_layout = QGridLayout()
        temp_layout.addWidget(self.temp_labels['Temp 1'], 0, 0)
        temp_layout.addWidget(self.temp_labels['Temp 2'], 0, 1)
        temp_layout.addWidget(self.temp_labels['Temp 3'], 1, 0)
        temp_layout.addWidget(self.temp_labels['Temp 4'], 1, 1)
        self.temp_group.setLayout(temp_layout)
        main_layout.addWidget(self.temp_group)
        
        # Outputs layout
        outputs_layout = QVBoxLayout()
        outputs_layout.addWidget(self.compressor_label)
        outputs_layout.addWidget(self.stepper_label)
        outputs_layout.addWidget(self.stepper_toggle_button)
        outputs_layout.addWidget(self.stepper_speed_label)
        outputs_layout.addWidget(self.stepper_speed_slider)
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
                self.sensor_labels[name].setStyleSheet(
                    f"font-size: 11px; padding: 5px; color: {color}; font-weight: bold;"
                )
    
    def update_temperatures(self, temps: dict = None):
        """Update temperature display (mock values)"""
        import random
        if temps is None:
            # Generate mock values with slight variation
            for name in self.temp_values:
                self.temp_values[name] += random.uniform(-0.5, 0.5)
                self.temp_values[name] = max(15.0, min(30.0, self.temp_values[name]))
        else:
            self.temp_values.update(temps)
        
        for name, value in self.temp_values.items():
            self.temp_labels[name].setText(f"{name}: {value:.1f}°C")
            # Color code based on temperature
            if value < 20:
                color = "#3b82f6"  # Blue - cold
            elif value > 25:
                color = "#ef4444"  # Red - hot
            else:
                color = "#16a34a"  # Green - normal
            self.temp_labels[name].setStyleSheet(
                f"font-size: 11px; padding: 5px; color: {color}; font-weight: bold;"
            )
    
    def update_outputs(self, compressor_on: bool = None, stepper_pos: int = None,
                       stepper_enabled: bool = None, stepper_fault: bool = None,
                       stepper_microstepping: int = None, stepper_speed_rpm: int = None):
        """Update output display"""
        if compressor_on is not None:
            self.compressor_on = compressor_on
        if stepper_pos is not None:
            self.stepper_position = stepper_pos
        if stepper_enabled is not None:
            self.stepper_enabled = stepper_enabled
        if stepper_fault is not None:
            self.stepper_fault = stepper_fault
        if stepper_microstepping is not None:
            self.stepper_microstepping = stepper_microstepping
        if stepper_speed_rpm is not None:
            self.stepper_speed_rpm = int(stepper_speed_rpm)
            if self.stepper_speed_slider.value() != self.stepper_speed_rpm:
                self.stepper_speed_slider.setValue(self.stepper_speed_rpm)
        
        # Update compressor label
        comp_status = "ON" if self.compressor_on else "OFF"
        comp_color = "#16a34a" if self.compressor_on else "#6b7280"
        self.compressor_label.setText(f"Compressor: {comp_status}")
        self.compressor_label.setStyleSheet(
            f"font-size: 11px; padding: 5px; color: {comp_color}; font-weight: bold;"
        )
        
        # Update stepper label with STSPIN220 driver state
        if self.stepper_fault:
            state_text = "FAULT"
            stepper_color = "#dc2626"  # Red - fault
        elif self.stepper_enabled:
            state_text = "ENABLED"
            stepper_color = "#16a34a"  # Green - energised
        else:
            state_text = "DISABLED"
            stepper_color = "#6b7280"  # Grey - standby
        
        self.stepper_label.setText(
            f"Stepper ({self.stepper_driver_name}): {state_text} - "
            f"Position {self.stepper_position} - 1/{self.stepper_microstepping} step"
        )
        self.stepper_label.setStyleSheet(
            f"font-size: 11px; padding: 5px; color: {stepper_color}; font-weight: bold;"
        )
        
        self.stepper_speed_label.setText(f"Stepper Speed: {self.stepper_speed_rpm} RPM")
        self._apply_stepper_button_style(self.stepper_enabled)
    
    def _apply_stepper_button_style(self, motor_on: bool):
        """Apply style/text for the stepper toggle button."""
        if motor_on:
            text = "TURN MOTOR OFF"
            bg = "#f59e0b"
            hover = "#d97706"
        else:
            text = "TURN MOTOR ON"
            bg = "#0ea5e9"
            hover = "#0284c7"
        
        self.stepper_toggle_button.setText(text)
        self.stepper_toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 11px;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #9ca3af;
            }}
        """)
    
    def _on_stepper_toggle_clicked(self):
        """Toggle stepper motor power state."""
        target_enabled = not self.stepper_enabled
        if self.on_stepper_toggle_callback:
            self.on_stepper_toggle_callback(target_enabled)
    
    def _on_stepper_speed_changed(self, value: int):
        """Handle speed slider changes."""
        self.stepper_speed_rpm = int(value)
        self.stepper_speed_label.setText(f"Stepper Speed: {self.stepper_speed_rpm} RPM")
        if self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(self.stepper_speed_rpm)


class SimulationTab(QWidget):
    """Simulation tab for manual sensor control"""
    
    def __init__(self, sensor_names: list, simulation_mode: bool = True):
        super().__init__()
        
        self.sensor_names = sensor_names
        self.checkboxes = {}
        self.simulation_mode = simulation_mode
        self.on_sensor_change_callback: Optional[Callable[[str, bool], None]] = None
        self.on_mode_change_callback: Optional[Callable[[bool], None]] = None
        
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        """Create simulation tab widgets"""
        
        # Sensors group
        self.sensors_group = QGroupBox("Sensor States")
        self.sensors_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #3b82f6;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #1f2937;
            }
        """)
        
        # Create checkboxes for each sensor
        for sensor_name in self.sensor_names:
            checkbox = QCheckBox(sensor_name)
            checkbox.setStyleSheet("""
                QCheckBox {
                    font-size: 12px;
                    padding: 8px;
                    color: #1f2937;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #fee2e2;
                    border: 2px solid #dc2626;
                    border-radius: 4px;
                }
                QCheckBox::indicator:checked {
                    background-color: #dcfce7;
                    border: 2px solid #16a34a;
                    border-radius: 4px;
                }
            """)
            checkbox.stateChanged.connect(lambda state, name=sensor_name: self._on_checkbox_changed(name, state))
            self.checkboxes[sensor_name] = checkbox
        
        # Mode toggle button
        self.mode_button = QPushButton("SIMULATION MODE" if self.simulation_mode else "REAL SENSOR MODE")
        self.mode_button.setMinimumHeight(40)
        self.mode_button.setStyleSheet("""
            QPushButton {
                background-color: #8b5cf6;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #7c3aed;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.mode_button.clicked.connect(self._on_mode_toggle_clicked)
        
        # Info label
        self.info_label = QLabel(
            "ℹ️ Simulation Mode\n\n"
            "Use the checkboxes above to manually control sensor states.\n"
            "Toggle between Simulation and Real Sensor modes using the button below.\n"
            "Changes take effect immediately."
        )
        self.info_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #64748b;
                padding: 10px;
                background-color: #f1f5f9;
                border-radius: 5px;
            }
        """)
        self.info_label.setWordWrap(True)
    
    def _setup_layout(self):
        """Setup simulation tab layout"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Add title
        main_layout.addWidget(self.info_label)
        
        # Sensors layout (horizontal)
        sensors_layout = QHBoxLayout()
        sensors_layout.setSpacing(5)
        for sensor_name in self.sensor_names:
            sensors_layout.addWidget(self.checkboxes[sensor_name])
        self.sensors_group.setLayout(sensors_layout)
        main_layout.addWidget(self.sensors_group)
        
        # Add mode toggle button
        main_layout.addWidget(self.mode_button)
        
        # Add stretch to push everything to top
        main_layout.addStretch()
        
        self.setLayout(main_layout)
    
    def _on_checkbox_changed(self, sensor_name: str, state: int):
        """Handle checkbox state change"""
        is_checked = state == Qt.CheckState.Checked.value
        if self.on_sensor_change_callback:
            self.on_sensor_change_callback(sensor_name, is_checked)
    
    def _on_mode_toggle_clicked(self):
        """Handle mode toggle button click"""
        # Toggle mode
        self.simulation_mode = not self.simulation_mode
        
        # Update button text
        if self.simulation_mode:
            self.mode_button.setText("Switch to REAL SENSOR MODE")
        else:
            self.mode_button.setText("Switch to SIMULATION MODE")
        
        # Notify callback
        if self.on_mode_change_callback:
            self.on_mode_change_callback(self.simulation_mode)
    
    def set_mode_button_enabled(self, enabled: bool):
        """Enable or disable mode toggle button"""
        self.mode_button.setEnabled(enabled)
    
    def update_mode_display(self, simulation_mode: bool):
        """Update mode button text"""
        self.simulation_mode = simulation_mode
        if simulation_mode:
            self.mode_button.setText("SIMULATION MODE")
        else:
            self.mode_button.setText("REAL SENSOR MODE")
    
    def set_sensor_state(self, sensor_name: str, state: bool):
        """Set a sensor state programmatically"""
        if sensor_name in self.checkboxes:
            self.checkboxes[sensor_name].setChecked(state)
    
    def get_sensor_states(self) -> dict:
        """Get current sensor states"""
        return {name: checkbox.isChecked() for name, checkbox in self.checkboxes.items()}


class EnhancedSensorMonitorWindow(QMainWindow):
    """Main window with enhanced cartridge visualization"""
    
    def __init__(self, config: dict, simulation_mode: bool = False):
        """Initialize main window"""
        super().__init__()
        
        self.config = config
        self.is_monitoring = False
        self.simulation_mode = simulation_mode
        
        # Callbacks
        self.on_start_callback: Optional[Callable] = None
        self.on_stop_callback: Optional[Callable] = None
        self.on_sensor_change_callback: Optional[Callable[[str, bool], None]] = None
        self.on_mode_change_callback: Optional[Callable[[bool], None]] = None
        self.on_start_pumping_callback: Optional[Callable] = None
        self.on_stop_pumping_callback: Optional[Callable] = None
        self.on_acknowledge_callback: Optional[Callable] = None
        self.on_stepper_enable_callback: Optional[Callable[[bool], None]] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_layout()
        self._setup_timer()
    
    def _setup_window(self):
        """Setup main window properties"""
        self.setWindowTitle("Cartridge Level Monitor")
        self.setFixedSize(800, 480)
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - 800) // 2
        y = (screen.height() - 480) // 2
        self.move(x, y)
    
    def _create_widgets(self):
        """Create UI widgets"""
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 5px;
            }
            QTabBar::tab {
                background: #e2e8f0;
                color: #334155;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #3b82f6;
                color: white;
            }
            QTabBar::tab:hover {
                background: #60a5fa;
                color: white;
            }
        """)
        
        # Cartridge visualization widget
        self.cartridge_widget = CartridgeWidget()
        
        # Service tab
        self.service_tab = ServiceTab(self.config.get('stepper_motor', {}))
        self.service_tab.on_stepper_toggle_callback = self._on_service_stepper_toggle
        self.service_tab.on_stepper_speed_change_callback = self._on_service_stepper_speed_change
        
        # Simulation tab (always create it)
        sensor_names = [sensor['name'] for sensor in self.config['sensors']]
        self.simulation_tab = SimulationTab(sensor_names, self.simulation_mode)
        self.simulation_tab.on_sensor_change_callback = self._on_simulation_sensor_changed
        self.simulation_tab.on_mode_change_callback = self._on_simulation_mode_changed
        
        # Add tabs
        self.tab_widget.addTab(self.cartridge_widget, "Monitor")
        self.tab_widget.addTab(self.service_tab, "Service")
        self.tab_widget.addTab(self.simulation_tab, "Simulation")
        
        # State indicator label (at top, 20px height)
        self.state_label = QLabel("State: INIT")
        self.state_label.setFixedHeight(20)
        self.state_label.setStyleSheet("""
            QLabel {
                background-color: #f3f4f6;
                color: #1f2937;
                font-size: 11px;
                font-weight: bold;
                padding: 2px;
                border-radius: 3px;
                border: 1px solid #d1d5db;
            }
        """)
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Pumping toggle button - acts as "START PUMPING" in Cooling state
        # and "STOP PUMPING" in Pumping state. Disabled in other states.
        self.pumping_toggle_button = QPushButton("START PUMPING")
        self.pumping_toggle_button.setMinimumHeight(40)
        self.pumping_toggle_button.clicked.connect(self._on_pumping_toggle_clicked)
        self.pumping_toggle_button.setEnabled(False)
        self._apply_pumping_button_style(active=False)
        
        # Acknowledge Error button (initially disabled)
        self.acknowledge_button = QPushButton("ACKNOWLEDGE ERROR")
        self.acknowledge_button.setMinimumHeight(40)
        self.acknowledge_button.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.acknowledge_button.clicked.connect(self._on_acknowledge_clicked)
        self.acknowledge_button.setEnabled(False)
        
        # Error message label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("""
            QLabel {
                background-color: #fee2e2;
                color: #991b1b;
                font-size: 12px;
                font-weight: bold;
                padding: 8px;
                border-radius: 5px;
                border: 2px solid #fca5a5;
            }
        """)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
    
    def _setup_layout(self):
        """Setup widget layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # State indicator at top (20px height)
        main_layout.addWidget(self.state_label)
        
        # Add tab widget
        main_layout.addWidget(self.tab_widget)
        
        # Error message (only visible in ERROR state)
        main_layout.addWidget(self.error_label)
        
        # State-specific buttons layout
        state_button_layout = QHBoxLayout()
        state_button_layout.setContentsMargins(10, 0, 10, 0)
        state_button_layout.addWidget(self.pumping_toggle_button)
        state_button_layout.addWidget(self.acknowledge_button)
        main_layout.addLayout(state_button_layout)
        
        central_widget.setLayout(main_layout)
    
    def _setup_timer(self):
        """Setup update timer"""
        self.update_timer = QTimer(self)
        # Timer connection will be set by main app
    
    def set_update_callback(self, callback):
        """Set the callback function for timer updates"""
        try:
            self.update_timer.timeout.disconnect()
        except:
            pass
        self.update_timer.timeout.connect(callback)
    
    def _on_simulation_sensor_changed(self, sensor_name: str, state: bool):
        """Handle simulation sensor change"""
        if self.on_sensor_change_callback:
            self.on_sensor_change_callback(sensor_name, state)
    
    def _on_simulation_mode_changed(self, simulation_mode: bool):
        """Handle mode change from simulation tab"""
        if self.is_monitoring:
            # Cannot change mode while monitoring - revert the change
            self.simulation_tab.update_mode_display(self.simulation_mode)
            return
        
        # Update internal state
        self.simulation_mode = simulation_mode
        
        # Refresh state display with new colors based on simulation mode
        state_text = self.state_label.text().replace("State: ", "")
        self.update_state_display(state_text)
        
        # Notify main app of mode change
        if self.on_mode_change_callback:
            self.on_mode_change_callback(self.simulation_mode)
    
    def _on_service_stepper_toggle(self, enabled: bool):
        """Forward service-tab stepper enable toggle to app callback."""
        if self.on_stepper_enable_callback:
            self.on_stepper_enable_callback(enabled)
    
    def _on_service_stepper_speed_change(self, speed_rpm: int):
        """Forward service-tab speed slider updates to app callback."""
        if self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(speed_rpm)
    
    def _on_pumping_toggle_clicked(self):
        """Handle the unified pumping toggle click.
        
        Routes to the start or stop callback based on the current state:
        - Cooling state  -> start pumping
        - Pumping state  -> stop pumping
        """
        current_state = self.state_label.text().replace("State: ", "")
        if current_state == "Pumping":
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
            bg = "#f59e0b"
            hover = "#d97706"
        else:
            bg = "#0ea5e9"
            hover = "#0284c7"
        
        self.pumping_toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #9ca3af;
            }}
        """)
    
    def _on_acknowledge_clicked(self):
        """Handle acknowledge error button click"""
        if self.on_acknowledge_callback:
            self.on_acknowledge_callback()
    
    def set_mode_button_enabled(self, enabled: bool):
        """Enable or disable mode toggle button in simulation tab"""
        if self.simulation_tab:
            self.simulation_tab.set_mode_button_enabled(enabled)
    
    def update_state_display(self, state_name: str, error_message: Optional[str] = None):
        """
        Update state display and button visibility
        
        Args:
            state_name: Current state name
            error_message: Error message if in ERROR state
        """
        # Update state label
        self.state_label.setText(f"State: {state_name}")
        
        # Update state label color based on state and simulation mode
        if state_name == "Error":
            # Error state is always red
            bg_color = "#fee2e2"
            border_color = "#ef4444"
            text_color = "#991b1b"
        else:
            # Non-error states: green if real mode, yellow if simulation mode
            if self.simulation_mode:
                # Simulation mode: yellow
                bg_color = "#fef3c7"
                border_color = "#f59e0b"
                text_color = "#92400e"
            else:
                # Real mode: green
                bg_color = "#dcfce7"
                border_color = "#16a34a"
                text_color = "#15803d"
        
        self.state_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                border: 2px solid {border_color};
            }}
        """)
        
        # Update unified pumping toggle button (label + style + enabled state)
        if state_name == "Pumping":
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
    
    def update_sensor_display(self, sensor_states: dict):
        """Update sensor display"""
        self.cartridge_widget.set_sensor_states(sensor_states)
        self.service_tab.update_sensors(sensor_states)
        self.service_tab.update_temperatures()  # Update mock temperatures
        
        # Feed Temp 1/Temp 2 into the cartridge graph for trend display
        temp1 = self.service_tab.temp_values.get('Temp 1', 0.0)
        temp2 = self.service_tab.temp_values.get('Temp 2', 0.0)
        self.cartridge_widget.add_temperature_sample(temp1, temp2)
        
        # Update simulation tab if in simulation mode
        if self.simulation_mode and self.simulation_tab:
            for sensor_name, state in sensor_states.items():
                self.simulation_tab.set_sensor_state(sensor_name, state)
        
        # Mock output updates (simulate compressor and STSPIN220 stepper driver)
        import random
        if random.random() < 0.1:  # 10% chance to toggle compressor
            self.service_tab.update_outputs(compressor_on=random.choice([True, False]))
        if random.random() < 0.05:  # 5% chance to move stepper
            new_pos = self.service_tab.stepper_position + random.randint(-10, 10)
            self.service_tab.update_outputs(
                stepper_pos=max(0, min(1000, new_pos)),
            )
    
    def set_status_message(self, message: str, is_error: bool = False):
        """Set status message (for compatibility)"""
        pass  # Status is shown visually in the cartridge widget
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.is_monitoring:
            self._on_stop_clicked()
        self.update_timer.stop()
        event.accept()


if __name__ == "__main__":
    # Test the enhanced UI
    import yaml
    
    print("Testing EnhancedSensorMonitorWindow...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create application
    app = QApplication(sys.argv)
    
    # Create window
    window = EnhancedSensorMonitorWindow(config)
    
    # Set dummy callbacks
    def on_start():
        print("Start button clicked")
        return True
    
    def on_stop():
        print("Stop button clicked")
    
    window.on_start_callback = on_start
    window.on_stop_callback = on_stop
    
    # Show window
    window.show()
    
    # Simulate sensor updates
    import random
    def simulate_update():
        states = {
            'Level Low': random.choice([True, False]),
            'Level Critical': random.choice([True, False]),
            'Cartridge In Place': random.choice([True, False])
        }
        window.update_sensor_display(states)
    
    # Timer for simulation
    sim_timer = QTimer()
    sim_timer.timeout.connect(simulate_update)
    sim_timer.start(2000)
    
    # Run application
    sys.exit(app.exec())

# Made with Bob
