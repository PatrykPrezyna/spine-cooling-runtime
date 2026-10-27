"""Application entry point.

Wires together hardware, the session recorder, the state machine, and the Qt UI.

- **GUI thread** — Qt UI and screen updates
- **IO worker thread** — sensor reads and thermistor I2C; sensor CSV rows go through SessionRecorder
- **Stepper thread** — motor pulse timing

Slow I/O runs on the worker so the GUI stays responsive and the stepper
thread is not delayed by Python's  Global Interpreter Lock.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # pragma: no cover - non-RPi environments
    GPIO = None  # type: ignore

from compressor_control import average_temperature_c, heat_ex_labels_from_config
from config_sections import (
    actuator_device,
    control_temp_label,
    ensure_actuator_device,
)
from cooling_tracker import CoolingEffectivenessTracker
from leak_debounce import LeakDebounceTracker
from fault_catalog import FaultCode, Severity, get_fault, stop_priority
from gui import MainScreen
from hardware_factory import build_hardware
from pump_flow_control import (
    PumpFlowController,
    flow_ml_per_min_to_rpm,
    rpm_to_flow_ml_per_min,
)
from safety_rules import RuleContext, TelemetrySnapshot, evaluate, is_fault_still_active
from sensor_injection import SensorInjectionController, select_temperatures
from sensor_override_ui import SensorOverrideWindow
from session_recorder import SessionRecorder
from state_machine import State, StateMachine


class _BackgroundIOWorker(QObject):
    """Runs all per-tick blocking I/O off the GUI thread.

    Owns no UI; results are emitted via the ``tick_complete`` signal and
    consumed back on the main thread.
    """

    tick_complete = pyqtSignal(object, object, object, object, object)
    # payload: (sensor_states, temperatures, pressures, flow_ml_per_min, error_message)

    def __init__(
        self,
        sensor_reader: Any,
        thermistor_reader: Any,
        pressure_reader: Any,
        recorder: Optional[SessionRecorder],
        config: Optional[dict] = None,
        flow_reader: Any = None,
    ):
        super().__init__()
        self._sensor_reader = sensor_reader
        self._thermistor_reader = thermistor_reader
        self._pressure_reader = pressure_reader
        self._flow_reader = flow_reader
        self._recorder = recorder
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
        temperatures: dict = {}
        thermistor_temperatures: dict = {}
        pressures: dict = {}
        flow_ml_per_min: Optional[float] = None
        error_message: Optional[str] = None
        try:
            logged_stepper_speed_rpm = (
                int(peristaltic_pump_set_speed_rpm)
                if bool(stepper_motor_running)
                else 0
            )
            if self._sensor_reader is not None:
                sensor_states = self._sensor_reader.read_all()
            if self._thermistor_reader is not None:
                notify_setpoint = getattr(self._thermistor_reader, "notify_setpoint", None)
                if notify_setpoint is not None:
                    notify_setpoint(
                        set_temperature_c,
                        compressor_cooling,
                        stepper_motor_running,
                        logged_stepper_speed_rpm,
                    )
                thermistor_temperatures = self._thermistor_reader.read_temperatures()
            temperatures = select_temperatures(thermistor_temperatures, self._config)
            if self._pressure_reader is not None:
                pressures = self._pressure_reader.read_pressures()
            if self._flow_reader is not None and getattr(
                self._flow_reader, "is_initialized", False
            ):
                flow_ml_per_min = self._flow_reader.read_flow_ml_per_min()
            if self._recorder is not None:
                self._recorder.record_sensors(
                    sensor_states,
                    temperatures,
                    peristaltic_pump_set_speed_rpm=logged_stepper_speed_rpm,
                    set_temperature_c=float(set_temperature_c),
                    compressor_cooling=int(compressor_cooling),
                    pressures=pressures,
                    flow_sensor_ml_per_min=flow_ml_per_min,
                )
        except Exception as exc:
            error_message = f"Error during update: {exc}"
        self.tick_complete.emit(
            sensor_states,
            temperatures,
            pressures,
            flow_ml_per_min,
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
        self.control_temp_label = control_temp_label(self.config)

        self.sensor_reader: Any = None
        self.sensor_injection: Optional[SensorInjectionController] = None
        self.override_ui: Optional[SensorOverrideWindow] = None
        # One stamp for the whole run; sensor, pressure, and status CSVs
        # all live in the same folder and share this filename prefix.
        self.session_start = datetime.now()
        self.recorder: Optional[SessionRecorder] = None
        self.ui: Optional[MainScreen] = None
        self.state_machine: Optional[StateMachine] = None
        self.stepper_driver: Any = None
        self.thermistor_reader: Any = None
        self.pressure_reader: Any = None
        self.flow_reader: Any = None
        stepper_cfg = actuator_device(self.config, "stepper_motor")
        compressor_cfg = actuator_device(self.config, "compressor")
        self.pump_flow_controller = PumpFlowController.from_config_dict(
            actuator_device(self.config, "pump_control") or None
        )
        self.stepper_speed_rpm: int = int(stepper_cfg.get('default_speed_rpm', 30))
        # Fallback RPM if closed-loop control has no temperature yet (~max flow).
        self.pumping_stepper_speed_rpm: int = int(
            stepper_cfg.get(
                "pumping_speed_rpm",
                flow_ml_per_min_to_rpm(
                    self.pump_flow_controller.config.max_flow_ml_per_min,
                ),
            )
        )
        self.pumping_slow_stepper_speed_rpm: int = int(
            stepper_cfg.get(
                "pumping_slow_speed_rpm",
                flow_ml_per_min_to_rpm(
                    self.pump_flow_controller.config.min_flow_ml_per_min,
                ),
            )
        )
        self.compressor_on: bool = False
        self.compressor_relay_pin: int = int(compressor_cfg.get('relay_pin', 16))
        # MOSFET gate: HIGH = compressor on. Idle is LOW (off).
        self.compressor_relay_high: bool = False
        self.compressor_control_enabled: bool = False
        self.compressor_latched_on: bool = False
        self.compressor_heat_ex_labels: list[str] = heat_ex_labels_from_config(
            compressor_cfg
        )
        self.compressor_off_temp_c: float = float(compressor_cfg.get('off_below_temp_c', 5))
        self.compressor_on_temp_c: float = float(compressor_cfg.get('on_above_temp_c', 10))
        self._last_temperatures: dict = {}
        self._last_sensor_states: dict = {}
        self._last_pressures: dict = {}
        self._last_measured_flow_ml_per_min: Optional[float] = None
        self.stepper_continuous_forward: bool = False
        self.stepper_motor_running: bool = False
        self.service_pid_run: bool = False
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
        with open(config_file, "r", encoding="utf-8") as f:
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
            self.recorder = SessionRecorder(
                self.config,
                self.session_start,
                simulation=self.simulation,
            )
            self.recorder.start_status_log()
            self.state_machine.on_state_change = self._on_state_changed

            bundle = build_hardware(self.config, simulation=self.simulation)
            if self.test_ui_enabled:
                self.sensor_injection = SensorInjectionController(self.config)
                bundle = self.sensor_injection.wrap_bundle(bundle)
            self.sensor_reader = bundle.sensor_reader
            self.thermistor_reader = bundle.thermistor_reader
            self.pressure_reader = bundle.pressure_reader
            self.flow_reader = bundle.flow_reader
            self.stepper_driver = bundle.stepper_driver

            if not self.sensor_reader.is_initialized:
                error_msg = "Sensor reader initialization failed"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False

            self._log_optional_status("Thermistor reader", self.thermistor_reader)
            self._log_optional_status("ADS1115 pressure reader", self.pressure_reader)
            if self.flow_reader is not None:
                self._log_optional_status("ADS1115 flow reader", self.flow_reader)

            if not self.simulation:
                self._initialize_compressor_relay()

            # Keep the driver energised while service jog controls are used.
            self.stepper_driver.disable_on_idle = False
            self.stepper_driver.enable()

            if not self.recorder.start_sensor_log():
                error_msg = "Failed to start CSV logging"
                print(f"Error: {error_msg}")
                self.state_machine.handle_init_complete(False, error_msg)
                return False

            self.recorder.start_pressure_capture(
                self.pressure_reader,
                self._logged_pump_set_speed_rpm,
            )
            self.recorder.start_usb_mirror()

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
        """Configure compressor MOSFET GPIO (active-high: HIGH = on)."""
        if GPIO is None:
            print("Compressor relay unavailable: RPi.GPIO not installed")
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.compressor_relay_pin, GPIO.OUT, initial=GPIO.LOW)
            self.compressor_relay_high = False
            print(f"Compressor relay initialized on GPIO{self.compressor_relay_pin}")
        except Exception as exc:
            print(f"Failed to initialize compressor relay GPIO{self.compressor_relay_pin}: {exc}")

    def _set_compressor_relay_high(self, high: bool) -> None:
        """Set compressor MOSFET gate. HIGH = compressor on, LOW = compressor off."""
        self.compressor_relay_high = bool(high)
        if GPIO is None:
            return
        try:
            GPIO.output(
                self.compressor_relay_pin,
                GPIO.HIGH if self.compressor_relay_high else GPIO.LOW,
            )
        except Exception as exc:
            print(f"Failed to set compressor relay GPIO{self.compressor_relay_pin}: {exc}")

    def _set_compressor_running(self, on: bool) -> None:
        """Drive compressor MOSFET (active-high)."""
        self.compressor_on = bool(on)
        self._set_compressor_relay_high(on)

    def _heat_ex_temperature_c(self, temperatures: dict) -> Optional[float]:
        """Control temperature from the configured plate probe (Plate 1)."""
        return average_temperature_c(temperatures, self.compressor_heat_ex_labels)

    def _apply_compressor_heat_ex_control(self, temperatures: dict) -> None:
        """Plate 1 hysteresis: off below off_temp_c, on above on_temp_c."""
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

        if self.recorder is not None:
            state = (
                self.state_machine.get_current_state()
                if self.state_machine is not None
                else None
            )
            self.recorder.stop(state)

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
        if self.flow_reader is not None:
            try:
                self.flow_reader.cleanup()
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
        self.thermistor_reader = None
        self.pressure_reader = None
        self.flow_reader = None

        print("Cleanup complete")

    def _sync_warning_log(self, message_codes: list[FaultCode]) -> None:
        """Log warning appear/clear edges (not every 10 Hz tick)."""
        if self.recorder is None:
            return
        state = self.state_machine.get_current_state() if self.state_machine else None
        self.recorder.sync_warnings(message_codes, state)

    def _refresh_usb_ui(self) -> None:
        if not self.ui:
            return
        status = self.recorder.usb_ui_status() if self.recorder is not None else None
        if status is None:
            self.ui.service_tab.update_usb_status(
                state="disabled",
                message="USB copy off",
                can_eject=False,
            )
            return
        state, message, can_eject = status
        self.ui.service_tab.update_usb_status(
            state=state,
            message=message,
            can_eject=can_eject,
        )

    def on_usb_eject(self) -> None:
        if self.recorder is None:
            return
        self.recorder.request_usb_eject()
        self._refresh_usb_ui()

    # ------------------------------------------------------------------
    # Background IO worker plumbing
    # ------------------------------------------------------------------
    def _start_io_worker(self) -> None:
        """Spin up the background QThread that runs the per-tick IO."""
        if self._io_thread is not None:
            return
        worker = _BackgroundIOWorker(
            self.sensor_reader,
            self.thermistor_reader,
            self.pressure_reader,
            self.recorder,
            self.config,
            flow_reader=self.flow_reader,
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
            telemetry=self._storage_telemetry(),
            config=self.config,
            cooling_tracker=self._cooling_tracker,
            leak_tracker=self._leak_tracker,
            now=now,
        )

    def _storage_telemetry(self) -> TelemetrySnapshot:
        """USB presence and free space for MESSAGE-severity storage warnings."""
        if self.recorder is None:
            return TelemetrySnapshot()
        return self.recorder.storage_telemetry()

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
            self._sync_warning_log([])
            self.state_machine.apply_fault(primary)
            self._stop_service_pid_run()
            if self.ui:
                self.ui.update_warnings([])
            return False

        message_codes = [c for c in active if get_fault(c).severity == Severity.MESSAGE]
        self._sync_warning_log(message_codes)
        if self.ui:
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
        if latched == FaultCode.PUMP_NOT_CLOSED:
            return self._pump_head_is_closed(sensor_states)
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
            fault_code=self.state_machine.get_latched_fault_code()
            if state == State.ERROR else None,
        )
        if state == State.ERROR:
            self.ui.set_acknowledge_enabled(False)

    def _on_state_changed(self, old_state: State, new_state: State, reason: str = ""):
        if self.recorder is not None:
            fault_code = (
                self.state_machine.get_latched_fault_code()
                if self.state_machine is not None and new_state == State.ERROR
                else None
            )
            self.recorder.log_state_change(
                old_state,
                new_state,
                reason,
                fault_code=fault_code,
            )
        self._refresh_ui_state_display()
        if new_state in (State.PUMPING, State.PUMPING_SLOWLY):
            if old_state not in (State.PUMPING, State.PUMPING_SLOWLY):
                self.pump_flow_controller.reset()
        elif old_state in (State.PUMPING, State.PUMPING_SLOWLY):
            self.pump_flow_controller.reset()
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
            min_rpm = int(
                actuator_device(self.config, "stepper_motor").get("min_pump_speed_rpm", 0)
                or 0
            )
            if min_rpm > 0:
                requested = max(min_rpm, requested)
        return requested

    def _rpm_for_flow_ml_per_min(self, flow_ml_per_min: float, *, enforce_min: bool = True) -> int:
        """Map a closed-loop flow command to a clamped stepper RPM."""
        cfg = self.pump_flow_controller.config
        flow = max(cfg.min_flow_ml_per_min, min(cfg.max_flow_ml_per_min, float(flow_ml_per_min)))
        rpm = flow_ml_per_min_to_rpm(flow)
        return self._clamp_pump_speed_rpm(rpm, enforce_min=enforce_min)

    def _apply_closed_loop_pump_control(
        self,
        csf_temp: Optional[float],
        set_temp: Optional[float],
    ) -> None:
        """Update pump RPM from CSF error while actively pumping."""
        if not self._closed_loop_pump_active():
            return
        if csf_temp is None or set_temp is None:
            return
        flow = self.pump_flow_controller.compute(float(csf_temp), float(set_temp))
        target_rpm = self._rpm_for_flow_ml_per_min(flow, enforce_min=True)
        if target_rpm == self.stepper_speed_rpm and self.stepper_continuous_forward:
            return
        self.stepper_speed_rpm = target_rpm
        if self.stepper_continuous_forward and self.stepper_driver:
            self.stepper_driver.set_continuous_speed(self.stepper_speed_rpm)
        elif not self.stepper_continuous_forward:
            self.on_stepper_continuous_toggle(True)

    def _closed_loop_pump_active(self) -> bool:
        """True during workflow pumping or a service-page PID run."""
        if self.service_pid_run:
            return True
        if self.state_machine is None:
            return False
        return self.state_machine.get_current_state() in (
            State.PUMPING,
            State.PUMPING_SLOWLY,
        )

    def _apply_state_driven_stepper_control(self, state: State):
        """Drive the stepper from state machine transitions."""
        if state in (State.PUMPING, State.PUMPING_SLOWLY):
            # Start at max flow; closed-loop tick will trim within [min, max].
            self.stepper_speed_rpm = self._rpm_for_flow_ml_per_min(
                self.pump_flow_controller.config.max_flow_ml_per_min,
                enforce_min=True,
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

    @pyqtSlot(object, object, object, object, object)
    def _on_io_tick_complete(
        self,
        sensor_states,
        temperatures,
        pressures,
        flow_ml_per_min,
        error_message,
    ):
        """Apply the worker's results back on the GUI thread."""
        try:
            if error_message:
                # A failed read is logged and this tick is dropped. It does not stop the session.
                print(error_message)
                self._refresh_usb_ui()
                return

            sensor_states = sensor_states or {}
            temperatures = temperatures or {}
            pressures = pressures or {}
            self._last_temperatures = temperatures
            self._last_sensor_states = sensor_states
            self._last_pressures = pressures
            self._last_measured_flow_ml_per_min = flow_ml_per_min
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
                    self._apply_closed_loop_pump_control(body_temp, set_temp)

            if self.ui:
                self.ui.update_sensor_display(
                    sensor_states,
                    temperatures,
                    pressures,
                    measured_flow_ml_per_min=flow_ml_per_min,
                    compressor_on=self.compressor_on,
                )
                self._refresh_acknowledge_button(sensor_states, temperatures, pressures)
                if self.stepper_driver:
                    self._update_stepper_ui_status()
                self._refresh_usb_ui()
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
        commanded_flow_ml_per_min = getattr(
            self.ui.service_tab, "_commanded_flow_ml_per_min", None
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
            flow_ml_per_min=commanded_flow_ml_per_min,
        )
        self.ui.pressure_service_tab.update_pump_speed(
            pump_speed_rpm=actual_pump_speed_rpm,
            flow_ml_per_min=commanded_flow_ml_per_min,
            measured_flow_ml_per_min=self._last_measured_flow_ml_per_min,
        )
        power_flow = self._last_measured_flow_ml_per_min
        if power_flow is None or (
            isinstance(power_flow, float) and power_flow != power_flow
        ):
            power_flow = commanded_flow_ml_per_min
        self.ui.power_graph_tab.update_pump_speed(
            pump_speed_rpm=actual_pump_speed_rpm,
            flow_ml_per_min=power_flow,
        )

    # ------------------------------------------------------------------
    # UI callbacks
    # ------------------------------------------------------------------
    def _pump_closed_label(self) -> str:
        return str(self.config.get("alarms", {}).get("pump_closed_label", "Pump Closed"))

    def _pump_head_is_closed(self, sensor_states: Optional[dict] = None) -> bool:
        """True when the pump head is closed, or the switch is not in this reading.

        A missing key means the switch was not read. An unwired input reads
        closed because of the pull-up, so an absent sensor does not block pumping.
        """
        states = self._last_sensor_states if sensor_states is None else sensor_states
        label = self._pump_closed_label()
        if label not in states:
            return True
        return bool(states[label])

    def pump_start_allowed(self) -> bool:
        """Refuse a new pump run and latch the stop fault while the head is open."""
        if self._pump_head_is_closed():
            return True
        if self.state_machine is not None:
            self.state_machine.apply_fault(FaultCode.PUMP_NOT_CLOSED)
        return False

    def on_start_pumping(self):
        if not self.pump_start_allowed():
            return
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
        enforce_min = self._closed_loop_pump_active()
        self.stepper_speed_rpm = self._clamp_pump_speed_rpm(
            speed_rpm,
            enforce_min=enforce_min,
        )
        if self.stepper_continuous_forward and self.stepper_driver:
            self.stepper_driver.set_continuous_speed(self.stepper_speed_rpm)
        self._log_pump_setpoints()
        if self.ui:
            self._update_stepper_ui_status()

    def on_set_temperature_changed(self, temperature_c: float) -> None:
        """Record the main-screen CSF setpoint in the status CSV."""
        self._log_setpoint_if_changed("set_temperature_c", f"{float(temperature_c):.1f}")

    def on_compressor_control_toggle(self, enabled: bool) -> None:
        """Enable/disable Plate 1 temperature control from the service page."""
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

    def _logged_pump_set_speed_rpm(self) -> int:
        """Stepper setpoint for CSV: speed when running, else 0."""
        return int(self.stepper_speed_rpm) if self.stepper_motor_running else 0

    def on_compressor_thresholds_changed(self, off_temp_c: float, on_temp_c: float) -> None:
        off_c = round(float(off_temp_c), 1)
        on_c = round(float(on_temp_c), 1)
        if on_c <= off_c:
            on_c = round(off_c + 0.1, 1)
        self.compressor_off_temp_c = off_c
        self.compressor_on_temp_c = on_c
        self._log_setpoint_if_changed("compressor_off_c", f"{off_c:.1f}")
        self._log_setpoint_if_changed("compressor_on_c", f"{on_c:.1f}")
        compressor_cfg = ensure_actuator_device(self.config, "compressor")
        compressor_cfg['off_below_temp_c'] = off_c
        compressor_cfg['on_above_temp_c'] = on_c
        self._save_config()
        if self.compressor_control_enabled:
            self._apply_compressor_heat_ex_control(self._last_temperatures)
        if self.ui:
            self._update_stepper_ui_status()

    def on_stepper_jog_start(self, direction: int):
        """Start jog while a jog button is held."""
        if not self.pump_start_allowed():
            return
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

    def on_service_pid_run_toggle(self, enabled: bool) -> None:
        """Start or stop a service-page PID run (same controller as Start Pumping)."""
        if enabled and not self.pump_start_allowed():
            return
        self.service_pid_run = bool(enabled)
        if enabled:
            self.pump_flow_controller.reset()
            self.stepper_speed_rpm = self._rpm_for_flow_ml_per_min(
                self.pump_flow_controller.config.max_flow_ml_per_min,
                enforce_min=True,
            )
            self.on_stepper_continuous_toggle(True)
            return
        self.pump_flow_controller.reset()
        in_workflow = (
            self.state_machine is not None
            and self.state_machine.get_current_state()
            in (State.PUMPING, State.PUMPING_SLOWLY)
        )
        if not in_workflow and self.stepper_continuous_forward:
            self.on_stepper_continuous_toggle(False)

    def _stop_service_pid_run(self) -> None:
        """Clear service PID mode without a second motor-stop command."""
        if not self.service_pid_run:
            return
        self.service_pid_run = False
        self.pump_flow_controller.reset()
        if self.ui is not None:
            service_tab = getattr(self.ui, "service_tab", None)
            if service_tab is not None:
                service_tab.stop_pid_run(notify=False)

    def on_stepper_continuous_toggle(self, enabled: bool):
        """Toggle continuous movement ON/OFF (direction: ``stepper_continuous_direction`` / config)."""
        if enabled and not self.pump_start_allowed():
            return
        if not enabled:
            self.service_pid_run = False
            if self.ui is not None:
                service_tab = getattr(self.ui, "service_tab", None)
                if service_tab is not None:
                    service_tab.stop_pid_run(notify=False)
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
                self.cleanup()
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
            self._refresh_usb_ui()

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
        ui.on_pid_run_toggle_callback = self.on_service_pid_run_toggle
        ui.on_compressor_control_toggle_callback = self.on_compressor_control_toggle
        ui.on_compressor_thresholds_change_callback = self.on_compressor_thresholds_changed
        ui.main_graph_widget.on_temperature_change_callback = self.on_set_temperature_changed
        ui.on_usb_eject_callback = self.on_usb_eject
        ui.service_tab.pump_start_allowed_callback = self.pump_start_allowed
        self._log_current_setpoints()

    def _log_setpoint_if_changed(self, name: str, value: str) -> None:
        """Append a setpoint row when the commanded value differs from the last one."""
        if self.recorder is None:
            return
        self.recorder.log_setpoint_if_changed(name, value)

    def _commanded_pump_flow_ml_per_min(self) -> str:
        """Return the operator flow setpoint, or the flow equivalent of the set RPM."""
        service = getattr(self.ui, "service_tab", None) if self.ui is not None else None
        commanded = getattr(service, "_commanded_flow_ml_per_min", None)
        if commanded is not None:
            return str(int(commanded))
        return f"{rpm_to_flow_ml_per_min(self.stepper_speed_rpm):.0f}"

    def _log_pump_setpoints(self) -> None:
        self._log_setpoint_if_changed("pump_speed_rpm", str(int(self.stepper_speed_rpm)))
        self._log_setpoint_if_changed(
            "pump_flow_ml_per_min",
            self._commanded_pump_flow_ml_per_min(),
        )

    def _log_current_setpoints(self) -> None:
        """Write the setpoints in force at session start."""
        set_temperature_c = 32.0
        if self.ui is not None:
            set_temperature_c = float(self.ui.main_graph_widget.set_temperature)
        self._log_setpoint_if_changed("set_temperature_c", f"{set_temperature_c:.1f}")
        self._log_pump_setpoints()
        self._log_setpoint_if_changed(
            "compressor_off_c",
            f"{float(self.compressor_off_temp_c):.1f}",
        )
        self._log_setpoint_if_changed(
            "compressor_on_c",
            f"{float(self.compressor_on_temp_c):.1f}",
        )


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
