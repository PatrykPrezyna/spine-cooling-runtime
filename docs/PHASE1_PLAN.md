# Phase 1 Implementation Plan - Minimal Viable Prototype

## Goal
Create a minimal working prototype to test the basic system before full implementation.

## Scope - What We'll Build

### 1. Single Level Sensor
- Read one digital level sensor via GPIO
- Display sensor state in real-time
- Log state changes

### 2. Simple UI
- Small window (not fullscreen)
- Display sensor status (ON/OFF or HIGH/LOW)
- Display timestamp of last reading
- Simple start/stop button
- Status message area

### 3. CSV Data Logging
- Log sensor readings with timestamps
- Simple CSV format: `timestamp,sensor_state`
- Save to `data/csv/` directory

## What We're NOT Building Yet
- ❌ State machine (will add later)
- ❌ Thermocouples (will add later)
- ❌ Compressor control (will add later)
- ❌ Stepper motor (will add later)
- ❌ Complex configuration (will add later)
- ❌ Multiple sensors (will add later)

## Simplified Architecture

```
┌─────────────────────────────┐
│      Simple UI Window       │
│  ┌───────────────────────┐  │
│  │ Sensor Status: HIGH   │  │
│  │ Last Update: 14:30:05 │  │
│  │                       │  │
│  │ [START] [STOP]        │  │
│  │                       │  │
│  │ Status: Running...    │  │
│  └───────────────────────┘  │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│     Main Application        │
│  - Read sensor via GPIO     │
│  - Update UI                │
│  - Log to CSV               │
└──────────────┬──────────────┘
               │
        ┌──────┴──────┐
        │             │
┌───────▼──────┐  ┌──▼─────┐
│ GPIO Reader  │  │  CSV   │
│ (Level Sensor)│  │ Logger │
└──────────────┘  └────────┘
```

## File Structure (Simplified)

```
spine-cooling-runtime/
├── src/
│   ├── __init__.py
│   ├── main.py              # Main application entry
│   ├── sensor_reader.py     # GPIO sensor reading
│   ├── csv_logger.py        # Simple CSV logging
│   └── simple_ui.py         # PyQt6 UI
├── data/
│   └── csv/                 # CSV log files
├── config.yaml              # Simple config file
├── requirements.txt
└── README.md
```

## Implementation Steps

### Step 1: Setup (15 minutes)
```bash
# Create directories
mkdir -p src data/csv

# Create empty files
touch src/__init__.py
touch src/main.py
touch src/sensor_reader.py
touch src/csv_logger.py
touch src/simple_ui.py
touch config.yaml
```

### Step 2: Configuration File (5 minutes)
Create `config.yaml`:
```yaml
# Simple configuration for Phase 1
sensor:
  gpio_pin: 23              # GPIO pin for level sensor
  active_high: true         # true if sensor is HIGH when triggered
  pull_up: true             # Enable internal pull-up resistor
  sample_rate_hz: 1.0       # Read sensor once per second

logging:
  csv_directory: "data/csv"
  filename_format: "sensor_log_%Y%m%d_%H%M%S.csv"

ui:
  window_width: 400
  window_height: 300
  update_interval_ms: 100   # Update UI every 100ms
```

### Step 3: Sensor Reader (30 minutes)
Implement `src/sensor_reader.py`:
- Initialize GPIO pin
- Read sensor state
- Handle cleanup

### Step 4: CSV Logger (20 minutes)
Implement `src/csv_logger.py`:
- Create CSV file with headers
- Write timestamped entries
- Handle file operations

### Step 5: Simple UI (45 minutes)
Implement `src/simple_ui.py`:
- Create main window
- Display sensor status
- Add start/stop buttons
- Show status messages

### Step 6: Main Application (30 minutes)
Implement `src/main.py`:
- Load configuration
- Initialize components
- Connect UI to sensor reader
- Start application loop

### Step 7: Testing (30 minutes)
- Test sensor reading
- Test UI updates
- Test CSV logging
- Test start/stop functionality

## Expected Output

### UI Window
```
┌─────────────────────────────────┐
│  Level Sensor Monitor           │
├─────────────────────────────────┤
│                                 │
│  Sensor Status: HIGH            │
│  Last Update: 2026-04-17 14:30:05│
│                                 │
│  [START]  [STOP]                │
│                                 │
│  Status: Monitoring active...   │
│                                 │
└─────────────────────────────────┘
```

### CSV Log File
```csv
timestamp,sensor_state
2026-04-17T14:30:00.123Z,1
2026-04-17T14:30:01.125Z,1
2026-04-17T14:30:02.127Z,0
2026-04-17T14:30:03.129Z,0
```

## Testing Checklist

- [ ] GPIO pin reads correctly
- [ ] Sensor state displays in UI
- [ ] UI updates in real-time
- [ ] Start button begins monitoring
- [ ] Stop button stops monitoring
- [ ] CSV file is created
- [ ] CSV entries are timestamped
- [ ] Application closes cleanly
- [ ] GPIO is cleaned up on exit

## Success Criteria

✅ Sensor state is read from GPIO
✅ UI displays current sensor state
✅ UI updates every 100ms
✅ Data is logged to CSV file
✅ Start/Stop buttons work
✅ Application runs without errors
✅ GPIO cleanup happens on exit

## Next Steps After Phase 1

Once this minimal prototype is working:
1. Add second level sensor
2. Add simple state machine (IDLE, RUNNING, STOPPED)
3. Add one thermocouple
4. Gradually add more features from full design

## Estimated Time

- Setup: 15 minutes
- Configuration: 5 minutes
- Sensor Reader: 30 minutes
- CSV Logger: 20 minutes
- Simple UI: 45 minutes
- Main Application: 30 minutes
- Testing: 30 minutes

**Total: ~3 hours**

## Hardware Requirements for Phase 1

- Raspberry Pi 4 B
- 1x Digital level sensor (or any digital sensor/button)
- Jumper wires
- Optional: Display (can also run via SSH with X11 forwarding)

## GPIO Connection for Phase 1

```
Raspberry Pi GPIO 23 (Pin 16) ──→ Sensor Signal
Raspberry Pi 3.3V (Pin 1)     ──→ Sensor VCC (if needed)
Raspberry Pi GND (Pin 6)      ──→ Sensor GND
```

## Code Implementation Order

1. **sensor_reader.py** - Core functionality
2. **csv_logger.py** - Data persistence
3. **simple_ui.py** - User interface
4. **main.py** - Application integration
5. **config.yaml** - Configuration

This order ensures each component can be tested independently before integration.