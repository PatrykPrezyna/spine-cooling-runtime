# Spine Cooling Raspberry Pi Data Acquisition

Raspberry Pi 4B application for temperature acquisition, compressor control, and on-screen monitoring.

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


3. Run in foreground for debugging:
   ```bash
   python main.py
   ```

