"""
Digital Sensor Reader Module
Reads digital level sensor via GPIO
"""

import time
from typing import Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. Running in simulation mode.")


class SensorReader:
    """Read digital level sensor via GPIO pin"""
    
    def __init__(self, config: dict):
        """
        Initialize sensor reader
        
        Args:
            config: Configuration dictionary with sensor settings
        """
        self.gpio_pin = config['sensor']['gpio_pin']
        self.sample_rate_hz = config['sensor']['sample_rate_hz']
        
        self.is_initialized = False
        self.last_state = None
        self.simulation_mode = not GPIO_AVAILABLE
        self.simulation_state = False
        
        if not self.simulation_mode:
            self._initialize_gpio()
        else:
            print(f"Simulation mode: GPIO pin {self.gpio_pin} (simulated)")
            self.is_initialized = True
    
    def _initialize_gpio(self):
        """Initialize GPIO pin for sensor reading"""
        try:
            # Set GPIO mode to BCM (Broadcom pin numbering)
            GPIO.setmode(GPIO.BCM)
            
            # Disable warnings about pins already in use
            GPIO.setwarnings(False)
            
            # Setup pin as input with pull-up or pull-down
            GPIO.setup(14, GPIO.IN)
            
            self.is_initialized = True
            print(f"GPIO pin {self.gpio_pin} initialized successfully")
            
        except Exception as e:
            print(f"Error initializing GPIO: {e}")
            self.is_initialized = False
            raise
    
    def read(self) -> bool:
        """
        Read current sensor state
        
        Returns:
            bool: True if sensor is active, False otherwise
        """
        if not self.is_initialized:
            return False
        
        if self.simulation_mode:
            # Simulate sensor reading (toggle every 5 seconds)
            if int(time.time()) % 5 < 2:
                self.simulation_state = True
            else:
                self.simulation_state = False
            return self.simulation_state
        
        try:
            # Read GPIO pin state
            pin_state = GPIO.input(self.gpio_pin)
            
            # Convert to boolean based on active_high setting
            if self.active_high:
                sensor_active = bool(pin_state)
            else:
                sensor_active = not bool(pin_state)
            
            self.last_state = sensor_active
            #state_text = "HIGH" if state == 1 else "LOW"
            #timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            #print(f"[{timestamp}] GPIO 14: {state_text} ({state})")
            return sensor_active
            
        except Exception as e:
            print(f"Error reading sensor: {e}")
            return False
    
    def get_state_string(self) -> str:
        """
        Get sensor state as string
        
        Returns:
            str: "HIGH" or "LOW"
        """
        state = self.read()
        return "HIGH" if state else "LOW"
    
    def wait_for_sample_interval(self):
        """Wait for the configured sample interval"""
        if self.sample_rate_hz > 0:
            time.sleep(1.0 / self.sample_rate_hz)
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        if not self.simulation_mode and self.is_initialized:
            try:
                GPIO.cleanup(self.gpio_pin)
                print(f"GPIO pin {self.gpio_pin} cleaned up")
            except Exception as e:
                print(f"Error cleaning up GPIO: {e}")
        
        self.is_initialized = False
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()


if __name__ == "__main__":
    # Test the sensor reader
    import yaml
    
    print("Testing SensorReader...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create sensor reader
    reader = SensorReader(config)
    
    print(f"Initialized: {reader.is_initialized}")
    print(f"Simulation mode: {reader.simulation_mode}")
    
    # Read sensor 10 times
    print("\nReading sensor 10 times:")
    for i in range(10):
        state = reader.read()
        state_str = reader.get_state_string()
        print(f"  Reading {i+1}: {state_str} ({state})")
        time.sleep(0.5)
    
    # Cleanup
    reader.cleanup()
    print("\nTest complete!")

# Made with Bob
