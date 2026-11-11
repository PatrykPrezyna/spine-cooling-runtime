# Bench scripts

Run these on the Raspberry Pi to check one piece of hardware. The device application is `src/main.py`; these scripts do not start it.

From the repo root, with the project virtualenv active:

| Script | What it checks |
|--------|----------------|
| `python examples/ads1115_thermistors.py` | All 8 ADS1115s on bus 1 and bus 6, every pin as a thermistor. 20–40 °C is highlighted |
| `python examples/ads1115_thermistors.py 1` | The four chips on `/dev/i2c-1` |
| `python examples/ads1115_thermistors.py 6` | The four chips on `/dev/i2c-6` |
| `python examples/ads1115_thermistor_calibrate.py` | Two-point ice / 37 °C voltage check |
| `python examples/ads1115_pressure.py` | One differential pressure sensor. ENTER stops it |
| `python examples/gpio_control.py` | Switch a BCM pin on or off (needs `pigpiod`) |
| `python examples/stepper_TB600.py` | Pulse the TB6600 pump driver |
| `python examples/thermocouple/read_one.py` | One channel on a Sequent SMtc thermocouple HAT |

The runtime measures temperature with thermistors. `examples/thermocouple/` is a separate bring-up for the SMtc HAT; see `examples/thermocouple/README.md`.
