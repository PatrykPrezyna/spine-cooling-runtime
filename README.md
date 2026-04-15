# Spine Cooling Raspberry Pi Data Acquisition

Raspberry Pi 4B application for temperature acquisition, compressor control, and on-screen monitoring.

## Raspberry Pi setup

1. Install Raspberry Pi OS and connect the device to the network via Wi-Fi or Ethernet.
2. Enable SSH access:
   - Use `sudo raspi-config` and enable SSH under `Interfacing Options`.
   - Alternatively, create an empty file named `ssh` in the boot partition before first boot.
3. Connect to the Pi using a keyboard and display, or remotely via SSH (for example, with PuTTY on Windows).

### Ethernet static IP configuration

On the laptop:
- IP address: `192.168.1.2`
- Netmask: `255.255.255.0`
- Gateway: `192.168.1.1`

On the Raspberry Pi:

1. Edit the DHCP client configuration:
   ```bash
   sudo nano /etc/dhcpcd.conf
   ```
2. Add the following block to the end of the file:
   ```ini
   interface eth0
   static ip_address=192.168.1.10/24
   static routers=192.168.1.1
   ```
3. Install or verify that `dhcpcd5` is present:
   ```bash
   sudo apt-get update
   sudo apt-get install dhcpcd5
   ```
4. Restart the DHCP client service:
   ```bash
   sudo systemctl restart dhcpcd
   ```
5. Verify connectivity from the laptop:
   ```bash
   ping 192.168.1.10
   ```

### Optional development tools

- Install the VS Code Remote - SSH extension (`ms-vscode-remote.remote-ssh`).
- Use `Ctrl+Shift+P` and select `Remote-SSH: Connect Current Window to Host...` to open the project on the Raspberry Pi over SSH.

## Features

- 5x MAX31855 thermocouple sensors via SPI
- 7" PyQt6 touchscreen UI with live strip chart
- RS-232 UART compressor controller state machine
- Dual logging: SQLite WAL + rotating CSV
- Watchdog kicker for /dev/watchdog
- Systemd-friendly service support

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

2. Update `config.yaml` with your GPIO and hardware configuration.

3. Run in foreground for debugging:
   ```bash
   python main.py
   ```

### Desktop / Laptop development mode

If you are developing on a laptop without Raspberry Pi GPIO, SPI, or watchdog hardware, use desktop mode.

- Install simulation dependencies on Windows or desktop:
  ```bash
  pip install -r requirements-sim.txt
  ```

  This installs `PyQt6-Charts` so the UI can use `PyQt6.QtCharts`.

- Command line:
  ```bash
  python main.py --desktop
  ```
- Or enable it in `config.yaml`:
  ```yaml
  app:
    run_mode: desktop
  ```

Desktop mode uses simulated sensor data and skips the Raspberry Pi watchdog hardware.

4. For systemd, install service file at `/etc/systemd/system/spine-cooling.service`.

## Service example

```ini
[Unit]
Description=Spine Cooling Data Acquisition
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/spine-cooling-raspberry
ExecStart=/usr/bin/python3 /home/pi/spine-cooling-raspberry/main.py
Restart=on-failure
RestartSec=3s
WatchdogSec=30s

[Install]
WantedBy=multi-user.target
```
