# Simulation Mode - Manual Sensor Control

## Overview

The application now includes a **Simulation Mode** that allows you to manually control all sensor states through a graphical interface. This is perfect for:
- Testing the application without physical hardware
- Demonstrating sensor behavior
- Development and debugging
- Training and demonstrations

## Features

### 1. Manual Sensor Control
- Control each sensor individually via checkboxes
- Set all sensors HIGH or LOW with one click
- Real-time visual feedback in the Monitor tab
- Changes take effect immediately

### 2. Simulation Tab
A dedicated tab in the UI provides:
- Individual checkboxes for each sensor
- "Set All HIGH" button
- "Set All LOW" button
- Visual indicators (green for HIGH, red for LOW)
- Information panel explaining simulation mode

### 3. Full Integration
- Works with all existing features (Monitor tab, Service tab)
- CSV logging still functions normally
- All visualizations update in real-time
- No hardware required

## How to Use

### Starting in Simulation Mode

Run the application with the `--sim` flag:

```bash
python src/main.py --sim
```

Alternative flags also work:
```bash
python src/main.py --simulation
python src/main.py -s
```

### Starting in Real Sensor Mode

Run without any flags to use real GPIO sensors:

```bash
python src/main.py
```

### Using the Simulation Tab

1. **Start the application in simulation mode**
   ```bash
   python src/main.py --sim
   ```

2. **Navigate to the Simulation tab**
   - Click on the "Simulation" tab in the UI

3. **Control individual sensors**
   - Check/uncheck boxes to set sensors HIGH/LOW
   - Changes apply immediately

4. **Use quick controls**
   - Click "Set All HIGH" to activate all sensors
   - Click "Set All LOW" to deactivate all sensors

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
- Command-line flag parsing (`--sim`)
- Conditional initialization (simulation vs. real)
- Callback integration for manual sensor changes
- Mode indicator in console output

### Integration Flow

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

In simulation mode, the GPIO pins are ignored, but sensor names are used for the UI.

## Testing

### Manual Testing Steps

1. **Start in simulation mode**
   ```bash
   python src/main.py --sim
   ```

2. **Verify the Simulation tab appears**
   - Should see three tabs: Monitor, Service, Simulation

3. **Test individual sensor control**
   - Go to Simulation tab
   - Check "Level Low" → Monitor tab should show level warning
   - Check "Cartridge In Place" → Monitor tab should show cartridge detected

4. **Test quick controls**
   - Click "Set All HIGH" → All sensors should activate
   - Click "Set All LOW" → All sensors should deactivate

5. **Test logging**
   - Click "START LOGGING"
   - Change sensor states
   - Click "STOP LOGGING"
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
| Simulation Tab | Visible | Hidden |
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

### Simulation tab not appearing
- Ensure you started with `--sim` flag
- Check console output for "SIMULATION MODE" message

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

Simulation mode provides a complete testing and demonstration environment without requiring physical hardware. It integrates seamlessly with all existing features while adding powerful manual control capabilities through an intuitive UI.

**To get started:** `python src/main.py --sim`

---

*Made with Bob*