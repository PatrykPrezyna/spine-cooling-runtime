"""
Enhanced UI Module with Visual Cartridge Representation
PyQt6-based user interface with graphical sensor display
"""

import sys
from datetime import datetime
from typing import Optional, Callable

from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QTabWidget,
    QLabel, QGridLayout, QGroupBox, QFrame, QCheckBox
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QLinearGradient,
    QFont, QPainterPath, QPolygonF
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
    
        
        # Draw machine slot
        # self._draw_machine_slot(painter)
        
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
    
    def _draw_machine_slot(self, painter: QPainter):
        """Draw the machine slot"""
        painter.setBrush(QColor("#dbeafe"))
        painter.setPen(QPen(QColor("#3b82f6"), 3))
        painter.drawRoundedRect(80, 90, 400, 320, 20, 20)
        
        # Label
        painter.setPen(QColor("#1e40af"))
        font = QFont("Arial", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(80, 95, 400, 25),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Machine Slot")
    
    def _draw_cartridge(self, painter: QPainter):
        """Draw the cartridge"""
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(QColor("#0f172a"), 3))
        painter.drawRoundedRect(150, 140, 260, 240, 16, 16)
        
        # Label
        painter.setPen(QColor("#0f172a"))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(150, 385, 260, 25),
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                        "Cartridge")
    
    def _draw_level_chambers(self, painter: QPainter):
        """Draw the two level chambers with liquid"""
        chambers = [
            {"x": 190, "level": self.level1_height, "color": "#38bdf8", "label": "Level 1", "critical": self.level_critical},
            {"x": 300, "level": self.level2_height, "color": "#0ea5e9", "label": "Level 2", "critical": self.level_low}
        ]
        
        chamber_y = 180
        chamber_width = 85
        chamber_height = 180
        
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
        painter.setPen(QPen(QColor("#16a34a"), 3))
        painter.drawRoundedRect(540, 230, 120, 60, 10, 10)
        
        # Green indicator circle
        if self.cartridge_present:
            painter.setBrush(QColor("#22c55e"))
        else:
            painter.setBrush(QColor("#94a3b8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(560, 260), 12, 12)
        
        # Text
        painter.setPen(QColor("#065f46"))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(575, 230, 80, 60),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        "Sensor")
    
    def _draw_detection_beam(self, painter: QPainter):
        """Draw detection beam from sensor to cartridge"""
        if self.cartridge_present:
            pen = QPen(QColor("#0ea5e9"), 4)
        else:
            pen = QPen(QColor("#94a3b8"), 4)
        painter.setPen(pen)
        
        # Draw line
        start_x, start_y = 540, 260
        end_x, end_y = 420, 260
        painter.drawLine(start_x, start_y, end_x, end_y)
        
        # Draw arrowhead
        arrow_size = 10
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
        font = QFont("Arial", 9)
        painter.setFont(font)
        painter.drawText(QRectF(540, 300, 120, 35),
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


class ServiceTab(QWidget):
    """Service tab showing all sensors and outputs"""
    
    def __init__(self):
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
        
        self.stepper_label = QLabel("Stepper Motor: Position 0")
        self.stepper_label.setStyleSheet("font-size: 11px; padding: 5px; color: #6b7280;")
    
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
    
    def update_outputs(self, compressor_on: bool = None, stepper_pos: int = None):
        """Update output display"""
        if compressor_on is not None:
            self.compressor_on = compressor_on
        if stepper_pos is not None:
            self.stepper_position = stepper_pos
        
        # Update compressor label
        comp_status = "ON" if self.compressor_on else "OFF"
        comp_color = "#16a34a" if self.compressor_on else "#6b7280"
        self.compressor_label.setText(f"Compressor: {comp_status}")
        self.compressor_label.setStyleSheet(
            f"font-size: 11px; padding: 5px; color: {comp_color}; font-weight: bold;"
        )
        
        # Update stepper label
        self.stepper_label.setText(f"Stepper Motor: Position {self.stepper_position}")
        self.stepper_label.setStyleSheet(
            "font-size: 11px; padding: 5px; color: #3b82f6; font-weight: bold;"
        )


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
                border: 2px solid #8b5cf6;
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
        
        # Sensors layout
        sensors_layout = QVBoxLayout()
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
        self.service_tab = ServiceTab()
        
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
        
        # Start Pumping button (visible only in COOLING state)
        self.start_pumping_button = QPushButton("START PUMPING")
        self.start_pumping_button.setMinimumHeight(40)
        self.start_pumping_button.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.start_pumping_button.clicked.connect(self._on_start_pumping_clicked)
        self.start_pumping_button.setEnabled(False)
        
        # Stop Pumping button (initially disabled)
        self.stop_pumping_button = QPushButton("STOP PUMPING")
        self.stop_pumping_button.setMinimumHeight(40)
        self.stop_pumping_button.setStyleSheet("""
            QPushButton {
                background-color: #f59e0b;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d97706;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.stop_pumping_button.clicked.connect(self._on_stop_pumping_clicked)
        self.stop_pumping_button.setEnabled(False)
        
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
        state_button_layout.addWidget(self.start_pumping_button)
        state_button_layout.addWidget(self.stop_pumping_button)
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
    
    def _on_start_pumping_clicked(self):
        """Handle start pumping button click"""
        if self.on_start_pumping_callback:
            self.on_start_pumping_callback()
    
    def _on_stop_pumping_clicked(self):
        """Handle stop pumping button click"""
        if self.on_stop_pumping_callback:
            self.on_stop_pumping_callback()
    
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
        
        # Enable/disable state-specific buttons (always visible, grayed out when not usable)
        self.start_pumping_button.setEnabled(state_name == "Cooling")
        self.stop_pumping_button.setEnabled(state_name == "Pumping")
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
        
        # Update simulation tab if in simulation mode
        if self.simulation_mode and self.simulation_tab:
            for sensor_name, state in sensor_states.items():
                self.simulation_tab.set_sensor_state(sensor_name, state)
        
        # Mock output updates (simulate compressor and stepper)
        import random
        if random.random() < 0.1:  # 10% chance to toggle compressor
            self.service_tab.update_outputs(compressor_on=random.choice([True, False]))
        if random.random() < 0.05:  # 5% chance to move stepper
            new_pos = self.service_tab.stepper_position + random.randint(-10, 10)
            self.service_tab.update_outputs(stepper_pos=max(0, min(1000, new_pos)))
    
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
