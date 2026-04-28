"""
Main Application Module
Integrates sensor reading, CSV logging, UI, and state machine
"""

import sys
import yaml
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from multi_sensor_reader import MultiSensorReader
from simulation_sensor_reader import SimulationSensorReader
from csv_logger import CSVLogger
from enhanced_ui import EnhancedSensorMonitorWindow
from state_machine import StateMachine, State
from stepper_driver import STSPIN220Driver
from thermocouple_reader import ThermocoupleReader


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
        self.stepper_driver: Optional[STSPIN220Driver] = None
        self.thermocouple_reader: Optional[ThermocoupleReader] = None
        self.stepper_speed_rpm: int = int(self.config.get('stepper_motor', {}).get('default_speed_rpm', 30))
        self.jog_direction: int = 0
        self.jog_step_chunk: int = int(self.config.get('stepper_motor', {}).get('jog_step_chunk', 24))
        self.stepper_continuous_forward: bool = False
        self.jog_timer: Optional[QTimer] = None
        
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

            # Initialize thermocouple reader (optional, non-fatal).
            self.thermocouple_reader = ThermocoupleReader(
                self.config,
                simulation_mode=self.simulation_mode,
            )
            if self.thermocouple_reader.is_initialized:
                print("Thermocouple reader initialized")
            elif self.thermocouple_reader.last_error:
                print(f"Thermocouple reader inactive: {self.thermocouple_reader.last_error}")
            
            # Initialize stepper motor driver
            # In simulation mode we keep the same API but avoid real GPIO access.
            self.stepper_driver = STSPIN220Driver(self.config, force_simulation=self.simulation_mode)
            # Keep the driver energised while service jog controls are used.
            self.stepper_driver.disable_on_idle = False
            self.stepper_driver.enable()
            
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
    
    def _update_stepper_ui_status(self):
        """Push latest stepper speed into the service tab."""
        if not self.ui or not self.stepper_driver:
            return
        self.ui.service_tab.update_outputs(
            stepper_speed_rpm=self.stepper_speed_rpm,
        )
    
    def update_display(self):
        """Update sensor display continuously (called every 1 second)"""
        try:
            # Read all sensors
            sensor_states = self.sensor_reader.read_all()
            temperatures = {}
            if self.thermocouple_reader:
                temperatures = self.thermocouple_reader.read_temperatures()
            
            # Update state machine with sensor states
            if self.state_machine:
                self.state_machine.update(sensor_states)
            
            # Update UI
            if self.ui:
                self.ui.update_sensor_display(sensor_states, temperatures)
                if self.stepper_driver:
                    self._update_stepper_ui_status()
            
            # Log to CSV (always active)
            if self.csv_logger:
                self.csv_logger.log(sensor_states, temperatures)
            
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
    
    def on_stepper_speed_changed(self, speed_rpm: int):
        """Handle stepper speed RPM change from service tab."""
        requested_speed = int(speed_rpm)
        if self.stepper_driver:
            requested_speed = min(requested_speed, int(self.stepper_driver.max_speed_rpm))
        self.stepper_speed_rpm = max(1, requested_speed)
        self._update_jog_timer_interval()
        if self.ui:
            self._update_stepper_ui_status()
    
    def on_stepper_jog_start(self, direction: int):
        """Start jog movement while jog button is held."""
        self.stepper_continuous_forward = False
        if not self.stepper_driver:
            return
        if not self.stepper_driver.enabled:
            self.stepper_driver.enable()
        self.jog_direction = 1 if direction >= 0 else -1
        if self.jog_timer:
            self._update_jog_timer_interval()
            if not self.jog_timer.isActive():
                self.jog_timer.start()
        # Execute one chunk immediately so hold-to-jog feels responsive.
        self._on_jog_tick()
        self._update_stepper_ui_status()
    
    def on_stepper_jog_stop(self):
        """Stop jog movement."""
        self.stepper_continuous_forward = False
        self.jog_direction = 0
        if self.jog_timer and self.jog_timer.isActive():
            self.jog_timer.stop()
        self._update_stepper_ui_status()

    def on_stepper_continuous_toggle(self, enabled: bool):
        """Toggle continuous forward movement ON/OFF."""
        self.stepper_continuous_forward = bool(enabled)
        if self.stepper_continuous_forward:
            if not self.stepper_driver:
                return
            if not self.stepper_driver.enabled:
                self.stepper_driver.enable()
            self.jog_direction = 1
            if self.jog_timer:
                self._update_jog_timer_interval()
                if not self.jog_timer.isActive():
                    self.jog_timer.start()
            self._on_jog_tick()
            self._update_stepper_ui_status()
            return
        self.on_stepper_jog_stop()
    
    def _compute_jog_interval_ms(self) -> int:
        """
        Compute jog timer interval.

        Motor speed is already controlled inside the stepper driver via pulse
        timing (RPM + microstepping). Keep the UI jog timer fast so it does not
        add a second speed limit.
        """
        return 1
    
    def _update_jog_timer_interval(self):
        """Apply current jog interval to timer."""
        if not self.jog_timer:
            return
        self.jog_timer.setInterval(self._compute_jog_interval_ms())
    
    def _on_jog_tick(self):
        """Execute one jog movement chunk."""
        if not self.stepper_driver:
            return
        if self.jog_direction == 0 or not self.stepper_driver.enabled:
            return
        moved = self.stepper_driver.step(
            self.jog_direction * self.jog_step_chunk,
            speed_rpm=self.stepper_speed_rpm,
        )
        if moved == 0:
            self.on_stepper_jog_stop()
        if self.ui:
            self._update_stepper_ui_status()
    
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

            # Recreate thermocouple reader for the new mode
            self.thermocouple_reader = ThermocoupleReader(
                self.config,
                simulation_mode=self.simulation_mode,
            )
            
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
            
            self.jog_timer = QTimer()
            self.jog_timer.timeout.connect(self._on_jog_tick)
            self._update_jog_timer_interval()
            
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
            self.ui.on_stepper_speed_change_callback = self.on_stepper_speed_changed
            self.ui.on_stepper_jog_start_callback = self.on_stepper_jog_start
            self.ui.on_stepper_jog_stop_callback = self.on_stepper_jog_stop
            self.ui.on_stepper_continuous_toggle_callback = self.on_stepper_continuous_toggle
            
            # Set the timer update callback
            self.ui.set_update_callback(self.update_display)
            
            # Start the display update timer immediately (runs continuously)
            self.ui.update_timer.start(1000)  # Update every 1 second
            
            # Show window
            self.ui.show()
            
            # Sync initial stepper display values
            if self.stepper_driver:
                self._update_stepper_ui_status()
            
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
        
        # Cleanup stepper driver
        self.on_stepper_jog_stop()
        if self.jog_timer:
            self.jog_timer.stop()
            self.jog_timer = None
        if self.stepper_driver:
            self.stepper_driver.cleanup()
        self.thermocouple_reader = None
        
        print("Cleanup complete")


def main():
    """Main entry point"""
    print("=" * 50)
    print("Level Sensor Monitor - Phase 1")
    print("Medical Device Prototype")
    print("=" * 50)
    print()
    
    # Start in real sensor mode by default (can be changed at runtime)
    print("Starting in REAL SENSOR MODE (default)")
    print("Use the mode toggle button to switch between Real Sensor and Simulation modes")
    print()
    
    # Create and run application (starts in real sensor mode)
    app = SensorMonitorApp(simulation_mode=False)
    exit_code = app.run()
    
    print()
    print("Application exited with code:", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())


