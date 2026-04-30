"""
Enhanced UI Module with Visual Cartridge Representation
PyQt6-based user interface with graphical sensor display
"""

import sys
import time
from collections import deque
from typing import Optional, Callable

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QTabWidget,
    QLabel, QGridLayout, QGroupBox, QCheckBox, QSlider, QComboBox, QStackedWidget,
    QSizePolicy, QTabBar
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QLinearGradient,
    QFont, QPainterPath
)


class CartridgeWidget(QWidget):
    """Custom widget to draw the cartridge with levels and sensor"""
    
    def __init__(self, show_cartridge: bool = True, show_graph: bool = True, show_temp_controls: bool = True):
        super().__init__()
        self.show_cartridge = show_cartridge
        self.show_graph = show_graph
        self.show_temp_controls = show_temp_controls
        # Keep this widget compact so the main action row below remains visible
        # on smaller/fullscreen Raspberry Pi displays.
        self.setMinimumSize(640, 300)
        
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
        self._x_window_minutes_options = [5, 15, 60]
        self._x_window_minutes = 5
        self._x_pan_windows = 0
        
        # Touch-friendly +/- buttons for fine adjustment
        if self.show_temp_controls:
            self._create_temp_buttons()
            self._create_graph_nav_controls()
    
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
            # Keep clear space above the global bottom action buttons.
            bottom_safe = 110
            graph_width = self.width() - (2 * margin)
            if self.show_temp_controls:
                # Keep room for the right-side gauge and +/- controls.
                graph_width -= 200
            self._draw_temperature_graph(
                painter,
                graph_x=margin,
                graph_y=margin,
                graph_width=max(220, graph_width),
                graph_height=max(140, self.height() - (2 * margin) - bottom_safe),
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
    _GRAPH_TEMP_MIN = 25.0
    _GRAPH_TEMP_MAX = 40.0
    _GRAPH_Y_MARGIN_DEG = 0.4
    _GRAPH_Y_MARGIN_RATIO = 0.08
    _GRAPH_SERIES = (
        # (history tuple index, label, color)
        (1, "Set Tmp",    "#0ea5e9"),
        (2, "CSF Temp", "#16a34a"),
    )
    
    def add_temperature_sample(self, temp1: float, temp2: float):
        """Record a new sample of (set temperature, CSF Temp, Heat Exchanger Temp) at current time"""
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
                painter.setPen(pen)
                
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

    def _compute_visible_y_range(self, visible_entries):
        if not visible_entries:
            return self._GRAPH_TEMP_MIN, self._GRAPH_TEMP_MAX
        values = [value for entry in visible_entries for value in entry[1:4]]
        data_min = min(values)
        data_max = max(values)
        data_range = max(0.5, data_max - data_min)
        margin = max(self._GRAPH_Y_MARGIN_DEG, data_range * self._GRAPH_Y_MARGIN_RATIO)
        y_min = data_min - margin
        y_max = data_max + margin
        if y_max - y_min < 1.0:
            midpoint = (y_min + y_max) / 2.0
            y_min = midpoint - 0.5
            y_max = midpoint + 0.5
        return y_min, y_max

    @staticmethod
    def _build_y_ticks(y_min: float, y_max: float, count: int = 4):
        if count < 2:
            return [y_min, y_max]
        step = (y_max - y_min) / float(count - 1)
        return [y_min + i * step for i in range(count)]
    
    def _draw_graph_legend(self, painter: QPainter, graph_x: int, y: int, graph_width: int):
        """Draw legend entries for the graph series"""
        entries = self._GRAPH_SERIES
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
        if not self.show_temp_controls:
            return False
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
                background-color: #0e6a76;
                color: white;
                font-size: 22px;
                font-weight: 600;
                border: 1px solid #0b565f;
                border-radius: 12px;
            }
            QPushButton:pressed {
                background-color: #0b565f;
            }
            QPushButton:hover {
                background-color: #0d616c;
            }
            QPushButton:disabled {
                background-color: #d9e0e6;
                border-color: #c8d1d8;
                color: #8b98a5;
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

    def _create_graph_nav_controls(self):
        """Create graph X-axis controls (window size and panning)."""
        nav_button_style = """
            QPushButton {
                background-color: #475569;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid #334155;
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: #334155;
            }
            QPushButton:disabled {
                background-color: #cbd5e1;
                border-color: #94a3b8;
                color: #64748b;
            }
        """
        self.graph_nav_left_button = QPushButton("<", self)
        self.graph_nav_left_button.setFixedSize(40, 32)
        self.graph_nav_left_button.setStyleSheet(nav_button_style)
        self.graph_nav_left_button.clicked.connect(self._on_graph_nav_left)

        self.graph_nav_right_button = QPushButton(">", self)
        self.graph_nav_right_button.setFixedSize(40, 32)
        self.graph_nav_right_button.setStyleSheet(nav_button_style)
        self.graph_nav_right_button.clicked.connect(self._on_graph_nav_right)

        self.graph_window_combo = QComboBox(self)
        for minutes in self._x_window_minutes_options:
            self.graph_window_combo.addItem(f"{minutes} min", minutes)
        self.graph_window_combo.setCurrentIndex(self._x_window_minutes_options.index(self._x_window_minutes))
        self.graph_window_combo.currentIndexChanged.connect(self._on_graph_window_changed)
        self.graph_window_combo.setStyleSheet("""
            QComboBox {
                font-size: 11px;
                font-weight: bold;
                color: #1f2937;
                background-color: white;
                border: 2px solid #94a3b8;
                border-radius: 6px;
                padding: 4px 8px;
            }
        """)
    
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
        buttons_top = gauge_y + gauge_height + 8
        # Keep a larger bottom gap so controls don't collide visually with
        # the main window action buttons below the tab area.
        max_top = self.height() - self._TEMP_BUTTON_SIZE - 52
        buttons_top = min(buttons_top, max_top)
        
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
        # Keep time-axis controls visible near the bottom-left of graph area.
        # Leave extra clearance from the widget bottom so they never clip.
        top = max(10, self.height() - 116)
        left = 12
        self.graph_nav_left_button.move(left, top)
        self.graph_window_combo.setFixedSize(86, 32)
        self.graph_window_combo.move(left + 44, top)
        self.graph_nav_right_button.move(left + 44 + 90, top)

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
        
        # Sensor states
        self.sensor_states = {}
        
        # Output states
        self.compressor_on = False
        self.compressor_command_on = False
        self.compressor_speed_rpm = int((compressor_config or {}).get("default_speed_rpm", 3000))
        self.compressor_max_speed_rpm = int((compressor_config or {}).get("max_speed_rpm", 6000))
        self.compressor_max_speed_rpm = max(100, self.compressor_max_speed_rpm)
        self.stepper_speed_rpm = int((stepper_config or {}).get("default_speed_rpm", 30))
        self.stepper_max_speed_rpm = int((stepper_config or {}).get("max_speed_rpm", 60))
        self.stepper_max_speed_rpm = max(5, self.stepper_max_speed_rpm)
        
        self.on_compressor_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        self.on_compressor_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_compressor_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None
        self.on_stepper_continuous_toggle_callback: Optional[Callable[[bool], None]] = None
        self.stepper_continuous_on: bool = False
        
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
        self.compressor_label = QLabel("Compressor: OFF")
        self.compressor_label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
        self.compressor_speed_label = QLabel(f"{self.compressor_speed_rpm} RPM")
        self.compressor_speed_label.setStyleSheet(self._CONTROL_LABEL_STYLE)
        self.compressor_speed_label.setFixedHeight(42)
        self.compressor_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.compressor_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.compressor_speed_slider.setRange(0, self.compressor_max_speed_rpm)
        self.compressor_speed_slider.setTickInterval(500)
        self.compressor_speed_slider.setSingleStep(50)
        self.compressor_speed_slider.setPageStep(200)
        self.compressor_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.compressor_speed_slider.setValue(max(0, min(self.compressor_max_speed_rpm, self.compressor_speed_rpm)))
        self.compressor_speed_slider.setMinimumHeight(42)
        self.compressor_speed_slider.valueChanged.connect(self._on_compressor_speed_changed)

        self.compressor_toggle_button = QPushButton("COMPRESSOR OFF")
        self.compressor_toggle_button.setMinimumHeight(40)
        self.compressor_toggle_button.clicked.connect(self._on_compressor_toggle_clicked)
        self._apply_compressor_button_style(False)
        
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
        compressor_speed_row = QHBoxLayout()
        compressor_speed_row.setContentsMargins(0, 0, 0, 0)
        compressor_speed_row.setSpacing(6)
        compressor_speed_row.addWidget(self.compressor_speed_slider, 1)
        compressor_speed_row.addWidget(self.compressor_speed_label, 0, Qt.AlignmentFlag.AlignVCenter)
        compressor_layout.addLayout(compressor_speed_row)
        compressor_layout.addWidget(self.compressor_toggle_button)
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
        stepper_speed_rpm: int = None,
    ):
        """Update output display"""
        if compressor_on is not None:
            self.compressor_on = compressor_on
        if compressor_speed_rpm is not None:
            self.compressor_speed_rpm = int(compressor_speed_rpm)
            if self.compressor_speed_slider.value() != self.compressor_speed_rpm:
                self.compressor_speed_slider.setValue(self.compressor_speed_rpm)
        if compressor_command_on is not None:
            self.compressor_command_on = bool(compressor_command_on)
            self._apply_compressor_button_style(self.compressor_command_on)
        if stepper_speed_rpm is not None:
            self.stepper_speed_rpm = int(stepper_speed_rpm)
            if self.stepper_speed_slider.value() != self.stepper_speed_rpm:
                self.stepper_speed_slider.setValue(self.stepper_speed_rpm)
        
        # Update compressor label
        comp_status = "ON" if self.compressor_on else "OFF"
        comp_color = "#16a34a" if self.compressor_on else "#6b7280"
        self.compressor_label.setText(f"Compressor: {comp_status}")
        self.compressor_label.setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=comp_color))
        self.compressor_speed_label.setText(f"{self.compressor_speed_rpm} RPM")
        
        self.stepper_speed_label.setText(f"{self.stepper_speed_rpm} RPM")
        self._update_stepper_control_enabled_state()
        self.stepper_continuous_button.setEnabled(True)

    def _on_stepper_speed_changed(self, value: int):
        """Handle speed slider changes."""
        self.stepper_speed_rpm = int(value)
        self.stepper_speed_label.setText(f"{self.stepper_speed_rpm} RPM")
        if self.on_stepper_speed_change_callback:
            self.on_stepper_speed_change_callback(self.stepper_speed_rpm)

    def _on_compressor_speed_changed(self, value: int):
        self.compressor_speed_rpm = int(value)
        self.compressor_speed_label.setText(f"{self.compressor_speed_rpm} RPM")
        if self.on_compressor_speed_change_callback:
            self.on_compressor_speed_change_callback(self.compressor_speed_rpm)

    def _on_compressor_toggle_clicked(self):
        self.compressor_command_on = not self.compressor_command_on
        self._apply_compressor_button_style(self.compressor_command_on)
        if self.on_compressor_toggle_callback:
            self.on_compressor_toggle_callback(self.compressor_command_on)

    def _apply_compressor_button_style(self, is_on: bool):
        if is_on:
            text = "COMPRESSOR ON"
            bg = "#16a34a"
            hover = "#15803d"
        else:
            text = "COMPRESSOR OFF"
            bg = "#6b7280"
            hover = "#4b5563"
        self.compressor_toggle_button.setText(text)
        self.compressor_toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-size: 13px;
                font-weight: 700;
                border-radius: 12px;
                padding: 8px 12px;
                border: 1px solid #cfd8e0;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    # Backward-compatible alias: some call sites may still reference the old
    # singular method name.
    def _on_stepper_speed_change(self, value: int):
        self._on_stepper_speed_changed(value)

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
    """Service 2 tab showing temperature channels."""
    _LABEL_NEUTRAL_STYLE = "font-size: 12px; padding: 6px; color: #5c6b79;"
    _LABEL_STRONG_TEMPLATE = "font-size: 12px; padding: 6px; color: {color}; font-weight: 600;"

    def __init__(self):
        super().__init__()
        self.temp_values = {
            'CSF Temp': float("nan"),
            'Heat Exchanger Temp': float("nan"),
            'Temp 3': float("nan"),
            'Temp 4': float("nan"),
        }
        self.temp_labels = {}
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self):
        self.temp_group = QGroupBox("Temperature Sensors")
        self.temp_group.setStyleSheet(ServiceTab._group_box_style("#f59e0b", "12px"))
        for name in ['CSF Temp', 'Heat Exchanger Temp', 'Temp 3', 'Temp 4']:
            label = QLabel(f"{name}: --°C")
            label.setStyleSheet(self._LABEL_NEUTRAL_STYLE)
            self.temp_labels[name] = label

    def _setup_layout(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        temp_layout = QGridLayout()
        temp_layout.addWidget(self.temp_labels['CSF Temp'], 0, 0)
        temp_layout.addWidget(self.temp_labels['Heat Exchanger Temp'], 0, 1)
        temp_layout.addWidget(self.temp_labels['Temp 3'], 1, 0)
        temp_layout.addWidget(self.temp_labels['Temp 4'], 1, 1)
        self.temp_group.setLayout(temp_layout)
        main_layout.addWidget(self.temp_group)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_temperatures(self, temps: dict = None):
        """Update temperature display with real thermocouple values."""
        if temps:
            self.temp_values.update(temps)

        for name, value in self.temp_values.items():
            if value != value:  # NaN check
                self.temp_labels[name].setText(f"{name}: --.-°C")
                self.temp_labels[name].setStyleSheet(self._LABEL_NEUTRAL_STYLE)
                continue
            self.temp_labels[name].setText(f"{name}: {value:.1f}°C")
            if value < 20:
                color = "#3b82f6"
            elif value > 25:
                color = "#ef4444"
            else:
                color = "#16a34a"
            self.temp_labels[name].setStyleSheet(self._LABEL_STRONG_TEMPLATE.format(color=color))
    
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
        
    def _setup_layout(self):
        """Setup simulation tab layout"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
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
        self.on_stepper_speed_change_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_start_callback: Optional[Callable[[int], None]] = None
        self.on_stepper_jog_stop_callback: Optional[Callable[[], None]] = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_layout()
        self._setup_timer()
        if getattr(self, "_fullscreen_requested", False):
            # Enter fullscreen only after widgets/layout exist.
            self.showFullScreen()
    
    def _setup_window(self):
        """Setup main window properties"""
        self.setWindowTitle("Cartridge Level Monitor")
        ui_config = self.config.get("ui", {})
        self._fullscreen_requested = bool(ui_config.get("fullscreen", False))
        if self._fullscreen_requested:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        else:
            self.setFixedSize(800, 480)
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
            QCheckBox {
                color: #2f3b47;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #fbe7e3;
                border: 2px solid #d97f66;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #dff0f2;
                border: 2px solid #0e6a76;
                border-radius: 4px;
            }
        """)
        
        # Center window on screen when running windowed.
        if not self._fullscreen_requested:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 800) // 2
            y = (screen.height() - 480) // 2
            self.move(x, y)
    
    def _create_widgets(self):
        """Create UI widgets"""
        # Main screen widget: temperature graph + setpoint controls
        self.main_graph_widget = CartridgeWidget(
            show_cartridge=False,
            show_graph=True,
            show_temp_controls=True,
        )
        self.main_graph_widget.setMinimumHeight(260)
        self.main_graph_widget.setMaximumHeight(360)
        self.main_graph_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Widgets tab: cartridge + 3 sensors only
        self.cartridge_widget = CartridgeWidget(
            show_cartridge=True,
            show_graph=False,
            show_temp_controls=False,
        )
        
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
        self.service_tab.on_compressor_speed_change_callback = self._on_service_compressor_speed_change

        # Service 2 tab (temperature channels)
        self.service2_tab = Service2Tab()
        
        # Simulation tab (always create it)
        sensor_names = [sensor['name'] for sensor in self.config['sensors']]
        self.simulation_tab = SimulationTab(sensor_names, self.simulation_mode)
        self.simulation_tab.on_sensor_change_callback = self._on_simulation_sensor_changed
        self.simulation_tab.on_mode_change_callback = self._on_simulation_mode_changed

        # In-window advanced area (service + simulation tabs)
        self.advanced_tab_selector = QTabBar()
        self.advanced_tab_selector.addTab("Service")
        self.advanced_tab_selector.addTab("Service 2")
        self.advanced_tab_selector.addTab("Simulation")
        self.advanced_tab_selector.addTab("Widgets")
        self.advanced_tab_selector.setExpanding(False)

        self.advanced_content_stack = QStackedWidget()
        self.advanced_content_stack.addWidget(self.service_tab)
        self.advanced_content_stack.addWidget(self.service2_tab)
        self.advanced_content_stack.addWidget(self.simulation_tab)
        self.advanced_content_stack.addWidget(self.cartridge_widget)
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
        """Setup widget layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        self._main_layout = main_layout
        
        # Header row: state indicator + advanced settings button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)
        header_row.addWidget(self.state_label, 1)
        header_row.addWidget(self.to_main_menu_button)
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
        self.state_buttons_row.setMinimumHeight(56)
        self.state_buttons_row.setMaximumHeight(56)
        self.state_buttons_row.setFixedHeight(56)
        self.state_buttons_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.state_buttons_row)
        
        central_widget.setLayout(main_layout)
        self._show_main_view()
    
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

    def _on_service_compressor_speed_change(self, speed_rpm: int):
        """Forward service-tab compressor speed setpoint change."""
        if self.on_compressor_speed_change_callback:
            self.on_compressor_speed_change_callback(speed_rpm)
    
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
        half_width = max(260, (self.width() - 20) // 2)
        self.state_label.setFixedWidth(half_width)

    def _show_main_view(self):
        """Return to main screen from advanced settings page."""
        self.content_stack.setCurrentWidget(self.main_graph_widget)
        self._ensure_state_buttons_row_attached()
        self.state_buttons_row.show()
        self.pumping_toggle_button.show()
        self.acknowledge_button.show()
        self.advanced_settings_button.show()
        self._set_main_action_buttons_visible(True)
        self.to_main_menu_button.setVisible(False)
        self.state_label.setMinimumWidth(0)
        self.state_label.setMaximumWidth(16777215)
        self.state_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Force a full relayout + repaint pass. Some Raspberry Pi Qt builds can
        # leave this row visually hidden after page switches unless we re-show
        # and refresh on the next event loop tick.
        self._refresh_main_action_buttons_row()
        QTimer.singleShot(0, self._refresh_main_action_buttons_row)
        QTimer.singleShot(60, self._refresh_main_action_buttons_row)
        QTimer.singleShot(140, self._refresh_main_action_buttons_row)

    def _set_main_action_buttons_visible(self, visible: bool):
        """Show/hide controls; fullscreen uses disable-only workaround."""
        fullscreen_mode = bool(getattr(self, "_fullscreen_requested", False) or self.isFullScreen())
        # Raspberry Pi fullscreen + frameless mode can fail to restore widgets
        # after hide/show cycles. In fullscreen, keep the row shown and only
        # toggle enabled state.
        if fullscreen_mode:
            self.state_buttons_row.show()
            self.pumping_toggle_button.show()
            self.acknowledge_button.show()
            self.advanced_settings_button.show()
            self.state_buttons_row.setEnabled(visible)
            if visible:
                self._refresh_main_action_buttons_row()
            return

        self.state_buttons_row.setVisible(visible)
        self.pumping_toggle_button.setVisible(visible)
        self.acknowledge_button.setVisible(visible)
        self.advanced_settings_button.setVisible(visible)

    def _refresh_main_action_buttons_row(self):
        """Force the bottom action row to be shown and repainted."""
        self.state_buttons_row.show()
        self.pumping_toggle_button.show()
        self.acknowledge_button.show()
        self.advanced_settings_button.show()
        layout = self.centralWidget().layout() if self.centralWidget() else None
        if layout:
            layout.invalidate()
            layout.activate()
        self.state_buttons_row.raise_()
        self.state_buttons_row.updateGeometry()
        self.state_buttons_row.update()
        self.state_buttons_row.repaint()

    def _ensure_state_buttons_row_attached(self):
        """Ensure the action row is attached at the bottom of the main layout."""
        if not hasattr(self, "_main_layout") or not self._main_layout:
            return
        self._main_layout.removeWidget(self.state_buttons_row)
        self._main_layout.addWidget(self.state_buttons_row)
    
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
            bg_color = "#f8e5db"
            border_color = "#d06a45"
            text_color = "#7e3f26"
        else:
            # Non-error states: green if real mode, yellow if simulation mode
            if self.simulation_mode:
                # Simulation mode: yellow
                bg_color = "#f4ead2"
                border_color = "#d2b06c"
                text_color = "#6f5522"
            else:
                # Real mode: green
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
    
    def update_sensor_display(self, sensor_states: dict, temperatures: Optional[dict] = None):
        """Update sensor display"""
        self.cartridge_widget.set_sensor_states(sensor_states)
        self.service_tab.update_sensors(sensor_states)
        self.service2_tab.update_temperatures(temperatures)
        
        # Feed CSF Temp / Heat Exchanger Temp into the graph for trend display
        temp1 = self.service2_tab.temp_values.get('CSF Temp', 0.0)
        temp2 = self.service2_tab.temp_values.get('Heat Exchanger Temp', 0.0)
        if temp1 == temp1 and temp2 == temp2:  # skip NaN values
            self.main_graph_widget.add_temperature_sample(temp1, temp2)
            self.cartridge_widget.add_temperature_sample(temp1, temp2)
        
        # Update simulation tab if in simulation mode
        if self.simulation_mode and self.simulation_tab:
            for sensor_name, state in sensor_states.items():
                self.simulation_tab.set_sensor_state(sensor_name, state)
        
        # Keep compressor display stable unless updated by app logic.
        self.service_tab.update_outputs()
    
    def set_status_message(self, message: str, is_error: bool = False):
        """Set status message (for compatibility)"""
        pass  # Status is shown visually in the cartridge widget

    def resizeEvent(self, event):
        """Keep advanced-mode status indicator at half-width on resize."""
        super().resizeEvent(event)
        if hasattr(self, "content_stack") and self.content_stack.currentWidget() is self.advanced_page:
            half_width = max(260, (self.width() - 20) // 2)
            self.state_label.setFixedWidth(half_width)

    def keyPressEvent(self, event):
        """Allow exiting/toggling fullscreen with keyboard shortcuts."""
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._leave_fullscreen_mode()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self._leave_fullscreen_mode()
            else:
                self._enter_fullscreen_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    def _enter_fullscreen_mode(self):
        """Switch to frameless fullscreen mode."""
        self._fullscreen_requested = True
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.showFullScreen()

    def _leave_fullscreen_mode(self):
        """Return to normal windowed mode with title bar."""
        self._fullscreen_requested = False
        self.setWindowFlags(Qt.WindowType.Window)
        self.showNormal()
        self.setFixedSize(800, 480)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - 800) // 2
        y = (screen.height() - 480) // 2
        self.move(x, y)
    
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


