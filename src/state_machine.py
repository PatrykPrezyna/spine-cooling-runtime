"""State machine for the spine cooling runtime.

Tracks where the device is in its workflow and which moves are legal next.

Typical happy path:

  INIT -> READY -> COOLING -> PUMPING <-> PUMPING SLOWLY
           ^                                    |
           +-------- ERROR (fault; ack) <-------+

``main.py`` calls ``update()`` every tick with sensor readings and
temperatures. Button handlers call ``start_pumping()``, ``stop_pumping()``,
and ``acknowledge_error()``.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

from fault_catalog import FaultCode, get_fault


class State(Enum):
    INIT = "Init"
    READY = "Ready"
    COOLING = "Cooling"
    PUMPING = "Pumping"
    PUMPING_SLOWLY = "Pumping Slowly"
    ERROR = "Error"


class StateMachine:
    """Controls application flow through the states above."""

    # Fast/slow pump toggle uses a band around the setpoint (degrees C).
    PUMPING_HYSTERESIS_C = 2.0
    READY_HOLD_AFTER_STARTUP_S = 10.0

    def __init__(self, ready_hold_after_startup_s: float = READY_HOLD_AFTER_STARTUP_S):
        self.current_state = State.INIT
        self.error_message: Optional[str] = None
        self.latched_fault_code: Optional[FaultCode] = None
        self.fault_context_state: Optional[State] = None
        self.state_entry_time = datetime.now()
        self.on_state_change: Optional[Callable[[State, State], None]] = None
        self._ready_hold_after_startup_s = max(0.0, float(ready_hold_after_startup_s))
        self._startup_ready_hold_until: Optional[datetime] = None
        print(f"State Machine initialized in {self.current_state.value} state")

    # --- things main.py and the UI call ---------------------------------

    def get_current_state(self) -> State:
        return self.current_state

    def get_error_message(self) -> Optional[str]:
        return self.error_message

    def get_latched_fault_code(self) -> Optional[FaultCode]:
        return self.latched_fault_code

    def get_fault_context_state(self) -> Optional[State]:
        return self.fault_context_state

    def get_time_in_state(self) -> float:
        return (datetime.now() - self.state_entry_time).total_seconds()

    def handle_init_complete(self, success: bool, error_msg: str = "") -> bool:
        """Called once hardware init finishes."""
        if success:
            if self._ready_hold_after_startup_s > 0:
                self._startup_ready_hold_until = (
                    datetime.now() + timedelta(seconds=self._ready_hold_after_startup_s)
                )
            return self._change_state(State.READY, "Initialization complete")
        self.error_message = error_msg or "Initialization failed"
        return self._change_state(State.ERROR, self.error_message)


    # --- user actions --------------------------------------------------
    def start_pumping(self) -> bool:
        """User pressed START PUMPING while in COOLING."""
        if self.current_state != State.COOLING:
            return False
        return self._change_state(State.PUMPING, "User started pumping")

    def stop_pumping(self) -> bool:
        """User pressed STOP PUMPING."""
        if self.current_state not in (State.PUMPING, State.PUMPING_SLOWLY):
            return False
        return self._change_state(State.COOLING, "User stopped pumping")

    def apply_fault(self, code: FaultCode, message_override: Optional[str] = None) -> bool:
        """Enter ERROR from a catalog fault (STOP severity)."""
        if self.current_state == State.ERROR:
            return False
        fault = get_fault(code)
        self.latched_fault_code = code
        self.fault_context_state = self.current_state
        self.error_message = message_override or fault.message
        return self._change_state(State.ERROR, self.error_message)

    def handle_sensor_error(self, error_msg: str) -> bool:
        """IO worker or sensor read failed."""
        return self.apply_fault(FaultCode.IO_READ_FAILURE, error_msg)

    def acknowledge_error(self) -> bool:
        """Operator cleared the error screen."""
        if self.current_state != State.ERROR:
            return False
        return self._change_state(State.READY, "Error acknowledged")

    def update(
        self,
        sensor_states: dict,
        body_temp: Optional[float] = None,
        set_temp: Optional[float] = None,
    ) -> None:
        """Run each sensor/temperature tick.

        ``sensor_states`` keys (from config.yaml / MultiSensorReader):
        ``Cartridge In Place``, ``Level Low``, ``Level Critical``.
        """
        cartridge = sensor_states.get("Cartridge In Place", False)
        level_low = sensor_states.get("Level Low", False)
        level_critical = sensor_states.get("Level Critical", False)

        # --- auto-start cooling when idle and all sensors are HIGH ------
        if self.current_state == State.READY:
            if self._startup_ready_hold_until is not None:
                if datetime.now() < self._startup_ready_hold_until:
                    return
                self._startup_ready_hold_until = None
            if cartridge and level_low and level_critical:
                self._change_state(State.COOLING, "All conditions met")
            return

        # --- switch pump speed from body temperature --------------------
        if body_temp is None or set_temp is None:
            return
        half_band = self.PUMPING_HYSTERESIS_C / 2.0
        too_cold = body_temp <= set_temp - half_band
        warm_enough = body_temp >= set_temp + half_band
        if self.current_state == State.PUMPING and too_cold:
            self._change_state(State.PUMPING_SLOWLY, "Body temperature below target")
        elif self.current_state == State.PUMPING_SLOWLY and warm_enough:
            self._change_state(State.PUMPING, "Body temperature above target")

    # --- internal: validate and apply a state change ------------------

    def _change_state(self, new_state: State, reason: str = "") -> bool:
        old_state = self.current_state

        # Allowed moves, written out explicitly (see module docstring).
        ok = (
            (old_state == State.INIT and new_state in (State.READY, State.ERROR))
            or (old_state == State.READY and new_state in (State.COOLING, State.ERROR))
            or (old_state == State.COOLING and new_state in (State.PUMPING, State.READY, State.ERROR))
            or (
                old_state == State.PUMPING
                and new_state in (State.PUMPING_SLOWLY, State.COOLING, State.READY, State.ERROR)
            )
            or (
                old_state == State.PUMPING_SLOWLY
                and new_state in (State.PUMPING, State.COOLING, State.READY, State.ERROR)
            )
            or (old_state == State.ERROR and new_state == State.READY)
        )
        if not ok:
            print(f"Invalid transition from {old_state.value} to {new_state.value}")
            return False

        self.current_state = new_state
        self.state_entry_time = datetime.now()

        if old_state == State.ERROR:
            self.error_message = None
            self.latched_fault_code = None
            self.fault_context_state = None

        reason_text = f" ({reason})" if reason else ""
        print(f"State transition: {old_state.value} -> {new_state.value}{reason_text}")

        if self.on_state_change:
            self.on_state_change(old_state, new_state)
        return True