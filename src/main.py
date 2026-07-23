"""Application entry point.

Wires together the sensor reader, CSV logger, state machine, drivers
(stepper, compressor, thermocouple) and the Qt UI.

- **GUI thread** — Qt UI and screen updates
- **IO worker thread** — sensor reads, thermocouple I2C, CSV logging
- **Stepper thread** — motor pulse timing

Slow I/O runs on the worker so the GUI stays responsive and the stepper
thread is not delayed by Python's  Global Interpreter Lock.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # pragma: no cover - non-RPi environments
    GPIO = None  # type: ignore

from cooling_tracker import CoolingEffectivenessTracker
from csv_logger import CSVLogger
from pressure_csv_logger import PressureCSVLogger, PressureCaptureLoop
from leak_debounce import LeakDebounceTracker
from fault_catalog import FaultCode, Severity, get_fault, stop_priority
from gui import MainScreen
from hardware_factory import build_hardware
from safety_rules import RuleContext, TelemetrySnapshot, evaluate, is_fault_still_active
from sensor_injection import SensorInjectionController, select_temperatures
from sensor_override_ui import SensorOverrideWindow
from state_machine import State, StateMachine


class _BackgroundIOWorker(QObject):
    """Runs all per-tick blocking I/O off the GUI thread.

    Owns no UI; results are emitted via the ``tick_complete`` signal and
    consumed back on the main thread.
    """

    tick_complete = pyqtSignal(object, object, object, object, object, object)
    # payload: (sensor_states, temperatures, raw_temperatures,
    #           thermocouple_temperatures, pressures, error_message)

    def __init__(
        self,
        sensor_reader: Any,
        thermocouple_reader: Any,
        thermistor_reader: Any,
        pressure_reader: Any,
        csv_logger: Optional[CSVLogger],
        config: Optional[dict] = None,
    ):
        super().__init__()
        self._sensor_reader = sensor_reader
        self._thermocouple_reader = thermocouple_reader
        self._thermistor_reader = thermistor_reader
        self._pressure_reader = pressure_reader
        self._csv_logger = csv_logger
        self._config = config or {}

    @pyqtSlot(bool, int, float, int)
    def tick(
        self,
        stepper_motor_running: bool,
        peristaltic_pump_set_speed_rpm: int,
        set_temperature_c: float,
        compressor_cooling: int,
    ) -> None:
        sensor_states: dict = {}
        thermocouple_temperatures: dict = {}
        temperatures: dict = {}
        raw_temperatures: dict = {}
        thermistor_temperatures: dict = {}
        pressures: dict = {}
        error_message: Optional[str] = None
        try:
            logged_stepper_speed_rpm = (
                int(peristaltic_pump_set_speed_rpm)
                if bool(stepper_motor_running)
                else 0
            )
            if self._sensor_reader is not None:
                sensor_states = self._sensor_reader.read_all()
            if self._thermocouple_reader is not None:
                notify_setpoint = getattr(self._thermocouple_reader, "notify_setpoint", None)
                if notify_setpoint is not None:
                    notify_setpoint(
                        set_temperature_c,
                        compressor_cooling,
                        stepper_motor_running,
                        logged_stepper_speed_rpm,
                    )
                thermocouple_temperatures = self._thermocouple_reader.read_temperatures()
                raw_getter = getattr(
                    self._thermocouple_reader, "get_last_raw_temperatures", None
                )
                raw_temperatures = raw_getter() if raw_getter is not None else {}
            if self._thermistor_reader is not None:
                thermistor_temperatures = self._thermistor_reader.read_temperatures()
            temperatures = select_temperatures(
                thermocouple_temperatures, thermistor_temperatures, self._config
            )
            if self._pressure_reader is not None:
                pressures = self._pressure_reader.read_pressures()
            if self._csv_logger is not None:
                self._csv_logger.log(
                    sensor_states,
                    temperatures,
                    peristaltic_pump_set_speed_rpm=logged_stepper_speed_rpm,
                    set_temperature_c=float(set_temperature_c),
                    compressor_cooling=int(compressor_cooling),
                    pressures=pressures,
                )
        except Exception as exc:
            error_message = f"Error during update: {exc}"
        self.tick_complete.emit(
            sensor_states,
            temperatures,
            raw_temperatures,
            thermocouple_temperatures,
            pressures,
            error_message,
        )


class SensorMonitorApp(QObject):
    """Top-level application coordinator (lives on the GUI thread)."""

    # Fallback when config has no ui.update_interval_ms (100 ms → 10 Hz).
    UPDATE_INTERVAL_MS = 100

    # Emitted on every UI tick to ask the IO worker thread to do its work.
    # Payload: (stepper_motor_running, peristaltic_pump_set_speed_rpm, set_temperature_c).
    request_io_tick = pyqtSignal(bool, int, float, int)

    def __init__(
        self,
        config_path: str = "config.yaml",
        *,
        simulation: bool = False,
        test_ui_enabled: bool = False,
    ):
        super().__init__()
        self.config_path = Path(config_path)
        self.simulation = bool(simulation)
        self.test_ui_enabled = bool(test_ui_enabled)
        self.config = self._load_config(config_path)
        ui_cfg = self.config.get("ui", {}) or {}
        self.update_interval_ms = int(
            ui_cfg.get("update_interval_ms", self.UPDATE_INTERVAL_MS)
        )
        self.temperature_sensor_names = self._temperature_sensor_names_from_config(self.config)
        self.primary_temperature_label = (
            self.temperature_sensor_names[1]
            if len(self.temperature_sensor_names) > 1
            else (self.temperature_sensor_names[0] if self.temperature_sensor_names else None)
        )
        self.control_temp_label = str(self.config.get("control_temp_label", "CSF 2"))

        self.sensor_reader: Any = None
        self.sensor_injection: Optional[SensorInjectionController] = None
        self.override_ui: Optional[SensorOverrideWindow] = None
        self.csv_logger: Optional[CSVLogger] = None
        self.pressure_csv_logger: Optional[PressureCSVLogger] = None
        self._pressure_capture_loop: Optional[PressureCaptureLoop] = None
        self.ui: Optional[MainScreen] = None
        self.state_machine: Optional[StateMachine] = None
        self.stepper_driver: Any = None
        self.thermocouple_reader: Any = None
        self.thermistor_reader: Any = None
        self.pressure_reader: Any = None
        stepper_cfg = self.config.get('stepper_motor', {})
        compressor_cfg = self.config.get('compressor', {})
        self.stepper_speed_rpm: int = int(stepper_cfg.get('default_speed_rpm', 30))
        self.pumping_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_speed_rpm', 60))
        self.pumping_slow_stepper_speed_rpm: int = int(stepper_cfg.get('pumping_slow_speed_rpm', 20))
        self.compressor_on: bool = False
        self.compressor_relay_pin: int = int(compressor_cfg.get('relay_pin', 6))
        self.compressor_relay_io6_high: bool = True
        self.compressor_control_enabled: bool = False
        self.compressor_latched_on: bool = False
        self.compressor_heat_ex_label: str = str(compressor_cfg.get('heat_ex_label', 'Heat Ex'))
        self.compressor_off_temp_c: float = float(compressor_cfg.get('off_below_temp_c', 5))
        self.compressor_on_temp_c: float = float(compressor_cfg.get('on_above_temp_c', 10))
        self._last_temperatures: dict = {}
        self._last_sensor_states: dict = {}
        self._last_pressures: dict = {}
        self.stepper_continuous_forward: bool = False
        self.stepper_motor_running: bool = False
        _cont_dir = int(stepper_cfg.get("continuous_direction", 1))
        self.stepper_continuous_direction: int = 1 if _cont_dir >= 0 else -1

        self.is_running = False

        self._io_thread: Optional[QThread] = None
        self._io_worker: Optional[_BackgroundIOWorker] = None
        # Skip a tick if the worker hasn't finished the previous one yet.
        self._tick_in_progress: bool = False
        self._cooling_tracker = CoolingEffectivenessTracker()
        leak_debounce_s = float(
            self.config.get("alarms", {}).get("leak_debounce_s", 0.5)
        )
        self._leak_tracker = LeakDebounceTracker(hold_s=leak_debounce_s)

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
        from sensor_injection import temperature_labels_from_config

        return temperature_labels_from_config(config)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> bool:
        """Initialize all components. Returns True on success."""
        try:
            print("Initializing components...")

            self.state_machine = StateMachine()
            self.state_machine.on_state_change = self._on_state_changed

            bundle = build_hardware(self.config, simulation=self.simulation)
            if self.test_ui_enabled:
                self.sensor_injection = SensorInjectionController(self.config)
                bundle = self.sensor_injection.wrap_bundle(bundle)
            self.sensor_reader = bundle.sensor_reader
            self.thermocouple_reader = bundle.thermocouple_reader
            self.thermistor_reader = bundle.thermistor_reader
            self.pressure_reader = bundle.pressure_reader
            self.stepper_driver = bundle.stepper_driver

            if not self.sensor_reader.is_initialized:
                error_msg = "Sensor reader initialization failed"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False

            self.csv_logger = CSVLogger(self.config)
            self.pressure_csv_logger = PressureCSVLogger(self.config)
            self._log_optional_status("Thermocouple reader", self.thermocouple_reader)
            self._log_optional_status("Thermistor reader", self.thermistor_reader)
            self._log_optional_status("ADS1115 pressure reader", self.pressure_reader)

            if not self.simulation:
                self._initialize_compressor_relay()

            # Keep the driver energised while service jog controls are used.
            self.stepper_driver.disable_on_idle = False
            self.stepper_driver.enable()

            csv_dir = Path(self.config['logging']['csv_directory'])
            csv_dir.mkdir(parents=True, exist_ok=True)
            pressure_csv_dir = Path(
                self.config.get('logging', {}).get(
                    'pressure_csv_directory',
                    self.config['logging']['csv_directory'],
                )
            )
            pressure_csv_dir.mkdir(parents=True, exist_ok=True)

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
            if not self.simulation:
                from stepper_driver import PigpioUnavailableError

                if isinstance(e, PigpioUnavailableError):
                    error_msg = str(e)
                    print(f"Error: {error_msg}")
                    if self.state_machine:
                        self.state_machine.handle_init_complete(False, error_msg)
                    return False
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

    def _initialize_compressor_relay(self) -> None:
        """Configure IO6 as compressor relay (active-low: LOW = on)."""
        if GPIO is None:
            print("Compressor relay unavailable: RPi.GPIO not installed")
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.compressor_relay_pin, GPIO.OUT, initial=GPIO.HIGH)
            self.compressor_relay_io6_high = True
            print(f"Compressor relay initialized on IO{self.compressor_relay_pin}")
        except Exception as exc:
            print(f"Failed to initialize compressor relay IO{self.compressor_relay_pin}: {exc}")

    def _set_compressor_relay_io6_high(self, io6_high: bool) -> None:
        """Set IO6 level. HIGH = compressor off, LOW = compressor on."""
        self.compressor_relay_io6_high = bool(io6_high)
        if GPIO is None:
            return
        try:
            GPIO.output(
                self.compressor_relay_pin,
                GPIO.HIGH if self.compressor_relay_io6_high else GPIO.LOW,
            )
        except Exception as exc:
            print(f"Failed to set compressor relay IO{self.compressor_relay_pin}: {exc}")

    def _set_compressor_running(self, on: bool) -> None:
        """Drive compressor relay (IO6 active-low)."""
        self.compressor_on = bool(on)
        self._set_compressor_relay_io6_high(not on)

    def _heat_ex_temperature_c(self, temperatures: dict) -> Optional[float]:
        value = temperatures.get(self.compressor_heat_ex_label)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _apply_compressor_heat_ex_control(self, temperatures: dict) -> None:
        """Heat Ex hysteresis: off below off_temp_c, on above on_temp_c."""
        if not self.compressor_control_enabled:
            self.compressor_latched_on = False
            self._set_compressor_running(False)
            return

        temp_c = self._heat_ex_temperature_c(temperatures)
        if temp_c is None:
            self._set_compressor_running(False)
            return

        if self.compressor_latched_on:
            if temp_c < self.compressor_off_temp_c:
                self.compressor_latched_on = False
        elif temp_c > self.compressor_on_temp_c:
            self.compressor_latched_on = True

        self._set_compressor_running(self.compressor_latched_on)

    def cleanup(self):
        """Release every resource owned by the application."""
        print("Cleaning up...")

        self._stop_io_worker()

        if self.is_running and self.csv_logger:
            self.csv_logger.stop_logging()
            print("CSV logging stopped")
        self._stop_pressure_capture()
        if self.pressure_csv_logger is not None:
            self.pressure_csv_logger.stop_logging()

        if self.thermocouple_reader is not None:
            try:
                self.thermocouple_reader.cleanup()
            except Exception:
                pass
        if self.thermistor_reader is not None:
            try:
                self.thermistor_reader.cleanup()
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
        self._set_compressor_running(False)
        self.compressor_control_enabled = False
        self.compressor_latched_on = False
        self.thermocouple_reader = None
        self.thermistor_reader = None
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
            self.thermistor_reader,
            self.pressure_reader,
            self.csv_logger,
            self.config,
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

    def _build_rule_context(
        self,
        sensor_states: dict,
        temperatures: dict,
        pressures: dict,
    ) -> RuleContext:
        alarms = self.config.get("alarms", {})
        csf_label = str(alarms.get("csf_label", "CSF"))
        csf_temp = temperatures.get(csf_label)
        now = time.monotonic()
        self._cooling_tracker.tick(
            pump=self.stepper_motor_running,
            compressor=self.compressor_on,
            csf_temp=float(csf_temp) if csf_temp is not None else None,
            now=now,
        )
        return RuleContext(
            current_state=self.state_machine.get_current_state(),
            seconds_in_state=self.state_machine.get_time_in_state(),
            sensor_states=sensor_states,
            temperatures=temperatures,
            pressures=pressures,
            pump_running=self.stepper_motor_running,
            compressor_on=self.compressor_on,
            telemetry=TelemetrySnapshot(),
            config=self.config,
            cooling_tracker=self._cooling_tracker,
            leak_tracker=self._leak_tracker,
            now=now,
        )

    def _evaluate_and_dispatch_safety(
        self,
        sensor_states: dict,
        temperatures: dict,
        pressures: dict,
    ) -> bool:
        """Evaluate safety rules. Returns True if workflow update should run."""
        ctx = self._build_rule_context(sensor_states, temperatures, pressures)
        active = evaluate(ctx)

        stop_codes = [c for c in active if get_fault(c).severity == Severity.STOP]
        if stop_codes:
            primary = min(stop_codes, key=stop_priority)
            self.state_machine.apply_fault(primary)
            if self.ui:
                self.ui.update_warnings([])
            return False

        if self.ui:
            message_codes = [c for c in active if get_fault(c).severity == Severity.MESSAGE]
            self.ui.update_warnings([get_fault(c).message for c in message_codes])

        return True

    def _can_acknowledge_error(
        self,
        sensor_states: dict,
        temperatures: dict,
        pressures: dict,
    ) -> bool:
        latched = self.state_machine.get_latched_fault_code()
        if latched is None:
            return True
        if latched == FaultCode.IO_READ_FAILURE:
            return True
        ctx = self._build_rule_context(sensor_states, temperatures, pressures)
        fault_state = self.state_machine.get_fault_context_state()
        if fault_state is not None:
            ctx.current_state = fault_state
        return not is_fault_still_active(latched, ctx)

    def _refresh_acknowledge_button(
        self,
        sensor_states: dict,
        temperatures: dict,
        pressures: dict,
    ) -> None:
        if not self.ui or not self.state_machine:
            return
        if self.state_machine.get_current_state() != State.ERROR:
            return
        self.ui.set_acknowledge_enabled(
            self._can_acknowledge_error(sensor_states, temperatures, pressures)
        )

    # ------------------------------------------------------------------
    # State machine bridge
    # ------------------------------------------------------------------
    def _refresh_ui_state_display(self) -> None:
        """Sync the top bar with the current state machine state."""
        if not self.ui or not self.state_machine:
            return
        state = self.state_machine.get_current_state()
        error_msg = None
        workflow_state_name = None
        if state == State.ERROR:
            error_msg = self.state_machine.get_error_message()
            fault_context = self.state_machine.get_fault_context_state()
            if fault_context is not None:
                workflow_state_name = fault_context.value
        self.ui.update_state_display(
            state.value,
            error_msg,
            workflow_state_name=workflow_state_name,
        )
        if state == State.ERROR:
            self.ui.set_acknowledge_enabled(False)

    def _on_state_changed(self, old_state: State, new_state: State):
        self._refresh_ui_state_display()
        self._apply_state_driven_stepper_control(new_state)
        self._apply_state_driven_compressor_control(new_state)
        if self.ui:
            self._update_stepper_ui_status()

    def _apply_state_driven_compressor_control(self, state: State) -> None:
        """Turn compressor on when precooling starts; off when session ends."""
        active_states = (State.COOLING, State.PUMPING, State.PUMPING_SLOWLY)
        if state == State.COOLING:
            self.compressor_control_enabled = True
            self.compressor_latched_on = True
            self._set_compressor_running(True)
        elif state not in active_states:
            self.compressor_control_enabled = False
            self.compressor_latched_on = False
            self._set_compressor_running(False)

    def _clamp_pump_speed_rpm(self, speed_rpm: int, *, enforce_min: bool = True) -> int:
        """Clamp requested pump speed to driver limits and optional minimum."""
        requested = max(1, int(speed_rpm))
        if self.stepper_driver:
            requested = min(requested, int(self.stepper_driver.max_speed_rpm))
        if enforce_min:
            min_rpm = int(self.config.get("stepper_motor", {}).get("min_pump_speed_rpm", 0) or 0)
            if min_rpm > 0:
                requested = max(min_rpm, requested)
        return requested

    def _apply_state_driven_stepper_control(self, state: State):
        """Drive the stepper from state machine transitions."""
        if state == State.PUMPING:
            self.stepper_speed_rpm = self._clamp_pump_speed_rpm(self.pumping_stepper_speed_rpm)
            self.on_stepper_continuous_toggle(True)
        elif state == State.PUMPING_SLOWLY:
            self.stepper_speed_rpm = self._clamp_pump_speed_rpm(
                self.pumping_slow_stepper_speed_rpm,
                enforce_min=False,
            )
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
        set_temperature_c = (
            float(self.ui.main_graph_widget.set_temperature)
            if self.ui else float("nan")
        )
        self._tick_in_progress = True
        self.request_io_tick.emit(
            bool(self.stepper_motor_running),
            int(self.stepper_speed_rpm),
            set_temperature_c,
            1 if self.compressor_on else 0,
        )

    @pyqtSlot(object, object, object, object, object, object)
    def _on_io_tick_complete(
        self,
        sensor_states,
        temperatures,
        raw_temperatures,
        thermocouple_temperatures,
        pressures,
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
            thermocouple_temperatures = thermocouple_temperatures or {}
            pressures = pressures or {}
            self._last_temperatures = temperatures
            self._last_sensor_states = sensor_states
            self._last_pressures = pressures
            self._apply_compressor_heat_ex_control(temperatures)

            body_temp = temperatures.get(self.control_temp_label)
            set_temp = self.ui.main_graph_widget.set_temperature if self.ui else None

            if self.state_machine:
                run_workflow = self._evaluate_and_dispatch_safety(
                    sensor_states, temperatures, pressures
                )
                if run_workflow:
                    self.state_machine.update(
                        sensor_states, body_temp=body_temp, set_temp=set_temp
                    )

            if self.ui:
                self.ui.update_sensor_display(
                    sensor_states,
                    temperatures,
                    raw_temperatures,
                    pressures,
                    calibration_temperatures=thermocouple_temperatures,
                )
                self._refresh_acknowledge_button(sensor_states, temperatures, pressures)
                if self.stepper_driver:
                    self._update_stepper_ui_status()
        finally:
            self._tick_in_progress = False

    def _update_stepper_ui_status(self):
        """Push latest compressor + stepper values into the service tabs."""
        if not self.ui or not self.stepper_driver:
            return
        heat_ex_c = self._heat_ex_temperature_c(self._last_temperatures)
        actual_pump_speed_rpm = (
            int(self.stepper_speed_rpm) if self.stepper_motor_running else 0
        )
        self.ui.service_tab.update_outputs(
            compressor_on=self.compressor_on,
            compressor_control_enabled=self.compressor_control_enabled,
            compressor_off_temp_c=float(self.compressor_off_temp_c),
            compressor_on_temp_c=float(self.compressor_on_temp_c),
            heat_ex_temp_c=heat_ex_c,
            refresh_heat_ex=True,
            stepper_speed_rpm=self.stepper_speed_rpm,
        )
        self.ui.service2_tab.update_actuators(
            pump_speed_rpm=actual_pump_speed_rpm,
            compressor_on=self.compressor_on,
        )
        self.ui.pressure_service_tab.update_pump_speed(
            pump_speed_rpm=actual_pump_speed_rpm,
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
        if not self.state_machine:
            return
        if self.state_machine.get_current_state() != State.ERROR:
            return
        if not self._can_acknowledge_error(
            self._last_sensor_states,
            self._last_temperatures,
            self._last_pressures,
        ):
            return
        self.state_machine.acknowledge_error()

    def on_stepper_speed_changed(self, speed_rpm: int):
        enforce_min = (
            self.state_machine is not None
            and self.state_machine.get_current_state() == State.PUMPING
        )
        self.stepper_speed_rpm = self._clamp_pump_speed_rpm(
            speed_rpm,
            enforce_min=enforce_min,
        )
        if self.stepper_continuous_forward and self.stepper_driver:
            self.stepper_driver.set_continuous_speed(self.stepper_speed_rpm)
        if self.ui:
            self._update_stepper_ui_status()

    def on_compressor_control_toggle(self, enabled: bool) -> None:
        """Enable/disable Heat Ex temperature control from the service page."""
        self.compressor_control_enabled = bool(enabled)
        if self.compressor_control_enabled:
            temp_c = self._heat_ex_temperature_c(self._last_temperatures)
            self.compressor_latched_on = (
                temp_c is not None and temp_c > self.compressor_off_temp_c
            )
        else:
            self.compressor_latched_on = False
        self._apply_compressor_heat_ex_control(self._last_temperatures)
        if self.ui:
            self._update_stepper_ui_status()

    def _stop_pressure_capture(self) -> None:
        """Stop the high-rate pressure capture thread if it is running."""
        if self._pressure_capture_loop is not None:
            self._pressure_capture_loop.stop()
            self._pressure_capture_loop = None

    def on_pressure_csv_logging_toggle(self, enabled: bool) -> None:
        """Start/stop dedicated high-rate pressure CSV capture from the Pressure tab.

        Each ON opens a new timestamped file under
        ``logging.pressure_csv_directory`` and starts a capture thread at
        ``pressure_sensors.capture_rate_hz``. OFF stops the thread and closes
        the file.
        """
        if self.pressure_csv_logger is None:
            return
        if enabled:
            self._stop_pressure_capture()
            started = self.pressure_csv_logger.start_logging()
            if not started:
                if self.ui is not None:
                    tab = getattr(self.ui, "pressure_service_tab", None)
                    if tab is not None:
                        tab.set_pressure_csv_logging(False)
                return
            self._pressure_capture_loop = PressureCaptureLoop(
                self.pressure_reader,
                self.pressure_csv_logger,
            )
            self._pressure_capture_loop.start()
        else:
            self._stop_pressure_capture()
            self.pressure_csv_logger.stop_logging()

    def on_compressor_thresholds_changed(self, off_temp_c: float, on_temp_c: float) -> None:
        off_c = round(float(off_temp_c), 1)
        on_c = round(float(on_temp_c), 1)
        if on_c <= off_c:
            on_c = round(off_c + 0.1, 1)
        self.compressor_off_temp_c = off_c
        self.compressor_on_temp_c = on_c
        compressor_cfg = self.config.setdefault('compressor', {})
        compressor_cfg['off_below_temp_c'] = off_c
        compressor_cfg['on_above_temp_c'] = on_c
        self._save_config()
        if self.compressor_control_enabled:
            self._apply_compressor_heat_ex_control(self._last_temperatures)
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
            self._refresh_ui_state_display()
            self.ui.set_update_callback(self.update_display)

            # Background IO must be started before the timer kicks off so
            # the very first tick can be dispatched right away.
            self._start_io_worker()

            self.ui.update_timer.start(self.update_interval_ms)
            self.ui.show()

            if self.test_ui_enabled and self.sensor_injection is not None:
                self.override_ui = SensorOverrideWindow(self.config, self.sensor_injection)
                self.override_ui.show()

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
        ui.on_compressor_control_toggle_callback = self.on_compressor_control_toggle
        ui.on_compressor_thresholds_change_callback = self.on_compressor_thresholds_changed
        ui.on_pressure_csv_logging_toggle_callback = self.on_pressure_csv_logging_toggle
        ui.on_temperature_calibration_callback = self.on_temperature_calibration_requested


def main() -> int:
    parser = argparse.ArgumentParser(description="Spine Cooling Runtime")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Use in-memory hardware fakes (no Raspberry Pi required)",
    )
    parser.add_argument(
        "--test-ui",
        action="store_true",
        help="Open sensor override window for manual/automated test injection",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("Spine Cooling Runtime")
    print("Medical Device Prototype")
    if args.sim:
        print("Mode: SIMULATION")
    if args.test_ui:
        print("Test UI: sensor override window enabled")
    print("=" * 50)
    print()

    app = SensorMonitorApp(
        config_path=args.config,
        simulation=args.sim,
        test_ui_enabled=args.test_ui,
    )
    exit_code = app.run()

    print()
    print("Application exited with code:", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
