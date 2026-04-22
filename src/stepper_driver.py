"""
STSPIN220 Stepper Motor Driver Module

Controls a stepper motor through an STMicroelectronics STSPIN220 low-voltage
stepper driver via Raspberry Pi GPIO pins.

The STSPIN220 uses the following control signals:
    - EN/FAULT    : Active-high enable input; also reports a fault when pulled low
                    by the driver (open-drain output).
    - STBY/RESET  : Active-low standby/reset line. Must be driven HIGH to leave
                    standby and accept step pulses.
    - STCK/MODE3  : Step clock input (rising-edge triggered). Doubles as MODE3
                    during the power-up microstep-latch sequence.
    - DIR/MODE4   : Direction input. Doubles as MODE4 during the power-up
                    microstep-latch sequence.
    - MODE1       : Microstep selector bit 1 (latched on STBY release).
    - MODE2       : Microstep selector bit 2 (latched on STBY release).

Microstepping is selected by driving MODE1..MODE4 to the desired pattern while
STBY/RESET is held LOW, then releasing STBY to latch the configuration. The
supported step resolutions are: full, 1/2, 1/4, 1/8, 1/16, 1/32, 1/64, 1/128
and 1/256 step.

If RPi.GPIO is unavailable (e.g. running on a workstation) the driver
transparently falls back to a simulation mode that tracks position without
touching hardware.
"""

import time
from threading import Lock
from typing import Dict, Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. STSPIN220 driver running in simulation mode.")


# Microstep selection table for the STSPIN220.
# Keys are the target step divisor, values are a 4-tuple of logic levels to
# apply to (MODE1, MODE2, MODE3/STCK, MODE4/DIR) while STBY/RESET is held LOW.
# Reference: STSPIN220 datasheet, Table 4 "Step mode selection".
STSPIN220_MICROSTEP_TABLE: Dict[int, tuple] = {
    1:   (0, 0, 0, 0),   # Full step
    2:   (1, 0, 1, 0),   # 1/2 step
    4:   (0, 1, 0, 1),   # 1/4 step
    8:   (1, 1, 0, 1),   # 1/8 step
    16:  (1, 1, 1, 0),   # 1/16 step
    32:  (1, 1, 1, 1),   # 1/32 step
    64:  (0, 1, 1, 1),   # 1/64 step
    128: (1, 0, 1, 1),   # 1/128 step
    256: (0, 0, 1, 1),   # 1/256 step
}


class STSPIN220Driver:
    """Stepper motor driver for the STMicroelectronics STSPIN220."""

    DRIVER_NAME = "STSPIN220"

    def __init__(self, config: dict, force_simulation: bool = False):
        """
        Initialize the STSPIN220 driver.

        Args:
            config: Configuration dictionary. The relevant section is
                ``stepper_motor`` with ``driver: "STSPIN220"`` and a ``pins``
                sub-section containing ``en_fault``, ``stby_reset``, ``step``,
                ``dir``, ``mode1`` and ``mode2``.
            force_simulation: If True, skip hardware initialisation and run
                in simulation mode even when RPi.GPIO is available.
        """
        stepper_cfg = config.get('stepper_motor', {})
        pins_cfg = stepper_cfg.get('pins', {})

        self.pin_en_fault: int = pins_cfg.get('en_fault', 22)
        self.pin_stby_reset: int = pins_cfg.get('stby_reset', 4)
        self.pin_step: int = pins_cfg.get('step', 17)
        self.pin_dir: int = pins_cfg.get('dir', 27)
        self.pin_mode1: int = pins_cfg.get('mode1', 5)
        self.pin_mode2: int = pins_cfg.get('mode2', 6)

        self.steps_per_revolution: int = stepper_cfg.get('steps_per_revolution', 200)
        self.microstepping: int = stepper_cfg.get('microstepping', 16)
        self.max_speed_rpm: float = stepper_cfg.get('max_speed_rpm', 60)
        self.max_position_steps: int = stepper_cfg.get('max_position_steps', 10000)
        self.home_position_steps: int = stepper_cfg.get('home_position_steps', 0)
        self.disable_on_idle: bool = stepper_cfg.get('disable_on_idle', True)
        self.enable_on_startup: bool = stepper_cfg.get('enable_on_startup', False)

        if self.microstepping not in STSPIN220_MICROSTEP_TABLE:
            valid = sorted(STSPIN220_MICROSTEP_TABLE.keys())
            raise ValueError(
                f"Unsupported microstepping '{self.microstepping}' for STSPIN220. "
                f"Valid values: {valid}"
            )

        self.simulation_mode: bool = force_simulation or not GPIO_AVAILABLE
        self.is_initialized: bool = False
        self.enabled: bool = False
        self.position_steps: int = self.home_position_steps
        self.fault: bool = False
        self._lock = Lock()

        if self.simulation_mode:
            print(f"{self.DRIVER_NAME}: simulation mode (no GPIO access)")
            self.is_initialized = True
        else:
            self._initialize_gpio()

        if self.enable_on_startup:
            self.enable()

    def _initialize_gpio(self) -> None:
        """Configure GPIO pins and latch the microstepping mode."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for pin in (self.pin_stby_reset, self.pin_step, self.pin_dir,
                        self.pin_mode1, self.pin_mode2):
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

            # EN/FAULT is open-drain on the STSPIN220 side. Configure it as an
            # input with pull-up so we can both drive it (as an output during
            # enable/disable) and read back the FAULT condition.
            GPIO.setup(self.pin_en_fault, GPIO.OUT, initial=GPIO.LOW)

            # Hold the driver in standby while we latch the microstep mode.
            GPIO.output(self.pin_stby_reset, GPIO.LOW)
            time.sleep(0.001)

            self._apply_microstep_mode(self.microstepping)

            # Release standby to latch the mode bits.
            GPIO.output(self.pin_stby_reset, GPIO.HIGH)
            time.sleep(0.001)

            self.is_initialized = True
            print(
                f"{self.DRIVER_NAME} initialized on GPIO "
                f"(EN/FAULT={self.pin_en_fault}, STBY={self.pin_stby_reset}, "
                f"STCK={self.pin_step}, DIR={self.pin_dir}, "
                f"MODE1={self.pin_mode1}, MODE2={self.pin_mode2}) "
                f"@ 1/{self.microstepping} microstep"
            )
        except Exception as exc:
            print(f"Error initializing {self.DRIVER_NAME}: {exc}")
            self.is_initialized = False
            raise

    def _apply_microstep_mode(self, microstepping: int) -> None:
        """Drive MODE1..MODE4 to the latch pattern for the requested resolution."""
        m1, m2, m3, m4 = STSPIN220_MICROSTEP_TABLE[microstepping]
        GPIO.output(self.pin_mode1, GPIO.HIGH if m1 else GPIO.LOW)
        GPIO.output(self.pin_mode2, GPIO.HIGH if m2 else GPIO.LOW)
        # STCK/DIR also serve as MODE3/MODE4 during the standby-release latch.
        GPIO.output(self.pin_step, GPIO.HIGH if m3 else GPIO.LOW)
        GPIO.output(self.pin_dir, GPIO.HIGH if m4 else GPIO.LOW)

    def set_microstepping(self, microstepping: int) -> None:
        """
        Change the microstep resolution. Requires cycling STBY/RESET so the
        STSPIN220 re-latches the MODE pins.
        """
        if microstepping not in STSPIN220_MICROSTEP_TABLE:
            raise ValueError(f"Unsupported microstepping '{microstepping}' for STSPIN220")

        with self._lock:
            self.microstepping = microstepping
            if self.simulation_mode or not self.is_initialized:
                return

            GPIO.output(self.pin_stby_reset, GPIO.LOW)
            time.sleep(0.001)
            self._apply_microstep_mode(microstepping)
            GPIO.output(self.pin_stby_reset, GPIO.HIGH)
            time.sleep(0.001)

    def enable(self) -> None:
        """Assert EN/FAULT HIGH to energise the motor coils."""
        with self._lock:
            self.enabled = True
            self.fault = False
            if not self.simulation_mode and self.is_initialized:
                GPIO.setup(self.pin_en_fault, GPIO.OUT)
                GPIO.output(self.pin_en_fault, GPIO.HIGH)

    def disable(self) -> None:
        """Release EN/FAULT so the coils are de-energised."""
        with self._lock:
            self.enabled = False
            if not self.simulation_mode and self.is_initialized:
                GPIO.output(self.pin_en_fault, GPIO.LOW)

    def check_fault(self) -> bool:
        """
        Read the EN/FAULT line. The STSPIN220 pulls it LOW when a thermal or
        over-current fault is active. Returns True if a fault is detected.
        """
        if self.simulation_mode or not self.is_initialized:
            return self.fault

        # Temporarily reconfigure EN/FAULT as an input with pull-up to sample
        # the driver's open-drain fault output, then restore the drive state.
        GPIO.setup(self.pin_en_fault, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        pin_state = GPIO.input(self.pin_en_fault)
        self.fault = (self.enabled and pin_state == GPIO.LOW)

        GPIO.setup(self.pin_en_fault, GPIO.OUT)
        GPIO.output(self.pin_en_fault, GPIO.HIGH if self.enabled else GPIO.LOW)

        return self.fault

    def _pulse_step(self, delay_seconds: float) -> None:
        """Emit a single STCK pulse."""
        GPIO.output(self.pin_step, GPIO.HIGH)
        time.sleep(delay_seconds)
        GPIO.output(self.pin_step, GPIO.LOW)
        time.sleep(delay_seconds)

    def _compute_pulse_delay(self, speed_rpm: Optional[float]) -> float:
        """Convert an RPM target into a half-period step delay in seconds."""
        rpm = speed_rpm if speed_rpm is not None else self.max_speed_rpm
        rpm = max(1.0, min(float(rpm), float(self.max_speed_rpm)))
        steps_per_second = (rpm / 60.0) * self.steps_per_revolution * self.microstepping
        if steps_per_second <= 0:
            return 0.001
        return 1.0 / (2.0 * steps_per_second)

    def step(self, num_steps: int, speed_rpm: Optional[float] = None) -> int:
        """
        Move the motor by ``num_steps`` microsteps.

        Positive values step "forward" (DIR=HIGH), negative values step "reverse".
        Honors ``max_position_steps`` as a soft limit.

        Returns:
            int: Number of microsteps actually executed.
        """
        if num_steps == 0:
            return 0

        with self._lock:
            if not self.is_initialized:
                return 0
            if not self.enabled:
                if not self.simulation_mode:
                    return 0
                # In simulation mode, auto-enable for convenience.
                self.enabled = True

            direction = 1 if num_steps > 0 else -1
            remaining = abs(num_steps)

            # Clamp against the configured soft limit.
            target = self.position_steps + direction * remaining
            if target > self.max_position_steps:
                remaining = max(0, self.max_position_steps - self.position_steps)
            elif target < 0:
                remaining = max(0, self.position_steps)

            if remaining == 0:
                return 0

            delay = self._compute_pulse_delay(speed_rpm)

            if self.simulation_mode:
                self.position_steps += direction * remaining
                return direction * remaining

            GPIO.output(self.pin_dir, GPIO.HIGH if direction > 0 else GPIO.LOW)
            time.sleep(0.000002)  # t_setup(DIR) per datasheet

            for _ in range(remaining):
                self._pulse_step(delay)
                self.position_steps += direction

            if self.disable_on_idle:
                # Release enable so the motor is not held energised between moves.
                GPIO.output(self.pin_en_fault, GPIO.LOW)
                self.enabled = False

            return direction * remaining

    def move_to(self, target_steps: int, speed_rpm: Optional[float] = None) -> int:
        """Move to an absolute microstep position."""
        delta = target_steps - self.position_steps
        return self.step(delta, speed_rpm=speed_rpm)

    def home(self, speed_rpm: Optional[float] = None) -> int:
        """Move to the configured home position."""
        return self.move_to(self.home_position_steps, speed_rpm=speed_rpm)

    def set_position(self, position_steps: int) -> None:
        """Manually override the tracked position (e.g. after homing)."""
        with self._lock:
            self.position_steps = position_steps

    def get_status(self) -> dict:
        """Return a snapshot of the driver state suitable for the UI."""
        return {
            'driver': self.DRIVER_NAME,
            'initialized': self.is_initialized,
            'simulation': self.simulation_mode,
            'enabled': self.enabled,
            'fault': self.fault,
            'position_steps': self.position_steps,
            'microstepping': self.microstepping,
        }

    def cleanup(self) -> None:
        """Release GPIO resources and leave the driver in standby."""
        if self.simulation_mode or not self.is_initialized:
            self.is_initialized = False
            return
        try:
            GPIO.output(self.pin_en_fault, GPIO.LOW)
            GPIO.output(self.pin_stby_reset, GPIO.LOW)
            for pin in (self.pin_en_fault, self.pin_stby_reset, self.pin_step,
                        self.pin_dir, self.pin_mode1, self.pin_mode2):
                GPIO.cleanup(pin)
            print(f"{self.DRIVER_NAME}: GPIO cleaned up")
        except Exception as exc:
            print(f"Error cleaning up {self.DRIVER_NAME}: {exc}")
        finally:
            self.is_initialized = False
            self.enabled = False

    def __del__(self):
        if self.is_initialized:
            self.cleanup()


if __name__ == "__main__":
    import yaml

    print("Testing STSPIN220Driver...")

    with open('config.yaml', 'r') as f:
        cfg = yaml.safe_load(f)

    driver = STSPIN220Driver(cfg, force_simulation=True)
    print("Status:", driver.get_status())

    driver.enable()
    moved = driver.step(400, speed_rpm=30)
    print(f"Moved {moved} microsteps -> position {driver.position_steps}")

    moved = driver.step(-200, speed_rpm=30)
    print(f"Moved {moved} microsteps -> position {driver.position_steps}")

    driver.home()
    print(f"After home -> position {driver.position_steps}")

    driver.disable()
    driver.cleanup()
    print("Test complete.")

# Made with Bob
