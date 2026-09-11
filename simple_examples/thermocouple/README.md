# Thermocouple board (one channel)

Standalone Raspberry Pi example for the [Sequent Microsystems 8-thermocouple HAT](https://sequentmicrosystems.com/products/thermocouple-hat-for-raspberry-pi) (`SMtc`). The main spine-cooling app does **not** use this board — it reads thermistors. This folder is only for bringing the HAT up and reading **one** thermocouple.

## Hardware

- Raspberry Pi with I2C enabled (`sudo raspi-config` → Interface Options → I2C)
- SMtc HAT on the 40-pin header, stack jumpers at **0** (I2C address `0x16`)
- One thermocouple on **channel 1** (screw terminals TC1). Type **T** (copper / constantan) is the default.

Check the bus after reboot:

```bash
ls /dev/i2c-1
sudo i2cdetect -y 1
```

Expect a device at `0x16` for stack 0. Other stack jumpers use `0x16 + stack`.

## Install

From the repo root, in the same venv as the rest of the project:

```bash
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r simple_examples/thermocouple/requirements.txt
```

`SMtc` is Linux / Pi only.

## Run

```bash
python simple_examples/thermocouple/read_one.py
```

Prints channel 1 once per second. Press ENTER to stop.

```bash
python simple_examples/thermocouple/read_one.py 2          # channel 2
python simple_examples/thermocouple/read_one.py 1 --type K # Type K on ch 1
```

A valid Type T reading is a plausible °C value (room temperature is typically 15–30). `0`, huge numbers, or an init error usually mean the wrong channel, open wires, or the HAT not on I2C.
