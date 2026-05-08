"""Application entry point.

Wires together the sensor reader, CSV logger, state machine, drivers
(stepper, compressor, thermocouple) and the Qt UI.

The slow per-tick I/O (sensor reads, thermocouple I2C reads, compressor
UART exchange, CSV append) runs on a dedicated ``QThread`` worker so the
main GUI thread stays free to repaint and the stepper PWM thread is not
starved by GIL contention.
"""

import sys
import time
from pathlib import Path
from typing import Optional

import yaml
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # pragma: no cover - non-RPi environments
    GPIO = None  # type: ignore

from compressor_uart_driver import CompressorTelemetry, CompressorUartDriver
from csv_logger import CSVLogger
from ads1115_pressure_reader import ADS1115PressureReader
from enhanced_ui import MainScreen
from multi_sensor_reader import MultiSensorReader
from state_machine import State, StateMachine
from stepper_driver import STSPIN220Driver
from thermocouple_reader import ThermocoupleReader


class _BackgroundIOWorker(QObject):
    """Runs all per-tick blocking I/O off the GUI thread.

    Owns no UI; results are emitted via the ``tick_complete`` signal and
    consumed back on the main thread.
    """

    tick_complete = pyqtSignal(object, object, object, object, object, object)
    # payload: (sensor_states, temperatures, raw_temperatures, pressures, telemetry, error_message)

    def __init__(
        self,
        sensor_reader: MultiSensorReader,
        thermocouple_reader: Optional[ThermocoupleReader],
        pressure_reader: Optional[ADS1115PressureReader],
        compressor_driver: Optional[CompressorUartDriver],
        csv_logger: Optional[CSVLogger],
    ):
        super().__init__()
        self._sensor_reader = sensor_reader
        self._thermocouple_reader = thermocouple_reader
        self._pressure_reader = pressure_reader
        self._compressor_driver = compressor_driver
        self._csv_logger = csv_logger

    @pyqtSlot(bool, int, bool, int, float)
    def tick(
        self,
        compressor_on: bool,
        compressor_speed_rpm: int,
        stepper_motor_running: bool,
        peristaltic_pump_set_speed_rpm: int,
        set_temperature_c: float,
    ) -> None:
        sensor_states: dict = {}
        temperatures: dict = {}
        raw_temperatures: dict = {}
        pressures: dict = {}
        telemetry: Optional[CompressorTelemetry] = None
        error_message: Optional[str] = None
        try:
            if self._sensor_reader is not None:
                sensor_states = self._sensor_reader.read_all()
            if self._thermocouple_reader is not None:
                temperatures = self._thermocouple_reader.read_temperatures()
                raw_temperatures = self._thermocouple_reader.get_last_raw_temperatures()
            if self._pressure_reader is not None:
                pressures = self._pressure_reader.read_pressures()
            if self._compressor_driver is not None:
                telemetry = self._compressor_driver.exchange(
                    on=bool(compressor_on),
                    set_speed_rpm=int(compressor_speed_rpm),
                )
            if self._csv_logger is not None:
                logged_stepper_speed_rpm = (
                    int(peristaltic_pump_set_speed_rpm) if bool(stepper_motor_running) else 0
                )
                self._csv_logger.log(
                    sensor_states,
                    temperatures,
                    peristaltic_pump_set_speed_rpm=logged_stepper_speed_rpm,
                    set_temperature_c=float(set_temperature_c),
                )
        except Exception as exc:
            error_message = f"Error during update: {exc}"
        self.tick_complete.emit(
            sensor_states,
            temperatures,
            raw_temperatures,
            pressures,
            telemetry,
            error_message,
        )


class SensorMonitorApp(QObject):
    """Top-level application coordinator (lives on the GUI thread)."""

    UPDATE_INTERVAL_MS = 1000

    # Emitted on every UI tick to ask the IO worker thread to do its work.
    # Payload: (compressor_on, compressor_speed_rpm, stepper_motor_running,
    #           peristaltic_pump_set_speed_rpm, set_temperature_c).
    request_io_tick = pyqtSignal(bool, int, bool, int, float)

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__()
        self.config_path = Path(config_path)
        self.config = self._load_config(config_path)
        self.temperature_sensor_names = self._temperature_sensor_names_from_config(self.config)
        self.primary_temperature_label = (
            self.temperature_sensor_names[1]
            if len(self.temperature_sensor_names) > 1
            else (self.temperature_sensor_names[0] if self.temperature_sensor_names else None)
        )

        self.sensor_reader: Optional[MultiSensorReader] = None
        self.csv_logger: Optional[CSVLogger] = None
        self.ui: Optional[MainScreen] = None
        self.state_machine: Optional[StateMachine] = None
        self.stepper_driver: Optional[STSPIN220Driver] = None
        self.thermocouple_reader: Optional[ThermocoupleReader] = None
        self.pressure_reader: Optional[ADS1115PressureReader] = None
        self.compressor_driver: Optional[CompressorUartDriver] = None
        self.last_compressor_telemetry: Optional[CompressorTelemetry] = None

        stepper_cfg = self.config.get('stepper_motor', {})
        compressor_cfg = self.config.get('compressor', {})
        self.stepper_speed_rpm: int = int(stepper_cfg.get('default_speed_rpm', 30))
        self.pumping_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_speed_rpm', 60))
        self.pumping_slow_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_slow_speed_rpm', 20))
        self.compressor_speed_rpm: int = int(compressor_cfg.get('default_speed_rpm', 3000))
        self.compressor_command_on: bool = bool(compressor_cfg.get('start_on', False))
        self.compressor_manual_output_pin: int = 6
        self.compressor_manual_on: bool = False
        self.compressor_manual_relay_on: bool = False
        self.compressor_manual_on_time_s: int = 20
        self.compressor_manual_off_time_s: int = 40
        self._compressor_manual_phase_started_at: Optional[float] = None
        self.stepper_continuous_forward: bool = False
        self.stepper_motor_running: bool = False
        _cont_dir = int(stepper_cfg.get("continuous_direction", 1))
        self.stepper_continuous_direction: int = 1 if _cont_dir >= 0 else -1

        self.is_running = False

        self._io_thread: Optional[QThread] = None
        self._io_worker: Optional[_BackgroundIOWorker] = None
        # Skip a tick if the worker hasn't finished the previous one yet.
        self._tick_in_progress: bool = False

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
            self.pressure_reader = ADS1115PressureReader(self.config)
            self._log_optional_status("ADS1115 pressure reader", self.pressure_reader)

            self.compressor_driver = CompressorUartDriver(self.config)
            self._log_optional_status("Compressor UART driver", self.compressor_driver)
            self._initialize_compressor_manual_output()

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

    def _initialize_compressor_manual_output(self) -> None:
        """Configure IO6 as compressor manual relay output (temporary UART workaround)."""
        if GPIO is None:
            print("Compressor manual relay unavailable: RPi.GPIO not installed")
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.compressor_manual_output_pin, GPIO.OUT, initial=GPIO.LOW)
            self.compressor_manual_on = False
            print(f"Compressor manual relay initialized on IO{self.compressor_manual_output_pin}")
        except Exception as exc:
            print(f"Failed to initialize compressor manual relay IO{self.compressor_manual_output_pin}: {exc}")

    def _set_compressor_manual_output(self, enabled: bool) -> None:
        """Drive IO6 high/low for manual compressor relay control."""
        self.compressor_manual_relay_on = bool(enabled)
        if GPIO is None:
            return
        try:
            GPIO.output(
                self.compressor_manual_output_pin,
                GPIO.HIGH if self.compressor_manual_relay_on else GPIO.LOW,
            )
        except Exception as exc:
            print(f"Failed to set compressor manual relay IO{self.compressor_manual_output_pin}: {exc}")

    def _update_compressor_manual_cycle(self) -> None:
        """When manual mode is enabled, alternate IO6 ON/OFF by configured seconds."""
        if not self.compressor_manual_on:
            return
        now = time.monotonic()
        if self._compressor_manual_phase_started_at is None:
            self._compressor_manual_phase_started_at = now
            self._set_compressor_manual_output(True)
            return
        elapsed = now - self._compressor_manual_phase_started_at
        if self.compressor_manual_relay_on:
            if elapsed >= float(self.compressor_manual_on_time_s):
                self._set_compressor_manual_output(False)
                self._compressor_manual_phase_started_at = now
        else:
            if elapsed >= float(self.compressor_manual_off_time_s):
                self._set_compressor_manual_output(True)
                self._compressor_manual_phase_started_at = now

    def cleanup(self):
        """Release every resource owned by the application."""
        print("Cleaning up...")

        self._stop_io_worker()

        if self.is_running and self.csv_logger:
            self.csv_logger.stop_logging()
            print("CSV logging stopped")

        if self.thermocouple_reader is not None:
            try:
                self.thermocouple_reader.cleanup()
            except Exception:
                pass
        if self.pressure_reader is not None:
            try:
                self.pressure_reader.cleanup()
            except Exception:
                pass

        if self.sensor_reader:
            self.sensor_reader.cleanup()

        self.on_stepper_jog_stop()
        if self.stepper_driver:
            self.stepper_driver.stop_continuous()
            self.stepper_driver.cleanup()
        if self.compressor_driver:
            self.compressor_driver.cleanup()
            self.compressor_driver = None
        self._set_compressor_manual_output(False)
        self.compressor_manual_on = False
        self._compressor_manual_phase_started_at = None
        self.thermocouple_reader = None
        self.pressure_reader = None

        print("Cleanup complete")

    # ------------------------------------------------------------------
    # Background IO worker plumbing
    # ------------------------------------------------------------------
    def _start_io_worker(self) -> None:
        """Spin up the background QThread that runs the per-tick IO."""
        if self._io_thread is not None:
            return
        worker = _BackgroundIOWorker(
            self.sensor_reader,
            self.thermocouple_reader,
            self.pressure_reader,
            self.compressor_driver,
            self.csv_logger,
        )
        thread = QThread()
        thread.setObjectName("io_worker")
        worker.moveToThread(thread)

        # Cross-thread connections: GUI->worker is queued (worker has no
        # event loop assumptions), worker->GUI is auto/queued because the
        # receiver lives on a different thread.
        self.request_io_tick.connect(worker.tick, Qt.ConnectionType.QueuedConnection)
        worker.tick_complete.connect(
            self._on_io_tick_complete, Qt.ConnectionType.QueuedConnection
        )

        thread.start()
        self._io_thread = thread
        self._io_worker = worker

    def _stop_io_worker(self) -> None:
        """Tear down the background IO thread cleanly."""
        if self._io_thread is None:
            return
        try:
            self.request_io_tick.disconnect()
        except (TypeError, RuntimeError):
            pass
        if self._io_worker is not None:
            try:
                self._io_worker.tick_complete.disconnect()
            except (TypeError, RuntimeError):
                pass
        self._io_thread.quit()
        if not self._io_thread.wait(1500):
            print("IO worker thread did not stop in time; terminating.")
            self._io_thread.terminate()
            self._io_thread.wait(500)
        self._io_thread = None
        self._io_worker = None

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
    # Periodic update tick (now non-blocking on the GUI thread)
    # ------------------------------------------------------------------
    def update_display(self):
        """Request a sensor/IO tick on the worker thread.

        Returns immediately. Results land in ``_on_io_tick_complete``.
        """
        if self._tick_in_progress:
            # Worker is still busy with the previous tick; skip this one
            # rather than queueing up and falling behind.
            return
        if self._io_worker is None:
            # Worker not started yet (e.g. UI flushing during startup).
            return
        self._update_compressor_manual_cycle()
        set_temperature_c = (
            float(self.ui.main_graph_widget.set_temperature)
            if self.ui else float("nan")
        )
        self._tick_in_progress = True
        self.request_io_tick.emit(
            bool(self.compressor_command_on),
            int(self.compressor_speed_rpm),
            bool(self.stepper_motor_running),
            int(self.stepper_speed_rpm),
            set_temperature_c,
        )

    @pyqtSlot(object, object, object, object, object, object)
    def _on_io_tick_complete(
        self,
        sensor_states,
        temperatures,
        raw_temperatures,
        pressures,
        telemetry,
        error_message,
    ):
        """Apply the worker's results back on the GUI thread."""
        try:
            if error_message:
                print(error_message)
                if self.state_machine:
                    self.state_machine.handle_sensor_error(error_message)
                if self.ui:
                    self.ui.set_status_message(error_message, is_error=True)
                return

            sensor_states = sensor_states or {}
            temperatures = temperatures or {}
            raw_temperatures = raw_temperatures or {}
            pressures = pressures or {}

            if telemetry is not None:
                self.last_compressor_telemetry = telemetry
            if self.compressor_driver and self.compressor_driver.last_error:
                print(self.compressor_driver.last_error)

            body_temp = (
                temperatures.get(self.primary_temperature_label)
                if self.primary_temperature_label
                else None
            )
            set_temp = self.ui.main_graph_widget.set_temperature if self.ui else None

            if self.state_machine:
                self.state_machine.update(
                    sensor_states, body_temp=body_temp, set_temp=set_temp
                )

            if self.ui:
                self.ui.update_sensor_display(
                    sensor_states,
                    temperatures,
                    raw_temperatures,
                    pressures,
                    telemetry=(telemetry if telemetry is not None else self.last_compressor_telemetry),
                    compressor_command_on=self.compressor_command_on,
                    compressor_set_speed_rpm=self.compressor_speed_rpm,
                    compressor_last_error=(
                        self.compressor_driver.last_error if self.compressor_driver else None
                    ),
                    compressor_initialized=(
                        self.compressor_driver.is_initialized if self.compressor_driver else False
                    ),
                )
                if self.stepper_driver:
                    self._update_stepper_ui_status()
        finally:
            self._tick_in_progress = False

    def _update_stepper_ui_status(self):
        """Push latest compressor + stepper values into the service tab."""
        if not self.ui or not self.stepper_driver:
            return
        compressor_on_from_uart = bool(
            self.last_compressor_telemetry and self.last_compressor_telemetry.actual_rpm > 0
        )
        # Manual relay output is active-low: IO6 LOW means compressor ON.
        compressor_on_from_manual_io6 = not self.compressor_manual_relay_on
        self.ui.service_tab.update_outputs(
            compressor_on=(compressor_on_from_uart or compressor_on_from_manual_io6),
            compressor_speed_rpm=self.compressor_speed_rpm,
            compressor_command_on=self.compressor_command_on,
            compressor_manual_on=self.compressor_manual_on,
            compressor_manual_on_time_s=self.compressor_manual_on_time_s,
            compressor_manual_off_time_s=self.compressor_manual_off_time_s,
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

    def on_compressor_manual_toggle(self, enabled: bool):
        self.compressor_manual_on = bool(enabled)
        if self.compressor_manual_on:
            self._compressor_manual_phase_started_at = time.monotonic()
            self._set_compressor_manual_output(True)
        else:
            self._set_compressor_manual_output(False)
            self._compressor_manual_phase_started_at = None
        if self.ui:
            self._update_stepper_ui_status()

    def on_compressor_manual_timing_changed(self, on_time_s: int, off_time_s: int):
        self.compressor_manual_on_time_s = max(1, int(on_time_s))
        self.compressor_manual_off_time_s = max(1, int(off_time_s))
        # Restart phase timing so new values apply immediately and predictably.
        if self.compressor_manual_on:
            self._compressor_manual_phase_started_at = time.monotonic()
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
        self.stepper_motor_running = True
        self._update_stepper_ui_status()

    def on_stepper_jog_stop(self):
        """Stop jog movement."""
        self.stepper_continuous_forward = False
        if self.stepper_driver:
            self.stepper_driver.stop_continuous()
        self.stepper_motor_running = False
        self._update_stepper_ui_status()

    def on_stepper_continuous_toggle(self, enabled: bool):
        """Toggle continuous movement ON/OFF (direction: ``stepper_continuous_direction`` / config)."""
        self.stepper_continuous_forward = bool(enabled)
        if not self.stepper_driver:
            return
        if self.stepper_continuous_forward:
            if not self.stepper_driver.enabled:
                self.stepper_driver.enable()
            # Restart so the latest speed/direction takes effect.
            self.stepper_driver.stop_continuous()
            self.stepper_driver.start_continuous(
                direction=self.stepper_continuous_direction,
                speed_rpm=self.stepper_speed_rpm,
            )
        else:
            self.stepper_driver.stop_continuous()
        self.stepper_motor_running = self.stepper_continuous_forward
        self._update_stepper_ui_status()

    def on_temperature_calibration_requested(
        self, sensor_name: str, measured_at_0c: float, measured_at_100c: float
    ) -> tuple[bool, str]:
        """Apply and persist two-point calibration for a selected sensor label."""
        if not self.thermocouple_reader or not self.thermocouple_reader.is_initialized:
            return False, "Thermocouple reader not available"
        channel = self._channel_for_sensor_label(sensor_name)
        if channel is None:
            return False, f"Unknown sensor label: {sensor_name}"

        ok, message = self.thermocouple_reader.set_channel_two_point_calibration(
            channel,
            measured_at_0c,
            measured_at_100c,
        )
        if not ok:
            return False, message

        self._save_channel_calibration(channel, measured_at_0c, measured_at_100c)
        return True, f"{sensor_name}: calibration saved"

    def _channel_for_sensor_label(self, sensor_name: str) -> Optional[int]:
        """Resolve configured thermocouple channel number for a UI label."""
        tc_cfg = self.config.get("thermocouples", {})
        channels = tc_cfg.get("channels", [])
        raw_labels = tc_cfg.get("labels", {})
        labels: dict[int, str] = {}
        for key, value in raw_labels.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        for channel in channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            label = str(labels.get(ch, f"Temp {ch}"))
            if label == sensor_name:
                return ch
        return None

    def _save_channel_calibration(
        self, channel: int, measured_at_0c: float, measured_at_100c: float
    ) -> None:
        """Persist per-channel calibration points into config.yaml."""
        tc_cfg = self.config.setdefault("thermocouples", {})
        calibration_cfg = tc_cfg.setdefault("calibration", {})
        channels_cfg = calibration_cfg.setdefault("channels", {})
        channels_cfg[int(channel)] = {
            "measured_at_0c": float(measured_at_0c),
            "measured_at_100c": float(measured_at_100c),
        }
        self._save_config()

    def _save_config(self) -> None:
        with self.config_path.open("w", encoding="utf-8") as config_file:
            yaml.safe_dump(self.config, config_file, sort_keys=False)

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

            # Background IO must be started before the timer kicks off so
            # the very first tick can be dispatched right away.
            self._start_io_worker()

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
        ui.on_compressor_manual_toggle_callback = self.on_compressor_manual_toggle
        ui.on_compressor_manual_timing_change_callback = self.on_compressor_manual_timing_changed
        ui.on_compressor_speed_change_callback = self.on_compressor_speed_changed
        ui.on_temperature_calibration_callback = self.on_temperature_calibration_requested


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
