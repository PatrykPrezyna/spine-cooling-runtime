"""Application entry point.

Wires together the sensor reader, CSV logger, state machine, drivers
(stepper, compressor, thermocouple) and the Qt UI.
"""

import sys
from pathlib import Path
from typing import Optional

import yaml
from PyQt6.QtWidgets import QApplication

from compressor_uart_driver import CompressorTelemetry, CompressorUartDriver
from csv_logger import CSVLogger
from enhanced_ui import MainScreen
from multi_sensor_reader import MultiSensorReader
from state_machine import State, StateMachine
from stepper_driver import STSPIN220Driver
from thermocouple_reader import ThermocoupleReader


class SensorMonitorApp:
    """Top-level application coordinator."""

    UPDATE_INTERVAL_MS = 1000

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)

        self.sensor_reader: Optional[MultiSensorReader] = None
        self.csv_logger: Optional[CSVLogger] = None
        self.ui: Optional[MainScreen] = None
        self.state_machine: Optional[StateMachine] = None
        self.stepper_driver: Optional[STSPIN220Driver] = None
        self.thermocouple_reader: Optional[ThermocoupleReader] = None
        self.compressor_driver: Optional[CompressorUartDriver] = None
        self.last_compressor_telemetry: Optional[CompressorTelemetry] = None

        stepper_cfg = self.config.get('stepper_motor', {})
        compressor_cfg = self.config.get('compressor', {})
        self.stepper_speed_rpm: int = int(stepper_cfg.get('default_speed_rpm', 30))
        self.pumping_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_speed_rpm', 60))
        self.pumping_slow_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_slow_speed_rpm', 20))
        self.compressor_speed_rpm: int = int(compressor_cfg.get('default_speed_rpm', 3000))
        self.compressor_command_on: bool = bool(compressor_cfg.get('start_on', False))
        self.stepper_continuous_forward: bool = False

        self.is_running = False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @staticmethod
    def _load_config(config_path: str) -> dict:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        print(f"Configuration loaded from: {config_path}")
        return config

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> bool:
        """Initialize all components. Returns True on success."""
        try:
            print("Initializing components...")

            self.state_machine = StateMachine()
            self.state_machine.on_state_change = self._on_state_changed

            self.sensor_reader = MultiSensorReader(self.config)
            if not self.sensor_reader.is_initialized:
                error_msg = "Sensor reader initialization failed"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False

            self.csv_logger = CSVLogger(self.config)

            # Optional, non-fatal subsystems.
            self.thermocouple_reader = ThermocoupleReader(self.config)
            self._log_optional_status("Thermocouple reader", self.thermocouple_reader)

            self.compressor_driver = CompressorUartDriver(self.config)
            self._log_optional_status("Compressor UART driver", self.compressor_driver)

            self.stepper_driver = STSPIN220Driver(self.config)
            # Keep the driver energised while service jog controls are used.
            self.stepper_driver.disable_on_idle = False
            self.stepper_driver.enable()

            csv_dir = Path(self.config['logging']['csv_directory'])
            csv_dir.mkdir(parents=True, exist_ok=True)

            if not self.csv_logger.start_logging():
                error_msg = "Failed to start CSV logging"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False

            self.is_running = True
            print("All components initialized successfully")
            self.state_machine.handle_init_complete(True)
            return True

        except Exception as e:
            error_msg = f"Initialization error: {e}"
            print(error_msg)
            if self.state_machine:
                self.state_machine.handle_init_complete(False, error_msg)
            return False

    @staticmethod
    def _log_optional_status(label: str, component) -> None:
        if component.is_initialized:
            print(f"{label} initialized")
        elif getattr(component, "last_error", None):
            print(f"{label} inactive: {component.last_error}")

    def cleanup(self):
        """Release every resource owned by the application."""
        print("Cleaning up...")

        if self.is_running and self.csv_logger:
            self.csv_logger.stop_logging()
            print("CSV logging stopped")

        if self.sensor_reader:
            self.sensor_reader.cleanup()

        self.on_stepper_jog_stop()
        if self.stepper_driver:
            self.stepper_driver.stop_continuous()
            self.stepper_driver.cleanup()
        if self.compressor_driver:
            self.compressor_driver.cleanup()
            self.compressor_driver = None
        self.thermocouple_reader = None

        print("Cleanup complete")

    # ------------------------------------------------------------------
    # State machine bridge
    # ------------------------------------------------------------------
    def _on_state_changed(self, old_state: State, new_state: State):
        if self.ui:
            error_msg = self.state_machine.get_error_message() if new_state == State.ERROR else None
            self.ui.update_state_display(new_state.value, error_msg)
        self._apply_state_driven_stepper_control(new_state)

    def _apply_state_driven_stepper_control(self, state: State):
        """Drive the stepper from state machine transitions."""
        if state == State.PUMPING:
            self.stepper_speed_rpm = self.pumping_stepper_speed_rpm
            self.on_stepper_continuous_toggle(True)
        elif state == State.PUMPING_SLOWLY:
            self.stepper_speed_rpm = self.pumping_slow_stepper_speed_rpm
            self.on_stepper_continuous_toggle(True)
        elif self.stepper_continuous_forward:
            self.on_stepper_continuous_toggle(False)

    # ------------------------------------------------------------------
    # Periodic update tick
    # ------------------------------------------------------------------
    def update_display(self):
        """Update sensors, drivers and UI. Called once per second."""
        try:
            sensor_states = self.sensor_reader.read_all()
            temperatures = (
                self.thermocouple_reader.read_temperatures()
                if self.thermocouple_reader
                else {}
            )
            body_temp = temperatures.get("CSF Temp")
            set_temp = self.ui.main_graph_widget.set_temperature if self.ui else None

            if self.compressor_driver:
                self.last_compressor_telemetry = self.compressor_driver.exchange(
                    on=self.compressor_command_on,
                    set_speed_rpm=self.compressor_speed_rpm,
                )
                if self.compressor_driver.last_error:
                    print(self.compressor_driver.last_error)

            if self.state_machine:
                self.state_machine.update(
                    sensor_states, body_temp=body_temp, set_temp=set_temp
                )

            if self.ui:
                self.ui.update_sensor_display(sensor_states, temperatures)
                if self.stepper_driver:
                    self._update_stepper_ui_status()

            if self.csv_logger:
                self.csv_logger.log(sensor_states, temperatures)

        except Exception as e:
            error_msg = f"Error during update: {e}"
            print(error_msg)
            if self.state_machine:
                self.state_machine.handle_sensor_error(error_msg)
            if self.ui:
                self.ui.set_status_message(error_msg, is_error=True)

    def _update_stepper_ui_status(self):
        """Push latest compressor + stepper values into the service tab."""
        if not self.ui or not self.stepper_driver:
            return
        compressor_on = bool(
            self.last_compressor_telemetry and self.last_compressor_telemetry.actual_rpm > 0
        )
        self.ui.service_tab.update_outputs(
            compressor_on=compressor_on,
            compressor_speed_rpm=self.compressor_speed_rpm,
            compressor_command_on=self.compressor_command_on,
            stepper_speed_rpm=self.stepper_speed_rpm,
        )

    # ------------------------------------------------------------------
    # UI callbacks
    # ------------------------------------------------------------------
    def on_start_pumping(self):
        if self.state_machine:
            self.state_machine.start_pumping()

    def on_stop_pumping(self):
        if self.state_machine:
            self.state_machine.stop_pumping()

    def on_acknowledge_error(self):
        if self.state_machine:
            self.state_machine.acknowledge_error()

    def on_stepper_speed_changed(self, speed_rpm: int):
        requested_speed = int(speed_rpm)
        if self.stepper_driver:
            requested_speed = min(requested_speed, int(self.stepper_driver.max_speed_rpm))
        self.stepper_speed_rpm = max(1, requested_speed)
        if self.stepper_continuous_forward and self.stepper_driver:
            # Update target speed without restarting the continuous ramp from zero.
            self.stepper_driver.set_continuous_speed(self.stepper_speed_rpm)
        if self.ui:
            self._update_stepper_ui_status()

    def on_compressor_toggle(self, enabled: bool):
        self.compressor_command_on = bool(enabled)
        if self.ui:
            self._update_stepper_ui_status()

    def on_compressor_speed_changed(self, speed_rpm: int):
        max_speed = int(self.config.get('compressor', {}).get('max_speed_rpm', 6000))
        self.compressor_speed_rpm = max(0, min(int(speed_rpm), max_speed))
        if self.ui:
            self._update_stepper_ui_status()

    def on_stepper_jog_start(self, direction: int):
        """Start jog while a jog button is held."""
        self.stepper_continuous_forward = False
        if not self.stepper_driver:
            return
        if not self.stepper_driver.enabled:
            self.stepper_driver.enable()
        jog_direction = 1 if direction >= 0 else -1
        self.stepper_driver.start_continuous(
            direction=jog_direction, speed_rpm=self.stepper_speed_rpm
        )
        self._update_stepper_ui_status()

    def on_stepper_jog_stop(self):
        """Stop jog movement."""
        self.stepper_continuous_forward = False
        if self.stepper_driver:
            self.stepper_driver.stop_continuous()
        self._update_stepper_ui_status()

    def on_stepper_continuous_toggle(self, enabled: bool):
        """Toggle continuous forward movement ON/OFF."""
        self.stepper_continuous_forward = bool(enabled)
        if not self.stepper_driver:
            return
        if self.stepper_continuous_forward:
            if not self.stepper_driver.enabled:
                self.stepper_driver.enable()
            # Restart so the latest speed/direction takes effect.
            self.stepper_driver.stop_continuous()
            self.stepper_driver.start_continuous(direction=1, speed_rpm=self.stepper_speed_rpm)
        else:
            self.stepper_driver.stop_continuous()
        self._update_stepper_ui_status()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> int:
        try:
            if not self.initialize():
                print("Initialization failed. Exiting.")
                return 1

            app = QApplication(sys.argv)

            self.ui = MainScreen(self.config)
            self._wire_ui_callbacks()
            self.ui.set_update_callback(self.update_display)
            self.ui.update_timer.start(self.UPDATE_INTERVAL_MS)
            self.ui.show()

            if self.stepper_driver:
                self._update_stepper_ui_status()

            print("Application started. Close window to exit.")

            exit_code = app.exec()
            self.cleanup()
            return exit_code

        except Exception as e:
            print(f"Error running application: {e}")
            self.cleanup()
            return 1

    def _wire_ui_callbacks(self) -> None:
        """Connect every UI callback hook to its handler on this app."""
        ui = self.ui
        ui.on_start_pumping_callback = self.on_start_pumping
        ui.on_stop_pumping_callback = self.on_stop_pumping
        ui.on_acknowledge_callback = self.on_acknowledge_error
        ui.on_stepper_speed_change_callback = self.on_stepper_speed_changed
        ui.on_stepper_jog_start_callback = self.on_stepper_jog_start
        ui.on_stepper_jog_stop_callback = self.on_stepper_jog_stop
        ui.on_stepper_continuous_toggle_callback = self.on_stepper_continuous_toggle
        ui.on_compressor_toggle_callback = self.on_compressor_toggle
        ui.on_compressor_speed_change_callback = self.on_compressor_speed_changed


def main() -> int:
    print("=" * 50)
    print("Spine Cooling Runtime - Phase 1")
    print("Medical Device Prototype")
    print("=" * 50)
    print()

    app = SensorMonitorApp()
    exit_code = app.run()

    print()
    print("Application exited with code:", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
