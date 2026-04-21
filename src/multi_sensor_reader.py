"""
Multiple Digital Sensor Reader Module
Reads multiple digital sensors via GPIO
"""

import time
from typing import Dict, List, Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. Running in simulation mode.")


class MultiSensorReader:
    """Read multiple digital sensors via GPIO pins"""
    
    def __init__(self, config: dict, force_simulation: bool = False):
        """
        Initialize multi-sensor reader
        
        Args:
            config: Configuration dictionary with sensors settings
            force_simulation: If True, force simulation mode regardless of GPIO availability
        """
        self.sensors = config['sensors']
        self.sample_rate_hz = config['sample_rate_hz']
        
        self.is_initialized = False
        self.sensor_states: Dict[str, bool] = {}
        self.simulation_mode = force_simulation
        self.simulation_counter = 0
        
        if not self.simulation_mode and not GPIO_AVAILABLE:
            raise RuntimeError("GPIO not available. Real sensor mode requires Raspberry Pi with GPIO support.")
        
        if not self.simulation_mode:
            self._initialize_gpio()
        else:
            print(f"Simulation mode: {len(self.sensors)} sensors (simulated)")
            self.is_initialized = True
            # Initialize simulation states
            for sensor in self.sensors:
                self.sensor_states[sensor['name']] = False
    
    def _initialize_gpio(self):
        """Initialize GPIO pins for all sensors"""
        try:
            # Set GPIO mode to BCM (Broadcom pin numbering)
            GPIO.setmode(GPIO.BCM)
            
            # Disable warnings about pins already in use
            GPIO.setwarnings(False)
            
            # Setup each sensor pin
            for sensor in self.sensors:
                gpio_pin = sensor['gpio_pin']
                pull_up = sensor.get('pull_up', True)
                
                if pull_up:
                    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                else:
                    GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                
                print(f"GPIO pin {gpio_pin} initialized for '{sensor['name']}'")
            
            self.is_initialized = True
            print(f"All {len(self.sensors)} sensors initialized successfully")
            
        except Exception as e:
            print(f"Error initializing GPIO: {e}")
            self.is_initialized = False
            raise
    
    def read_all(self) -> Dict[str, bool]:
        """
        Read all sensors
        
        Returns:
            dict: Dictionary mapping sensor names to their states (True/False)
        """
        if not self.is_initialized:
            return {sensor['name']: False for sensor in self.sensors}
        
        if self.simulation_mode:
            # Simulate sensor readings with different patterns
            self.simulation_counter += 1
            for i, sensor in enumerate(self.sensors):
                # Different simulation pattern for each sensor
                if i == 0:  # Level Low - toggles every 3 seconds
                    self.sensor_states[sensor['name']] = (self.simulation_counter % 3) == 0
                elif i == 1:  # Level Critical - toggles every 5 seconds
                    self.sensor_states[sensor['name']] = (self.simulation_counter % 5) == 0
                else:  # Cartridge - toggles every 7 seconds
                    self.sensor_states[sensor['name']] = (self.simulation_counter % 7) == 0
            
            return self.sensor_states.copy()
        
        try:
            # Read all GPIO pins
            for sensor in self.sensors:
                gpio_pin = sensor['gpio_pin']
                active_high = sensor.get('active_high', True)
                
                pin_state = GPIO.input(gpio_pin)
                
                # Convert to boolean based on active_high setting
                if active_high:
                    sensor_active = bool(pin_state)
                else:
                    sensor_active = not bool(pin_state)
                
                self.sensor_states[sensor['name']] = sensor_active
            
            return self.sensor_states.copy()
            
        except Exception as e:
            print(f"Error reading sensors: {e}")
            return {sensor['name']: False for sensor in self.sensors}
    
    def read_sensor(self, sensor_name: str) -> Optional[bool]:
        """
        Read a specific sensor by name
        
        Args:
            sensor_name: Name of the sensor to read
            
        Returns:
            bool: Sensor state, or None if sensor not found
        """
        states = self.read_all()
        return states.get(sensor_name)
    
    def get_sensor_names(self) -> List[str]:
        """
        Get list of all sensor names
        
        Returns:
            list: List of sensor names
        """
        return [sensor['name'] for sensor in self.sensors]
    
    def wait_for_sample_interval(self):
        """Wait for the configured sample interval"""
        if self.sample_rate_hz > 0:
            time.sleep(1.0 / self.sample_rate_hz)
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        if not self.simulation_mode and self.is_initialized:
            try:
                for sensor in self.sensors:
                    GPIO.cleanup(sensor['gpio_pin'])
                print(f"All {len(self.sensors)} GPIO pins cleaned up")
            except Exception as e:
                print(f"Error cleaning up GPIO: {e}")
        
        self.is_initialized = False
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()


if __name__ == "__main__":
    # Test the multi-sensor reader
    import yaml
    
    print("Testing MultiSensorReader...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create sensor reader
    reader = MultiSensorReader(config)
    
    print(f"Initialized: {reader.is_initialized}")
    print(f"Simulation mode: {reader.simulation_mode}")
    print(f"Sensors: {reader.get_sensor_names()}")
    
    # Read sensors 10 times
    print("\nReading sensors 10 times:")
    for i in range(10):
        states = reader.read_all()
        print(f"  Reading {i+1}:")
        for name, state in states.items():
            state_str = "HIGH" if state else "LOW"
            print(f"    {name}: {state_str}")
        time.sleep(1)
    
    # Cleanup
    reader.cleanup()
    print("\nTest complete!")

# Made with Bob
