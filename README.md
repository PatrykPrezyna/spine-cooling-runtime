# Spine Cooling Medical Device Prototype

Raspberry Pi 4B application for medical device monitoring with visual UI, sensor reading, and data logging.

## Current Implementation: Phase 1

✅ **Multi-Sensor Monitoring System**
- 3 digital GPIO sensors (Level Low, Level Critical, Cartridge In Place)
- Real-time sensor reading at 1 Hz
- Enhanced visual UI with cartridge representation
- CSV data logging with timestamps

See [ENHANCED_UI_README.md](ENHANCED_UI_README.md) for detailed UI documentation.

## Raspberry Pi setup

1. Install Raspberry Pi OS and connect the device to the network via Wi-Fi or Ethernet.
2. Enable SSH access:
   - Use `sudo raspi-config` and enable SSH under `Interfacing Options`.
   - Alternatively, create an empty file named `ssh` in the boot partition before first boot.
3. Connect to the Pi using a keyboard and display, or remotely via SSH (for example, with PuTTY on Windows).


## Enable SPI
1. enable spi echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
2. sudo reboot


## Installation

1. Clone or download this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```


3. Configure sensors in `config.yaml`:
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

4. Run the application:
   ```bash
   python src/main.py
   ```

## Features

### Enhanced Visual UI
- **Cartridge Visualization**: Real-time graphical representation of cartridge and liquid levels
- **Sensor Status**: Visual indicators for all three sensors
- **Detection Beam**: Animated beam showing cartridge detection
- **Level Chambers**: Two liquid level displays with warning indicators
- **Status Display**: Clear cartridge presence indication

### Data Logging
- CSV logging with timestamps
- User-controlled START/STOP
- Continuous sensor display (independent of logging)
- Files saved to `data/csv/` directory

### Hardware Support
- Raspberry Pi 4B GPIO interface
- Simulation mode for development without hardware
- Configurable sensor pins via YAML

## Hardware Connections

| Sensor | GPIO Pin | Function |
|--------|----------|----------|
| Level Low | 23 | Monitors Level 2 chamber |
| Level Critical | 15 | Monitors Level 1 chamber |
| Cartridge In Place | 18 | Detects cartridge presence |

Connect sensors between GPIO pin and GND. Sensors should pull pin LOW when triggered.

## Project Structure

```
spine-cooling-runtime/
├── src/
│   ├── main.py                    # Main application
│   ├── enhanced_ui.py             # Visual UI with cartridge display
│   ├── multi_sensor_reader.py     # GPIO sensor interface
│   ├── csv_logger.py              # Data logging
│   └── simple_ui.py               # Original simple UI (backup)
├── data/
│   └── csv/                       # CSV log files
├── config.yaml                    # Sensor configuration
├── requirements.txt               # Python dependencies
├── README.md                      # This file
└── ENHANCED_UI_README.md          # Detailed UI documentation
```

## Usage

1. **Start Application**: Run `python src/main.py`
2. **Monitor Sensors**: Display updates automatically every second
3. **Start Logging**: Click "START LOGGING" button
4. **Stop Logging**: Click "STOP LOGGING" button
5. **View Data**: Check `data/csv/` directory for log files

## Development

### Testing Without Hardware

The application includes simulation mode for development:

```bash
# Test UI independently
python src/enhanced_ui.py
```

### Configuration

Edit `config.yaml` to modify:
- Sensor GPIO pins
- Sensor names
- Sample rate

## Future Phases

### Phase 2: Analog Sensors
- Potentiometer via MCP3008 ADC
- Historical data charts
- Temperature monitoring

### Phase 3+: Full System
- State machine (initialization, precooling, operation, error modes)
- Thermocouple integration (MAX31855)
- UART compressor control
- Stepper motor control
- Database integration
- Advanced error handling

## Troubleshooting

### Sensors Not Reading
- Verify GPIO connections
- Check `config.yaml` sensor pins
- Ensure RPi.GPIO is installed
- Try simulation mode for testing

### UI Not Updating
- Check console for errors
- Verify timer is running
- Restart application

### CSV Not Logging
- Click "START LOGGING" button
- Check `data/csv/` directory exists
- Verify write permissions

## Documentation

- [Enhanced UI Documentation](ENHANCED_UI_README.md) - Detailed UI features and customization
- [Requirements](requirements.txt) - Python package dependencies

## License

Medical device prototype - Internal use only

#TODO:

1) pump microsteps
2) service 2, simulation 2
3) ask cpude to improve the first page
4) tehmocouples
6) errors table
5) Uart simulation
6) validation plan 

Stepper Motor:
sources: https://www.instructables.com/Raspberry-Pi-Python-and-a-TB6600-Stepper-Motor-Dri/
