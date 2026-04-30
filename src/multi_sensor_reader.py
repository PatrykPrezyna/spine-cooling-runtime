"""GPIO multi-channel digital sensor reader (Raspberry Pi only)."""

import time
from typing import Dict, List, Optional

import RPi.GPIO as GPIO


class MultiSensorReader:
    """Read multiple digital sensors via GPIO pins."""

    def __init__(self, config: dict):
        self.sensors = config['sensors']
        self.sample_rate_hz = config['sample_rate_hz']

        self.is_initialized = False
        self.sensor_states: Dict[str, bool] = {}

        self._initialize_gpio()

    def _initialize_gpio(self):
        """Configure GPIO pins for all sensors as inputs with pull-up/down."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for sensor in self.sensors:
                gpio_pin = sensor['gpio_pin']
                pull = GPIO.PUD_UP if sensor.get('pull_up', True) else GPIO.PUD_DOWN
                GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=pull)
                print(f"GPIO pin {gpio_pin} initialized for '{sensor['name']}'")

            self.is_initialized = True
            print(f"All {len(self.sensors)} sensors initialized successfully")
        except Exception as e:
            print(f"Error initializing GPIO: {e}")
            self.is_initialized = False
            raise

    def read_all(self) -> Dict[str, bool]:
        """Read all sensors and return a {name: bool} mapping."""
        if not self.is_initialized:
            return {sensor['name']: False for sensor in self.sensors}

        try:
            for sensor in self.sensors:
                pin_state = bool(GPIO.input(sensor['gpio_pin']))
                if not sensor.get('active_high', True):
                    pin_state = not pin_state
                self.sensor_states[sensor['name']] = pin_state
            return self.sensor_states.copy()
        except Exception as e:
            print(f"Error reading sensors: {e}")
            return {sensor['name']: False for sensor in self.sensors}

    def read_sensor(self, sensor_name: str) -> Optional[bool]:
        """Read one sensor by name; returns None if unknown."""
        return self.read_all().get(sensor_name)

    def get_sensor_names(self) -> List[str]:
        return [sensor['name'] for sensor in self.sensors]

    def wait_for_sample_interval(self):
        if self.sample_rate_hz > 0:
            time.sleep(1.0 / self.sample_rate_hz)

    def cleanup(self):
        """Release GPIO resources."""
        if not self.is_initialized:
            return
        try:
            for sensor in self.sensors:
                GPIO.cleanup(sensor['gpio_pin'])
            print(f"All {len(self.sensors)} GPIO pins cleaned up")
        except Exception as e:
            print(f"Error cleaning up GPIO: {e}")
        self.is_initialized = False

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            # Avoid destructor-time exceptions during interpreter shutdown.
            pass


if __name__ == "__main__":
    import yaml

    print("Testing MultiSensorReader...")
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    reader = MultiSensorReader(config)
    print(f"Initialized: {reader.is_initialized}")
    print(f"Sensors: {reader.get_sensor_names()}")

    print("\nReading sensors 5 times:")
    for i in range(5):
        print(f"  Reading {i + 1}: {reader.read_all()}")
        time.sleep(1)

    reader.cleanup()
    print("Test complete!")
