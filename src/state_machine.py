"""State machine for the spine cooling runtime.

Tracks where the device is in its workflow and which moves are legal next.

Typical happy path:

  INIT -> READY -> COOLING -> PUMPING
           ^                     |
           +-- ERROR (fault; ack)+

Pump flow during ``PUMPING`` is closed-loop (ml/min PID) in ``main.py``;
this machine only owns workflow states.

``main.py`` calls ``update()`` every tick with sensor readings.
Button handlers call ``start_pumping()``, ``stop_pumping()``,
and ``acknowledge_error()``.

``TRANSITIONS`` lists every legal move. ``docs/state-machine.svg`` is
generated from that table.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, NamedTuple, Optional

from fault_catalog import FaultCode, get_fault


class State(Enum):
    INIT = "Init"
    READY = "Ready"
    COOLING = "Cooling"
    PUMPING = "Pumping"
    ERROR = "Error"


INITIAL_STATE = State.INIT


class Transition(NamedTuple):
    """One legal move.

    ``label`` is the short name on the generated diagram.
    ``log_reason`` is the fixed session-log text, when the caller does not
    supply its own (a fault message, or the init failure text).
    ``requested`` is false for moves the machine still accepts and no current
    caller takes. ``tools/generate_state_machine_diagram.py`` reads this table.
    """

    source: State
    target: State
    label: str
    log_reason: Optional[str] = None
    requested: bool = True


TRANSITIONS: tuple[Transition, ...] = (
    Transition(State.INIT, State.READY, "init ok", "Initialization complete"),
    Transition(State.INIT, State.ERROR, "init failed"),
    Transition(State.READY, State.COOLING, "sensors OK", "All conditions met"),
    Transition(State.READY, State.ERROR, "stop fault"),
    Transition(State.COOLING, State.PUMPING, "start pumping", "User started pumping"),
    Transition(State.COOLING, State.ERROR, "stop fault"),
    Transition(State.PUMPING, State.COOLING, "stop pumping", "User stopped pumping"),
    Transition(State.PUMPING, State.ERROR, "stop fault"),
    Transition(State.ERROR, State.READY, "acknowledge", "Error acknowledged"),
)

_TRANSITIONS = {(item.source, item.target): item for item in TRANSITIONS}


def find_transition(source: State, target: State) -> Transition:
    try:
        return _TRANSITIONS[(source, target)]
    except KeyError as exc:
        raise KeyError(f"No transition {source.value} -> {target.value}") from exc


def log_reason(source: State, target: State) -> str:
    """Fixed log text for a transition, or "" when the caller passes the reason."""
    return find_transition(source, target).log_reason or ""


class StateMachine:
    """Controls application flow through the states above."""

    READY_HOLD_AFTER_STARTUP_S = 10.0

    def __init__(self, ready_hold_after_startup_s: float = READY_HOLD_AFTER_STARTUP_S):
        self.current_state = INITIAL_STATE
        self.error_message: Optional[str] = None
        self.latched_fault_code: Optional[FaultCode] = None
        self.fault_context_state: Optional[State] = None
        self.state_entry_time = datetime.now()
        self.on_state_change: Optional[Callable[[State, State, str], None]] = None
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
            return self._change_state(State.READY, log_reason(State.INIT, State.READY))
        self.error_message = error_msg or "Initialization failed"
        return self._change_state(State.ERROR, self.error_message)


    # --- user actions --------------------------------------------------
    def start_pumping(self) -> bool:
        """User pressed START PUMPING while in COOLING."""
        if self.current_state != State.COOLING:
            return False
        return self._change_state(State.PUMPING, log_reason(State.COOLING, State.PUMPING))

    def stop_pumping(self) -> bool:
        """User pressed STOP PUMPING."""
        if self.current_state != State.PUMPING:
            return False
        return self._change_state(State.COOLING, log_reason(State.PUMPING, State.COOLING))

    def apply_fault(self, code: FaultCode, message_override: Optional[str] = None) -> bool:
        """Enter ERROR from a catalog fault (STOP severity)."""
        if self.current_state == State.ERROR:
            return False
        fault = get_fault(code)
        self.latched_fault_code = code
        self.fault_context_state = self.current_state
        self.error_message = message_override or fault.message
        return self._change_state(State.ERROR, self.error_message)

    def acknowledge_error(self) -> bool:
        """Operator cleared the error screen."""
        if self.current_state != State.ERROR:
            return False
        return self._change_state(State.READY, log_reason(State.ERROR, State.READY))

    def update(
        self,
        sensor_states: dict,
        body_temp: Optional[float] = None,
        set_temp: Optional[float] = None,
    ) -> None:
        """Run each sensor tick.

        ``sensor_states`` keys (from config.yaml / MultiSensorReader):
        ``Cartridge In Place``, ``Level Low``, ``Level Critical``.

        ``body_temp`` / ``set_temp`` are accepted for call-site compatibility;
        pump speed is controlled outside this machine.
        """
        del body_temp, set_temp
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
                self._change_state(State.COOLING, log_reason(State.READY, State.COOLING))

    # --- internal: validate and apply a state change ------------------

    def _change_state(self, new_state: State, reason: str = "") -> bool:
        old_state = self.current_state

        if (old_state, new_state) not in _TRANSITIONS:
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
            self.on_state_change(old_state, new_state, reason)
        return True
