# Implementation Guide

## Overview

This guide provides step-by-step instructions for implementing the medical device prototype system. Follow these steps in order to build a complete, working system.

## Implementation Phases

### Phase 1: Foundation (Week 1)
- Setup project structure
- Implement configuration management
- Create base hardware interfaces
- Setup logging system

### Phase 2: Hardware Integration (Week 2)
- Implement thermocouple interface
- Implement UART compressor control
- Implement stepper motor control
- Implement level sensor interface

### Phase 3: State Machine (Week 3)
- Implement state definitions
- Implement state transitions
- Implement state machine controller
- Add safety checks

### Phase 4: User Interface (Week 4)
- Create main window layout
- Implement temperature display widgets
- Implement control panel
- Add state visualization

### Phase 5: Testing & Refinement (Week 5)
- Unit testing
- Integration testing
- Hardware-in-loop testing
- Performance optimization

## Detailed Implementation Steps

### Step 1: Project Setup

#### 1.1 Create Directory Structure
```bash
# Create all directories
mkdir -p src/{state_machine,hardware,ui/{widgets,dialogs},data,utils,simulation}
mkdir -p config data/{csv,backups} logs tests/{unit,integration,fixtures}
mkdir -p docs scripts systemd

# Create __init__.py files
touch src/__init__.py
touch src/state_machine/__init__.py
touch src/hardware/__init__.py
touch src/ui/__init__.py
touch src/ui/widgets/__init__.py
touch src/ui/dialogs/__init__.py
touch src/data/__init__.py
touch src/utils/__init__.py
touch src/simulation/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/fixtures/__init__.py

# Create .gitkeep for empty directories
touch data/csv/.gitkeep
touch data/backups/.gitkeep
touch logs/.gitkeep
```

#### 1.2 Create Configuration Files
```bash
# Copy configuration template from docs/CONFIGURATION.md
# Create config/default_config.yaml with all parameters
# Create config/hardware_pins.yaml with pin mappings
```

#### 1.3 Setup Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### Step 2: Configuration Management

#### 2.1 Implement Config Manager (`src/data/config_manager.py`)

**Key Features:**
- Load YAML configuration files
- Merge default and user configs
- Validate all parameters
- Provide easy access to config values

**Implementation Priority:**
1. Basic YAML loading
2. Configuration validation
3. Override mechanism
4. Error handling

**Example Structure:**
```python
class ConfigManager:
    def __init__(self, config_path: str):
        """Load and validate configuration"""
        
    def get(self, key_path: str, default=None):
        """Get configuration value by dot-notation path"""
        
    def validate(self) -> bool:
        """Validate all configuration parameters"""
        
    def reload(self):
        """Reload configuration from disk"""
```

### Step 3: Hardware Abstraction Layer

#### 3.1 Base Hardware Interface (`src/hardware/base.py`)

**Purpose:** Common interface for all hardware devices

**Key Methods:**
- `initialize()`: Setup hardware
- `shutdown()`: Clean shutdown
- `is_ready()`: Check if hardware is operational
- `get_status()`: Get current status
- `handle_error()`: Error handling

#### 3.2 Temperature Manager (`src/hardware/temperature.py`)

**Implementation Steps:**
1. Initialize SPI interface
2. Configure MAX31855 chip select pins
3. Implement temperature reading
4. Add fault detection
5. Implement averaging/filtering
6. Add calibration offset support

**Key Features:**
- Multiple thermocouple support
- Fault detection (open/short circuit)
- Temperature validation
- Configurable sampling rate

**Testing:**
- Test with ice bath (0°C)
- Test with boiling water (100°C)
- Test fault detection
- Test multiple sensors

#### 3.3 Compressor Manager (`src/hardware/compressor.py`)

**Implementation Steps:**
1. Initialize UART interface
2. Implement command sending
3. Implement response parsing
4. Add timeout handling
5. Add retry logic
6. Implement status monitoring

**Key Features:**
- Configurable baud rate
- Command/response protocol
- Timeout and retry
- Status tracking

**Testing:**
- Test start/stop commands
- Test status queries
- Test timeout handling
- Test error recovery

#### 3.4 Stepper Motor Manager (`src/hardware/stepper.py`)

**Implementation Steps:**
1. Initialize GPIO pins
2. Implement step pulse generation
3. Add direction control
4. Implement speed control
5. Add acceleration/deceleration
6. Implement position tracking

**Key Features:**
- Step/direction interface
- Speed and acceleration control
- Position feedback
- Enable/disable control

**Testing:**
- Test basic stepping
- Test direction changes
- Test speed control
- Test position accuracy

#### 3.5 Level Sensor Manager (`src/hardware/level_sensors.py`)

**Implementation Steps:**
1. Initialize GPIO input pins
2. Configure pull-up/pull-down
3. Implement debouncing
4. Add state change detection
5. Implement callback system

**Key Features:**
- Multiple sensor support
- Debouncing
- State change callbacks
- Configurable active level

**Testing:**
- Test sensor reading
- Test debouncing
- Test state changes
- Test callbacks

### Step 4: State Machine Implementation

#### 4.1 State Definitions (`src/state_machine/states.py`)

**States to Implement:**
1. **IDLE**: Waiting for user to start
2. **INITIALIZATION**: System self-check
3. **PRECOOLING**: Cooling to target temperature
4. **OPERATION**: Normal operation
5. **PAUSED**: Temporarily suspended
6. **SHUTDOWN**: Controlled shutdown
7. **ERROR**: Error condition

**For Each State:**
- Entry action (what to do when entering)
- Update action (what to do each loop)
- Exit action (what to do when leaving)
- Allowed transitions

#### 4.2 State Transitions (`src/state_machine/transitions.py`)

**Transition Logic:**
- Validate transition is allowed
- Check transition conditions
- Execute transition actions
- Update system state

**Transition Guards:**
- Temperature in range
- Sensors operational
- Hardware ready
- User confirmation

#### 4.3 State Machine Controller (`src/state_machine/controller.py`)

**Implementation Steps:**
1. Initialize all hardware managers
2. Load configuration
3. Setup state machine
4. Implement main control loop
5. Add user command handling
6. Implement safety monitoring

**Main Loop:**
```python
def update(self):
    """Main control loop iteration"""
    # 1. Read all sensors
    # 2. Check safety conditions
    # 3. Update current state
    # 4. Process user commands
    # 5. Update hardware outputs
    # 6. Log data
```

### Step 5: Data Logging

#### 5.1 Data Logger (`src/data/logger.py`)

**Implementation Steps:**
1. Create CSV file with headers
2. Implement buffered writing
3. Add file rotation
4. Implement timestamp formatting
5. Add error handling

**Key Features:**
- Configurable fields
- Automatic file rotation
- Buffer management
- Timestamp precision

**CSV Format:**
```csv
timestamp,state,temp_1,temp_2,temp_3,temp_4,compressor,motor_pos,level_upper,level_lower
2026-04-17T14:30:00.123Z,OPERATION,10.5,11.2,10.8,11.0,ON,1500,1,1
```

### Step 6: User Interface

#### 6.1 Main Window (`src/ui/main_window.py`)

**Layout Structure:**
```
┌─────────────────────────────────────┐
│  Title Bar with State               │
├─────────────────────────────────────┤
│  Temperature Panel                  │
├─────────────────────────────────────┤
│  Status Panel                       │
├─────────────────────────────────────┤
│  Control Panel                      │
├─────────────────────────────────────┤
│  Status Message                     │
└─────────────────────────────────────┘
```

**Implementation Steps:**
1. Create main window class
2. Setup layout
3. Add widget containers
4. Connect to state machine
5. Implement update timer
6. Add event handlers

#### 6.2 Temperature Panel (`src/ui/widgets/temperature_panel.py`)

**Features:**
- Display all thermocouple readings
- Color-coded temperature values
- Large, readable fonts
- Update in real-time

**Implementation:**
- Grid layout for multiple sensors
- QLabel for each temperature
- Color coding based on thresholds
- Decimal formatting

#### 6.3 Status Panel (`src/ui/widgets/status_panel.py`)

**Features:**
- Compressor status
- Motor status
- Level sensor status
- System health indicators

**Implementation:**
- Icon-based status display
- Text labels
- Color indicators
- Real-time updates

#### 6.4 Control Panel (`src/ui/widgets/control_panel.py`)

**Features:**
- START button
- PAUSE button
- STOP button
- RESET button
- Emergency stop

**Implementation:**
- Large touch-friendly buttons
- Confirmation dialogs
- Button enable/disable based on state
- Visual feedback

#### 6.5 State Indicator (`src/ui/widgets/state_indicator.py`)

**Features:**
- Visual representation of current state
- State transition animation
- Color coding
- State name display

**Implementation:**
- Custom widget
- State-to-color mapping
- Smooth transitions
- Clear typography

### Step 7: Safety Systems

#### 7.1 Safety Checks (`src/utils/safety.py`)

**Implement:**
- Temperature limit checking
- Sensor validation
- Communication timeout detection
- Hardware fault detection

**Safety Functions:**
```python
def check_temperature_limits(temps: List[float]) -> bool:
    """Verify all temperatures within safe range"""

def validate_sensors(sensor_data: dict) -> bool:
    """Check sensor readings are valid"""

def check_communication(last_response_time: float) -> bool:
    """Verify communication is active"""
```

#### 7.2 Watchdog Timer (`src/utils/watchdog.py`)

**Implementation:**
- Periodic heartbeat
- Timeout detection
- Automatic error state
- Recovery mechanism

### Step 8: Testing

#### 8.1 Unit Tests

**Test Coverage:**
- Configuration loading
- Hardware interfaces (mocked)
- State machine logic
- Data logging
- Safety checks

**Example Test:**
```python
def test_temperature_reading():
    """Test temperature sensor reading"""
    temp_mgr = TemperatureManager(mock_spi)
    temp = temp_mgr.read_temperature(0)
    assert -5.0 <= temp <= 45.0
```

#### 8.2 Integration Tests

**Test Scenarios:**
- Complete state machine flow
- Hardware coordination
- UI updates
- Data logging
- Error handling

#### 8.3 Hardware Tests

**Test Procedures:**
- Sensor calibration
- Motor movement
- Compressor control
- Level sensor response
- Emergency stop

### Step 9: Deployment

#### 9.1 Installation Script (`scripts/install.sh`)

**Steps:**
1. Check system requirements
2. Install dependencies
3. Configure hardware interfaces
4. Setup systemd service
5. Create log directories
6. Set permissions

#### 9.2 Systemd Service (`systemd/spine-cooling.service`)

**Service Configuration:**
```ini
[Unit]
Description=Spine Cooling Medical Device
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/spine-cooling-runtime
ExecStart=/home/pi/spine-cooling-runtime/venv/bin/python -m src.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 9.3 Startup Procedure

**Sequence:**
1. Load configuration
2. Initialize hardware
3. Run self-test
4. Start UI
5. Enter IDLE state
6. Wait for user

#### 9.4 Shutdown Procedure

**Sequence:**
1. Stop compressor
2. Stop motor
3. Save final log entry
4. Close hardware interfaces
5. Cleanup GPIO
6. Exit application

## Implementation Checklist

### Foundation
- [ ] Project directory structure created
- [ ] Configuration files created
- [ ] Virtual environment setup
- [ ] Dependencies installed
- [ ] Git repository initialized

### Configuration
- [ ] ConfigManager implemented
- [ ] YAML loading working
- [ ] Validation implemented
- [ ] Override mechanism working

### Hardware Layer
- [ ] Base hardware interface defined
- [ ] Temperature manager implemented
- [ ] Compressor manager implemented
- [ ] Stepper motor manager implemented
- [ ] Level sensor manager implemented
- [ ] GPIO manager implemented

### State Machine
- [ ] All states defined
- [ ] State behaviors implemented
- [ ] Transitions implemented
- [ ] Controller implemented
- [ ] Safety checks integrated

### Data Management
- [ ] Data logger implemented
- [ ] CSV writing working
- [ ] File rotation working
- [ ] Buffer management working

### User Interface
- [ ] Main window created
- [ ] Temperature panel implemented
- [ ] Status panel implemented
- [ ] Control panel implemented
- [ ] State indicator implemented
- [ ] Dialogs implemented

### Safety
- [ ] Safety checks implemented
- [ ] Watchdog timer implemented
- [ ] Emergency stop working
- [ ] Error handling complete

### Testing
- [ ] Unit tests written
- [ ] Integration tests written
- [ ] Hardware tests performed
- [ ] Test coverage >80%

### Deployment
- [ ] Installation script created
- [ ] Systemd service configured
- [ ] Startup procedure tested
- [ ] Shutdown procedure tested
- [ ] Documentation complete

## Development Tips

### 1. Start Simple
- Implement basic functionality first
- Add features incrementally
- Test each component thoroughly

### 2. Use Simulation Mode
- Develop without hardware
- Mock all hardware interfaces
- Test logic independently

### 3. Incremental Testing
- Test each component as you build
- Don't wait until the end
- Fix issues immediately

### 4. Document As You Go
- Add docstrings to all functions
- Update documentation
- Keep README current

### 5. Version Control
- Commit frequently
- Use meaningful commit messages
- Tag stable versions

## Common Pitfalls

### 1. GPIO Conflicts
- Track all pin assignments
- Check for conflicts
- Document pin usage

### 2. SPI Communication
- Verify wiring
- Check clock speed
- Test with known good device

### 3. UART Issues
- Disable console on serial
- Check baud rate
- Verify voltage levels

### 4. Threading Issues
- Use proper synchronization
- Avoid race conditions
- Test under load

### 5. Memory Leaks
- Close files properly
- Cleanup GPIO on exit
- Monitor memory usage

## Performance Optimization

### 1. Sensor Reading
- Batch SPI transactions
- Use appropriate sampling rate
- Implement efficient filtering

### 2. UI Updates
- Update only when changed
- Use appropriate refresh rate
- Avoid blocking operations

### 3. Data Logging
- Use buffered writes
- Batch log entries
- Rotate files efficiently

### 4. State Machine
- Optimize loop timing
- Minimize processing
- Use efficient data structures

## Next Steps After Implementation

1. **Validation Testing**
   - Extensive hardware testing
   - Long-duration testing
   - Stress testing

2. **Calibration**
   - Sensor calibration
   - Motor calibration
   - Timing calibration

3. **Documentation**
   - User manual
   - Maintenance guide
   - Troubleshooting guide

4. **Certification** (if required)
   - Medical device standards
   - Safety certifications
   - Regulatory compliance

5. **Production Preparation**
   - Manufacturing documentation
   - Quality control procedures
   - Support infrastructure