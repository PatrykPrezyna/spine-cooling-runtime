# State Machine Implementation

## Overview

The application now includes a comprehensive **State Machine** that controls the application flow through five distinct states. The state machine ensures safe operation by enforcing valid state transitions and handling errors appropriately.

## States

### 1. INIT (Initialization)
**Purpose:** System initialization and validation

**Activities:**
- Initialize sensor readers
- Initialize CSV logger
- Check CSV directory exists (database check)
- Validate configuration

**Transitions:**
- ✅ Success → **READY**
- ❌ Failure → **ERROR**

**UI Indicators:**
- State label: Blue background
- No action buttons visible

---

### 2. READY (Ready to Start)
**Purpose:** System idle, waiting for conditions to start cooling

**Activities:**
- Monitor sensors continuously
- Wait for all conditions to be met
- Display current sensor states

**Conditions to Enter COOLING:**
- ✅ Cartridge In Place = TRUE
- ✅ Level Low = TRUE
- ✅ Level Critical = TRUE

**Transitions:**
- All conditions met → **COOLING**
- Error detected → **ERROR**

**UI Indicators:**
- State label: Green background
- No action buttons visible
- System ready for operation

---

### 3. COOLING (Cooling Mode Active)
**Purpose:** System is in cooling mode, ready for pumping

**Activities:**
- Monitor sensors for safety
- Display "START PUMPING" button
- Wait for user to start pumping

**Transitions:**
- User clicks "START PUMPING" → **PUMPING**
- Cartridge removed → **READY**
- Level sensor fails → **ERROR**
- Any error → **ERROR**

**UI Indicators:**
- State label: Purple background
- "START PUMPING" button visible and enabled
- System actively cooling

---

### 4. PUMPING (Pumping Mode Active)
**Purpose:** System is actively pumping

**Activities:**
- Monitor pump operation
- Monitor sensors for safety
- Display "STOP PUMPING" button
- Continue until user stops

**Transitions:**
- User clicks "STOP PUMPING" → **COOLING**
- Cartridge removed → **READY**
- Level sensor fails → **ERROR**
- Any error → **ERROR**

**UI Indicators:**
- State label: Yellow/Orange background
- "STOP PUMPING" button visible and enabled
- System actively pumping

---

### 5. ERROR (Error State)
**Purpose:** Handle errors and require user acknowledgment

**Activities:**
- Display error message
- Show "ACKNOWLEDGE ERROR" button
- Log error details
- Prevent further operations

**Transitions:**
- User clicks "ACKNOWLEDGE ERROR" → **READY**

**UI Indicators:**
- State label: Red background
- Error message displayed
- "ACKNOWLEDGE ERROR" button visible and enabled
- All other operations disabled

---

## State Transition Diagram

```
┌─────────┐
│  INIT   │ (Blue)
└────┬────┘
     │ Success
     ▼
┌─────────┐     All Conditions Met     ┌──────────┐
│  READY  │ ───────────────────────► │ COOLING  │ (Purple)
└────▲────┘ (Green)                    └────┬─────┘
     │                                      │ Start Pumping
     │ Acknowledge                          ▼
┌────┴────┐                            ┌──────────┐
│  ERROR  │ ◄──────────────────────── │ PUMPING  │ (Yellow)
└─────────┘ (Red)    Any Error         └──────────┘
     ▲                                      │
     └──────────────────────────────────────┘
              Cartridge Removed / Error
```

## Implementation Details

### State Machine Class (`src/state_machine.py`)

**Key Methods:**
- `transition_to(new_state, reason)` - Perform state transition
- `handle_init_complete(success, error_msg)` - Handle initialization result
- `check_cooling_conditions(...)` - Check if ready to enter COOLING
- `start_pumping()` - User starts pumping
- `stop_pumping()` - User stops pumping
- `handle_cartridge_removed()` - Handle cartridge removal
- `handle_sensor_error(error_msg)` - Handle sensor errors
- `acknowledge_error()` - User acknowledges error
- `update(sensor_states)` - Update based on sensor states

**State Validation:**
- All transitions are validated before execution
- Invalid transitions are rejected and logged
- State history is maintained

### Integration with Main Application

**Initialization:**
```python
self.state_machine = StateMachine()
self.state_machine.on_state_change = self._on_state_changed
```

**State Updates:**
```python
def update_display(self):
    sensor_states = self.sensor_reader.read_all()
    self.state_machine.update(sensor_states)  # Automatic state transitions
    self.ui.update_sensor_display(sensor_states)
```

**User Actions:**
```python
# Connected to UI buttons
self.ui.on_start_pumping_callback = self.on_start_pumping
self.ui.on_stop_pumping_callback = self.on_stop_pumping
self.ui.on_acknowledge_callback = self.on_acknowledge_error
```

### UI Integration

**State Display:**
- State label shows current state with color coding
- Error message displayed in ERROR state
- State-specific buttons appear/disappear automatically

**Button Visibility:**
- **COOLING state:** "START PUMPING" button visible
- **PUMPING state:** "STOP PUMPING" button visible
- **ERROR state:** "ACKNOWLEDGE ERROR" button visible
- **Other states:** No action buttons visible

**Color Coding:**
- 🔵 **INIT:** Blue - Initializing
- 🟢 **READY:** Green - Ready for operation
- 🟣 **COOLING:** Purple - Cooling active
- 🟡 **PUMPING:** Yellow - Pumping active
- 🔴 **ERROR:** Red - Error requires attention

## Usage Examples

### Normal Operation Flow

1. **Application starts** → INIT state
2. **Initialization succeeds** → READY state
3. **User inserts cartridge and fills levels** → Sensors detect conditions
4. **All conditions met** → COOLING state (automatic)
5. **User clicks "START PUMPING"** → PUMPING state
6. **User clicks "STOP PUMPING"** → COOLING state
7. **User removes cartridge** → READY state (automatic)

### Error Handling Flow

1. **System in any state**
2. **Error occurs** (sensor failure, etc.) → ERROR state (automatic)
3. **Error message displayed**
4. **User clicks "ACKNOWLEDGE ERROR"** → READY state
5. **System ready to retry**

### Simulation Mode Testing

In simulation mode, you can manually control sensors to test state transitions:

1. Start application (INIT → READY)
2. Go to Simulation tab
3. Check all three sensors:
   - ☑️ Cartridge In Place
   - ☑️ Level Low
   - ☑️ Level Critical
4. System automatically transitions to COOLING
5. Click "START PUMPING" → PUMPING state
6. Uncheck "Cartridge In Place" → Returns to READY
7. System handles transitions automatically

## Safety Features

### Automatic Error Detection
- **Sensor failures:** Detected during COOLING/PUMPING
- **Cartridge removal:** Detected during COOLING/PUMPING
- **Initialization failures:** Caught during INIT

### State Validation
- **Invalid transitions blocked:** Cannot skip states
- **State history maintained:** Previous state tracked
- **Transition logging:** All changes logged to console

### User Protection
- **Cannot change modes during PUMPING:** Mode button disabled
- **Cannot start logging in ERROR state:** Buttons disabled
- **Must acknowledge errors:** Cannot proceed without acknowledgment

## Configuration

No configuration changes needed. The state machine uses the existing sensor configuration:

```yaml
sensors:
  - name: "Level Low"
    gpio_pin: 14
  - name: "Level Critical"
    gpio_pin: 15
  - name: "Cartridge In Place"
    gpio_pin: 18
```

## Testing

### Manual Testing

1. **Test INIT → READY:**
   ```bash
   python src/main.py
   ```
   - Verify state changes to READY
   - Check green state indicator

2. **Test READY → COOLING:**
   - Enable all three sensors in Simulation tab
   - Verify automatic transition to COOLING
   - Check purple state indicator
   - Verify "START PUMPING" button appears

3. **Test COOLING → PUMPING:**
   - Click "START PUMPING"
   - Verify transition to PUMPING
   - Check yellow state indicator
   - Verify "STOP PUMPING" button appears

4. **Test PUMPING → COOLING:**
   - Click "STOP PUMPING"
   - Verify return to COOLING
   - Check "START PUMPING" button reappears

5. **Test Error Handling:**
   - While in PUMPING, uncheck "Level Low"
   - Verify transition to ERROR
   - Check red state indicator
   - Verify error message displayed
   - Click "ACKNOWLEDGE ERROR"
   - Verify return to READY

### Automated Testing

Run the state machine unit tests:
```bash
python src/state_machine.py
```

Expected output:
```
Testing StateMachine...
✓ All state machine tests passed!
```

## Troubleshooting

### State not changing
- Check console for transition messages
- Verify sensor conditions are met
- Ensure no errors are blocking transitions

### Buttons not appearing
- Verify you're in the correct state
- Check state label color and text
- Restart application if UI is stuck

### Cannot acknowledge error
- Ensure you're in ERROR state
- Check error message is displayed
- Click the red "ACKNOWLEDGE ERROR" button

## Future Enhancements

Potential additions to the state machine:

- [ ] Timeout handling (auto-transition after time limit)
- [ ] State persistence (save/restore state on restart)
- [ ] Advanced error recovery strategies
- [ ] State-based logging levels
- [ ] Maintenance mode state
- [ ] Calibration mode state
- [ ] Historical state tracking and analytics

## Summary

The state machine provides:
- ✅ **Safe operation** through validated state transitions
- ✅ **Clear visual feedback** with color-coded state indicators
- ✅ **Automatic transitions** based on sensor conditions
- ✅ **Manual control** through user action buttons
- ✅ **Error handling** with required acknowledgment
- ✅ **Easy testing** in simulation mode

The state machine ensures the application operates safely and predictably, preventing invalid operations and handling errors gracefully.

---

*Made with Bob*