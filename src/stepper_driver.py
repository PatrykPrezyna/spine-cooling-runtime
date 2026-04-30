"""Pulse/dir/enable stepper driver (TB6600/TB600 style) for Raspberry Pi."""

import time
from threading import Event, Lock, Thread
from typing import Optional

import RPi.GPIO as GPIO


class TB6600Driver:
    """
    Simple stepper driver using TB6600/TB600-style control lines:
    - STEP (PUL)
    - DIR
    - ENA
    """

    DRIVER_NAME = "TB6600"
    SUPPORTED_MICROSTEPPING = (1, 2, 4, 8, 16, 32, 64, 128, 256)

    def __init__(self, config: dict):
        """
        Initialize the simplified pulse/dir/enable driver.

        Args:
            config: Configuration dictionary. The relevant section is
                ``stepper_motor`` with a ``pins`` sub-section containing
                ``pul/step``, ``dir``, and ``ena/en_fault``.
        """
        stepper_cfg = config.get('stepper_motor', {})
        pins_cfg = stepper_cfg.get('pins', {})

        self.pin_enable: int = pins_cfg.get('ena', pins_cfg.get('en_fault', 24))
        self.pin_step: int = pins_cfg.get('pul', pins_cfg.get('step', 5))
        self.pin_dir: int = pins_cfg.get('dir', 25)
        self.en_active_high: bool = bool(stepper_cfg.get('en_active_high', True))
        self.steps_per_revolution: int = stepper_cfg.get('steps_per_revolution', 200)
        if int(self.steps_per_revolution) <= 0:
            raise ValueError("steps_per_revolution must be > 0")
        requested_microstepping = int(stepper_cfg.get('microstepping', 4))
        if requested_microstepping not in self.SUPPORTED_MICROSTEPPING:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, "
                f"got {requested_microstepping}."
            )
        self.microstepping: int = requested_microstepping
        self.max_speed_rpm: float = stepper_cfg.get('max_speed_rpm', 60)
        self.ramp_seconds: float = float(stepper_cfg.get('ramp_seconds', 1.0))
        self.ramp_start_rpm: float = float(stepper_cfg.get('ramp_start_rpm', 5.0))
        self.disable_on_idle: bool = stepper_cfg.get('disable_on_idle', True)
        self.enable_on_startup: bool = stepper_cfg.get('enable_on_startup', False)
        if self.ramp_seconds < 0:
            raise ValueError("ramp_seconds must be >= 0")
        if self.ramp_start_rpm <= 0:
            raise ValueError("ramp_start_rpm must be > 0")

        self.is_initialized: bool = False
        self.enabled: bool = False
        self.position_steps: int = 0
        self.fault: bool = False
        self._lock = Lock()
        self._continuous_stop_event = Event()
        self._continuous_thread: Optional[Thread] = None
        self._continuous_pwm = None
        self._continuous_direction: int = 1
        self._continuous_target_rpm: float = 0.0
        self._continuous_current_rpm: float = 0.0

        self._initialize_gpio()

        if self.enable_on_startup:
            self.enable()

    # ------------------------------------------------------------------
    # GPIO setup / shutdown
    # ------------------------------------------------------------------
    def _initialize_gpio(self) -> None:
        """Configure GPIO pins for STEP, DIR and ENABLE outputs."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            for pin in (self.pin_step, self.pin_dir, self.pin_enable):
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

    def cleanup(self) -> None:
        """Release GPIO resources and disable the driver."""
        self.stop_continuous()
        if not self.is_initialized:
            return
        try:
            GPIO.output(self.pin_enable, self._en_off_level())
            for pin in (self.pin_enable, self.pin_step, self.pin_dir):
                GPIO.cleanup(pin)
            print(f"{self.DRIVER_NAME}: GPIO cleaned up")
        except Exception as exc:
            print(f"Error cleaning up {self.DRIVER_NAME}: {exc}")
        finally:
            self.is_initialized = False
            self.enabled = False

    def __del__(self):
        try:
            if self.is_initialized:
                self.cleanup()
        except Exception:
            # Avoid destructor-time exceptions during interpreter shutdown.
            pass

    # ------------------------------------------------------------------
    # Enable/disable + status
    # ------------------------------------------------------------------
    def enable(self) -> None:
        """Assert ENA to energise the motor coils."""
        with self._lock:
            self.enabled = True
            self.fault = False
            if self.is_initialized:
                GPIO.output(self.pin_enable, self._en_on_level())

    def disable(self) -> None:
        """Release ENA so the coils are de-energised."""
        with self._lock:
            self.enabled = False
            if self.is_initialized:
                GPIO.output(self.pin_enable, self._en_off_level())

    def check_fault(self) -> bool:
        """
        Return current fault state.

        Simple external drivers usually do not expose a fault pin on ENA.
        Keeping this API for compatibility with the UI/main loop.
        """
        return self.fault

    def get_status(self) -> dict:
        """Return a snapshot of the driver state suitable for the UI."""
        return {
            'driver': self.DRIVER_NAME,
            'initialized': self.is_initialized,
            'enabled': self.enabled,
            'fault': self.fault,
            'position_steps': self.position_steps,
            'microstepping': self.microstepping,
            'en_active_high': self.en_active_high,
        }

    def set_microstepping(self, microstepping: int) -> int:
        """Apply a new microstepping ratio. Returns the applied value."""
        requested = int(microstepping)
        if requested not in self.SUPPORTED_MICROSTEPPING:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, got {requested}."
            )

        with self._lock:
            # For simple drivers microstepping is typically set via DIP
            # switches. We still store the user-selected value so the speed
            # math stays coherent with the configured mechanical behavior.
            self.microstepping = requested
            return self.microstepping

    # ------------------------------------------------------------------
    # Pulse generation primitives
    # ------------------------------------------------------------------
    def _pulse_step(self, period_seconds: float) -> None:
        """Emit a single step pulse paced by a target pulse period."""
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
        """Sleep with better precision for short pulse timings."""
        if delay_seconds <= 0:
            return
        if delay_seconds >= 0.0005:
            time.sleep(delay_seconds)
            return
        target = time.perf_counter() + delay_seconds
        while time.perf_counter() < target:
            time.sleep(0)

    def _compute_step_period(self, speed_rpm: Optional[float]) -> float:
        """Convert an RPM target into a per-step period in seconds."""
        frequency_hz = self._frequency_from_rpm(self._resolve_speed_rpm(speed_rpm))
        if frequency_hz <= 0:
            return 0.001
        return 1.0 / frequency_hz

    def _pulses_per_revolution(self) -> int:
        """Return pulse count for one motor revolution at current microstepping."""
        return int(self.steps_per_revolution) * int(self.microstepping)

    def _resolve_speed_rpm(self, speed_rpm: Optional[float]) -> float:
        """Clamp requested speed to a safe positive RPM range."""
        rpm = float(self.max_speed_rpm if speed_rpm is None else speed_rpm)
        max_rpm = max(0.1, float(self.max_speed_rpm))
        return max(0.1, min(rpm, max_rpm))

    def _frequency_from_rpm(self, rpm: float) -> float:
        """Convert RPM to pulse frequency (Hz) using current microstepping."""
        return (float(rpm) / 60.0) * float(self._pulses_per_revolution())

    def _en_on_level(self):
        return GPIO.HIGH if self.en_active_high else GPIO.LOW

    def _en_off_level(self):
        return GPIO.LOW if self.en_active_high else GPIO.HIGH

    # ------------------------------------------------------------------
    # Finite-step move
    # ------------------------------------------------------------------
    def step(
        self,
        num_steps: int,
        speed_rpm: Optional[float] = None,
        ramp_seconds: Optional[float] = None,
        start_rpm: Optional[float] = None,
    ) -> int:
        """
        Move the motor by ``num_steps`` microsteps.

        Positive values step "forward" (DIR=HIGH), negative values step "reverse".

        Returns:
            int: Number of steps actually executed.
        """
        if num_steps == 0:
            return 0

        # Ensure continuous mode is not active before finite-step moves.
        self.stop_continuous()

        with self._lock:
            if not self.is_initialized or not self.enabled:
                return 0

            direction = 1 if num_steps > 0 else -1
            remaining = abs(num_steps)

            target_rpm = self._resolve_speed_rpm(speed_rpm)
            applied_ramp_seconds = (
                self.ramp_seconds if ramp_seconds is None else max(0.0, float(ramp_seconds))
            )
            applied_start_rpm = self.ramp_start_rpm if start_rpm is None else float(start_rpm)
            applied_start_rpm = max(0.1, min(applied_start_rpm, target_rpm))

            GPIO.output(self.pin_dir, GPIO.HIGH if direction > 0 else GPIO.LOW)
            time.sleep(0.000002)

            if applied_ramp_seconds > 0:
                target_hz = self._frequency_from_rpm(target_rpm)
                ramp_steps = max(1, int(round(applied_ramp_seconds * target_hz)))
            else:
                ramp_steps = 0

            for i in range(remaining):
                if ramp_steps > 0 and i < ramp_steps:
                    alpha = (i + 1) / float(ramp_steps)
                    current_rpm = applied_start_rpm + (target_rpm - applied_start_rpm) * alpha
                    step_period = self._compute_step_period(current_rpm)
                else:
                    step_period = self._compute_step_period(target_rpm)
                self._pulse_step(step_period)
                self.position_steps += direction

            if self.disable_on_idle:
                GPIO.output(self.pin_enable, self._en_off_level())
                self.enabled = False

            return direction * remaining

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

    # ------------------------------------------------------------------
    # Continuous stepping (background thread + PWM)
    # ------------------------------------------------------------------
    def start_continuous(
        self,
        direction: int = 1,
        speed_rpm: Optional[float] = None,
        ramp_seconds: Optional[float] = None,
        start_rpm: Optional[float] = None,
    ) -> None:
        """Start uninterrupted continuous stepping in a background loop."""
        with self._lock:
            if not self.is_initialized:
                return
            if not self.enabled:
                self.enable()
            # Stop existing continuous mode first so speed/direction can update.
            self._stop_continuous_locked()
            self._continuous_stop_event.clear()
            run_direction = 1 if direction >= 0 else -1
            run_speed = self._resolve_speed_rpm(speed_rpm)
            run_ramp_seconds = (
                self.ramp_seconds if ramp_seconds is None else max(0.0, float(ramp_seconds))
            )
            run_start_rpm = self.ramp_start_rpm if start_rpm is None else float(start_rpm)
            self._continuous_direction = run_direction
            self._continuous_target_rpm = run_speed
            self._continuous_current_rpm = max(0.1, min(run_start_rpm, run_speed))
            self._continuous_thread = Thread(
                target=self._continuous_loop,
                args=(run_ramp_seconds,),
                name="stepper_continuous_loop",
                daemon=True,
            )
            self._continuous_thread.start()

    def set_continuous_speed(self, speed_rpm: float) -> None:
        """Update continuous speed target without restarting motion."""
        with self._lock:
            if not self._continuous_thread or not self._continuous_thread.is_alive():
                return
            self._continuous_target_rpm = self._resolve_speed_rpm(speed_rpm)

    def stop_continuous(self) -> None:
        """Stop continuous stepping loop."""
        with self._lock:
            self._stop_continuous_locked()

    def _stop_continuous_locked(self) -> None:
        """Internal stop helper; caller must hold _lock."""
        self._continuous_stop_event.set()
        if self._continuous_pwm is not None:
            try:
                self._continuous_pwm.stop()
            except Exception:
                pass
            self._continuous_pwm = None
            if self.is_initialized:
                GPIO.output(self.pin_step, GPIO.LOW)
        thread = self._continuous_thread
        if thread and thread.is_alive():
            thread.join(timeout=0.5)
        self._continuous_thread = None
        self._continuous_target_rpm = 0.0
        self._continuous_current_rpm = 0.0

    def _continuous_loop(self, ramp_seconds: float) -> None:
        """Background step loop used for true continuous movement."""
        ramp_duration = max(0.0, float(ramp_seconds))
        if ramp_duration > 0:
            ramp_rate_rpm_per_s = max(1.0, float(self.max_speed_rpm)) / ramp_duration
        else:
            ramp_rate_rpm_per_s = float("inf")

        def current_state() -> tuple[int, float]:
            with self._lock:
                return self._continuous_direction, self._continuous_target_rpm

        last_tick = time.perf_counter()

        def advance_ramp(target_rpm: float) -> float:
            nonlocal last_tick
            now = time.perf_counter()
            dt = max(0.0, now - last_tick)
            last_tick = now
            current = self._continuous_current_rpm
            if not (ramp_rate_rpm_per_s < float("inf")):
                self._continuous_current_rpm = target_rpm
                return self._continuous_current_rpm
            delta = target_rpm - current
            max_delta = ramp_rate_rpm_per_s * dt
            if abs(delta) <= max_delta:
                self._continuous_current_rpm = target_rpm
            else:
                self._continuous_current_rpm = current + max_delta * (1.0 if delta > 0 else -1.0)
            return self._continuous_current_rpm

        current_direction, _ = current_state()
        GPIO.output(self.pin_dir, GPIO.HIGH if current_direction > 0 else GPIO.LOW)
        time.sleep(0.000002)
        initial_hz = max(1.0, self._frequency_from_rpm(self._continuous_current_rpm))
        self._continuous_pwm = GPIO.PWM(self.pin_step, initial_hz)
        self._continuous_pwm.start(50.0)
        while not self._continuous_stop_event.is_set():
            direction, target_rpm = current_state()
            if direction != current_direction:
                current_direction = direction
                if self._continuous_pwm is not None:
                    try:
                        self._continuous_pwm.stop()
                    except Exception:
                        pass
                    self._continuous_pwm = None
                GPIO.output(self.pin_step, GPIO.LOW)
                GPIO.output(self.pin_dir, GPIO.HIGH if current_direction > 0 else GPIO.LOW)
                time.sleep(0.000002)
                restart_hz = max(1.0, self._frequency_from_rpm(self._continuous_current_rpm))
                self._continuous_pwm = GPIO.PWM(self.pin_step, restart_hz)
                self._continuous_pwm.start(50.0)
            current_rpm = advance_ramp(target_rpm)
            if self._continuous_pwm is not None:
                target_hz = max(1.0, self._frequency_from_rpm(current_rpm))
                self._continuous_pwm.ChangeFrequency(target_hz)
            # Polling interval for smooth ramp updates without high CPU load.
            self._sleep_precise(0.02)


# Backward-compat alias for older imports in the app.
STSPIN220Driver = TB6600Driver


if __name__ == "__main__":
    import yaml

    print("Testing TB6600Driver...")

    with open('config.yaml', 'r') as f:
        cfg = yaml.safe_load(f)

    driver = TB6600Driver(cfg)
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
