"""GPIO multi-channel digital sensor reader (with simulation fallback)."""

import time
from typing import Dict, List, Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. Running in simulation mode.")


class MultiSensorReader:
    """Read multiple digital sensors via GPIO pins."""

    def __init__(self, config: dict, force_simulation: bool = False):
        self.sensors = config['sensors']
        self.sample_rate_hz = config['sample_rate_hz']

        self.is_initialized = False
        self.sensor_states: Dict[str, bool] = {}
        self.simulation_mode = force_simulation
        self.simulation_counter = 0

        if not self.simulation_mode and not GPIO_AVAILABLE:
            raise RuntimeError(
                "GPIO not available. Real sensor mode requires Raspberry Pi with GPIO support."
            )

        if self.simulation_mode:
            print(f"Simulation mode: {len(self.sensors)} sensors (simulated)")
            self.is_initialized = True
            for sensor in self.sensors:
                self.sensor_states[sensor['name']] = False
        else:
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

        if self.simulation_mode:
            self.simulation_counter += 1
            for i, sensor in enumerate(self.sensors):
                # Different toggle period per sensor for visible variety.
                period = (3, 5, 7)[i] if i < 3 else 11
                self.sensor_states[sensor['name']] = (self.simulation_counter % period) == 0
            return self.sensor_states.copy()

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
        if not self.simulation_mode and self.is_initialized:
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
    print(f"Simulation mode: {reader.simulation_mode}")
    print(f"Sensors: {reader.get_sensor_names()}")

    print("\nReading sensors 10 times:")
    for i in range(10):
        print(f"  Reading {i + 1}: {reader.read_all()}")
        time.sleep(1)

    reader.cleanup()
    print("Test complete!")
