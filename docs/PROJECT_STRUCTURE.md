# Project Structure

## Directory Layout

```
spine-cooling-runtime/
│
├── config/                          # Configuration files
│   ├── default_config.yaml         # Default system configuration
│   ├── hardware_pins.yaml          # Hardware pin mappings
│   └── user_config.yaml            # User overrides (optional)
│
├── src/                            # Source code
│   ├── __init__.py
│   ├── main.py                     # Application entry point
│   │
│   ├── state_machine/              # State machine implementation
│   │   ├── __init__.py
│   │   ├── controller.py           # Main state machine controller
│   │   ├── states.py               # State definitions and behaviors
│   │   └── transitions.py          # State transition logic
│   │
│   ├── hardware/                   # Hardware interface layer
│   │   ├── __init__.py
│   │   ├── base.py                 # Base hardware interface class
│   │   ├── temperature.py          # Thermocouple/MAX31855 interface
│   │   ├── compressor.py           # Compressor UART interface
│   │   ├── stepper.py              # Stepper motor control
│   │   ├── level_sensors.py        # Level sensor interface
│   │   └── gpio_manager.py         # GPIO pin management
│   │
│   ├── ui/                         # User interface
│   │   ├── __init__.py
│   │   ├── main_window.py          # Main application window
│   │   ├── styles.py               # UI styling and themes
│   │   │
│   │   ├── widgets/                # Custom UI widgets
│   │   │   ├── __init__.py
│   │   │   ├── temperature_panel.py    # Temperature display widget
│   │   │   ├── status_panel.py         # System status widget
│   │   │   ├── control_panel.py        # Control buttons widget
│   │   │   ├── state_indicator.py      # State visualization widget
│   │   │   └── chart_widget.py         # Temperature chart widget
│   │   │
│   │   └── dialogs/                # Dialog windows
│   │       ├── __init__.py
│   │       ├── error_dialog.py         # Error message dialog
│   │       ├── config_dialog.py        # Configuration editor dialog
│   │       ├── calibration_dialog.py   # Calibration wizard
│   │       └── about_dialog.py         # About/info dialog
│   │
│   ├── data/                       # Data management
│   │   ├── __init__.py
│   │   ├── logger.py               # CSV data logger
│   │   ├── config_manager.py       # Configuration loader/validator
│   │   └── database.py             # Future: Database interface
│   │
│   ├── utils/                      # Utility modules
│   │   ├── __init__.py
│   │   ├── validators.py           # Input validation functions
│   │   ├── formatters.py           # Data formatting utilities
│   │   ├── safety.py               # Safety check functions
│   │   └── watchdog.py             # Watchdog timer implementation
│   │
│   └── simulation/                 # Hardware simulation (for testing)
│       ├── __init__.py
│       ├── mock_hardware.py        # Mock hardware interfaces
│       └── test_scenarios.py       # Predefined test scenarios
│
├── data/                           # Data storage
│   ├── csv/                        # CSV log files
│   │   └── .gitkeep
│   └── backups/                    # Configuration backups
│       └── .gitkeep
│
├── logs/                           # System logs
│   ├── system.log                  # Main system log
│   └── error.log                   # Error log
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── conftest.py                 # Pytest configuration
│   │
│   ├── unit/                       # Unit tests
│   │   ├── __init__.py
│   │   ├── test_state_machine.py
│   │   ├── test_temperature.py
│   │   ├── test_compressor.py
│   │   ├── test_stepper.py
│   │   ├── test_logger.py
│   │   └── test_config.py
│   │
│   ├── integration/                # Integration tests
│   │   ├── __init__.py
│   │   ├── test_hardware_integration.py
│   │   ├── test_state_transitions.py
│   │   └── test_ui_integration.py
│   │
│   └── fixtures/                   # Test fixtures and data
│       ├── __init__.py
│       ├── sample_configs.py
│       └── mock_data.py
│
├── docs/                           # Documentation
│   ├── ARCHITECTURE.md             # System architecture
│   ├── HARDWARE_SETUP.md           # Hardware setup guide
│   ├── CONFIGURATION.md            # Configuration guide
│   ├── PROJECT_STRUCTURE.md        # This file
│   ├── API_REFERENCE.md            # API documentation
│   ├── USER_MANUAL.md              # User manual
│   ├── DEVELOPMENT.md              # Development guide
│   └── TROUBLESHOOTING.md          # Troubleshooting guide
│
├── scripts/                        # Utility scripts
│   ├── install.sh                  # Installation script
│   ├── setup_raspberry_pi.sh       # Raspberry Pi setup
│   ├── start_service.sh            # Start as service
│   ├── stop_service.sh             # Stop service
│   ├── backup_config.sh            # Backup configuration
│   ├── validate_hardware.py        # Hardware validation
│   └── calibrate_sensors.py        # Sensor calibration
│
├── systemd/                        # Systemd service files
│   └── spine-cooling.service       # Service definition
│
├── .gitignore                      # Git ignore rules
├── .env.example                    # Environment variables example
├── requirements.txt                # Python dependencies
├── requirements-dev.txt            # Development dependencies
├── setup.py                        # Package setup
├── pytest.ini                      # Pytest configuration
├── README.md                       # Project README
└── LICENSE                         # License file
```

## Module Descriptions

### Core Application (`src/`)

#### `main.py`
- Application entry point
- Initializes all subsystems
- Starts the main event loop
- Handles graceful shutdown

#### State Machine (`src/state_machine/`)

**`controller.py`**
- Main state machine controller
- Coordinates state transitions
- Manages system lifecycle
- Handles user commands

**`states.py`**
- Defines all system states (IDLE, INITIALIZATION, PRECOOLING, etc.)
- Implements state-specific behaviors
- Entry/exit actions for each state

**`transitions.py`**
- State transition logic
- Transition validation
- Transition guards and conditions

#### Hardware Layer (`src/hardware/`)

**`base.py`**
- Base class for all hardware interfaces
- Common error handling
- Hardware abstraction patterns

**`temperature.py`**
- MAX31855 thermocouple interface
- SPI communication
- Temperature reading and validation
- Fault detection

**`compressor.py`**
- UART communication with compressor
- Command/response protocol
- Status monitoring
- Error handling

**`stepper.py`**
- Stepper motor control
- Step/direction interface
- Speed and acceleration control
- Position tracking

**`level_sensors.py`**
- Digital level sensor interface
- Debouncing logic
- State change detection

**`gpio_manager.py`**
- Centralized GPIO management
- Pin allocation and conflict detection
- Cleanup on shutdown

#### User Interface (`src/ui/`)

**`main_window.py`**
- Main application window
- Layout management
- Widget coordination
- Event handling

**`widgets/`**
- Reusable UI components
- Temperature displays
- Status indicators
- Control buttons
- Real-time charts

**`dialogs/`**
- Modal dialog windows
- Error messages
- Configuration editor
- Calibration wizard

#### Data Management (`src/data/`)

**`logger.py`**
- CSV file logging
- File rotation
- Buffer management
- Timestamp formatting

**`config_manager.py`**
- YAML configuration loading
- Configuration validation
- Override management
- Default value handling

#### Utilities (`src/utils/`)

**`validators.py`**
- Input validation functions
- Range checking
- Type validation
- Configuration validation

**`safety.py`**
- Safety check implementations
- Temperature limit validation
- Sensor fault detection
- Emergency shutdown logic

**`watchdog.py`**
- Watchdog timer implementation
- System health monitoring
- Automatic recovery

### Testing (`tests/`)

#### Unit Tests (`tests/unit/`)
- Test individual components in isolation
- Mock hardware interfaces
- Fast execution

#### Integration Tests (`tests/integration/`)
- Test component interactions
- Hardware-in-loop testing
- State machine flow testing

### Documentation (`docs/`)

Comprehensive documentation covering:
- System architecture
- Hardware setup
- Configuration
- API reference
- User manual
- Development guide

### Scripts (`scripts/`)

Utility scripts for:
- System installation
- Service management
- Hardware validation
- Sensor calibration
- Configuration backup

## File Naming Conventions

### Python Files
- Use lowercase with underscores: `temperature_sensor.py`
- Test files: `test_<module_name>.py`
- Private modules: `_internal.py`

### Configuration Files
- Use lowercase with underscores: `default_config.yaml`
- Environment-specific: `config_production.yaml`

### Documentation
- Use UPPERCASE for main docs: `README.md`
- Use UPPERCASE with underscores: `USER_MANUAL.md`

## Import Structure

### Absolute Imports
```python
from src.hardware.temperature import TemperatureManager
from src.state_machine.controller import StateMachineController
from src.data.logger import DataLogger
```

### Relative Imports (within package)
```python
from .base import HardwareInterface
from ..utils.validators import validate_temperature
```

## Code Organization Principles

### 1. Separation of Concerns
- Hardware layer isolated from business logic
- UI separated from data processing
- Configuration separate from code

### 2. Dependency Injection
- Pass dependencies through constructors
- Avoid global state
- Enable easy testing

### 3. Single Responsibility
- Each module has one clear purpose
- Classes do one thing well
- Functions are focused and small

### 4. Interface Abstraction
- Hardware interfaces are abstract
- Easy to mock for testing
- Simulation mode support

## Configuration Files

### `config/default_config.yaml`
Complete default configuration with all parameters

### `config/hardware_pins.yaml`
Hardware-specific pin mappings (can be separate for different hardware revisions)

### `config/user_config.yaml`
User overrides (not in version control)

## Data Files

### CSV Logs (`data/csv/`)
- Timestamped temperature logs
- System event logs
- Automatic rotation

### Backups (`data/backups/`)
- Configuration backups
- Automatic backup on changes
- Timestamped archives

## Development Workflow

### 1. Local Development
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run in simulation mode
python -m src.main --simulate

# Run tests
pytest
```

### 2. Hardware Testing
```bash
# Validate hardware connections
python scripts/validate_hardware.py

# Calibrate sensors
python scripts/calibrate_sensors.py

# Run on actual hardware
python -m src.main
```

### 3. Deployment
```bash
# Install on Raspberry Pi
./scripts/install.sh

# Setup as service
sudo ./scripts/start_service.sh

# Check status
systemctl status spine-cooling
```

## Adding New Features

### Adding a New Hardware Device

1. Create interface in `src/hardware/new_device.py`
2. Inherit from `HardwareInterface` base class
3. Implement required methods
4. Add configuration to `default_config.yaml`
5. Add pin assignments to `hardware_pins.yaml`
6. Create unit tests in `tests/unit/test_new_device.py`
7. Update documentation

### Adding a New State

1. Define state in `src/state_machine/states.py`
2. Implement state behavior methods
3. Add transitions in `src/state_machine/transitions.py`
4. Update state machine controller
5. Add UI representation
6. Create tests
7. Update documentation

### Adding a New UI Widget

1. Create widget in `src/ui/widgets/new_widget.py`
2. Inherit from appropriate Qt base class
3. Implement update methods
4. Add to main window layout
5. Connect to data sources
6. Style appropriately
7. Test responsiveness

## Best Practices

### Code Style
- Follow PEP 8
- Use type hints
- Write docstrings
- Keep functions small

### Error Handling
- Use specific exceptions
- Log all errors
- Provide user-friendly messages
- Implement recovery where possible

### Testing
- Write tests first (TDD)
- Aim for >80% coverage
- Test edge cases
- Use fixtures for common setups

### Documentation
- Keep docs up to date
- Document all public APIs
- Include examples
- Explain "why" not just "what"

### Version Control
- Commit often
- Write clear commit messages
- Use feature branches
- Tag releases

## Dependencies

### Core Dependencies
- `PyQt6`: User interface
- `pyserial`: UART communication
- `spidev`: SPI communication
- `RPi.GPIO`: GPIO control
- `adafruit-circuitpython-max31855`: Thermocouple interface
- `PyYAML`: Configuration management

### Development Dependencies
- `pytest`: Testing framework
- `pytest-cov`: Coverage reporting
- `black`: Code formatting
- `flake8`: Linting
- `mypy`: Type checking

## Future Enhancements

### Planned Directory Additions
- `src/network/`: Remote monitoring
- `src/analytics/`: Data analysis
- `src/database/`: Database integration
- `docs/api/`: Auto-generated API docs
- `examples/`: Example configurations and scripts

### Planned Features
- Web interface
- Mobile app integration
- Cloud data sync
- Predictive maintenance
- Advanced analytics