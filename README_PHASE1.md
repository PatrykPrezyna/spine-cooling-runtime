# Phase 1: Level Sensor Monitor

Simple sensor monitoring application with UI and CSV logging.

## Features

- ✅ Read digital level sensor via GPIO
- ✅ Real-time UI display
- ✅ CSV data logging with timestamps
- ✅ Start/Stop controls
- ✅ Simulation mode for development without hardware

## Hardware Requirements

- Raspberry Pi 4 Model B
- 1x Digital level sensor (or button for testing)
- Jumper wires

## GPIO Connection

```
Raspberry Pi GPIO 23 (Pin 16) → Sensor Signal
Raspberry Pi 3.3V (Pin 1)     → Sensor VCC (if needed)
Raspberry Pi GND (Pin 6)      → Sensor GND
```

## Software Requirements

```bash
# Install Python dependencies
pip install PyQt6 PyYAML RPi.GPIO
```

## Configuration

Edit `config.yaml` to adjust settings:

```yaml
sensor:
  gpio_pin: 23              # Change GPIO pin if needed
  active_high: true         # Sensor logic level
  pull_up: true             # Enable pull-up resistor
  sample_rate_hz: 1.0       # Sampling frequency

logging:
  csv_directory: "data/csv"
  filename_format: "sensor_log_%Y%m%d_%H%M%S.csv"

ui:
  window_width: 400
  window_height: 300
  update_interval_ms: 100
```

## Running the Application

### On Raspberry Pi (with hardware)

```bash
# Navigate to project directory
cd spine-cooling-runtime

# Run the application
python src/main.py
```

### On Development Machine (simulation mode)

The application automatically detects if RPi.GPIO is not available and runs in simulation mode:

```bash
python src/main.py
```

In simulation mode, the sensor will toggle between HIGH and LOW every few seconds.

## Using the Application

1. **Start Monitoring**
   - Click the green "START" button
   - Sensor readings will begin
   - Data will be logged to CSV file

2. **Monitor Sensor**
   - Watch the "Sensor Status" display
   - HIGH = Sensor active (green)
   - LOW = Sensor inactive (red)
   - Timestamp shows last update

3. **Stop Monitoring**
   - Click the red "STOP" button
   - Logging will stop
   - CSV file will be saved

4. **Close Application**
   - Close the window
   - Monitoring will stop automatically
   - GPIO will be cleaned up

## CSV Log Files

Log files are saved in `data/csv/` with format:

```csv
timestamp,sensor_state
2026-04-17T14:30:00.123456,1
2026-04-17T14:30:01.125678,1
2026-04-17T14:30:02.127890,0
```

- `timestamp`: ISO 8601 format
- `sensor_state`: 1 (HIGH) or 0 (LOW)

## Testing Individual Components

### Test Sensor Reader

```bash
python src/sensor_reader.py
```

### Test CSV Logger

```bash
python src/csv_logger.py
```

### Test UI

```bash
python src/simple_ui.py
```

## Troubleshooting

### GPIO Permission Error

```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER

# Reboot
sudo reboot
```

### SPI/GPIO Not Available

The application will run in simulation mode automatically.

### UI Not Displaying

Make sure PyQt6 is installed:
```bash
pip install PyQt6
```

For Raspberry Pi, you may need:
```bash
sudo apt-get install python3-pyqt6
```

### CSV File Not Created

Check that `data/csv/` directory exists:
```bash
mkdir -p data/csv
```

## Project Structure

```
spine-cooling-runtime/
├── src/
│   ├── __init__.py
│   ├── main.py              # Main application
│   ├── sensor_reader.py     # GPIO sensor reading
│   ├── csv_logger.py        # CSV logging
│   └── simple_ui.py         # PyQt6 UI
├── data/
│   └── csv/                 # Log files stored here
├── config.yaml              # Configuration file
├── requirements.txt         # Python dependencies
└── README_PHASE1.md         # This file
```

## Next Steps

After Phase 1 is working:
- **Phase 2**: Add analog sensor (potentiometer) with historical chart
- **Phase 3**: Add state machine
- **Phase 4**: Add thermocouples
- **Phase 5**: Add compressor and motor control

## Support

For issues or questions, refer to:
- `docs/PHASE1_PLAN.md` - Detailed implementation plan
- `docs/ARCHITECTURE.md` - System architecture
- `docs/HARDWARE_SETUP.md` - Hardware wiring guide