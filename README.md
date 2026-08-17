# Spine Cooling - Medical Device Prototype

Raspberry Pi 4B application for medical device with visual UI, sensor reading, and data logging.


## Raspberry Pi setup (can be further automated)

1. Install Raspberry Pi OS and connect the device to the network via Wi-Fi or Ethernet.
   1.1 We recoment to use the imager: https://www.raspberrypi.com/software/ 
   1.2 Select the newest OS (for now Debian 13 64bit)
   1.3 Hostname spine (refere to the keypass for password)
   1.4 Enable SHH with passwor and Raspebbry pi connect 
2. Connect to the Pi using a keyboard and display, or remotely via SSH (for example, with PuTTY on Windows)
   2.1 check 
   2.2 https://connect.raspberrypi.com/devices
3. Enable interfaces: SSH, SPI, I2C, ...:
   - Use `sudo raspi-config` and enable SSH, I2C under `Interface Options` > `I2C` > `Enable`. 
   Optional check: `ls /dev/i2c-1`
   - enable spi `sudo dtparam spi=on  `. Optional check: `sudo tee -a /boot/config.txt`
   - `sudo reboot`
4. Install pigpio (Debian/Raspberry Pi)
   - `sudo apt update` and `sudo apt install -y pigpio python3-pigpio`
   If `pigpiod` is not available from apt on your image, build from source:

   ```bash
   sudo apt install -y git make gcc
   cd /tmp
   git clone https://github.com/joan2937/pigpio.git
   cd pigpio
   make
   sudo make install
   sudo ldconfig
   ```
   - Enable and start the pigpio daemon `sudo systemctl enable pigpiod` and `sudo systemctl start pigpiod`  
      Or start manually for the current session: `sudo pigpiod`. Optional check `pigs t`
5. Follow the installation instruction
   

## Installation

1. Clone or download this repository https://github.com/PatrykPrezyna/spine-cooling-runtime.git
2. Create a virtual environment (on Windows: use python.org or the Microsoft Store Python — **not** Miniconda/Anaconda, which breaks PyQt6):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Pi-only packages (`RPi.GPIO`, `pigpio`, Blinka, …) are gated with environment markers, so the same command works for Windows/macOS simulation and for the Raspberry Pi.
4. Edit `config.yaml` — sensor names, GPIO pins, stepper speeds, temperature thresholds
5. Run on a Raspberry Pi: `python src/main.py`
6. Run without hardware (PC dev): `python src/main.py --sim`
7. Run with sensor simulation: `python src/main.py --sim --test-ui`
8. Run unit tests: `python -m unittest discover tests -v`

Off-Pi mode uses fakes in `src/sim/`; tweak default sensor/temp values under `simulation:` in `config.yaml`.

## Download data

1 Install Filezilla
2 check ip adress `ifconfig`
3 log in using port 22
4 Go to spine-cooling-runtime/data/csv and doube cloick selected file

### The two log files

Each run writes two kinds of CSV, because temperature and pressure are sampled
at different rates. Eight thermistors on two ADS1115s take ~60 ms for a full
sweep, so temperatures cannot go much above ~16 Hz; the pressure chips run at
860 SPS specifically to sustain 100 Hz.

| File | Rate | Contents |
|------|------|----------|
| `data/csv/sensor_log_<session>.csv` | `ui.update_interval_ms` (100 ms → 10 Hz) | Temperatures, setpoint, pump, compressor, pressures |
| `data/csv/pressure/pressure_log_<session>_runNN.csv` | `pressure_sensors.capture_rate_hz` (100 Hz) | Pressures + pump setpoint only |

Both names share one `<session>` stamp taken at startup, so a pressure file
always pairs with the session log of the same run. `NN` starts at `01` and
increments each time pressure capture is toggled off and on again, so one
session can hold several captures.

High-rate capture starts automatically with the session; set
`logging.pressure_autostart: false` to require the Service 2 toggle instead.
The toggle still works either way — turning it off closes the current run, and
turning it back on opens the next `runNN`.

To combine them, join on the timestamp — the fast file carries the detail and
the session file supplies the temperatures around it:

```python
import pandas as pd

session = pd.read_csv("sensor_log_20260817_170941.csv", parse_dates=["timestamp"])
fast = pd.read_csv("pressure/pressure_log_20260817_170941_run01.csv", parse_dates=["timestamp"])
merged = pd.merge_asof(fast, session, on="timestamp", direction="nearest")
```

## Project structure

**Entry point:** `src/main.py` — wires sensors, drivers, state machine, and GUI together.

| Module | Role |
|--------|------|
| `src/gui.py` | PyQt6 touchscreen UI (the main piece you can work on without a Pi) |
| `src/state_machine.py` | Operating flow: Init → Ready → Cooling → Pumping |
| `src/multi_sensor_reader.py` | Digital GPIO sensors (cartridge, level) |
| `src/thermocouple_reader.py` | I2C thermocouple readings |
| `src/ads1115_thermistor_reader.py` | Thermistor temps via ADS1115 (0x48 / 0x49, up to 8) |
| `src/thermistor_conversion.py` | Shared NTC V→R→°C using `data/calibration/Thermistor_MA300TA103C.csv` |
| `src/ads1115_pressure_reader.py` | Differential pressure via 3rd+4th ADS1115 (addrs 74/75, up to 4) |
| `src/stepper_driver.py` | Peristaltic pump stepper motor |
| `src/csv_logger.py` | CSV session logging |
| `src/sim/` | In-memory hardware fakes (used with `--sim`) |
| `src/hardware_factory.py` | Picks real vs simulated drivers at startup |
| `config.yaml` | Hardware mapping and runtime settings |

**`simple_examples/`** — small standalone scripts to test one subsystem at a time (GPIO, stepper, thermocouples, UART).

**`tests/`** — unit tests (state machine, temperature calibration, etc.).

## Additional info
Stepper Motor:
sources: https://www.instructables.com/Raspberry-Pi-Python-and-a-TB6600-Stepper-Motor-Dri/

run on startup instruction:(is not working yet)
https://www.instructables.com/Raspberry-Pi-Launch-Python-script-on-startup/
sudo apt-get update
sudo apt-get install libxcb-cursor0 libxcb-xinerama0 libxcb-shape0
sudo apt-get install libqt6gui6 libqt6core6 qt6-qpa-plugins