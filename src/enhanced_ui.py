"""
Enhanced UI Module with Visual Cartridge Representation
PyQt6-based user interface with graphical sensor display
"""

import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QLinearGradient,
    QFont, QPainterPath, QPolygonF
)


class CartridgeWidget(QWidget):
    """Custom widget to draw the cartridge with levels and sensor"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(900, 650)
        
        # Sensor states
        self.level_low = False
        self.level_critical = False
        self.cartridge_present = False
        
        # Level heights (0.0 to 1.0, where 1.0 is full)
        self.level1_height = 0.6  # 60% full
        self.level2_height = 0.8  # 80% full
    
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
        
        # Draw title
        self._draw_title(painter)
        
        # Draw machine slot
        self._draw_machine_slot(painter)
        
        # Draw cartridge (if present)
        if self.cartridge_present:
            self._draw_cartridge(painter)
            self._draw_level_chambers(painter)
        
        # Draw sensor module
        self._draw_sensor_module(painter)
        
        # Draw detection beam
        self._draw_detection_beam(painter)
        
        # Draw status indicator
        self._draw_status_indicator(painter)
    
    def _draw_background(self, painter: QPainter):
        """Draw gradient background"""
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#f8fbff"))
        gradient.setColorAt(1, QColor("#eaf2ff"))
        painter.fillRect(self.rect(), gradient)
    
    def _draw_title(self, painter: QPainter):
        """Draw title text"""
        painter.setPen(QColor("#0f172a"))
        font = QFont("Arial", 32, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, 20, 0, 0),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Cartridge With 2 Levels + Presence Sensor")
    
    def _draw_machine_slot(self, painter: QPainter):
        """Draw the machine slot"""
        painter.setBrush(QColor("#dbeafe"))
        painter.setPen(QPen(QColor("#3b82f6"), 4))
        painter.drawRoundedRect(120, 150, 560, 500, 24, 24)
        
        # Label
        painter.setPen(QColor("#1e40af"))
        font = QFont("Arial", 16, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(120, 160, 560, 30),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Machine Slot")
    
    def _draw_cartridge(self, painter: QPainter):
        """Draw the cartridge"""
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#0f172a"), 4))
        painter.drawRoundedRect(220, 230, 360, 360, 20, 20)
        
        # Label
        painter.setPen(QColor("#0f172a"))
        font = QFont("Arial", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(220, 600, 360, 30),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Cartridge")
    
    def _draw_level_chambers(self, painter: QPainter):
        """Draw the two level chambers with liquid"""
        chambers = [
            {"x": 265, "level": self.level1_height, "color": "#38bdf8", "label": "Level 1", "critical": self.level_critical},
            {"x": 415, "level": self.level2_height, "color": "#0ea5e9", "label": "Level 2", "critical": self.level_low}
        ]
        
        chamber_y = 280
        chamber_width = 120
        chamber_height = 260
        
        for chamber in chambers:
            x = chamber["x"]
            
            # Draw chamber outline
            painter.setBrush(QColor("#f1f5f9"))
            painter.setPen(QPen(QColor("#64748b"), 3))
            painter.drawRoundedRect(x, chamber_y, chamber_width, chamber_height, 10, 10)
            
            # Draw liquid level
            liquid_height = chamber_height * chamber["level"]
            liquid_y = chamber_y + chamber_height - liquid_height
            
            # Liquid color with opacity
            liquid_color = QColor(chamber["color"])
            liquid_color.setAlphaF(0.85)
            painter.setBrush(liquid_color)
            painter.setPen(Qt.PenStyle.NoPen)
            
            # Create rounded bottom for liquid
            path = QPainterPath()
            path.addRoundedRect(QRectF(x + 3, liquid_y, chamber_width - 6, liquid_height - 3), 8, 8)
            painter.drawPath(path)
            
            # Draw level line (dashed)
            pen = QPen(QColor("#0284c7"), 2)
            pen.setDashPattern([10, 8])
            painter.setPen(pen)
            painter.drawLine(x, int(liquid_y), x + chamber_width, int(liquid_y))
            
            # Draw level label
            painter.setPen(QColor("#0f172a"))
            font = QFont("Arial", 11, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(x, liquid_y - 25, chamber_width, 20),
                            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                            chamber["label"])
            
            # Draw warning indicator if level is critical
            if chamber["critical"]:
                painter.setBrush(QColor("#ef4444"))
                painter.setPen(QPen(QColor("#991b1b"), 2))
                painter.drawEllipse(QPointF(x + chamber_width + 15, liquid_y), 8, 8)
    
    def _draw_sensor_module(self, painter: QPainter):
        """Draw the sensor module"""
        painter.setBrush(QColor("#dcfce7"))
        painter.setPen(QPen(QColor("#16a34a"), 4))
        painter.drawRoundedRect(700, 360, 160, 80, 12, 12)
        
        # Green indicator circle
        if self.cartridge_present:
            painter.setBrush(QColor("#22c55e"))
        else:
            painter.setBrush(QColor("#94a3b8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(730, 400), 16, 16)
        
        # Text
        painter.setPen(QColor("#065f46"))
        font = QFont("Arial", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(750, 360, 100, 80),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        "Sensor")
    
    def _draw_detection_beam(self, painter: QPainter):
        """Draw detection beam from sensor to cartridge"""
        if self.cartridge_present:
            pen = QPen(QColor("#0ea5e9"), 5)
        else:
            pen = QPen(QColor("#94a3b8"), 5)
        painter.setPen(pen)
        
        # Draw line
        start_x, start_y = 700, 400
        end_x, end_y = 590, 400
        painter.drawLine(start_x, start_y, end_x, end_y)
        
        # Draw arrowhead
        arrow_size = 12
        arrow = QPolygonF([
            QPointF(end_x, end_y),
            QPointF(end_x + arrow_size, end_y - arrow_size/2),
            QPointF(end_x + arrow_size, end_y + arrow_size/2)
        ])
        if self.cartridge_present:
            painter.setBrush(QColor("#0ea5e9"))
        else:
            painter.setBrush(QColor("#94a3b8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)
        
        # Helper text
        painter.setPen(QColor("#475569"))
        font = QFont("Arial", 11)
        painter.setFont(font)
        painter.drawText(QRectF(700, 450, 160, 40),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Checks cartridge\nis in place")
    
    def _draw_status_indicator(self, painter: QPainter):
        """Draw status indicator at bottom right"""
        # Status circle
        if self.cartridge_present:
            painter.setBrush(QColor("#16a34a"))
            status_text = "Cartridge detected"
            text_color = "#16a34a"
        else:
            painter.setBrush(QColor("#dc2626"))
            status_text = "No cartridge"
            text_color = "#dc2626"
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(720, 580), 20, 20)
        
        # Checkmark or X
        painter.setPen(QPen(QColor("white"), 3))
        if self.cartridge_present:
            # Draw checkmark
            painter.drawLine(712, 580, 718, 586)
            painter.drawLine(718, 586, 728, 574)
        else:
            # Draw X
            painter.drawLine(710, 570, 730, 590)
            painter.drawLine(730, 570, 710, 590)
        
        # Status text
        painter.setPen(QColor(text_color))
        font = QFont("Arial", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(750, 565, 140, 30),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        status_text)


class EnhancedSensorMonitorWindow(QMainWindow):
    """Main window with enhanced cartridge visualization"""
    
    def __init__(self, config: dict):
        """Initialize main window"""
        super().__init__()
        
        self.config = config
        self.is_monitoring = False
        
        # Callbacks
        self.on_start_callback: Optional[callable] = None
        self.on_stop_callback: Optional[callable] = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_layout()
        self._setup_timer()
    
    def _setup_window(self):
        """Setup main window properties"""
        self.setWindowTitle("Cartridge Level Monitor")
        self.setFixedSize(900, 750)
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - 900) // 2
        y = (screen.height() - 750) // 2
        self.move(x, y)
    
    def _create_widgets(self):
        """Create UI widgets"""
        # Cartridge visualization widget
        self.cartridge_widget = CartridgeWidget()
        
        # Start button
        self.start_button = QPushButton("START LOGGING")
        self.start_button.setMinimumHeight(50)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.start_button.clicked.connect(self._on_start_clicked)
        
        # Stop button
        self.stop_button = QPushButton("STOP LOGGING")
        self.stop_button.setMinimumHeight(50)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
    
    def _setup_layout(self):
        """Setup widget layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 10)
        main_layout.setSpacing(10)
        
        # Add cartridge widget
        main_layout.addWidget(self.cartridge_widget)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(20, 0, 20, 0)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)
        
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
    
    def _on_start_clicked(self):
        """Handle start button click"""
        if self.on_start_callback:
            success = self.on_start_callback()
            if success:
                self.is_monitoring = True
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
    
    def _on_stop_clicked(self):
        """Handle stop button click"""
        if self.on_stop_callback:
            self.on_stop_callback()
        
        self.is_monitoring = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def update_sensor_display(self, sensor_states: dict):
        """Update sensor display"""
        self.cartridge_widget.set_sensor_states(sensor_states)
    
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
