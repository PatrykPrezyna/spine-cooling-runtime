# Enhanced UI Documentation

## Overview

The enhanced UI provides a visual representation of the cartridge monitoring system with real-time sensor feedback and intuitive graphical display.

## Features

### Visual Components

1. **Gradient Background**
   - Smooth vertical gradient from light blue (#f8fbff) at top to deeper blue (#eaf2ff) at bottom
   - Professional medical device appearance

2. **Title Section**
   - Large, bold title: "Cartridge With 2 Levels + Presence Sensor"
   - Dark navy color (#0f172a) for high contrast
   - Centered at top of display

3. **Machine Slot**
   - Large rounded rectangle representing the device slot
   - Light blue fill (#dbeafe) with blue border (#3b82f6)
   - Labeled "Machine Slot" at top

4. **Cartridge Visualization**
   - White rounded rectangle inside machine slot
   - Only visible when cartridge is detected
   - Labeled "Cartridge" below

5. **Level Chambers**
   - Two vertical chambers showing liquid levels
   - **Left Chamber (Level 1)**: Light blue liquid (#38bdf8)
   - **Right Chamber (Level 2)**: Darker blue liquid (#0ea5e9)
   - Dashed horizontal lines indicating current level
   - Level labels above each line
   - Red warning indicators when levels are critical

6. **Sensor Module**
   - Green rounded rectangle on right side
   - Green indicator light when cartridge detected
   - Gray indicator when no cartridge
   - Labeled "Sensor"

7. **Detection Beam**
   - Visual beam from sensor to cartridge
   - Blue when cartridge detected
   - Gray when no cartridge
   - Arrowhead pointing to cartridge
   - Helper text: "Checks cartridge is in place"

8. **Status Indicator**
   - Bottom-right status circle
   - Green with checkmark: "Cartridge detected"
   - Red with X: "No cartridge"

### Control Buttons

- **START LOGGING**: Green button to begin CSV data logging
- **STOP LOGGING**: Red button to stop logging

## Sensor Mapping

The UI responds to three GPIO sensors:

| Sensor Name | GPIO Pin | Function | Visual Indicator |
|-------------|----------|----------|------------------|
| Level Low | 23 | Monitors Level 2 chamber | Red dot when triggered |
| Level Critical | 15 | Monitors Level 1 chamber | Red dot when triggered |
| Cartridge In Place | 18 | Detects cartridge presence | Cartridge visibility, beam color, status |

## Usage

### Running the Application

```bash
python src/main.py
```

### Sensor States

- **Cartridge Present**: 
  - Cartridge appears in machine slot
  - Detection beam turns blue
  - Status shows green checkmark
  - Level chambers are visible

- **Cartridge Absent**:
  - Cartridge disappears
  - Detection beam turns gray
  - Status shows red X
  - Machine slot remains empty

- **Level Warnings**:
  - Red indicator dots appear next to chambers when levels are critical
  - Helps identify which chamber needs attention

### Data Logging

1. Click **START LOGGING** to begin recording sensor data to CSV
2. Sensor display continues updating in real-time
3. Click **STOP LOGGING** to stop recording
4. CSV file saved in `data/csv/` directory with timestamp

## Technical Details

### Implementation

- **Framework**: PyQt6
- **Graphics**: QPainter with anti-aliasing
- **Update Rate**: 1 second (1 Hz)
- **Resolution**: 900x750 pixels (optimized for 7-inch display)

### Key Classes

- `CartridgeWidget`: Custom QWidget for graphical visualization
- `EnhancedSensorMonitorWindow`: Main window with controls
- `MultiSensorReader`: Handles GPIO sensor reading
- `CSVLogger`: Manages data logging

### Customization

Level heights can be adjusted in `CartridgeWidget`:

```python
self.level1_height = 0.6  # 60% full (0.0 to 1.0)
self.level2_height = 0.8  # 80% full (0.0 to 1.0)
```

Colors can be modified in the `_draw_*` methods of `CartridgeWidget`.

## File Structure

```
src/
├── main.py                    # Main application entry point
├── enhanced_ui.py             # Enhanced UI with visual cartridge
├── multi_sensor_reader.py     # Multi-sensor GPIO interface
├── csv_logger.py              # CSV data logging
└── simple_ui.py               # Original simple UI (backup)

config.yaml                    # Sensor configuration
data/csv/                      # CSV log files
```

## Configuration

Edit `config.yaml` to modify sensor pins and sample rate:

```yaml
sensors:
  - name: "Level Low"
    gpio_pin: 23
  - name: "Level Critical"
    gpio_pin: 15
  - name: "Cartridge In Place"
    gpio_pin: 18

sample_rate_hz: 1.0
```

## Troubleshooting

### Sensors Show "--"
- Check GPIO connections
- Verify sensor configuration in `config.yaml`
- Ensure RPi.GPIO is installed (or simulation mode is active)

### UI Not Updating
- Timer should start automatically on launch
- Check console for error messages
- Verify sensor reader initialization

### Cartridge Not Appearing
- Check "Cartridge In Place" sensor (GPIO 18)
- Verify sensor is properly connected
- Test with simulation mode

## Simulation Mode

When running on non-Raspberry Pi hardware, the application automatically enters simulation mode:

```bash
# Test UI without hardware
python src/enhanced_ui.py
```

This allows development and testing without physical sensors.

## Future Enhancements

Potential improvements for future phases:

- Animated liquid level changes
- Temperature display integration
- Historical level charts
- Alarm indicators for critical states
- Touch-optimized controls for 7-inch display
- State machine integration (initialization, precooling, operation modes)

## Support

For issues or questions, refer to the main project README.md or check the source code comments.