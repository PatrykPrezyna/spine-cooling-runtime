"""
State Machine Module
Manages application states and transitions
"""

from enum import Enum
from typing import Optional, Callable
from datetime import datetime


class State(Enum):
    """Application states"""
    INIT = "Init"
    READY = "Ready"
    COOLING = "Cooling"
    PUMPING = "Pumping"
    ERROR = "Error"


class StateMachine:
    """State machine for controlling application flow"""
    
    def __init__(self):
        """Initialize state machine"""
        self.current_state = State.INIT
        self.previous_state: Optional[State] = None
        self.error_message: Optional[str] = None
        self.state_entry_time = datetime.now()
        
        # Callbacks for state changes
        self.on_state_change: Optional[Callable[[State, State], None]] = None
        
        print(f"State Machine initialized in {self.current_state.value} state")
    
    def get_current_state(self) -> State:
        """Get current state"""
        return self.current_state
    
    def get_state_name(self) -> str:
        """Get current state name"""
        return self.current_state.value
    
    def get_error_message(self) -> Optional[str]:
        """Get current error message"""
        return self.error_message
    
    def transition_to(self, new_state: State, reason: str = "") -> bool:
        """
        Transition to a new state
        
        Args:
            new_state: Target state
            reason: Reason for transition
            
        Returns:
            bool: True if transition was successful
        """
        if not self._is_valid_transition(self.current_state, new_state):
            print(f"Invalid transition from {self.current_state.value} to {new_state.value}")
            return False
        
        old_state = self.current_state
        self.previous_state = old_state
        self.current_state = new_state
        self.state_entry_time = datetime.now()
        
        # Clear error message when leaving ERROR state
        if old_state == State.ERROR and new_state != State.ERROR:
            self.error_message = None
        
        reason_text = f" ({reason})" if reason else ""
        print(f"State transition: {old_state.value} → {new_state.value}{reason_text}")
        
        # Notify callback
        if self.on_state_change:
            self.on_state_change(old_state, new_state)
        
        return True
    
    def _is_valid_transition(self, from_state: State, to_state: State) -> bool:
        """
        Check if a state transition is valid
        
        Args:
            from_state: Current state
            to_state: Target state
            
        Returns:
            bool: True if transition is valid
        """
        # Define valid transitions
        valid_transitions = {
            State.INIT: [State.READY, State.ERROR],
            State.READY: [State.COOLING, State.ERROR],
            State.COOLING: [State.PUMPING, State.READY, State.ERROR],
            State.PUMPING: [State.COOLING, State.READY, State.ERROR],
            State.ERROR: [State.READY]
        }
        
        return to_state in valid_transitions.get(from_state, [])
    
    def handle_init_complete(self, success: bool, error_msg: str = "") -> bool:
        """
        Handle initialization completion
        
        Args:
            success: True if initialization was successful
            error_msg: Error message if initialization failed
            
        Returns:
            bool: True if state changed
        """
        if success:
            return self.transition_to(State.READY, "Initialization complete")
        else:
            self.error_message = error_msg or "Initialization failed"
            return self.transition_to(State.ERROR, self.error_message)
    
    def check_cooling_conditions(self, cartridge_present: bool, 
                                 level_low: bool, level_critical: bool) -> bool:
        """
        Check if conditions are met to enter COOLING state
        
        Args:
            cartridge_present: Cartridge sensor state
            level_low: Level low sensor state
            level_critical: Level critical sensor state
            
        Returns:
            bool: True if conditions are met and state changed
        """
        if self.current_state != State.READY:
            return False
        
        if cartridge_present and level_low and level_critical:
            return self.transition_to(State.COOLING, "All conditions met")
        
        return False
    
    def start_pumping(self) -> bool:
        """
        Start pumping (user action)
        
        Returns:
            bool: True if state changed
        """
        if self.current_state == State.COOLING:
            return self.transition_to(State.PUMPING, "User started pumping")
        return False
    
    def stop_pumping(self) -> bool:
        """
        Stop pumping (user action)
        
        Returns:
            bool: True if state changed
        """
        if self.current_state == State.PUMPING:
            return self.transition_to(State.COOLING, "User stopped pumping")
        return False
    
    def handle_cartridge_removed(self) -> bool:
        """
        Handle cartridge removal
        
        Returns:
            bool: True if state changed
        """
        if self.current_state in [State.COOLING, State.PUMPING]:
            return self.transition_to(State.READY, "Cartridge removed")
        return False
    
    def handle_sensor_error(self, error_msg: str) -> bool:
        """
        Handle sensor error
        
        Args:
            error_msg: Error message
            
        Returns:
            bool: True if state changed
        """
        if self.current_state != State.ERROR:
            self.error_message = error_msg
            return self.transition_to(State.ERROR, error_msg)
        return False
    
    def acknowledge_error(self) -> bool:
        """
        Acknowledge error (user action)
        
        Returns:
            bool: True if state changed
        """
        if self.current_state == State.ERROR:
            return self.transition_to(State.READY, "Error acknowledged")
        return False
    
    def update(self, sensor_states: dict) -> None:
        """
        Update state machine based on sensor states
        
        Args:
            sensor_states: Dictionary of sensor states
        """
        cartridge_present = sensor_states.get('Cartridge In Place', False)
        level_low = sensor_states.get('Level Low', False)
        level_critical = sensor_states.get('Level Critical', False)
        
        # Check for cartridge removal in COOLING or PUMPING states
        if self.current_state in [State.COOLING, State.PUMPING]:
            if not cartridge_present:
                self.handle_cartridge_removed()
                return
        
        # Check for sensor errors (missing required sensors in active states)
        if self.current_state in [State.COOLING, State.PUMPING]:
            if not level_low or not level_critical:
                self.handle_sensor_error("Level sensor failure detected")
                return
        
        # Check if conditions are met to enter COOLING from READY
        if self.current_state == State.READY:
            self.check_cooling_conditions(cartridge_present, level_low, level_critical)
    
    def get_time_in_state(self) -> float:
        """
        Get time spent in current state (in seconds)
        
        Returns:
            float: Time in seconds
        """
        return (datetime.now() - self.state_entry_time).total_seconds()
    
    def reset(self) -> None:
        """Reset state machine to INIT state"""
        self.current_state = State.INIT
        self.previous_state = None
        self.error_message = None
        self.state_entry_time = datetime.now()
        print("State Machine reset to INIT state")


if __name__ == "__main__":
    # Test the state machine
    print("Testing StateMachine...")
    
    sm = StateMachine()
    
    # Test INIT → READY
    print("\n1. Testing INIT → READY")
    sm.handle_init_complete(True)
    assert sm.get_current_state() == State.READY
    
    # Test READY → COOLING (conditions met)
    print("\n2. Testing READY → COOLING")
    sm.check_cooling_conditions(True, True, True)
    assert sm.get_current_state() == State.COOLING
    
    # Test COOLING → PUMPING
    print("\n3. Testing COOLING → PUMPING")
    sm.start_pumping()
    assert sm.get_current_state() == State.PUMPING
    
    # Test PUMPING → COOLING
    print("\n4. Testing PUMPING → COOLING")
    sm.stop_pumping()
    assert sm.get_current_state() == State.COOLING
    
    # Test COOLING → READY (cartridge removed)
    print("\n5. Testing COOLING → READY")
    sm.handle_cartridge_removed()
    assert sm.get_current_state() == State.READY
    
    # Test READY → ERROR
    print("\n6. Testing READY → ERROR")
    sm.handle_sensor_error("Test error")
    assert sm.get_current_state() == State.ERROR
    assert sm.get_error_message() == "Test error"
    
    # Test ERROR → READY
    print("\n7. Testing ERROR → READY")
    sm.acknowledge_error()
    assert sm.get_current_state() == State.READY
    assert sm.get_error_message() is None
    
    print("\n✓ All state machine tests passed!")

# Made with Bob