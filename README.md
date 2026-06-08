# Spine Cooling - Medical Device Prototype

Raspberry Pi 4B application for medical device with visual UI, sensor reading, and data logging.


## Raspberry Pi setup (can be further automated)

1. Install Raspberry Pi OS and connect the device to the network via Wi-Fi or Ethernet.
2. Connect to the Pi using a keyboard and display, or remotely via SSH (for example, with PuTTY on Windows).2. 
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
4. Configure sensors in `config.yaml`:
5. Run the application: `python src/main.py`

## Project info:

1. Use the scripts from *simple example* folder to test each function
2. 

## Additional info
Stepper Motor:
sources: https://www.instructables.com/Raspberry-Pi-Python-and-a-TB6600-Stepper-Motor-Dri/

run on startup instruction:(is not working yet)
https://www.instructables.com/Raspberry-Pi-Launch-Python-script-on-startup/
sudo apt-get update
sudo apt-get install libxcb-cursor0 libxcb-xinerama0 libxcb-shape0
sudo apt-get install libqt6gui6 libqt6core6 qt6-qpa-plugins