# Simple Raspberry Pi CPU Temperature UI

A minimal PyQt6 application that displays the Raspberry Pi CPU temperature and refreshes every 3 seconds.

## Requirements

- Python 3.10+
- PyQt6

## Run

From the `simple_ui` folder:

```bash
python main.py
```

## Notes

- The UI reads the CPU temperature from `/sys/class/thermal/thermal_zone0/temp`.
- If the file is unavailable, the app displays an "unavailable" message.
