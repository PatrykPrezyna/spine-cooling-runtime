# Hardware Setup Guide

## Overview

This guide provides detailed instructions for setting up the hardware components of the medical device prototype on Raspberry Pi 4 B.

## Required Hardware

### Main Components
- Raspberry Pi 4 Model B (4GB+ RAM recommended)
- 7-inch touchscreen display (800x480 resolution)
- MicroSD card (32GB+ Class 10)
- 5V 3A USB-C power supply for Raspberry Pi
- External 12V/24V power supply for compressor and motor

### Sensors and Actuators
- MAX31855 thermocouple amplifier modules (quantity based on config)
- K-type thermocouples (quantity based on config)
- Compressor unit with UART interface
- Stepper motor with driver (e.g., A4988, DRV8825)
- Digital level sensors (2x)

### Connectivity
- Jumper wires (male-to-female, male-to-male)
- Breadboard or custom PCB
- UART-to-TTL converter (if needed)
- SPI breakout board (optional)

## Raspberry Pi 4 B Pinout Reference

```
                    3.3V  (1) (2)  5V
       GPIO2 (SDA1)       (3) (4)  5V
       GPIO3 (SCL1)       (5) (6)  GND
       GPIO4              (7) (8)  GPIO14 (TXD)
                   GND    (9) (10) GPIO15 (RXD)
       GPIO17            (11) (12) GPIO18
       GPIO27            (13) (14) GND
       GPIO22            (15) (16) GPIO23
                   3.3V  (17) (18) GPIO24
       GPIO10 (MOSI)     (19) (20) GND
       GPIO9 (MISO)      (21) (22) GPIO25
       GPIO11 (SCLK)     (23) (24) GPIO8 (CE0)
                   GND   (25) (26) GPIO7 (CE1)
       GPIO0 (ID_SD)     (27) (28) GPIO1 (ID_SC)
       GPIO5             (29) (30) GND
       GPIO6             (31) (32) GPIO12
       GPIO13            (33) (34) GND
       GPIO19            (35) (36) GPIO16
       GPIO26            (37) (38) GPIO20
                   GND   (39) (40) GPIO21
```

## Pin Assignments

### SPI Interface (Thermocouples)

**MAX31855 Module 1 (Primary)**
- VCC → 3.3V (Pin 1)
- GND → GND (Pin 6)
- SCK → GPIO11/SCLK (Pin 23)
- SO (MISO) → GPIO9/MISO (Pin 21)
- CS → GPIO8/CE0 (Pin 24)

**MAX31855 Module 2 (if used)**
- VCC → 3.3V (Pin 17)
- GND → GND (Pin 20)
- SCK → GPIO11/SCLK (Pin 23) - shared
- SO (MISO) → GPIO9/MISO (Pin 21) - shared
- CS → GPIO7/CE1 (Pin 26)

**Additional MAX31855 Modules**
- Use GPIO25, GPIO16, GPIO20, GPIO21 as additional CS pins
- Share SCK and MISO lines

### UART Interface (Compressor)

**Compressor UART Connection**
- TX (from Pi) → GPIO14/TXD (Pin 8) → Compressor RX
- RX (to Pi) → GPIO15/RXD (Pin 10) → Compressor TX
- GND → GND (Pin 14) → Compressor GND

**Note**: Ensure voltage levels match. Use level shifter if compressor uses 5V logic.

### GPIO Interface (Stepper Motor)

**Stepper Motor Driver (e.g., A4988)**
- STEP → GPIO17 (Pin 11)
- DIR → GPIO27 (Pin 13)
- ENABLE → GPIO22 (Pin 15)
- GND → GND (Pin 9)
- VDD → 3.3V (Pin 1) - for logic
- VMOT → External 12V/24V supply
- Motor coils → Connect to driver outputs

**Motor Power Supply**
- Use separate power supply for motor (12V or 24V depending on motor)
- Common ground with Raspberry Pi
- Add decoupling capacitor (100µF) near driver

### GPIO Interface (Level Sensors)

**Upper Level Sensor**
- Signal → GPIO23 (Pin 16)
- VCC → 3.3V or 5V (depending on sensor)
- GND → GND (Pin 14)

**Lower Level Sensor**
- Signal → GPIO24 (Pin 18)
- VCC → 3.3V or 5V (depending on sensor)
- GND → GND (Pin 20)

**Note**: If sensors are 5V, use voltage divider or level shifter for GPIO protection.

## Wiring Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4 B                          │
│                                                              │
│  3.3V ──┬──────────────────────────────────────────────────┤
│         │                                                    │
│  GPIO8 ─┼─────────────────────────────────────────────────┤
│  GPIO9 ─┼─────────────────────────────────────────────────┤
│  GPIO11─┼─────────────────────────────────────────────────┤
│         │                                                    │
│  GPIO14─┼─────────────────────────────────────────────────┤
│  GPIO15─┼─────────────────────────────────────────────────┤
│         │                                                    │
│  GPIO17─┼─────────────────────────────────────────────────┤
│  GPIO22─┼─────────────────────────────────────────────────┤
│  GPIO27─┼─────────────────────────────────────────────────┤
│         │                                                    │
│  GPIO23─┼─────────────────────────────────────────────────┤
│  GPIO24─┼─────────────────────────────────────────────────┤
│         │                                                    │
│  GND ───┴──────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────┘
         │         │         │         │         │         │
         │         │         │         │         │         │
    ┌────▼────┐   │    ┌────▼────┐   │    ┌────▼────┐   │
    │MAX31855 │   │    │Compressor│   │    │ Stepper │   │
    │  (SPI)  │   │    │  (UART) │   │    │  Driver │   │
    └────┬────┘   │    └────┬────┘   │    └────┬────┘   │
         │         │         │         │         │         │
    ┌────▼────┐   │         │         │    ┌────▼────┐   │
    │Thermo-  │   │         │         │    │ Stepper │   │
    │ couple  │   │         │         │    │  Motor  │   │
    └─────────┘   │         │         │    └─────────┘   │
                  │         │         │                   │
             ┌────▼────┐   │    ┌────▼────┐         ┌───▼────┐
             │MAX31855 │   │    │  Level  │         │ Level  │
             │  (SPI)  │   │    │ Sensor  │         │ Sensor │
             └────┬────┘   │    │ (Upper) │         │ (Lower)│
                  │         │    └─────────┘         └────────┘
             ┌────▼────┐   │
             │Thermo-  │   │
             │ couple  │   │
             └─────────┘   │
                           │
                      ┌────▼────┐
                      │Compressor│
                      │   Unit   │
                      └──────────┘
```

## Setup Instructions

### 1. Raspberry Pi OS Configuration

```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Enable SPI
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable

# Enable UART (disable console)
sudo raspi-config
# Navigate to: Interface Options → Serial Port
# - Login shell over serial: No
# - Serial port hardware: Yes

# Edit boot config
sudo nano /boot/config.txt
# Add or verify:
dtparam=spi=on
enable_uart=1
dtoverlay=disable-bt

# Reboot
sudo reboot
```

### 2. Install Required Packages

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install system packages
sudo apt install -y python3-pyqt6 python3-serial python3-spidev

# Install GPIO library
sudo apt install -y python3-rpi.gpio
```

### 3. Hardware Connection Steps

#### Step 1: Power Off
- Ensure Raspberry Pi is powered off
- Disconnect all power sources

#### Step 2: Connect MAX31855 Modules
1. Connect first MAX31855 to SPI pins as shown above
2. Connect thermocouple to MAX31855 screw terminals (observe polarity)
3. Repeat for additional sensors using different CS pins

#### Step 3: Connect Compressor UART
1. Identify compressor TX/RX pins
2. Connect to Raspberry Pi UART pins
3. Ensure common ground connection
4. Add level shifter if voltage mismatch

#### Step 4: Connect Stepper Motor
1. Wire stepper driver to GPIO pins
2. Connect motor coils to driver outputs
3. Connect external power supply to driver
4. Ensure common ground with Raspberry Pi

#### Step 5: Connect Level Sensors
1. Wire sensor signals to GPIO pins
2. Connect power (3.3V or 5V based on sensor)
3. Add pull-up/pull-down resistors if needed
4. Use level shifter for 5V sensors

#### Step 6: Connect Display
1. Connect 7-inch display via DSI or HDMI
2. Configure display in `/boot/config.txt` if needed
3. Enable touchscreen if applicable

### 4. Verify Connections

```bash
# Check SPI devices
ls -l /dev/spidev*
# Should show: /dev/spidev0.0, /dev/spidev0.1

# Check UART
ls -l /dev/ttyAMA0
# Should exist

# Check GPIO
gpio readall
# Should show pin status

# Test SPI communication
python3 -c "import spidev; spi = spidev.SpiDev(); spi.open(0, 0); print('SPI OK')"

# Test UART
python3 -c "import serial; ser = serial.Serial('/dev/ttyAMA0', 9600); print('UART OK')"
```

### 5. Safety Checks

Before powering on:
- [ ] All connections are secure
- [ ] No short circuits between pins
- [ ] Correct voltage levels (3.3V vs 5V)
- [ ] External power supplies properly rated
- [ ] Common ground established
- [ ] Thermocouples properly connected (polarity)
- [ ] Motor power supply isolated from Pi power
- [ ] Display properly connected

## Troubleshooting

### SPI Not Working
```bash
# Check if SPI is enabled
lsmod | grep spi
# Should show: spi_bcm2835

# Check permissions
sudo chmod 666 /dev/spidev0.0

# Test with loopback (connect MOSI to MISO)
python3 -c "import spidev; spi = spidev.SpiDev(); spi.open(0,0); print(spi.xfer([0x01, 0x02]))"
```

### UART Not Working
```bash
# Check if UART is enabled
ls -l /dev/ttyAMA0

# Disable Bluetooth (if conflicts)
sudo systemctl disable hciuart

# Check for console on serial
sudo systemctl stop serial-getty@ttyAMA0.service
sudo systemctl disable serial-getty@ttyAMA0.service
```

### GPIO Not Responding
```bash
# Check GPIO permissions
sudo usermod -a -G gpio $USER

# Test GPIO
python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.OUT); GPIO.output(17, GPIO.HIGH); print('GPIO OK')"
```

### Thermocouple Reading Errors
- Check thermocouple polarity (+ and -)
- Verify MAX31855 power supply (3.3V)
- Check SPI wiring (SCK, MISO, CS)
- Ensure proper grounding
- Test with known good thermocouple

### Stepper Motor Not Moving
- Verify driver power supply
- Check ENABLE pin (should be LOW to enable)
- Verify STEP and DIR connections
- Check motor coil connections
- Test with simple step sequence

## Electrical Specifications

### Power Requirements
- Raspberry Pi 4: 5V @ 3A (USB-C)
- MAX31855: 3.3V @ 1.5mA each
- Level Sensors: 3.3V or 5V @ 10mA each
- Stepper Motor: 12-24V @ 1-2A (depends on motor)
- Compressor: Per manufacturer specs

### Signal Levels
- GPIO Input: 3.3V max (5V will damage!)
- GPIO Output: 3.3V @ 16mA max per pin
- SPI: 3.3V logic
- UART: 3.3V logic (use level shifter for 5V devices)

### Protection
- Add 330Ω resistors in series with GPIO outputs
- Use optocouplers for high-voltage isolation
- Add flyback diodes across motor coils
- Use TVS diodes for ESD protection
- Fuse external power supplies

## Maintenance

### Regular Checks
- Inspect wire connections monthly
- Clean thermocouple junctions
- Check for corrosion on connectors
- Verify motor driver heat dissipation
- Test emergency stop functionality

### Calibration
- Calibrate thermocouples with ice bath (0°C) and boiling water (100°C)
- Verify level sensor thresholds
- Check motor step accuracy
- Validate compressor response times

## Safety Warnings

⚠️ **IMPORTANT SAFETY INFORMATION**

1. **Electrical Safety**
   - Never connect/disconnect while powered
   - Use proper insulation
   - Avoid water near electronics
   - Use appropriate fuses

2. **Medical Device Considerations**
   - This is a prototype, not certified for medical use
   - Requires proper validation and testing
   - Follow all applicable regulations
   - Implement redundant safety systems

3. **Temperature Safety**
   - Monitor temperature limits continuously
   - Implement emergency shutdown
   - Test all safety interlocks
   - Have backup cooling method

4. **Mechanical Safety**
   - Secure all moving parts
   - Implement emergency stop
   - Guard against pinch points
   - Test motor limits

## Additional Resources

- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.org/documentation/hardware/raspberrypi/)
- [MAX31855 Datasheet](https://www.maximintegrated.com/en/products/sensors/MAX31855.html)
- [SPI Protocol Guide](https://www.raspberrypi.org/documentation/hardware/raspberrypi/spi/)
- [UART Configuration](https://www.raspberrypi.org/documentation/configuration/uart.md)