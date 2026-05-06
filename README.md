# Spine Cooling Medical Device Prototype

Raspberry Pi 4B application for medical device monitoring with visual UI, sensor reading, and data logging.


## Raspberry Pi setup

1. Install Raspberry Pi OS and connect the device to the network via Wi-Fi or Ethernet.
2. Enable SSH access:
   - Use `sudo raspi-config` and enable SSH under `Interfacing Options`.
   - Alternatively, create an empty file named `ssh` in the boot partition before first boot.
3. Connect to the Pi using a keyboard and display, or remotely via SSH (for example, with PuTTY on Windows).


## Enable SPI
1. enable spi echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
2. sudo reboot


### Enable I2C on Raspberry Pi

1. Open Raspberry Pi configuration:
   ```bash
   sudo raspi-config
   ```
2. Go to `Interface Options` > `I2C` > `Enable`.
3. Reboot:
   ```bash
   sudo reboot
   ```
4. Optional check:
   ```bash
   ls /dev/i2c-1
   ```



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

### Install pigpio (Debian/Raspberry Pi)

```bash
sudo apt update
sudo apt install -y pigpio python3-pigpio
```

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

### Enable and start the pigpio daemon

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

Or start manually for the current session:

```bash
sudo pigpiod
```

### Verify pigpio is running

```bash
pigs t
```


   
## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```


3. Configure sensors in `config.yaml`:
  

4. Run the application:
   ```bash
   python src/main.py
   ```


## Development

### Testing Without Hardware

Run the calibration unit test:

```bash
python -m unittest tests.test_temperature_calibration
```

If you are using the project virtual environment on Windows:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_temperature_calibration
```

## License

Medical device prototype - Internal use only


----
#TODO:

1) test original fillin system with water
2) test with our pump
3) add the battery tot hes sytem 
3) parametrisize the thermocouple type

4) claibrate sensors



Stepper Motor:
sources: https://www.instructables.com/Raspberry-Pi-Python-and-a-TB6600-Stepper-Motor-Dri/

run on startup instruction:
https://www.instructables.com/Raspberry-Pi-Launch-Python-script-on-startup/


sudo apt-get update
sudo apt-get install libxcb-cursor0 libxcb-xinerama0 libxcb-shape0
sudo apt-get install libqt6gui6 libqt6core6 qt6-qpa-plugins