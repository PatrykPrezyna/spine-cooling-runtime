"""State machine for the spine cooling runtime.

Models the high-level operating state and the transitions allowed between
states. Used by the main app to decide which UI controls are active and
which actuators (compressor, stepper) should run.
"""

from datetime import datetime
from enum import Enum
from typing import Callable, Optional


class State(Enum):
    INIT = "Init"
    READY = "Ready"
    COOLING = "Cooling"
    PUMPING = "Pumping"
    PUMPING_SLOWLY = "Pumping Slowly"
    ERROR = "Error"


# All states in which the cartridge must remain present and level sensors
# must remain healthy. Used by `update()` to detect runtime errors.
_ACTIVE_STATES = (State.COOLING, State.PUMPING, State.PUMPING_SLOWLY)

# Allowed state transitions.
_VALID_TRANSITIONS: dict = {
    State.INIT: [State.READY, State.ERROR],
    State.READY: [State.COOLING, State.ERROR],
    State.COOLING: [State.PUMPING, State.READY, State.ERROR],
    State.PUMPING: [State.PUMPING_SLOWLY, State.COOLING, State.READY, State.ERROR],
    State.PUMPING_SLOWLY: [State.PUMPING, State.COOLING, State.READY, State.ERROR],
    State.ERROR: [State.READY],
}


class StateMachine:
    """State machine for controlling application flow."""

    # Total width of the temperature hysteresis band around the setpoint
    # (degrees Celsius). PUMPING <-> PUMPING_SLOWLY toggles at the edges.
    PUMPING_HYSTERESIS_C = 2.0

    def __init__(self):
        self.current_state = State.INIT
        self.previous_state: Optional[State] = None
        self.error_message: Optional[str] = None
        self.state_entry_time = datetime.now()
        self.on_state_change: Optional[Callable[[State, State], None]] = None

        print(f"State Machine initialized in {self.current_state.value} state")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def get_current_state(self) -> State:
        return self.current_state

    def get_state_name(self) -> str:
        return self.current_state.value

    def get_error_message(self) -> Optional[str]:
        return self.error_message

    def get_time_in_state(self) -> float:
        """Return seconds spent in the current state."""
        return (datetime.now() - self.state_entry_time).total_seconds()

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def transition_to(self, new_state: State, reason: str = "") -> bool:
        """Transition to `new_state` if it's allowed from the current state."""
        if new_state not in _VALID_TRANSITIONS.get(self.current_state, []):
            print(f"Invalid transition from {self.current_state.value} to {new_state.value}")
            return False

        old_state = self.current_state
        self.previous_state = old_state
        self.current_state = new_state
        self.state_entry_time = datetime.now()

        # Clear the error message when leaving ERROR.
        if old_state == State.ERROR and new_state != State.ERROR:
            self.error_message = None

        reason_text = f" ({reason})" if reason else ""
        print(f"State transition: {old_state.value} -> {new_state.value}{reason_text}")

        if self.on_state_change:
            self.on_state_change(old_state, new_state)
        return True

    # ------------------------------------------------------------------
    # User-facing event handlers
    # ------------------------------------------------------------------
    def handle_init_complete(self, success: bool, error_msg: str = "") -> bool:
        if success:
            return self.transition_to(State.READY, "Initialization complete")
        self.error_message = error_msg or "Initialization failed"
        return self.transition_to(State.ERROR, self.error_message)

    def check_cooling_conditions(
        self,
        cartridge_present: bool,
        level_low: bool,
        level_critical: bool,
    ) -> bool:
        """READY -> COOLING when all required sensors report HIGH."""
        if self.current_state != State.READY:
            return False
        if cartridge_present and level_low and level_critical:
            return self.transition_to(State.COOLING, "All conditions met")
        return False

    def start_pumping(self) -> bool:
        if self.current_state == State.COOLING:
            return self.transition_to(State.PUMPING, "User started pumping")
        return False

    def stop_pumping(self) -> bool:
        if self.current_state in (State.PUMPING, State.PUMPING_SLOWLY):
            return self.transition_to(State.COOLING, "User stopped pumping")
        return False

    def handle_cartridge_removed(self) -> bool:
        if self.current_state in _ACTIVE_STATES:
            return self.transition_to(State.READY, "Cartridge removed")
        return False

    def handle_sensor_error(self, error_msg: str) -> bool:
        if self.current_state == State.ERROR:
            return False
        self.error_message = error_msg
        return self.transition_to(State.ERROR, error_msg)

    def acknowledge_error(self) -> bool:
        if self.current_state == State.ERROR:
            return self.transition_to(State.READY, "Error acknowledged")
        return False

    def reset(self) -> None:
        self.current_state = State.INIT
        self.previous_state = None
        self.error_message = None
        self.state_entry_time = datetime.now()
        print("State Machine reset to INIT state")

    # ------------------------------------------------------------------
    # Periodic update from sensor + temperature inputs
    # ------------------------------------------------------------------
    def update(
        self,
        sensor_states: dict,
        body_temp: Optional[float] = None,
        set_temp: Optional[float] = None,
    ) -> None:
        """Drive transitions from sensor states + optional temperature inputs.

        Args:
            sensor_states: dict containing 'Cartridge In Place', 'Level Low',
                'Level Critical' booleans.
            body_temp: latest CSF temperature (Celsius), or None if unknown.
            set_temp: target temperature (Celsius), or None if unknown.
        """
        cartridge_present = sensor_states.get('Cartridge In Place', False)
        level_low = sensor_states.get('Level Low', False)
        level_critical = sensor_states.get('Level Critical', False)

        if self.current_state in _ACTIVE_STATES:
            if not cartridge_present:
                self.handle_cartridge_removed()
                return
            if not level_low or not level_critical:
                self.handle_sensor_error("Level sensor failure detected")
                return

        if self.current_state == State.READY:
            self.check_cooling_conditions(cartridge_present, level_low, level_critical)
            return

        # Temperature-driven pumping mode control with hysteresis.
        if body_temp is None or set_temp is None:
            return
        half_band = self.PUMPING_HYSTERESIS_C / 2.0
        if self.current_state == State.PUMPING and body_temp <= set_temp - half_band:
            self.transition_to(State.PUMPING_SLOWLY, "Body temperature below target")
        elif self.current_state == State.PUMPING_SLOWLY and body_temp >= set_temp + half_band:
            self.transition_to(State.PUMPING, "Body temperature above target")


if __name__ == "__main__":
    print("Testing StateMachine...")

    sm = StateMachine()

    print("\n1. Testing INIT -> READY")
    sm.handle_init_complete(True)
    assert sm.get_current_state() == State.READY

    print("\n2. Testing READY -> COOLING")
    sm.check_cooling_conditions(True, True, True)
    assert sm.get_current_state() == State.COOLING

    print("\n3. Testing COOLING -> PUMPING")
    sm.start_pumping()
    assert sm.get_current_state() == State.PUMPING

    print("\n4. Testing PUMPING -> COOLING")
    sm.stop_pumping()
    assert sm.get_current_state() == State.COOLING

    print("\n5. Testing COOLING -> READY")
    sm.handle_cartridge_removed()
    assert sm.get_current_state() == State.READY

    print("\n6. Testing READY -> ERROR")
    sm.handle_sensor_error("Test error")
    assert sm.get_current_state() == State.ERROR
    assert sm.get_error_message() == "Test error"

    print("\n7. Testing ERROR -> READY")
    sm.acknowledge_error()
    assert sm.get_current_state() == State.READY
    assert sm.get_error_message() is None

    print("\nAll state machine tests passed!")
