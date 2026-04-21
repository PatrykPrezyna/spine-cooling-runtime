"""
Main Application Module
Integrates sensor reading, CSV logging, UI, and state machine
"""

import sys
import yaml
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication

from multi_sensor_reader import MultiSensorReader
from simulation_sensor_reader import SimulationSensorReader
from csv_logger import CSVLogger
from enhanced_ui import EnhancedSensorMonitorWindow
from state_machine import StateMachine, State


class SensorMonitorApp:
    """Main application class"""
    
    def __init__(self, config_path: str = "config.yaml", simulation_mode: bool = True):
        """
        Initialize application
        
        Args:
            config_path: Path to configuration file
            simulation_mode: If True, use simulation mode with manual sensor control (default: True)
        """
        # Load configuration
        self.config = self._load_config(config_path)
        self.simulation_mode = simulation_mode
        
        # Initialize components
        self.sensor_reader: Optional[MultiSensorReader | SimulationSensorReader] = None
        self.csv_logger: Optional[CSVLogger] = None
        self.ui: Optional[EnhancedSensorMonitorWindow] = None
        self.state_machine: Optional[StateMachine] = None
        
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
            
            # Initialize state machine
            self.state_machine = StateMachine()
            self.state_machine.on_state_change = self._on_state_changed
            
            # Initialize sensor reader (simulation or real)
            if self.simulation_mode:
                print("Using SIMULATION mode with manual sensor control")
                self.sensor_reader = SimulationSensorReader(self.config)
            else:
                print("Using REAL sensor mode")
                self.sensor_reader = MultiSensorReader(self.config)
            
            if not self.sensor_reader.is_initialized:
                error_msg = "Sensor reader initialization failed"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False
            
            # Initialize CSV logger
            self.csv_logger = CSVLogger(self.config)
            
            # Check CSV directory exists (database check)
            csv_dir = Path(self.config['logging']['csv_directory'])
            if not csv_dir.exists():
                csv_dir.mkdir(parents=True, exist_ok=True)
                print(f"Created CSV directory: {csv_dir}")
            
            # Start CSV logging automatically
            if not self.csv_logger.start_logging():
                error_msg = "Failed to start CSV logging"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False
            
            self.is_running = True
            print("CSV logging started automatically")
            
            print("All components initialized successfully")
            
            # Transition to READY state
            self.state_machine.handle_init_complete(True)
            
            return True
            
        except Exception as e:
            error_msg = f"Initialization error: {e}"
            print(error_msg)
            if self.state_machine:
                self.state_machine.handle_init_complete(False, error_msg)
            return False
    
    
    def _on_state_changed(self, old_state: State, new_state: State):
        """
        Handle state machine state changes
        
        Args:
            old_state: Previous state
            new_state: New state
        """
        if self.ui:
            error_msg = self.state_machine.get_error_message() if new_state == State.ERROR else None
            self.ui.update_state_display(new_state.value, error_msg)
    
    def update_display(self):
        """Update sensor display continuously (called every 1 second)"""
        try:
            # Read all sensors
            sensor_states = self.sensor_reader.read_all()
            
            # Update state machine with sensor states
            if self.state_machine:
                self.state_machine.update(sensor_states)
            
            # Update UI
            if self.ui:
                self.ui.update_sensor_display(sensor_states)
            
            # Log to CSV (always active)
            if self.csv_logger:
                self.csv_logger.log(sensor_states)
            
        except Exception as e:
            error_msg = f"Error during update: {e}"
            print(error_msg)
            if self.state_machine:
                self.state_machine.handle_sensor_error(error_msg)
            if self.ui:
                self.ui.set_status_message(error_msg, is_error=True)
    
    def on_start_pumping(self):
        """Handle start pumping button click"""
        if self.state_machine:
            self.state_machine.start_pumping()
    
    def on_stop_pumping(self):
        """Handle stop pumping button click"""
        if self.state_machine:
            self.state_machine.stop_pumping()
    
    def on_acknowledge_error(self):
        """Handle acknowledge error button click"""
        if self.state_machine:
            self.state_machine.acknowledge_error()
    
    def on_simulation_sensor_changed(self, sensor_name: str, state: bool):
        """Handle manual sensor change in simulation mode"""
        if self.simulation_mode and isinstance(self.sensor_reader, SimulationSensorReader):
            self.sensor_reader.set_sensor(sensor_name, state)
            # Immediately update display
            self.update_display()
    
    def on_mode_changed(self, simulation_mode: bool):
        """Handle mode change from UI"""
        print(f"Switching to {'SIMULATION' if simulation_mode else 'REAL SENSOR'} mode...")
        
        # Cleanup old sensor reader
        if self.sensor_reader:
            self.sensor_reader.cleanup()
        
        # Update mode
        self.simulation_mode = simulation_mode
        
        try:
            # Initialize new sensor reader
            if self.simulation_mode:
                self.sensor_reader = SimulationSensorReader(self.config)
                print("Simulation mode activated - use Simulation tab to control sensors")
            else:
                self.sensor_reader = MultiSensorReader(self.config, force_simulation=False)
                print("Real sensor mode activated - reading from GPIO")
            
            # Update UI to reflect actual mode
            if self.ui:
                self.ui.simulation_mode = self.simulation_mode
            
            # Update display immediately
            self.update_display()
            
        except RuntimeError as e:
            error_msg = str(e)
            print(f"Error switching to real sensor mode: {error_msg}")
            
            # Revert to simulation mode
            self.simulation_mode = True
            self.sensor_reader = SimulationSensorReader(self.config)
            
            # Update UI to show simulation mode
            if self.ui:
                self.ui.simulation_mode = True
                self.ui.simulation_tab.update_mode_display(True)
            
            # Show error message
            if self.ui:
                self.ui.set_status_message(f"Real sensors not available: {error_msg}", is_error=True)
            
            # Update display
            self.update_display()
    
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
            
            # Create main window (pass simulation mode flag)
            self.ui = EnhancedSensorMonitorWindow(self.config, simulation_mode=self.simulation_mode)
            
            # Connect callbacks
            self.ui.on_mode_change_callback = self.on_mode_changed
            
            # Connect simulation sensor change callback
            self.ui.on_sensor_change_callback = self.on_simulation_sensor_changed
            
            # Connect state machine callbacks
            self.ui.on_start_pumping_callback = self.on_start_pumping
            self.ui.on_stop_pumping_callback = self.on_stop_pumping
            self.ui.on_acknowledge_callback = self.on_acknowledge_error
            
            # Set the timer update callback
            self.ui.set_update_callback(self.update_display)
            
            # Start the display update timer immediately (runs continuously)
            self.ui.update_timer.start(1000)  # Update every 1 second
            
            # Show window
            self.ui.show()
            
            mode_text = "SIMULATION MODE" if self.simulation_mode else "REAL SENSOR MODE"
            print(f"Application started in {mode_text}. Close window to exit.")
            
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
        
        # Stop CSV logging if active
        if self.is_running and self.csv_logger:
            self.csv_logger.stop_logging()
            print("CSV logging stopped")
        
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
    
    # Start in simulation mode by default (can be changed at runtime)
    print("Starting in SIMULATION MODE (default)")
    print("Use the mode toggle button to switch between Simulation and Real Sensor modes")
    print()
    
    # Create and run application (starts in simulation mode)
    app = SensorMonitorApp(simulation_mode=True)
    exit_code = app.run()
    
    print()
    print("Application exited with code:", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

# Made with Bob
