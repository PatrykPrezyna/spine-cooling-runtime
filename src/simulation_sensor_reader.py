"""
Simulation Sensor Reader Module
Allows manual control of sensor states for testing and simulation
"""

from typing import Dict, List, Optional


class SimulationSensorReader:
    """Simulated sensor reader with manual control"""
    
    def __init__(self, config: dict):
        """
        Initialize simulation sensor reader
        
        Args:
            config: Configuration dictionary with sensors settings
        """
        self.sensors = config['sensors']
        self.sample_rate_hz = config['sample_rate_hz']
        
        self.is_initialized = True
        self.simulation_mode = True
        
        # Initialize all sensors to False (LOW)
        self.sensor_states: Dict[str, bool] = {}
        for sensor in self.sensors:
            self.sensor_states[sensor['name']] = False
        
        print(f"Simulation mode initialized: {len(self.sensors)} sensors (manual control)")
    
    def read_all(self) -> Dict[str, bool]:
        """
        Read all sensors (returns current manual states)
        
        Returns:
            dict: Dictionary mapping sensor names to their states (True/False)
        """
        return self.sensor_states.copy()
    
    def read_sensor(self, sensor_name: str) -> Optional[bool]:
        """
        Read a specific sensor by name
        
        Args:
            sensor_name: Name of the sensor to read
            
        Returns:
            bool: Sensor state, or None if sensor not found
        """
        return self.sensor_states.get(sensor_name)
    
    def set_sensor(self, sensor_name: str, state: bool) -> bool:
        """
        Manually set a sensor state
        
        Args:
            sensor_name: Name of the sensor to set
            state: New state (True/False)
            
        Returns:
            bool: True if successful, False if sensor not found
        """
        if sensor_name in self.sensor_states:
            self.sensor_states[sensor_name] = state
            print(f"Simulation: {sensor_name} set to {'HIGH' if state else 'LOW'}")
            return True
        return False
    
    def set_all_sensors(self, states: Dict[str, bool]):
        """
        Set multiple sensor states at once
        
        Args:
            states: Dictionary mapping sensor names to states
        """
        for sensor_name, state in states.items():
            if sensor_name in self.sensor_states:
                self.sensor_states[sensor_name] = state
    
    def get_sensor_names(self) -> List[str]:
        """
        Get list of all sensor names
        
        Returns:
            list: List of sensor names
        """
        return [sensor['name'] for sensor in self.sensors]
    
    def wait_for_sample_interval(self):
        """Wait for the configured sample interval (no-op in simulation)"""
        pass
    
    def cleanup(self):
        """Cleanup resources (no-op in simulation)"""
        print("Simulation mode: cleanup complete")
        self.is_initialized = False
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        if self.is_initialized:
            self.cleanup()


if __name__ == "__main__":
    # Test the simulation sensor reader
    import yaml
    import time
    
    print("Testing SimulationSensorReader...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create simulation reader
    reader = SimulationSensorReader(config)
    
    print(f"Initialized: {reader.is_initialized}")
    print(f"Simulation mode: {reader.simulation_mode}")
    print(f"Sensors: {reader.get_sensor_names()}")
    
    # Test manual control
    print("\nTesting manual control:")
    
    # Set individual sensors
    reader.set_sensor('Level Low', True)
    reader.set_sensor('Level Critical', False)
    reader.set_sensor('Cartridge In Place', True)
    
    # Read all sensors
    states = reader.read_all()
    print("\nCurrent states:")
    for name, state in states.items():
        state_str = "HIGH" if state else "LOW"
        print(f"  {name}: {state_str}")
    
    # Set all sensors at once
    print("\nSetting all sensors to HIGH:")
    reader.set_all_sensors({
        'Level Low': True,
        'Level Critical': True,
        'Cartridge In Place': True
    })
    
    states = reader.read_all()
    for name, state in states.items():
        state_str = "HIGH" if state else "LOW"
        print(f"  {name}: {state_str}")
    
    # Cleanup
    reader.cleanup()
    print("\nTest complete!")

# Made with Bob