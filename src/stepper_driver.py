"""STSPIN220 stepper motor driver module."""

import time
from threading import Lock
from typing import Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. STSPIN220 driver running in simulation mode.")


class STSPIN220Driver:
    """Stepper motor driver for the STMicroelectronics STSPIN220."""

    DRIVER_NAME = "STSPIN220"
    # MODE1..MODE4 latch patterns. MODE3/4 are sampled on STCK/DIR during STBY
    # release and become runtime STCK/DIR afterwards.
    _MICROSTEP_TO_MODE_BITS = {
        1: (0, 0, 0, 0),
        2: (1, 0, 0, 0),
        4: (0, 1, 0, 0),
        8: (1, 1, 0, 0),
        16: (0, 0, 1, 0),
        32: (1, 0, 1, 0),
        64: (0, 1, 1, 0),
        128: (1, 1, 1, 0),
        256: (0, 0, 0, 1),
    }
    SUPPORTED_MICROSTEPPING = tuple(sorted(_MICROSTEP_TO_MODE_BITS.keys()))

    def __init__(self, config: dict, force_simulation: bool = False):
        """
        Initialize the STSPIN220 driver.

        Args:
            config: Configuration dictionary. The relevant section is
                ``stepper_motor`` with ``driver: "STSPIN220"`` and a ``pins``
                sub-section containing ``en_fault``, ``stby_reset``, ``step``,
                and ``dir``.
            force_simulation: If True, skip hardware initialisation and run
                in simulation mode even when RPi.GPIO is available.
        """
        stepper_cfg = config.get('stepper_motor', {})
        pins_cfg = stepper_cfg.get('pins', {})

        self.pin_en_fault: int = pins_cfg.get('en_fault', 22)
        self.pin_stby_reset: int = pins_cfg.get('stby_reset', 4)
        self.pin_step: int = pins_cfg.get('step', 17)
        self.pin_dir: int = pins_cfg.get('dir', 27)
        # Keep MODE pins explicitly driven for deterministic full-step operation.
        self.pin_mode1: int = pins_cfg.get('mode1', 5)
        self.pin_mode2: int = pins_cfg.get('mode2', 6)
        self.steps_per_revolution: int = stepper_cfg.get('steps_per_revolution', 200)
        requested_microstepping = int(stepper_cfg.get('microstepping', 1))
        if requested_microstepping not in self._MICROSTEP_TO_MODE_BITS:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, "
                f"got {requested_microstepping}."
            )
        self.microstepping: int = requested_microstepping
        self.max_speed_rpm: float = stepper_cfg.get('max_speed_rpm', 60)
        self.max_position_steps: int = stepper_cfg.get('max_position_steps', 10000)
        self.home_position_steps: int = stepper_cfg.get('home_position_steps', 0)
        self.disable_on_idle: bool = stepper_cfg.get('disable_on_idle', True)
        self.enable_on_startup: bool = stepper_cfg.get('enable_on_startup', False)

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
        """Configure GPIO pins and latch selected microstep resolution."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for pin in (
                self.pin_stby_reset,
                self.pin_step,
                self.pin_dir,
                self.pin_mode1,
                self.pin_mode2,
            ):
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

            # EN/FAULT is open-drain on the STSPIN220 side. Configure it as an
            # input with pull-up so we can both drive it (as an output during
            # enable/disable) and read back the FAULT condition.
            GPIO.setup(self.pin_en_fault, GPIO.OUT, initial=GPIO.LOW)

            self._latch_microstepping_mode()

            self.is_initialized = True
            print(
                f"{self.DRIVER_NAME} initialized on GPIO "
                f"(EN/FAULT={self.pin_en_fault}, STBY={self.pin_stby_reset}, "
                f"STCK={self.pin_step}, DIR={self.pin_dir}, "
                f"MODE1={self.pin_mode1}, MODE2={self.pin_mode2}) "
                f"@ 1/{self.microstepping} step"
            )
        except Exception as exc:
            print(f"Error initializing {self.DRIVER_NAME}: {exc}")
            self.is_initialized = False
            raise

    def _latch_microstepping_mode(self) -> None:
        """
        Latch MODE1..MODE4 on STBY/RESET rising edge.

        STSPIN220 samples MODE bits on STBY/RESET release. MODE3 and MODE4 share
        pins with STCK and DIR respectively.
        """
        mode1, mode2, mode3, mode4 = self._MICROSTEP_TO_MODE_BITS[self.microstepping]
        GPIO.output(self.pin_stby_reset, GPIO.LOW)
        GPIO.output(self.pin_mode1, GPIO.HIGH if mode1 else GPIO.LOW)
        GPIO.output(self.pin_mode2, GPIO.HIGH if mode2 else GPIO.LOW)
        GPIO.output(self.pin_step, GPIO.HIGH if mode3 else GPIO.LOW)
        GPIO.output(self.pin_dir, GPIO.HIGH if mode4 else GPIO.LOW)
        time.sleep(0.000002)
        GPIO.output(self.pin_stby_reset, GPIO.HIGH)
        time.sleep(0.001)
        # Return shared pins to runtime-safe idle states.
        GPIO.output(self.pin_step, GPIO.LOW)
        GPIO.output(self.pin_dir, GPIO.LOW)

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

    def set_microstepping(self, microstepping: int) -> int:
        """
        Apply a new microstepping ratio and re-latch MODE bits.

        Returns the applied microstepping value.
        """
        requested = int(microstepping)
        if requested not in self._MICROSTEP_TO_MODE_BITS:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, got {requested}."
            )

        with self._lock:
            if requested == self.microstepping:
                return self.microstepping

            self.microstepping = requested
            if self.simulation_mode or not self.is_initialized:
                return self.microstepping

            was_enabled = self.enabled
            if was_enabled:
                GPIO.output(self.pin_en_fault, GPIO.LOW)
                self.enabled = False

            self._latch_microstepping_mode()

            if was_enabled:
                GPIO.output(self.pin_en_fault, GPIO.HIGH)
                self.enabled = True

            return self.microstepping

    def step(self, num_steps: int, speed_rpm: Optional[float] = None) -> int:
        """
        Move the motor by ``num_steps`` microsteps.

        Positive values step "forward" (DIR=HIGH), negative values step "reverse".
        Honors ``max_position_steps`` as a soft limit.

        Returns:
            int: Number of steps actually executed.
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
        """Move to an absolute step position."""
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
            for pin in (
                self.pin_en_fault,
                self.pin_stby_reset,
                self.pin_step,
                self.pin_dir,
                self.pin_mode1,
                self.pin_mode2,
            ):
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
    print(f"Moved {moved} steps -> position {driver.position_steps}")

    moved = driver.step(-200, speed_rpm=30)
    print(f"Moved {moved} steps -> position {driver.position_steps}")

    driver.home()
    print(f"After home -> position {driver.position_steps}")

    driver.disable()
    driver.cleanup()
    print("Test complete.")

# Made with Bob
