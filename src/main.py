"""
Main Application Module
Integrates sensor reading, CSV logging, and UI
"""

import sys
import yaml
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication

from sensor_reader import SensorReader
from csv_logger import CSVLogger
from simple_ui import SensorMonitorWindow


class SensorMonitorApp:
    """Main application class"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize application
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Initialize components
        self.sensor_reader: Optional[SensorReader] = None
        self.csv_logger: Optional[CSVLogger] = None
        self.ui: Optional[SensorMonitorWindow] = None
        
        self.is_running = False
    
    def _load_config(self, config_path: str) -> dict:
        """
        Load configuration from YAML file
        
        Args:
            config_path: Path to config file
            
        Returns:
            dict: Configuration dictionary
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
            
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            print(f"Configuration loaded from: {config_path}")
            return config
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            raise
    
    def initialize(self) -> bool:
        """
        Initialize all components
        
        Returns:
            bool: True if initialization successful
        """
        try:
            print("Initializing components...")
            
            # Initialize sensor reader
            self.sensor_reader = SensorReader(self.config)
            if not self.sensor_reader.is_initialized:
                print("Error: Sensor reader initialization failed")
                return False
            
            # Initialize CSV logger
            self.csv_logger = CSVLogger(self.config)
            
            print("All components initialized successfully")
            return True
            
        except Exception as e:
            print(f"Error during initialization: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """
        Start sensor monitoring and logging
        
        Returns:
            bool: True if started successfully
        """
        if self.is_running:
            print("Warning: Monitoring already active")
            return False
        
        try:
            # Start CSV logging
            if not self.csv_logger.start_logging():
                print("Error: Failed to start logging")
                return False
            
            self.is_running = True
            print("Monitoring started")
            return True
            
        except Exception as e:
            print(f"Error starting monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop sensor monitoring and logging"""
        if not self.is_running:
            return
        
        try:
            # Stop CSV logging
            self.csv_logger.stop_logging()
            
            self.is_running = False
            print("Monitoring stopped")
            
        except Exception as e:
            print(f"Error stopping monitoring: {e}")
    
    def update_display(self):
        """Update sensor display continuously (called every 1 second)"""
        try:
            # Read sensor
            sensor_state = self.sensor_reader.read()
            
            # Update UI
            if self.ui:
                self.ui.update_sensor_display(sensor_state)
            
            # If monitoring is active, also log to CSV
            if self.is_running:
                self.csv_logger.log(sensor_state)
            
        except Exception as e:
            print(f"Error during update: {e}")
            if self.ui:
                self.ui.set_status_message(f"Error: {e}", is_error=True)
    
    def run(self) -> int:
        """
        Run the application
        
        Returns:
            int: Exit code
        """
        try:
            # Initialize components
            if not self.initialize():
                print("Initialization failed. Exiting.")
                return 1
            
            # Create Qt application
            app = QApplication(sys.argv)
            
            # Create main window
            self.ui = SensorMonitorWindow(self.config)
            
            # Connect callbacks
            self.ui.on_start_callback = self.start_monitoring
            self.ui.on_stop_callback = self.stop_monitoring
            
            # Set the timer update callback
            self.ui.set_update_callback(self.update_display)
            
            # Start the display update timer immediately (runs continuously)
            self.ui.update_timer.start(1000)  # Update every 1 second
            
            # Show window
            self.ui.show()
            
            print("Application started. Close window to exit.")
            
            # Run Qt event loop
            exit_code = app.exec()
            
            # Cleanup
            self.cleanup()
            
            return exit_code
            
        except Exception as e:
            print(f"Error running application: {e}")
            self.cleanup()
            return 1
    
    def cleanup(self):
        """Cleanup resources"""
        print("Cleaning up...")
        
        # Stop monitoring if active
        if self.is_running:
            self.stop_monitoring()
        
        # Cleanup sensor reader
        if self.sensor_reader:
            self.sensor_reader.cleanup()
        
        print("Cleanup complete")


def main():
    """Main entry point"""
    print("=" * 50)
    print("Level Sensor Monitor - Phase 1")
    print("Medical Device Prototype")
    print("=" * 50)
    print()
    
    # Create and run application
    app = SensorMonitorApp()
    exit_code = app.run()
    
    print()
    print("Application exited with code:", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

# Made with Bob
