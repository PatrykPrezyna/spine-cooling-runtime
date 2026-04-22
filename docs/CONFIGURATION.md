# Configuration Guide

## Overview

The medical device prototype uses YAML configuration files to manage all adjustable parameters. This allows for easy customization without modifying code.

## Configuration File Location

- **Default Configuration**: `config/default_config.yaml`
- **Hardware Pin Mapping**: `config/hardware_pins.yaml`
- **User Configuration**: `config/user_config.yaml` (optional, overrides defaults)

## Default Configuration Structure

### Complete Configuration Example

```yaml
# Medical Device Prototype - Default Configuration
# All parameters are adjustable to match your specific hardware setup

# ============================================================================
# HARDWARE CONFIGURATION
# ============================================================================

hardware:
  # UART Configuration for Compressor
  uart:
    port: "/dev/ttyAMA0"           # Serial port device
    baudrate: 9600                  # Adjustable: 9600, 19200, 38400, 57600, 115200
    timeout: 1.0                    # Read timeout in seconds
    bytesize: 8                     # Data bits
    parity: "N"                     # N=None, E=Even, O=Odd
    stopbits: 1                     # Stop bits
  
  # SPI Configuration for Thermocouples
  spi:
    bus: 0                          # SPI bus number (usually 0)
    device: 0                       # SPI device number
    max_speed_hz: 5000000          # SPI clock speed (5 MHz)
    mode: 0                         # SPI mode (0-3)
  
  # GPIO Pin Assignments
  gpio:
    # STSPIN220 Stepper Motor Driver Control
    stepper_pins:
      en_fault: 22                  # EN/FAULT   (active-high enable, open-drain fault)
      stby_reset: 4                 # STBY/RESET (active-low standby; latches MODE on release)
      step: 17                      # STCK/MODE3 (step clock, rising-edge)
      direction: 27                 # DIR/MODE4  (direction)
      mode1: 5                      # MODE1      (microstep select bit 1)
      mode2: 6                      # MODE2      (microstep select bit 2)
    
    # Level Sensors (digital inputs)
    level_sensors:
      - pin: 23
        name: "Upper Level Sensor"
        active_high: true           # true if sensor is HIGH when triggered
        pull_up: true               # Enable internal pull-up resistor
      - pin: 24
        name: "Lower Level Sensor"
        active_high: true
        pull_up: true
    
    # Additional GPIO for future expansion
    emergency_stop_pin: 25          # Emergency stop button
    status_led_pin: 26              # Status indicator LED

# ============================================================================
# SENSOR CONFIGURATION
# ============================================================================

sensors:
  # Thermocouple Configuration
  thermocouples:
    count: 4                        # Number of thermocouples (adjustable)
    chip_select_pins:               # CS pins for each MAX31855
      - 8                           # CE0 - First thermocouple
      - 7                           # CE1 - Second thermocouple
      - 25                          # GPIO25 - Third thermocouple
      - 16                          # GPIO16 - Fourth thermocouple
    
    names:                          # Descriptive names for each sensor
      - "Inlet Temperature"
      - "Outlet Temperature"
      - "Cooling Zone 1"
      - "Cooling Zone 2"
    
    sample_rate_hz: 1.0            # Sampling frequency (adjustable)
    averaging_samples: 3            # Number of samples to average
    
    # Fault detection
    fault_detection:
      enabled: true
      open_circuit_check: true
      short_circuit_check: true
      max_consecutive_faults: 3     # Trigger error after N faults

# ============================================================================
# TEMPERATURE THRESHOLDS
# ============================================================================

thresholds:
  temperature:
    # Operating limits (adjustable based on medical requirements)
    min_celsius: -5.0               # Minimum safe temperature
    max_celsius: 45.0               # Maximum safe temperature
    
    # Precooling target
    target_precool_celsius: 10.0    # Target temperature for precooling phase
    precool_tolerance: 2.0          # ±tolerance for reaching target
    
    # Normal operation range
    operation_range:
      min: 8.0                      # Minimum operating temperature
      max: 12.0                     # Maximum operating temperature
    
    # Warning thresholds
    warning_range:
      min: 6.0                      # Warning if below this
      max: 14.0                     # Warning if above this
    
    # Rate of change limits
    max_rate_celsius_per_minute: 5.0  # Maximum allowed temperature change rate
  
  # Timing Configuration
  timing:
    precool_timeout_seconds: 300    # Max time for precooling (5 minutes)
    operation_timeout_seconds: 7200 # Max continuous operation (2 hours)
    sensor_read_interval_ms: 1000   # How often to read sensors
    ui_update_interval_ms: 100      # UI refresh rate
    state_machine_loop_ms: 100      # State machine update rate
    watchdog_timeout_seconds: 5     # Watchdog timer threshold

# ============================================================================
# COMPRESSOR CONFIGURATION
# ============================================================================

compressor:
  # Command Protocol (adjustable based on your compressor)
  commands:
    start: "START\r\n"              # Command to start compressor
    stop: "STOP\r\n"                # Command to stop compressor
    status: "STATUS\r\n"            # Command to query status
    set_speed: "SPEED:{speed}\r\n"  # Command to set speed (if supported)
  
  # Expected Responses
  responses:
    running: "RUNNING"              # Response when compressor is running
    stopped: "STOPPED"              # Response when compressor is stopped
    error: "ERROR"                  # Response on error
  
  # Communication Settings
  response_timeout_seconds: 2.0     # Max time to wait for response
  retry_attempts: 3                 # Number of retries on failure
  retry_delay_seconds: 0.5          # Delay between retries
  
  # Operational Parameters
  startup_delay_seconds: 2.0        # Wait time after start command
  shutdown_delay_seconds: 3.0       # Wait time after stop command
  min_runtime_seconds: 60           # Minimum continuous run time
  cooldown_period_seconds: 30       # Cooldown before restart

# ============================================================================
# STEPPER MOTOR CONFIGURATION
# ============================================================================

stepper_motor:
  # Driver selection
  driver: "STSPIN220"               # STMicroelectronics low-voltage stepper driver

  # Motor Specifications
  steps_per_revolution: 200         # Full steps per revolution (1.8° motor)
  microstepping: 16                 # STSPIN220 supports 1, 2, 4, 8, 16, 32, 64, 128, 256

  # Speed and Acceleration
  max_speed_rpm: 60                 # Maximum rotation speed
  acceleration_steps_per_sec2: 100  # Acceleration rate
  deceleration_steps_per_sec2: 100  # Deceleration rate

  # Position Control
  home_position_steps: 0            # Home position reference
  max_position_steps: 10000         # Maximum allowed position

  # Safety
  enable_on_startup: false          # Leave EN/FAULT LOW at boot (outputs tri-state)
  disable_on_idle: true             # Release EN/FAULT between moves
  idle_timeout_seconds: 30          # Time before auto-disable

  # STSPIN220 control line pin assignment (BCM numbering)
  pins:
    en_fault: 22                    # EN/FAULT   (active-high enable, open-drain fault)
    stby_reset: 4                   # STBY/RESET (active-low standby; latches MODE on release)
    step: 17                        # STCK/MODE3 (step clock, rising-edge)
    dir: 27                         # DIR/MODE4  (direction)
    mode1: 5                        # MODE1      (microstep select bit 1)
    mode2: 6                        # MODE2      (microstep select bit 2)

# ============================================================================
# DATA LOGGING CONFIGURATION
# ============================================================================

logging:
  # CSV File Settings
  csv_directory: "data/csv"         # Directory for CSV log files
  filename_format: "temp_log_%Y%m%d_%H%M%S.csv"  # Timestamp format
  
  # File Rotation
  rotation_size_mb: 10              # Rotate file after this size
  max_files: 100                    # Maximum number of log files to keep
  compress_old_files: true          # Compress rotated files
  
  # Logging Fields
  fields:
    - timestamp                     # ISO 8601 timestamp
    - state                         # Current system state
    - thermocouple_1                # Temperature readings
    - thermocouple_2
    - thermocouple_3
    - thermocouple_4
    - compressor_status             # ON/OFF/ERROR
    - compressor_runtime_seconds    # Total runtime
    - motor_position                # Current motor position
    - motor_speed_rpm               # Current motor speed
    - level_sensor_upper            # Upper level sensor state
    - level_sensor_lower            # Lower level sensor state
    - error_code                    # Error code if any
  
  # Logging Behavior
  log_interval_seconds: 1.0         # How often to write log entries
  buffer_size: 100                  # Number of entries to buffer
  flush_interval_seconds: 10        # How often to flush buffer to disk
  
  # System Logging
  system_log_file: "logs/system.log"
  system_log_level: "INFO"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
  system_log_rotation: "daily"      # daily, weekly, size-based

# ============================================================================
# USER INTERFACE CONFIGURATION
# ============================================================================

ui:
  # Display Settings
  display:
    width: 800                      # Display width in pixels
    height: 480                     # Display height in pixels
    fullscreen: true                # Run in fullscreen mode
    frameless: false                # Remove window frame
  
  # Theme and Colors
  theme:
    background_color: "#FFFFFF"
    text_color: "#000000"
    accent_color: "#007BFF"
    warning_color: "#FFC107"
    error_color: "#DC3545"
    success_color: "#28A745"
  
  # Font Settings
  fonts:
    family: "Arial"
    size_normal: 14
    size_large: 24
    size_xlarge: 48
  
  # Temperature Display
  temperature_display:
    decimal_places: 1               # Number of decimal places
    show_fahrenheit: false          # Also show Fahrenheit
    color_coding:
      enabled: true
      cold_threshold: 5.0           # Blue below this
      normal_min: 8.0               # Green in range
      normal_max: 12.0
      warm_threshold: 15.0          # Orange above this
      hot_threshold: 20.0           # Red above this
  
  # Button Configuration
  buttons:
    size: "large"                   # small, medium, large
    enable_touch: true              # Enable touch input
    enable_keyboard: true           # Enable keyboard shortcuts
    confirmation_required:          # Require confirmation for these actions
      - "start"
      - "stop"
      - "reset"
  
  # Update Rates
  refresh_rate_hz: 10               # UI refresh frequency
  animation_enabled: true           # Enable UI animations
  
  # Alerts and Notifications
  alerts:
    sound_enabled: false            # Enable alert sounds
    popup_timeout_seconds: 5        # Auto-close popups after this time
    show_warnings: true             # Show warning messages
    show_info: true                 # Show info messages

# ============================================================================
# STATE MACHINE CONFIGURATION
# ============================================================================

state_machine:
  # Initial State
  initial_state: "IDLE"
  
  # State Timeouts
  timeouts:
    initialization_seconds: 30      # Max time for initialization
    precooling_seconds: 300         # Max time for precooling
    operation_seconds: 7200         # Max continuous operation time
    shutdown_seconds: 60            # Max time for shutdown
  
  # Transition Delays
  transition_delays:
    idle_to_init: 0.5               # Delay before starting init
    init_to_precool: 1.0            # Delay before starting precool
    precool_to_operation: 2.0       # Delay before starting operation
    any_to_error: 0.0               # Immediate transition to error
  
  # Auto-transitions
  auto_transitions:
    enabled: false                  # Enable automatic state transitions
    precool_to_operation: false     # Auto-start operation after precool
    operation_to_shutdown: false    # Auto-shutdown after timeout

# ============================================================================
# SAFETY CONFIGURATION
# ============================================================================

safety:
  # Emergency Stop
  emergency_stop:
    enabled: true
    gpio_pin: 25                    # Emergency stop button pin
    active_low: true                # Button pulls pin LOW when pressed
  
  # Watchdog Timer
  watchdog:
    enabled: true
    timeout_seconds: 5              # Trigger error if no update
    auto_reset: false               # Auto-reset on timeout
  
  # Sensor Validation
  sensor_validation:
    enabled: true
    max_consecutive_errors: 3       # Error after N consecutive failures
    cross_check_enabled: true       # Compare sensor readings
    max_sensor_deviation: 5.0       # Max difference between sensors
  
  # Fail-Safe Actions
  fail_safe:
    on_sensor_failure: "ERROR"      # State to enter on sensor failure
    on_communication_failure: "ERROR"  # State on comm failure
    on_temperature_limit: "ERROR"   # State on temp out of range
    on_timeout: "ERROR"             # State on operation timeout
  
  # Recovery Options
  recovery:
    auto_recovery_enabled: false    # Attempt automatic recovery
    max_recovery_attempts: 3        # Max auto-recovery tries
    recovery_delay_seconds: 10      # Wait before recovery attempt

# ============================================================================
# ADVANCED SETTINGS
# ============================================================================

advanced:
  # Performance
  performance:
    thread_priority: "normal"       # low, normal, high
    cpu_affinity: null              # CPU core to bind to (null = any)
    nice_level: 0                   # Process priority (-20 to 19)
  
  # Debugging
  debug:
    enabled: false                  # Enable debug mode
    verbose_logging: false          # Extra verbose logs
    simulate_hardware: false        # Simulate hardware for testing
    mock_sensors: false             # Use mock sensor data
  
  # Network (for future remote monitoring)
  network:
    enabled: false
    port: 8080
    allow_remote_control: false
  
  # Backup and Recovery
  backup:
    auto_backup_config: true        # Backup config on changes
    backup_directory: "backups"
    max_backups: 10

# ============================================================================
# CALIBRATION DATA
# ============================================================================

calibration:
  # Thermocouple Calibration Offsets
  thermocouple_offsets:
    - 0.0                           # Offset for thermocouple 1 (°C)
    - 0.0                           # Offset for thermocouple 2 (°C)
    - 0.0                           # Offset for thermocouple 3 (°C)
    - 0.0                           # Offset for thermocouple 4 (°C)
  
  # Motor Calibration
  motor_calibration:
    steps_per_mm: 100               # Steps per millimeter (if linear)
    backlash_compensation: 0        # Backlash compensation steps
  
  # Last Calibration Date
  last_calibration_date: null       # ISO 8601 date
```

## Configuration Override

You can create a `config/user_config.yaml` file to override specific settings without modifying the default configuration:

```yaml
# User Configuration Override
# Only include settings you want to change

sensors:
  thermocouples:
    count: 6  # Override to use 6 thermocouples instead of 4

thresholds:
  temperature:
    target_precool_celsius: 8.0  # Different target temperature

compressor:
  commands:
    start: "ON\r\n"  # Different command format
    stop: "OFF\r\n"
```

## Loading Configuration

The system loads configuration in this order:
1. Default configuration (`default_config.yaml`)
2. User configuration (`user_config.yaml`) - overrides defaults
3. Command-line arguments - override both files

## Configuration Validation

The system validates all configuration parameters on startup:
- Range checks for numeric values
- Existence checks for file paths
- GPIO pin conflict detection
- Hardware capability verification

## Adjustable Parameters Summary

### Most Commonly Adjusted

| Parameter | Location | Purpose |
|-----------|----------|---------|
| `baudrate` | `hardware.uart.baudrate` | Match compressor communication speed |
| `count` | `sensors.thermocouples.count` | Number of temperature sensors |
| `target_precool_celsius` | `thresholds.temperature.target_precool_celsius` | Target cooling temperature |
| `min_celsius` / `max_celsius` | `thresholds.temperature` | Safe operating temperature range |
| `commands` | `compressor.commands` | Compressor control protocol |

### Hardware-Specific

| Parameter | Location | Purpose |
|-----------|----------|---------|
| `chip_select_pins` | `sensors.thermocouples.chip_select_pins` | SPI CS pins for each sensor |
| `stepper_pins` | `hardware.gpio.stepper_pins` | STSPIN220 control pins (EN/FAULT, STBY/RESET, STCK, DIR, MODE1, MODE2) |
| `level_sensors` | `hardware.gpio.level_sensors` | Level sensor pins |

### Safety-Critical

| Parameter | Location | Purpose |
|-----------|----------|---------|
| `min_celsius` / `max_celsius` | `thresholds.temperature` | Absolute temperature limits |
| `watchdog.timeout_seconds` | `safety.watchdog` | System health monitoring |
| `max_consecutive_errors` | `safety.sensor_validation` | Fault tolerance |

## Best Practices

1. **Always backup** configuration before making changes
2. **Test changes** in simulation mode first (`advanced.debug.simulate_hardware: true`)
3. **Document changes** in comments within the YAML file
4. **Validate** configuration after changes using the validation tool
5. **Version control** your configuration files

## Configuration Tools

### Validation Tool
```bash
python -m src.utils.validate_config config/user_config.yaml
```

### Configuration Editor
```bash
python -m src.utils.config_editor
```

### Backup Tool
```bash
python -m src.utils.backup_config
```

## Troubleshooting

### Configuration Not Loading
- Check YAML syntax (indentation, colons, quotes)
- Verify file permissions
- Check for duplicate keys
- Review system logs for error messages

### Invalid Values
- Ensure numeric values are in valid ranges
- Check that file paths exist
- Verify GPIO pins are not conflicting
- Confirm hardware capabilities match settings

### Performance Issues
- Reduce `sample_rate_hz` if CPU usage is high
- Increase `sensor_read_interval_ms` for slower updates
- Disable `animation_enabled` for better performance
- Adjust `thread_priority` if needed