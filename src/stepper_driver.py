"""Simple pulse/dir/enable stepper driver module (TB6600/TB600 style)."""

import time
from threading import Event, Thread
from threading import Lock
from typing import Optional

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available. Stepper driver running in simulation mode.")


class TB6600Driver:
    """
    Simple stepper driver using TB6600/TB600-style control lines:
    - STEP (PUL)
    - DIR
    - ENA
    """

    DRIVER_NAME = "TB6600"
    SUPPORTED_MICROSTEPPING = (1, 2, 4, 8, 16, 32, 64, 128, 256)

    def __init__(self, config: dict, force_simulation: bool = False):
        """
        Initialize the simplified pulse/dir/enable driver.

        Args:
            config: Configuration dictionary. The relevant section is
                ``stepper_motor`` with a ``pins`` sub-section containing
                ``pul/step``, ``dir``, and ``ena/en_fault``.
            force_simulation: If True, skip hardware initialisation and run
                in simulation mode even when RPi.GPIO is available.
        """
        stepper_cfg = config.get('stepper_motor', {})
        pins_cfg = stepper_cfg.get('pins', {})

        self.pin_enable: int = pins_cfg.get('ena', pins_cfg.get('en_fault', 24))
        self.pin_step: int = pins_cfg.get('pul', pins_cfg.get('step', 5))
        self.pin_dir: int = pins_cfg.get('dir', 25)
        self.en_active_high: bool = bool(stepper_cfg.get('en_active_high', True))
        self.steps_per_revolution: int = stepper_cfg.get('steps_per_revolution', 200)
        requested_microstepping = int(stepper_cfg.get('microstepping', 4))
        if requested_microstepping not in self.SUPPORTED_MICROSTEPPING:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, "
                f"got {requested_microstepping}."
            )
        self.microstepping: int = requested_microstepping
        self.max_speed_rpm: float = stepper_cfg.get('max_speed_rpm', 60)
        self.disable_on_idle: bool = stepper_cfg.get('disable_on_idle', True)
        self.enable_on_startup: bool = stepper_cfg.get('enable_on_startup', False)

        self.simulation_mode: bool = force_simulation or not GPIO_AVAILABLE
        self.is_initialized: bool = False
        self.enabled: bool = False
        self.position_steps: int = 0
        self.fault: bool = False
        self._lock = Lock()
        self._continuous_stop_event = Event()
        self._continuous_thread: Optional[Thread] = None

        if self.simulation_mode:
            print(f"{self.DRIVER_NAME}: simulation mode (no GPIO access)")
            self.is_initialized = True
        else:
            self._initialize_gpio()

        if self.enable_on_startup:
            self.enable()

    def _initialize_gpio(self) -> None:
        """Configure GPIO pins for STEP, DIR and ENABLE outputs."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for pin in (
                self.pin_step,
                self.pin_dir,
                self.pin_enable,
            ):
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

            GPIO.output(self.pin_enable, self._en_off_level())
            GPIO.output(self.pin_step, GPIO.LOW)
            GPIO.output(self.pin_dir, GPIO.LOW)

            self.is_initialized = True
            print(
                f"{self.DRIVER_NAME} initialized on GPIO "
                f"(ENA={self.pin_enable}, PUL={self.pin_step}, DIR={self.pin_dir}) "
                f"@ 1/{self.microstepping} step"
            )
        except Exception as exc:
            print(f"Error initializing {self.DRIVER_NAME}: {exc}")
            self.is_initialized = False
            raise

    def enable(self) -> None:
        """Assert ENA to energise the motor coils."""
        with self._lock:
            self.enabled = True
            self.fault = False
            if not self.simulation_mode and self.is_initialized:
                GPIO.output(self.pin_enable, self._en_on_level())

    def disable(self) -> None:
        """Release ENA so the coils are de-energised."""
        with self._lock:
            self.enabled = False
            if not self.simulation_mode and self.is_initialized:
                GPIO.output(self.pin_enable, self._en_off_level())

    def check_fault(self) -> bool:
        """
        Return current fault state.

        Simple external drivers usually do not expose a fault pin on ENA.
        Keeping this API for compatibility with the UI/main loop.
        """
        return self.fault

    def _pulse_step(self, period_seconds: float) -> None:
        """
        Emit a single step pulse paced by a target pulse period.

        Using a full-period budget (instead of two symmetric sleeps) keeps the
        achieved speed closer to the requested RPM because GPIO/loop overhead is
        accounted for inside the period.
        """
        pulse_high_seconds = min(0.00001, period_seconds / 2.0)
        start = time.perf_counter()
        GPIO.output(self.pin_step, GPIO.HIGH)
        self._sleep_precise(pulse_high_seconds)
        GPIO.output(self.pin_step, GPIO.LOW)
        elapsed = time.perf_counter() - start
        remaining = period_seconds - elapsed
        if remaining > 0:
            self._sleep_precise(remaining)

    @staticmethod
    def _sleep_precise(delay_seconds: float) -> None:
        """
        Sleep with better precision for short pulse timings.

        `time.sleep()` is often too coarse for sub-millisecond delays used at
        higher microstepping ratios, which makes the motor appear much slower
        than requested. For short waits we busy-wait on perf_counter.
        """
        if delay_seconds <= 0:
            return
        if delay_seconds >= 0.0005:
            time.sleep(delay_seconds)
            return

        target = time.perf_counter() + delay_seconds
        while time.perf_counter() < target:
            # Cooperative yield helps avoid periodic long stalls under load.
            time.sleep(0)

    def _compute_step_period(self, speed_rpm: Optional[float]) -> float:
        """Convert an RPM target into a per-step period in seconds."""
        rpm = speed_rpm if speed_rpm is not None else self.max_speed_rpm
        rpm = max(1.0, min(float(rpm), float(self.max_speed_rpm)))
        steps_per_second = (rpm / 60.0) * self.steps_per_revolution * self.microstepping
        if steps_per_second <= 0:
            return 0.001
        return 1.0 / steps_per_second

    def set_microstepping(self, microstepping: int) -> int:
        """
        Apply a new microstepping ratio.

        Returns the applied microstepping value.
        """
        requested = int(microstepping)
        if requested not in self.SUPPORTED_MICROSTEPPING:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, got {requested}."
            )

        with self._lock:
            if requested == self.microstepping:
                return self.microstepping

            # For simple drivers microstepping is typically set via DIP switches.
            # We still store user-selected value so speed calculations remain
            # coherent with the configured mechanical behavior.
            self.microstepping = requested
            return self.microstepping

    def step(self, num_steps: int, speed_rpm: Optional[float] = None) -> int:
        """
        Move the motor by ``num_steps`` microsteps.

        Positive values step "forward" (DIR=HIGH), negative values step "reverse".

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

            step_period = self._compute_step_period(speed_rpm)

            if self.simulation_mode:
                self.position_steps += direction * remaining
                return direction * remaining

            GPIO.output(self.pin_dir, GPIO.HIGH if direction > 0 else GPIO.LOW)
            time.sleep(0.000002)

            for _ in range(remaining):
                self._pulse_step(step_period)
                self.position_steps += direction

            if self.disable_on_idle:
                GPIO.output(self.pin_enable, self._en_off_level())
                self.enabled = False

            return direction * remaining

    def start_continuous(self, direction: int = 1, speed_rpm: Optional[float] = None) -> None:
        """Start uninterrupted continuous stepping in a background loop."""
        with self._lock:
            if not self.is_initialized:
                return
            if not self.enabled:
                if self.simulation_mode:
                    self.enabled = True
                else:
                    self.enable()
            if self._continuous_thread and self._continuous_thread.is_alive():
                return
            self._continuous_stop_event.clear()
            run_direction = 1 if direction >= 0 else -1
            run_speed = speed_rpm if speed_rpm is not None else self.max_speed_rpm
            self._continuous_thread = Thread(
                target=self._continuous_loop,
                args=(run_direction, float(run_speed)),
                name="stepper_continuous_loop",
                daemon=True,
            )
            self._continuous_thread.start()

    def stop_continuous(self) -> None:
        """Stop continuous stepping loop."""
        self._continuous_stop_event.set()
        thread = self._continuous_thread
        if thread and thread.is_alive():
            thread.join(timeout=0.5)
        self._continuous_thread = None

    def _continuous_loop(self, direction: int, speed_rpm: float) -> None:
        """Background step loop used for true continuous movement."""
        step_period = self._compute_step_period(speed_rpm)
        if self.simulation_mode:
            while not self._continuous_stop_event.is_set():
                self.position_steps += direction
                # Keep sim load light while still indicating movement.
                self._sleep_precise(min(0.002, step_period))
            return

        GPIO.output(self.pin_dir, GPIO.HIGH if direction > 0 else GPIO.LOW)
        time.sleep(0.000002)
        while not self._continuous_stop_event.is_set():
            self._pulse_step(step_period)
            self.position_steps += direction

    def move_to(self, target_steps: int, speed_rpm: Optional[float] = None) -> int:
        """Move to an absolute step position."""
        delta = target_steps - self.position_steps
        return self.step(delta, speed_rpm=speed_rpm)

    def home(self, speed_rpm: Optional[float] = None) -> int:
        """Move to position 0."""
        return self.move_to(0, speed_rpm=speed_rpm)

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
            'en_active_high': self.en_active_high,
        }

    def cleanup(self) -> None:
        """Release GPIO resources and disable the driver."""
        self.stop_continuous()
        if self.simulation_mode or not self.is_initialized:
            self.is_initialized = False
            return
        try:
            GPIO.output(self.pin_enable, self._en_off_level())
            for pin in (
                self.pin_enable,
                self.pin_step,
                self.pin_dir,
            ):
                GPIO.cleanup(pin)
            print(f"{self.DRIVER_NAME}: GPIO cleaned up")
        except Exception as exc:
            print(f"Error cleaning up {self.DRIVER_NAME}: {exc}")
        finally:
            self.is_initialized = False
            self.enabled = False

    def _en_on_level(self):
        return GPIO.HIGH if self.en_active_high else GPIO.LOW

    def _en_off_level(self):
        return GPIO.LOW if self.en_active_high else GPIO.HIGH

    def __del__(self):
        try:
            if self.is_initialized:
                self.cleanup()
        except Exception:
            # Avoid destructor-time exceptions during interpreter shutdown.
            pass


# Backward compatibility for existing imports in the app.
STSPIN220Driver = TB6600Driver


if __name__ == "__main__":
    import yaml

    print("Testing TB6600Driver...")

    with open('config.yaml', 'r') as f:
        cfg = yaml.safe_load(f)

    driver = TB6600Driver(cfg, force_simulation=True)
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


