# Spine Cooling Runtime

Raspberry Pi 4 application for the spine-cooling prototype: touchscreen UI, sensors, peristaltic pump, compressor, and session logs.

## Repository map

```text
config.yaml            pins, sensor names, thresholds, simulation defaults
src/main.py            start the device
src/                   application code (table below)
tests/                 automatic tests
examples/              Pi bench scripts for one subsystem (see examples/README.md)
tools/                 log viewer, plots, operator-guide builder
docs/                  guides, verification, faults, state machine
data/calibration/      thermistor resistance tables loaded at runtime
```

`logs/` is created when the app runs. It is not in git.

### Where to start

| You want to… | Open |
|--------------|------|
| Run or change startup, threads, and wiring | `src/main.py` |
| Change the touchscreen | `src/gui.py` |
| Change operating states | `src/state_machine.py`, `docs/state-machine.md` |
| Change when a fault trips, and the text the operator sees | `src/safety_rules.py`, `src/fault_catalog.py` |
| Change pins, names, or limits | `config.yaml` |
| Run without a Pi | `python src/main.py --sim` (`src/sim/`, `src/hardware_factory.py`) |
| Check one sensor on the bench | `examples/` |
| Read a recorded session | `python tools/log_viewer/log_analyzer.py` |

### `src/` — the program

`python src/main.py` puts `src/` on the import path and wires the pieces below. Modules import each other by filename (`from gui import MainScreen`), so they stay in this flat folder.

| Module | Role |
|--------|------|
| `main.py` | Entry point. GUI thread, I/O thread, stepper thread |
| `gui.py` | PyQt6 touchscreen |
| `graph_history.py` | Graph time window and axis ticks (no Qt, so tests can import it anywhere) |
| `state_machine.py` | Init → Ready → Cooling → Pumping → Error |
| `safety_rules.py` | Which readings become a stop or a warning |
| `fault_catalog.py` | Fault codes, severity, operator text |
| `hardware_factory.py` | Real drivers, or `sim/` with `--sim` |
| `sim/` | In-memory sensors, thermistors, pressure, flow, and stepper |
| `multi_sensor_reader.py` | Digital GPIO: cartridge, level, leak |
| `ads1115_thermistor_reader.py` | 12 thermistors on three ADS1115s |
| `thermistor_conversion.py` | NTC voltage → °C, using `data/calibration/` |
| `ads1115_pressure_reader.py` | Differential pressure |
| `ads1115_flow_reader.py` | 4–20 mA flow |
| `stepper_driver.py` | Peristaltic pump (TB6600 step/dir/enable via pigpio) |
| `pump_flow_control.py` | Flow setpoint ↔ RPM |
| `compressor_control.py` | Compressor on/off from the plate temperatures |
| `cooling_power.py` | Cooling power from flow and temperatures |
| `cooling_tracker.py` | Whether cooling is actually taking effect |
| `leak_debounce.py` | Leak input must hold before it trips |
| `csv_logger.py` | Sensor CSV (UI rate, about 10 Hz) |
| `pressure_csv_logger.py` | Pressure CSV (about 100 Hz) |
| `status_event_logger.py` | State changes, stops, and warnings |
| `session_log_paths.py` | Log folder and file names |
| `session_logs.py` | Read those CSVs back |
| `usb_log_mirror.py` | Copy new log bytes onto a USB stick |
| `sensor_injection.py`, `sensor_override_ui.py` | Manual sensor values with `--test-ui` |

### `docs/`

| File | Who it is for |
|------|----------------|
| `docs/Spine_Cooling_Operator_Guide.html` (and the PDF next to it) | People running the device |
| `docs/state-machine.md` | Operating states and transitions |
| `docs/verification/Verification_Protocol.html` | Verification steps |
| `docs/fault-messages-and-reactions.pptx` and `.xlsx` | Fault text and the reaction to each fault |
| `docs/GANTT.md` | Prototype schedule |
| `docs/screenshots/` | Pictures used by the operator guide |

Regenerate the guide from the current UI with `python tools/generate_operator_pdf.py`.

### `tools/`

| Script | Role |
|--------|------|
| `tools/log_viewer/` | Windows session viewer. How to open it and build the exe: `tools/log_viewer/README.md` |
| `tools/pump_flow_fit/` | Fit RPM → ml/min from `pump_flow_data.csv` and save the residual plot. Pass another CSV to use a different calibration. |
| `tools/generate_operator_pdf.py` | Capture screenshots and write the operator PDF |

The log viewer looks for `*_sensors.csv` in the repo root, in `logs/`, and in a local `evaluation tool/` folder (sample sessions and the built exe live there; CSVs and exe files are gitignored).

## Run

1. Clone https://github.com/PatrykPrezyna/spine-cooling-runtime.git
2. Create a virtual environment. On Windows, use Python from python.org or the Microsoft Store. Miniconda and Anaconda ship a PyQt6 build whose DLLs fail to load, and the window never opens.

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. Install dependencies. Pi-only packages (`RPi.GPIO`, `pigpio`, Blinka, …) are skipped automatically off the Pi.

   ```bash
   pip install -r requirements.txt
   ```

4. Edit `config.yaml` — sensor names, GPIO pins, stepper speeds, temperature thresholds.
5. On the Raspberry Pi: `python src/main.py`
6. On a PC, with simulated hardware: `python src/main.py --sim`
7. Simulated hardware plus on-screen sensor overrides: `python src/main.py --sim --test-ui`

Off-Pi mode uses `src/sim/`. Default sensor values are under `simulation:` in `config.yaml`.

## Tests

Automatic tests run on every push and pull request (`.github/workflows/test.yml`).

```bash
python -m unittest discover -s tests -v
```

The workflow installs PyQt6 and runs the GUI checks with `QT_QPA_PLATFORM=offscreen`. On a machine whose PyQt6 DLLs do not load, the GUI checks skip and the rest of the suite still runs.

## Session logs

Each run writes three CSVs into `logs/`, all sharing one startup stamp. Twelve thermistors on three ADS1115s take about 90 ms for a full sweep at 128 SPS, so temperatures stay near 10 Hz. The pressure chips run at 860 SPS so the pressure file can hold 100 Hz. Status and faults are written when they happen.

| File | Rate | Contents |
|------|------|----------|
| `logs/<session>_sensors.csv` | `ui.update_interval_ms` (100 ms → 10 Hz) | Temperatures, setpoint, pump, compressor, pressures |
| `logs/<session>_pressure_100Hz.csv` | `pressure_sensors.capture_rate_hz` (100 Hz) | Pressures and pump setpoint |
| `logs/<session>_status_and_errors.csv` | On each event | State transitions, STOP errors, warnings (including clears) |

High-rate pressure capture starts with the session and runs until shutdown. A later capture in the same session is named `<session>_pressure_100Hz_run02.csv`, `_run03`, and so on.

Join the periodic files on the timestamp. The fast file has the pressure detail; the sensor file has the temperatures around it:

```python
import pandas as pd

session = pd.read_csv("20260817_170941_sensors.csv", parse_dates=["timestamp"])
fast = pd.read_csv("20260817_170941_pressure_100Hz.csv", parse_dates=["timestamp"])
merged = pd.merge_asof(fast, session, on="timestamp", direction="nearest")
```

### Copy logs off the Pi

FileZilla, port 22, then `spine-cooling-runtime/logs`. The Pi address is `ifconfig` (or `hostname -I`).

Or plug in a USB stick labeled **SPINELOGS** (exFAT or FAT32). The runtime keeps writing `logs/` on the Pi and copies new bytes onto the stick every couple of seconds (`USB/logs/<same filenames>`). Use **Service → Manual Operation → Eject** before unplugging. Copying stays paused until the stick is unplugged and inserted again, so a remount after eject does not keep writing.

Format a stick:

```text
Windows:  format E: /FS:exFAT /V:SPINELOGS /Q
Linux:    sudo fatlabel /dev/sda1 SPINELOGS
```

Set `logging.usb.enabled: false` in `config.yaml` to leave the stick unused.

## Raspberry Pi setup

1. Install Raspberry Pi OS and connect the Pi to the network.
   - Use the imager: https://www.raspberrypi.com/software/
   - Select the current OS (Debian 13, 64-bit, as of this note).
   - Hostname `spine`. The password is in the team KeePass.
   - Enable SSH with password authentication, and Raspberry Pi Connect.
2. Log in with a keyboard and display, or over SSH. Devices also show up at https://connect.raspberrypi.com/devices
3. Enable SSH, SPI, and I2C with `sudo raspi-config` → Interface Options.
   - I2C check: `ls /dev/i2c-1`
   - SPI: `sudo dtparam spi=on`
   - Second I2C bus on a Pi 4: GPIO 22 SDA / GPIO 23 SCL (header pins 15 / 16). Add 2.2 kΩ–4.7 kΩ pull-ups to 3.3 V, then append this line to `/boot/firmware/config.txt` (or `/boot/config.txt` on older images):

     ```text
     dtoverlay=i2c6,pins_22_23
     ```

     After reboot: `ls /dev/i2c-6` and `sudo i2cdetect -y 6` (expect `0x48` for the extra thermistor ADS1115). The original sensors stay on `/dev/i2c-1`.
   - `sudo reboot`
4. Install pigpio (the pump step pulses need the daemon):

   ```bash
   sudo apt update
   sudo apt install -y pigpio python3-pigpio
   ```

   If `pigpiod` is not in apt, build it:

   ```bash
   sudo apt install -y git make gcc
   cd /tmp
   git clone https://github.com/joan2937/pigpio.git
   cd pigpio
   make
   sudo make install
   sudo ldconfig
   ```

   Then `sudo systemctl enable pigpiod` and `sudo systemctl start pigpiod`. For the current session only: `sudo pigpiod`. Check with `pigs t`.
5. Follow [Run](#run) above.

Qt on the Pi image also needs:

```bash
sudo apt-get install libxcb-cursor0 libxcb-xinerama0 libxcb-shape0
sudo apt-get install libqt6gui6 libqt6core6 qt6-qpa-plugins
```

Launching the app at boot is still open. Background notes: https://www.instructables.com/Raspberry-Pi-Launch-Python-script-on-startup/

Stepper wiring background: https://www.instructables.com/Raspberry-Pi-Python-and-a-TB6600-Stepper-Motor-Dri/

## Troubleshooting temperatures

If the main app shows no temperatures, check the bus without the UI:

```bash
python examples/ads1115_thermistors.py      # bus 1 and bus 6
python examples/ads1115_thermistors.py 1    # eight channels on /dev/i2c-1
python examples/ads1115_thermistors.py 6    # four channels on /dev/i2c-6
```

Live numbers mean that bus and ADS1115 are fine — compare the names with `config.yaml`. No devices, or only one bus, means the connector, overlay, address, or pull-ups. Check with `ls /dev/i2c-1 /dev/i2c-6` and `sudo i2cdetect -y 1` / `sudo i2cdetect -y 6`.
