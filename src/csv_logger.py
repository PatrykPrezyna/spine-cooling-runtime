"""
CSV Data Logger Module
Logs sensor data to CSV files with timestamps
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class CSVLogger:
    """Log sensor data to CSV files"""
    
    def __init__(self, config: dict):
        """
        Initialize CSV logger
        
        Args:
            config: Configuration dictionary with logging settings
        """
        self.csv_directory = config['logging']['csv_directory']
        self.filename_format = config['logging']['filename_format']
        
        self.csv_file: Optional[Path] = None
        self.csv_writer: Optional[csv.writer] = None
        self.file_handle = None
        self.is_logging = False
        self.temperature_columns = ["Body Temp", "Plate Temp", "Temp 3", "Temp 4"]
        
        # Create directory if it doesn't exist
        Path(self.csv_directory).mkdir(parents=True, exist_ok=True)
    
    def start_logging(self) -> bool:
        """
        Start logging to a new CSV file
        
        Returns:
            bool: True if logging started successfully
        """
        if self.is_logging:
            print("Warning: Logging already active")
            return False
        
        try:
            # Generate filename with timestamp
            timestamp = datetime.now().strftime(self.filename_format)
            self.csv_file = Path(self.csv_directory) / timestamp
            
            # Open file for writing
            self.file_handle = open(self.csv_file, 'w', newline='')
            self.csv_writer = csv.writer(self.file_handle)
            
            # Write header including thermocouple columns.
            self.csv_writer.writerow([
                'timestamp',
                'level_low',
                'level_critical',
                'cartridge_in_place',
                'body_temp_c',
                'plate_temp_c',
                'temp_3_c',
                'temp_4_c',
            ])
            self.file_handle.flush()
            
            self.is_logging = True
            print(f"Started logging to: {self.csv_file}")
            return True
            
        except Exception as e:
            print(f"Error starting logging: {e}")
            self.is_logging = False
            return False
    
    def log(self, sensor_states: dict, temperatures: Optional[dict] = None):
        """
        Log sensor readings
        
        Args:
            sensor_states: Dictionary of sensor names to states (True/False)
        """
        if not self.is_logging:
            return
        
        try:
            # Get current timestamp in ISO 8601 format
            timestamp = datetime.now().isoformat()
            
            # Convert boolean states to integers (1/0)
            level_low = 1 if sensor_states.get('Level Low', False) else 0
            level_critical = 1 if sensor_states.get('Level Critical', False) else 0
            cartridge = 1 if sensor_states.get('Cartridge In Place', False) else 0
            
            temperatures = temperatures or {}
            row = [timestamp, level_low, level_critical, cartridge]
            for column in self.temperature_columns:
                value = temperatures.get(column)
                row.append(f"{float(value):.3f}" if value is not None else "")

            # Write row
            self.csv_writer.writerow(row)
            
            # Flush to ensure data is written
            self.file_handle.flush()
            
        except Exception as e:
            print(f"Error logging data: {e}")
    
    def stop_logging(self):
        """Stop logging and close file"""
        if not self.is_logging:
            return
        
        try:
            if self.file_handle:
                self.file_handle.close()
                print(f"Stopped logging. File saved: {self.csv_file}")
            
            self.is_logging = False
            self.csv_writer = None
            self.file_handle = None
            
        except Exception as e:
            print(f"Error stopping logging: {e}")
    
    def get_log_file_path(self) -> Optional[str]:
        """
        Get current log file path
        
        Returns:
            str: Path to current log file, or None if not logging
        """
        if self.csv_file:
            return str(self.csv_file)
        return None
    
    def get_log_file_size(self) -> int:
        """
        Get current log file size in bytes
        
        Returns:
            int: File size in bytes, or 0 if not logging
        """
        if self.csv_file and self.csv_file.exists():
            return self.csv_file.stat().st_size
        return 0
    
    def __del__(self):
        """Destructor to ensure file is closed"""
        self.stop_logging()


if __name__ == "__main__":
    # Test the CSV logger
    import yaml
    import time
    
    print("Testing CSVLogger...")
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create logger
    logger = CSVLogger(config)
    
    # Start logging
    logger.start_logging()
    print(f"Log file: {logger.get_log_file_path()}")
    
    # Log some test data
    print("\nLogging test data...")
    for i in range(10):
        state = i % 2 == 0  # Alternate between True/False
        logger.log(
            {
                "Level Low": state,
                "Level Critical": not state,
                "Cartridge In Place": True,
            },
            {
                "Body Temp": 22.0 + i * 0.1,
                "Plate Temp": 23.0 + i * 0.1,
            },
        )
        print(f"  Logged sample {i + 1}")
        time.sleep(0.5)
    
    # Check file size
    print(f"\nLog file size: {logger.get_log_file_size()} bytes")
    
    # Stop logging
    logger.stop_logging()
    print("\nTest complete!")

# Made with Bob
