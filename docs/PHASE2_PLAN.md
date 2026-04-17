# Phase 2 Implementation Plan - Analog Sensor with History Display

## Goal
Expand Phase 1 prototype by adding an analog sensor (potentiometer) with real-time value display and historical data visualization.

## What's New in Phase 2

### 1. Analog Sensor (Potentiometer)
- Read analog values using MCP3008 ADC via SPI
- Convert to meaningful units (0-100% or voltage)
- Sample at configurable rate

### 2. Enhanced UI
- Display current analog value
- Show real-time chart of historical values
- Scrolling time-series graph
- Keep existing digital sensor display

### 3. Enhanced CSV Logging
- Add analog sensor column to CSV
- Log both digital and analog values
- Maintain timestamp precision

### 4. Historical Data Display
- Real-time line chart showing last N readings
- X-axis: Time
- Y-axis: Analog value (0-100%)
- Auto-scrolling as new data arrives

## Architecture Changes

```
┌─────────────────────────────────────────────────┐
│           Enhanced UI Window                    │
│  ┌───────────────────────────────────────────┐  │
│  │ Digital Sensor: HIGH                      │  │
│  │ Analog Sensor: 67.5%                      │  │
│  │ Last Update: 14:30:05                     │  │
│  ├───────────────────────────────────────────┤  │
│  │         Historical Chart                  │  │
│  │  100% ┤                    ╭──            │  │
│  │   75% ┤              ╭────╯              │  │
│  │   50% ┤        ╭────╯                     │  │
│  │   25% ┤   ╭───╯                           │  │
│  │    0% └───┴───┴───┴───┴───┴───┴───┴───   │  │
│  │       14:29  14:29:30  14:30  14:30:30   │  │
│  ├───────────────────────────────────────────┤  │
│  │ [START] [STOP] [CLEAR CHART]              │  │
│  │                                           │  │
│  │ Status: Monitoring active...              │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────▼─────────────────────┐
│        Main Application                   │
│  - Read digital sensor (GPIO)             │
│  - Read analog sensor (SPI/ADC)           │
│  - Update UI with current values          │
│  - Update chart with history              │
│  - Log to CSV                             │
└─────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐  ┌──▼─────┐  ┌───▼────────┐
│ GPIO Reader  │  │  SPI   │  │    CSV     │
│(Level Sensor)│  │ Reader │  │   Logger   │
│              │  │ (ADC)  │  │            │
└──────────────┘  └────────┘  └────────────┘
```

## Hardware Addition - MCP3008 ADC

### Why MCP3008?
- Raspberry Pi doesn't have built-in ADC
- MCP3008 provides 8 channels of 10-bit ADC
- SPI interface (easy to use)
- 3.3V compatible
- Inexpensive and widely available

### MCP3008 Connections

```
MCP3008 Pin    →  Raspberry Pi Pin
─────────────────────────────────────
VDD (Pin 16)   →  3.3V (Pin 1)
VREF (Pin 15)  →  3.3V (Pin 1)
AGND (Pin 14)  →  GND (Pin 6)
CLK (Pin 13)   →  GPIO 11/SCLK (Pin 23)
DOUT (Pin 12)  →  GPIO 9/MISO (Pin 21)
DIN (Pin 11)   →  GPIO 10/MOSI (Pin 19)
CS (Pin 10)    →  GPIO 8/CE0 (Pin 24)
DGND (Pin 9)   →  GND (Pin 6)

Potentiometer Connections:
─────────────────────────────────────
Pot Pin 1      →  GND
Pot Pin 2      →  MCP3008 CH0 (Pin 1)
Pot Pin 3      →  3.3V
```

### Wiring Diagram

```
                    Raspberry Pi 4
                    ┌──────────┐
         3.3V ──────┤ 1     2  ├──── 5V
                    ├──────────┤
                    │    ...   │
                    ├──────────┤
         GND  ──────┤ 6        │
                    ├──────────┤
                    │    ...   │
    GPIO10/MOSI ────┤19    20  ├──── GND
    GPIO9/MISO  ────┤21    22  │
    GPIO11/SCLK ────┤23    24  ├──── GPIO8/CE0
                    └──────────┘
                         │││└────────┐
                         │││         │
                    ┌────▼▼▼─────────▼──┐
                    │     MCP3008       │
                    │  ┌──────────────┐ │
         CH0 ───────┤1 │              │ │
                    │  │   10-bit     │ │
                    │  │     ADC      │ │
                    │  │              │ │
         VDD ───────┤16│              │ │
         VREF ──────┤15└──────────────┘ │
         AGND ──────┤14                 │
         CLK ───────┤13                 │
         DOUT ──────┤12                 │
         DIN ───────┤11                 │
         CS ────────┤10                 │
         DGND ──────┤9                  │
                    └───────────────────┘
                         │
                    ┌────▼────┐
                    │  10kΩ   │
                    │  Pot    │
                    │         │
         GND ───────┤1      3 ├──── 3.3V
                    │    2    │
                    └─────────┘
```

## Updated File Structure

```
spine-cooling-runtime/
├── src/
│   ├── __init__.py
│   ├── main.py              # Updated: integrate analog sensor
│   ├── sensor_reader.py     # Existing: digital sensor
│   ├── analog_reader.py     # NEW: analog sensor via MCP3008
│   ├── csv_logger.py        # Updated: add analog column
│   ├── simple_ui.py         # Updated: add chart widget
│   └── chart_widget.py      # NEW: historical data chart
├── data/
│   └── csv/                 # CSV log files
├── config.yaml              # Updated: add analog sensor config
├── requirements.txt         # Updated: add chart library
└── README.md
```

## Implementation Steps

### Step 1: Update Requirements (5 minutes)

Add to `requirements.txt`:
```
PyQt6
PyYAML
RPi.GPIO
spidev
adafruit-circuitpython-mcp3xxx  # For MCP3008
pyqtgraph                        # For real-time charting
```

Install:
```bash
pip install adafruit-circuitpython-mcp3xxx pyqtgraph
```

### Step 2: Update Configuration (10 minutes)

Update `config.yaml`:
```yaml
# Digital sensor (from Phase 1)
digital_sensor:
  gpio_pin: 23
  active_high: true
  pull_up: true
  sample_rate_hz: 1.0

# NEW: Analog sensor configuration
analog_sensor:
  enabled: true
  adc_channel: 0              # MCP3008 channel (0-7)
  sample_rate_hz: 10.0        # Sample 10 times per second
  voltage_reference: 3.3      # Reference voltage
  conversion:
    type: "percentage"        # "percentage", "voltage", or "raw"
    min_value: 0.0
    max_value: 100.0
  smoothing:
    enabled: true
    window_size: 5            # Moving average of 5 samples

# SPI configuration for MCP3008
spi:
  bus: 0
  device: 0
  max_speed_hz: 1000000       # 1 MHz

# Updated logging
logging:
  csv_directory: "data/csv"
  filename_format: "sensor_log_%Y%m%d_%H%M%S.csv"
  fields:
    - timestamp
    - digital_sensor
    - analog_value
    - analog_percentage

# Updated UI
ui:
  window_width: 600           # Wider for chart
  window_height: 500          # Taller for chart
  update_interval_ms: 100
  chart:
    history_seconds: 60       # Show last 60 seconds
    max_points: 600           # Maximum data points to display
    line_color: "#007BFF"
    line_width: 2
    background_color: "#FFFFFF"
    grid_enabled: true
```

### Step 3: Implement Analog Reader (45 minutes)

Create `src/analog_reader.py`:

**Key Features:**
- Initialize MCP3008 via SPI
- Read analog value from specified channel
- Convert to percentage/voltage
- Apply smoothing (moving average)
- Handle errors gracefully

**Main Methods:**
```python
class AnalogReader:
    def __init__(self, config):
        """Initialize MCP3008 ADC"""
        
    def read_raw(self) -> int:
        """Read raw ADC value (0-1023)"""
        
    def read_voltage(self) -> float:
        """Read and convert to voltage"""
        
    def read_percentage(self) -> float:
        """Read and convert to percentage (0-100)"""
        
    def read_smoothed(self) -> float:
        """Read with moving average smoothing"""
        
    def cleanup(self):
        """Cleanup SPI resources"""
```

### Step 4: Implement Chart Widget (60 minutes)

Create `src/chart_widget.py`:

**Key Features:**
- Real-time line chart using pyqtgraph
- Auto-scrolling X-axis (time)
- Configurable Y-axis range
- Grid lines for readability
- Efficient data management (circular buffer)

**Main Methods:**
```python
class HistoricalChartWidget(QWidget):
    def __init__(self, config):
        """Initialize chart widget"""
        
    def add_data_point(self, timestamp: float, value: float):
        """Add new data point to chart"""
        
    def clear_chart(self):
        """Clear all historical data"""
        
    def update_chart(self):
        """Redraw chart with current data"""
        
    def set_y_range(self, min_val: float, max_val: float):
        """Set Y-axis range"""
```

### Step 5: Update CSV Logger (20 minutes)

Update `src/csv_logger.py`:

**Changes:**
- Add analog_value and analog_percentage columns
- Update CSV header
- Modify log entry format

**New CSV Format:**
```csv
timestamp,digital_sensor,analog_value,analog_percentage
2026-04-17T14:30:00.123Z,1,2.15,65.2
2026-04-17T14:30:00.223Z,1,2.18,66.1
2026-04-17T14:30:00.323Z,0,2.20,66.7
```

### Step 6: Update UI (60 minutes)

Update `src/simple_ui.py`:

**New Layout:**
```
┌─────────────────────────────────────┐
│  Sensor Monitor                     │
├─────────────────────────────────────┤
│  Digital Sensor: HIGH               │
│  Analog Sensor: 67.5% (2.23V)       │
│  Last Update: 14:30:05              │
├─────────────────────────────────────┤
│                                     │
│     [Historical Chart Area]         │
│                                     │
│                                     │
├─────────────────────────────────────┤
│  [START] [STOP] [CLEAR CHART]       │
│                                     │
│  Status: Monitoring active...       │
└─────────────────────────────────────┘
```

**New Features:**
- Display analog value with units
- Embed chart widget
- Add "Clear Chart" button
- Update both sensors in real-time

### Step 7: Update Main Application (30 minutes)

Update `src/main.py`:

**Changes:**
- Initialize analog reader
- Read both sensors in main loop
- Update UI with both values
- Add data points to chart
- Log both values to CSV

**Main Loop:**
```python
def update(self):
    """Main update loop"""
    # Read digital sensor
    digital_state = self.digital_reader.read()
    
    # Read analog sensor
    analog_value = self.analog_reader.read_smoothed()
    analog_percent = self.analog_reader.read_percentage()
    
    # Update UI
    self.ui.update_digital(digital_state)
    self.ui.update_analog(analog_value, analog_percent)
    
    # Update chart
    current_time = time.time()
    self.ui.chart.add_data_point(current_time, analog_percent)
    
    # Log to CSV
    self.logger.log(digital_state, analog_value, analog_percent)
```

### Step 8: Testing (45 minutes)

**Test Checklist:**
- [ ] MCP3008 reads analog values correctly
- [ ] Potentiometer changes reflected in readings
- [ ] Analog value displays in UI
- [ ] Chart updates in real-time
- [ ] Chart scrolls as time progresses
- [ ] Clear chart button works
- [ ] CSV includes analog values
- [ ] Both sensors log simultaneously
- [ ] Application handles errors gracefully
- [ ] Cleanup happens on exit

## Expected Output

### Enhanced UI Window

```
┌──────────────────────────────────────────────┐
│  Sensor Monitor                              │
├──────────────────────────────────────────────┤
│  Digital Sensor: HIGH                        │
│  Analog Sensor: 67.5% (2.23V)                │
│  Last Update: 2026-04-17 14:30:05            │
├──────────────────────────────────────────────┤
│  Historical Data (Last 60 seconds)           │
│                                              │
│  100% ┤                              ╭──     │
│   75% ┤                        ╭────╯        │
│   50% ┤                  ╭────╯              │
│   25% ┤            ╭────╯                    │
│    0% └────────────┴────────────────────     │
│       14:29:00  14:29:30  14:30:00           │
│                                              │
├──────────────────────────────────────────────┤
│  [START]  [STOP]  [CLEAR CHART]              │
│                                              │
│  Status: Monitoring active...                │
└──────────────────────────────────────────────┘
```

### Enhanced CSV Log

```csv
timestamp,digital_sensor,analog_value,analog_percentage
2026-04-17T14:30:00.123Z,1,2.15,65.2
2026-04-17T14:30:00.223Z,1,2.18,66.1
2026-04-17T14:30:00.323Z,0,2.20,66.7
2026-04-17T14:30:00.423Z,0,2.22,67.3
2026-04-17T14:30:00.523Z,0,2.23,67.6
```

## Testing Procedure

### 1. Hardware Test
```bash
# Test MCP3008 reading
python -c "
import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = digitalio.DigitalInOut(board.CE0)
mcp = MCP.MCP3008(spi, cs)
chan = AnalogIn(mcp, MCP.P0)

print(f'Raw: {chan.value}, Voltage: {chan.voltage}V')
"
```

### 2. Potentiometer Test
- Turn potentiometer fully counter-clockwise → should read ~0%
- Turn potentiometer to middle → should read ~50%
- Turn potentiometer fully clockwise → should read ~100%

### 3. Chart Test
- Start monitoring
- Slowly turn potentiometer
- Verify chart updates smoothly
- Verify chart scrolls after 60 seconds
- Click "Clear Chart" → chart should reset

### 4. Logging Test
- Start monitoring
- Change potentiometer position
- Stop monitoring
- Check CSV file has both sensor columns
- Verify timestamps are accurate

## Success Criteria

✅ MCP3008 ADC reads analog values
✅ Potentiometer changes reflected in readings
✅ UI displays both digital and analog sensors
✅ Real-time chart shows historical data
✅ Chart auto-scrolls with time
✅ Clear chart button works
✅ CSV logs both sensor types
✅ Application runs smoothly
✅ No memory leaks in chart
✅ Proper cleanup on exit

## Performance Considerations

### Chart Performance
- Limit data points to prevent slowdown
- Use circular buffer for efficient memory
- Update chart at reasonable rate (10 Hz)
- Consider downsampling for long histories

### Memory Management
- Clear old data points beyond history window
- Avoid memory leaks in chart updates
- Monitor memory usage during long runs

## Estimated Time

- Update requirements: 5 minutes
- Update configuration: 10 minutes
- Implement analog reader: 45 minutes
- Implement chart widget: 60 minutes
- Update CSV logger: 20 minutes
- Update UI: 60 minutes
- Update main application: 30 minutes
- Testing: 45 minutes

**Total: ~4.5 hours**

## Hardware Shopping List

- MCP3008 ADC chip (~$3-5)
- 10kΩ potentiometer (~$1-2)
- Breadboard and jumper wires (~$5-10)
- Optional: Breakout board for MCP3008 (~$5)

## Next Steps After Phase 2

Once Phase 2 is working:
1. Add second analog sensor (use CH1 on MCP3008)
2. Add multiple charts (one per sensor)
3. Add data export functionality
4. Add chart zoom/pan controls
5. Move toward full system (thermocouples, state machine, etc.)

## Troubleshooting Tips

### MCP3008 Not Reading
- Check SPI is enabled: `ls /dev/spidev*`
- Verify wiring connections
- Check 3.3V power supply
- Test with simple read script

### Chart Not Updating
- Check update timer is running
- Verify data points are being added
- Check pyqtgraph installation
- Monitor console for errors

### Noisy Readings
- Add capacitor across potentiometer (0.1µF)
- Increase smoothing window size
- Check for loose connections
- Verify ground connections

### CSV Not Logging Analog Values
- Check column headers match
- Verify analog reader is initialized
- Check file permissions
- Monitor for exceptions in logger