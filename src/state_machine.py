"""State machine for the spine cooling runtime.

Tracks where the device is in its workflow and which moves are legal next.

Typical happy path:

  INIT -> READY -> COOLING -> PUMPING <-> PUMPING SLOWLY
           ^         ^          ^              ^
           |         |          |              |
           +---------+----------+--------------+   cartridge removed
           |
           ERROR   (init/sensor fault; operator ack returns to READY)

``main.py`` calls ``update()`` every tick with sensor readings and
temperatures. Button handlers call ``start_pumping()``, ``stop_pumping()``,
and ``acknowledge_error()``.
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


class StateMachine:
    """Controls application flow through the states above."""

    # Fast/slow pump toggle uses a band around the setpoint (degrees C).
    PUMPING_HYSTERESIS_C = 2.0

    def __init__(self):
        self.current_state = State.INIT
        self.error_message: Optional[str] = None
        self.state_entry_time = datetime.now()
        self.on_state_change: Optional[Callable[[State, State], None]] = None
        print(f"State Machine initialized in {self.current_state.value} state")

    # --- things main.py and the UI call ---------------------------------

    def get_current_state(self) -> State:
        return self.current_state

    def get_error_message(self) -> Optional[str]:
        return self.error_message

    def handle_init_complete(self, success: bool, error_msg: str = "") -> bool:
        """Called once hardware init finishes."""
        if success:
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

    def handle_sensor_error(self, error_msg: str) -> bool:
        """IO worker or sensor read failed."""
        if self.current_state == State.ERROR:
            return False
        self.error_message = error_msg
        return self._change_state(State.ERROR, error_msg)

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

        ## ERROR HANDLING
        # --- safety checks while cooling or pumping ---------------------
        if self.current_state in (State.COOLING, State.PUMPING, State.PUMPING_SLOWLY):
            if not cartridge:
                self._change_state(State.READY, "Cartridge removed")
                return
            if not level_low or not level_critical:
                self.error_message = "Level sensor failure detected"
                self._change_state(State.ERROR, self.error_message)
                return


        ## AUTOMATIC STATE TRANSITIONS
        # --- auto-start cooling when idle and all sensors are HIGH ------
        if self.current_state == State.READY:
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

        reason_text = f" ({reason})" if reason else ""
        print(f"State transition: {old_state.value} -> {new_state.value}{reason_text}")

        if self.on_state_change:
            self.on_state_change(old_state, new_state)
        return True