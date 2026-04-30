"""In-memory sensor reader used in simulation mode (manual control)."""

from typing import Dict, List, Optional


class SimulationSensorReader:
    """Mirror of `MultiSensorReader` whose state is fully manually controlled."""

    def __init__(self, config: dict):
        self.sensors = config['sensors']
        self.sample_rate_hz = config['sample_rate_hz']

        self.is_initialized = True
        self.simulation_mode = True
        self.sensor_states: Dict[str, bool] = {
            sensor['name']: False for sensor in self.sensors
        }

        print(f"Simulation mode initialized: {len(self.sensors)} sensors (manual control)")

    def read_all(self) -> Dict[str, bool]:
        return self.sensor_states.copy()

    def read_sensor(self, sensor_name: str) -> Optional[bool]:
        return self.sensor_states.get(sensor_name)

    def set_sensor(self, sensor_name: str, state: bool) -> bool:
        """Manually set a sensor state. Returns True if the name was known."""
        if sensor_name not in self.sensor_states:
            return False
        self.sensor_states[sensor_name] = state
        print(f"Simulation: {sensor_name} set to {'HIGH' if state else 'LOW'}")
        return True

    def set_all_sensors(self, states: Dict[str, bool]) -> None:
        for name, state in states.items():
            if name in self.sensor_states:
                self.sensor_states[name] = state

    def get_sensor_names(self) -> List[str]:
        return [sensor['name'] for sensor in self.sensors]

    def wait_for_sample_interval(self) -> None:
        """No-op in simulation."""

    def cleanup(self) -> None:
        print("Simulation mode: cleanup complete")
        self.is_initialized = False

    def __del__(self):
        try:
            if self.is_initialized:
                self.cleanup()
        except Exception:
            # Avoid destructor-time exceptions during interpreter shutdown.
            pass


if __name__ == "__main__":
    import yaml

    print("Testing SimulationSensorReader...")
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    reader = SimulationSensorReader(config)
    print(f"Sensors: {reader.get_sensor_names()}")

    reader.set_sensor('Level Low', True)
    reader.set_sensor('Level Critical', False)
    reader.set_sensor('Cartridge In Place', True)
    print(f"States: {reader.read_all()}")

    reader.set_all_sensors({
        'Level Low': True,
        'Level Critical': True,
        'Cartridge In Place': True,
    })
    print(f"States: {reader.read_all()}")

    reader.cleanup()
    print("Test complete!")
