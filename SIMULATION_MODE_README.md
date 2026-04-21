# Simulation Mode - Runtime Switchable Manual Sensor Control

## Overview

The application now includes a **Simulation Mode** that allows you to manually control all sensor states through a graphical interface. You can **switch between Simulation and Real Sensor modes at runtime** using a toggle button in the UI. This is perfect for:
- Testing the application without physical hardware
- Demonstrating sensor behavior
- Development and debugging
- Training and demonstrations
- Switching between real and simulated sensors on the fly

## Features

### 1. Manual Sensor Control
- Control each sensor individually via checkboxes
- Set all sensors HIGH or LOW with one click
- Real-time visual feedback in the Monitor tab
- Changes take effect immediately

### 2. Simulation Tab
A dedicated tab in the UI provides:
- Individual checkboxes for each sensor
- Visual indicators (green for HIGH, red for LOW)
- Information panel explaining simulation mode

### 3. Full Integration
- Works with all existing features (Monitor tab, Service tab)
- CSV logging still functions normally
- All visualizations update in real-time
- No hardware required

## How to Use

### Starting the Application

Simply run the application (starts in Simulation Mode by default):

```bash
python src/main.py
```

The application always starts in **Simulation Mode** for safety and ease of testing.

### Switching Modes at Runtime

You can switch between Simulation and Real Sensor modes at any time using the **mode toggle button** in the UI:

1. **Locate the mode button** - It's a purple button at the bottom of the window showing the current mode
2. **Click to toggle** - Click the button to switch between modes
3. **Note**: You cannot change modes while logging is active (stop logging first)

### Using the Simulation Tab

1. **Start the application**
   ```bash
   python src/main.py
   ```

2. **Ensure you're in Simulation Mode**
   - Check the mode button shows "SIMULATION MODE"
   - If not, click it to switch to Simulation Mode

3. **Navigate to the Simulation tab**
   - Click on the "Simulation" tab in the UI

4. **Control individual sensors**
   - Check/uncheck boxes to set sensors HIGH/LOW
   - Changes apply immediately

5. **Monitor the effects**
   - Switch to the "Monitor" tab to see the cartridge visualization
   - Switch to the "Service" tab to see detailed sensor states

6. **Start logging (optional)**
   - Click "START LOGGING" to begin CSV logging
   - All manual sensor changes will be logged

## Architecture

### New Components

#### 1. SimulationSensorReader (`src/simulation_sensor_reader.py`)
- Replaces `MultiSensorReader` in simulation mode
- Maintains sensor states in memory
- Provides methods to manually set sensor states
- Compatible with existing sensor reader interface

#### 2. SimulationTab (`src/enhanced_ui.py`)
- New tab widget for manual control
- Checkboxes for each sensor
- Quick control buttons
- Real-time state synchronization

#### 3. Enhanced Main Application (`src/main.py`)
- Runtime mode switching capability
- Mode toggle button integration
- Automatic sensor reader switching
- Callback integration for manual sensor changes
- Mode change handling and validation

### Integration Flow

#### Sensor Control Flow
```
User clicks checkbox in Simulation Tab
    ↓
SimulationTab.on_sensor_change_callback()
    ↓
SensorMonitorApp.on_simulation_sensor_changed()
    ↓
SimulationSensorReader.set_sensor()
    ↓
SensorMonitorApp.update_display()
    ↓
UI updates (Monitor, Service, Simulation tabs)
```

#### Mode Switching Flow
```
User clicks Mode Toggle Button
    ↓
EnhancedSensorMonitorWindow._on_mode_toggle_clicked()
    ↓
SensorMonitorApp.on_mode_changed()
    ↓
Cleanup old sensor reader
    ↓
Initialize new sensor reader (Simulation or Real)
    ↓
Update display with new sensor states
```

## Configuration

No configuration changes are needed. The same `config.yaml` file works for both modes:

```yaml
sensors:
  - name: "Level Low"
    gpio_pin: 14
    active_high: true
    pull_up: true
  - name: "Level Critical"
    gpio_pin: 15
    active_high: true
    pull_up: true
  - name: "Cartridge In Place"
    gpio_pin: 18
    active_high: true
    pull_up: true
```

- **In Simulation Mode**: GPIO pins are ignored, sensor names are used for the UI
- **In Real Sensor Mode**: GPIO pins are used to read actual hardware sensors
- **Mode switching**: Automatically handled at runtime, no restart required

## Testing

### Manual Testing Steps

1. **Start the application**
   ```bash
   python src/main.py
   ```

2. **Verify the UI elements**
   - Should see three tabs: Monitor, Service, Simulation
   - Should see purple "SIMULATION MODE" button at bottom
   - Should see green "START LOGGING" and red "STOP LOGGING" buttons

3. **Test simulation mode**
   - Verify mode button shows "SIMULATION MODE"
   - Go to Simulation tab
   - Check "Level Low" → Monitor tab should show level warning
   - Check "Cartridge In Place" → Monitor tab should show cartridge detected

4. **Test mode switching**
   - Click mode button to switch to "REAL SENSOR MODE"
   - Verify console shows mode change message
   - Click mode button again to return to "SIMULATION MODE"
   - Verify you cannot switch modes while logging is active

5. **Test logging**
   - Click "START LOGGING"
   - Verify mode button is disabled
   - Change sensor states in Simulation tab
   - Click "STOP LOGGING"
   - Verify mode button is re-enabled
   - Verify CSV file contains the changes

6. **Test real-time updates**
   - Keep Monitor tab visible
   - Switch to Simulation tab
   - Change sensors and observe immediate visual updates

### Automated Testing

Run the simulation sensor reader test:
```bash
python src/simulation_sensor_reader.py
```

## Comparison: Simulation vs. Real Mode

| Feature | Simulation Mode | Real Sensor Mode |
|---------|----------------|------------------|
| Hardware Required | No | Yes (Raspberry Pi + GPIO) |
| Sensor Control | Manual via UI | Automatic from GPIO |
| Simulation Tab | Always visible | Always visible |
| Mode Switching | ✓ At runtime | ✓ At runtime |
| CSV Logging | ✓ Works | ✓ Works |
| Monitor Tab | ✓ Works | ✓ Works |
| Service Tab | ✓ Works | ✓ Works |
| Use Case | Testing, Demo | Production |

## Benefits

### For Development
- Test without hardware setup
- Rapid iteration and debugging
- Simulate edge cases easily
- No GPIO cleanup issues

### For Demonstrations
- Show all sensor states
- Control timing precisely
- Demonstrate error conditions
- No hardware dependencies

### For Training
- Safe learning environment
- Hands-on practice
- Understand sensor behavior
- No risk of hardware damage

## Troubleshooting

### Mode button not working
- Ensure logging is stopped before switching modes
- Check console for error messages

### Sensor changes not taking effect
- Verify you're in the Simulation tab
- Check that checkboxes are responding to clicks
- Look for console messages confirming changes

### Application won't start
- Install dependencies: `pip install -r requirements.txt`
- Check Python version (3.8+)
- Verify PyQt6 is installed

## Future Enhancements

Potential additions to simulation mode:
- [ ] Save/load sensor state presets
- [ ] Automated sensor state sequences
- [ ] Time-based sensor patterns
- [ ] Export/import test scenarios
- [ ] Sensor state history playback

## Code Examples

### Setting a sensor programmatically

```python
from simulation_sensor_reader import SimulationSensorReader

# Create reader
reader = SimulationSensorReader(config)

# Set individual sensor
reader.set_sensor('Level Low', True)

# Set multiple sensors
reader.set_all_sensors({
    'Level Low': True,
    'Level Critical': False,
    'Cartridge In Place': True
})

# Read current states
states = reader.read_all()
print(states)
```

### Integrating with custom code

```python
from main import SensorMonitorApp

# Create app in simulation mode
app = SensorMonitorApp(simulation_mode=True)

# Initialize
app.initialize()

# Access simulation reader
if app.simulation_mode:
    app.sensor_reader.set_sensor('Level Low', True)
```

## Summary

Simulation mode provides a complete testing and demonstration environment without requiring physical hardware. It integrates seamlessly with all existing features while adding powerful manual control capabilities through an intuitive UI. **You can now switch between Simulation and Real Sensor modes at runtime** using the mode toggle button, making it easy to test and demonstrate without restarting the application.

**To get started:** `python src/main.py`

**Key Features:**
- ✅ Runtime mode switching via UI button
- ✅ Always starts in safe Simulation Mode
- ✅ Manual sensor control through Simulation tab
- ✅ Seamless transition between modes
- ✅ Mode switching disabled during logging for safety

---

*Made with Bob*