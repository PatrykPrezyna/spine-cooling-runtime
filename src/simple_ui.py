"""
Simple UI Module
PyQt6-based user interface for sensor monitoring
"""

import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget
)
from PyQt6.QtGui import QFont


class SensorMonitorWindow(QMainWindow):
    """Main window for sensor monitoring"""
    
    def __init__(self, config: dict):
        """
        Initialize main window
        
        Args:
            config: Configuration dictionary
        """
        super().__init__()
        
        self.config = config
        self.is_monitoring = False
        
        # Callbacks (to be set by main application)
        self.on_start_callback: Optional[callable] = None
        self.on_stop_callback: Optional[callable] = None
        
        self._setup_window()
        self._create_widgets()
        self._setup_layout()
        self._setup_timer()
    
    def _setup_window(self):
        """Setup main window properties"""
        self.setWindowTitle("Level Sensor Monitor")
        
        width = self.config['ui']['window_width']
        height = self.config['ui']['window_height']
        self.setFixedSize(width, height)
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        self.move(x, y)
    
    def _create_widgets(self):
        """Create UI widgets"""
        # Title label
        self.title_label = QLabel("Level Sensor Monitor")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Sensor status label
        self.sensor_label = QLabel("Sensor Status: --")
        sensor_font = QFont()
        sensor_font.setPointSize(14)
        self.sensor_label.setFont(sensor_font)
        self.sensor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Last update label
        self.update_label = QLabel("Last Update: --")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Start button
        self.start_button = QPushButton("START")
        self.start_button.setMinimumHeight(50)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.start_button.clicked.connect(self._on_start_clicked)
        
        # Stop button
        self.stop_button = QPushButton("STOP")
        self.stop_button.setMinimumHeight(50)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
        
        # Status message label
        self.status_label = QLabel("Status: Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #6c757d; font-style: italic;")
    
    def _setup_layout(self):
        """Setup widget layout"""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main vertical layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Add title
        main_layout.addWidget(self.title_label)
        
        # Add spacing
        main_layout.addSpacing(10)
        
        # Add sensor status
        main_layout.addWidget(self.sensor_label)
        main_layout.addWidget(self.update_label)
        
        # Add stretch to push buttons to bottom
        main_layout.addStretch()
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)
        
        # Add status label
        main_layout.addWidget(self.status_label)
        
        central_widget.setLayout(main_layout)
    
    def _setup_timer(self):
        """Setup update timer"""
        self.update_timer = QTimer(self)
        # Don't connect here - will be connected by main app
        
    def set_update_callback(self, callback):
        """Set the callback function for timer updates"""
        # Disconnect any existing connection
        try:
            self.update_timer.timeout.disconnect()
        except:
            pass
        # Connect new callback
        self.update_timer.timeout.connect(callback)
    
    def _on_start_clicked(self):
        """Handle start button click"""
        if self.on_start_callback:
            success = self.on_start_callback()
            if success:
                self.is_monitoring = True
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.status_label.setText("Status: Logging active...")
                self.status_label.setStyleSheet("color: #28a745; font-style: italic;")
                
                # Timer is already running continuously, no need to start it here
    
    def _on_stop_clicked(self):
        """Handle stop button click"""
        if self.on_stop_callback:
            self.on_stop_callback()
        
        self.is_monitoring = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Status: Logging stopped (display continues)")
        self.status_label.setStyleSheet("color: #dc3545; font-style: italic;")
        
        # Don't stop the timer - keep reading and displaying sensor
    
    def _on_timer_update(self):
        """Handle timer update (placeholder for main app to override)"""
        pass
    
    def update_sensor_display(self, sensor_state: bool):
        """
        Update sensor status display
        
        Args:
            sensor_state: Current sensor state
        """
        state_text = "HIGH" if sensor_state else "LOW"
        self.sensor_label.setText(f"Sensor Status: {state_text}")
        
        # Color code the status
        if sensor_state:
            self.sensor_label.setStyleSheet("color: #28a745; font-size: 14pt;")
        else:
            self.sensor_label.setStyleSheet("color: #dc3545; font-size: 14pt;")
        
        # Update timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_label.setText(f"Last Update: {timestamp}")
    
    def set_status_message(self, message: str, is_error: bool = False):
        """
        Set status message
        
        Args:
            message: Status message to display
            is_error: True if this is an error message
        """
        self.status_label.setText(f"Status: {message}")
        if is_error:
            self.status_label.setStyleSheet("color: #dc3545; font-style: italic;")
        else:
            self.status_label.setStyleSheet("color: #6c757d; font-style: italic;")
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop monitoring if active
        if self.is_monitoring:
            self._on_stop_clicked()
        
        # Stop the update timer
        self.update_timer.stop()
        
        event.accept()


if __name__ == "__main__":
    # Test the UI
    import yaml
    
    print("Testing SensorMonitorWindow...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create application
    app = QApplication(sys.argv)
    
    # Create window
    window = SensorMonitorWindow(config)
    
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
        if window.is_monitoring:
            state = random.choice([True, False])
            window.update_sensor_display(state)
    
    # Timer for simulation
    sim_timer = QTimer()
    sim_timer.timeout.connect(simulate_update)
    sim_timer.start(1000)
    
    # Run application
    sys.exit(app.exec())

# Made with Bob
