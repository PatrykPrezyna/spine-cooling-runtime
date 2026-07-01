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
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Edit `config.yaml` — sensor names, GPIO pins, stepper speeds, temperature thresholds
5. Run on a Raspberry Pi: `python src/main.py`
6. Run without hardware (PC dev): `python src/main.py --sim`
6. Run with sensor simulation: `python src/main.py --sim --test-ui`
7. Run unit tests: `python -m unittest discover tests -v`

Off-Pi mode uses fakes in `src/sim/`; tweak default sensor/temp values under `simulation:` in `config.yaml`.


## Project structure

**Entry point:** `src/main.py` — wires sensors, drivers, state machine, and GUI together.

| Module | Role |
|--------|------|
| `src/gui.py` | PyQt6 touchscreen UI (the main piece you can work on without a Pi) |
| `src/state_machine.py` | Operating flow: Init → Ready → Cooling → Pumping |
| `src/multi_sensor_reader.py` | Digital GPIO sensors (cartridge, level) |
| `src/thermocouple_reader.py` | I2C thermocouple readings |
| `src/ads1115_pressure_reader.py` | Pressure sensors via ADS1115 |
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