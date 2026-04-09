# Spine Cooling Raspberry Pi Data Acquisition

Raspberry Pi 4B application for temperature acquisition, compressor control, and on-screen monitoring.

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
