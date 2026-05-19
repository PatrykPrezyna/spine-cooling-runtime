"""Pulse/dir/enable stepper driver (TB6600/TB600 style) for Raspberry Pi.

STEP pulses are generated with pigpio DMA-timed waves only. The pigpio daemon
must be running (``sudo pigpiod``).
"""

import time
from threading import Event, Lock, Thread
from typing import Optional

try:
    import pigpio  # type: ignore

    _PIGPIO_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep at runtime
    pigpio = None  # type: ignore
    _PIGPIO_AVAILABLE = False


class PigpioUnavailableError(RuntimeError):
    """Raised when pigpio is required but the daemon is not reachable."""


class TB6600Driver:
    """
    Simple stepper driver using TB6600/TB600-style control lines:
    - STEP (PUL)
    - DIR
    - ENA
    """

    DRIVER_NAME = "TB6600"
    SUPPORTED_MICROSTEPPING = (1, 2, 4, 8, 16, 32, 64, 128, 256)
    _WAVE_CHUNK_PULSES = 1200
    _CONTINUOUS_CHUNK_SECONDS = 0.05

    def __init__(self, config: dict):
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
        self._continuous_direction: int = 1
        self._continuous_target_rpm: float = 0.0
        self._continuous_current_rpm: float = 0.0

        self._pi = None
        if not _PIGPIO_AVAILABLE:
            raise PigpioUnavailableError(
                f"{self.DRIVER_NAME}: pigpio Python module is not installed. "
                "Install pigpio and start the daemon with: sudo pigpiod"
            )
        try:
            pi = pigpio.pi()  # type: ignore[union-attr]
            if pi.connected:
                self._pi = pi
            else:
                try:
                    pi.stop()
                except Exception:
                    pass
        except Exception as exc:
            raise PigpioUnavailableError(
                f"{self.DRIVER_NAME}: pigpio daemon not reachable ({exc}). "
                "Start it with: sudo pigpiod"
            ) from exc

        if self._pi is None:
            raise PigpioUnavailableError(
                f"{self.DRIVER_NAME}: pigpio daemon is not connected. Start it with: sudo pigpiod"
            )

        self._initialize_gpio()
        self._log_startup_configuration()

        if self.enable_on_startup:
            self.enable()

    def _using_pigpio(self) -> bool:
        return self._pi is not None

    def _write_pin(self, pin: int, level: int) -> None:
        pi = self._pi
        assert pi is not None
        pi.write(pin, 1 if level else 0)

    def _initialize_gpio(self) -> None:
        """Configure GPIO pins for STEP, DIR and ENABLE outputs."""
        try:
            pi = self._pi
            assert pi is not None
            for pin in (self.pin_step, self.pin_dir, self.pin_enable):
                pi.set_mode(pin, pigpio.OUTPUT)  # type: ignore[union-attr]
                pi.write(pin, 0)
            pi.write(self.pin_enable, 1 if self._en_off_level_logical() else 0)
            self.is_initialized = True
            print(
                f"{self.DRIVER_NAME} initialized on GPIO "
                f"(ENA={self.pin_enable}, PUL={self.pin_step}, DIR={self.pin_dir}) "
                f"@ 1/{self.microstepping} step [backend=pigpio-dma-wave]"
            )
        except Exception as exc:
            print(f"Error initializing {self.DRIVER_NAME}: {exc}")
            self.is_initialized = False
            raise

    def cleanup(self) -> None:
        """Release GPIO resources and disable the driver."""
        self.stop_continuous()
        if not self.is_initialized:
            self._teardown_pigpio()
            return
        try:
            pi = self._pi
            assert pi is not None
            pi.wave_clear()
            pi.write(self.pin_step, 0)
            pi.write(self.pin_enable, 1 if self._en_off_level_logical() else 0)
            print(f"{self.DRIVER_NAME}: GPIO cleaned up")
        except Exception as exc:
            print(f"Error cleaning up {self.DRIVER_NAME}: {exc}")
        finally:
            self._teardown_pigpio()
            self.is_initialized = False
            self.enabled = False

    def _teardown_pigpio(self) -> None:
        if self._pi is not None:
            try:
                self._pi.stop()
            except Exception:
                pass
            self._pi = None

    def __del__(self):
        try:
            if self.is_initialized:
                self.cleanup()
        except Exception:
            pass

    def enable(self) -> None:
        with self._lock:
            self.enabled = True
            self.fault = False
            if self.is_initialized:
                self._write_pin(self.pin_enable, self._en_on_level_logical())

    def disable(self) -> None:
        with self._lock:
            self.enabled = False
            if self.is_initialized:
                self._write_pin(self.pin_enable, self._en_off_level_logical())

    def check_fault(self) -> bool:
        return self.fault

    def get_status(self) -> dict:
        return {
            'driver': self.DRIVER_NAME,
            'initialized': self.is_initialized,
            'enabled': self.enabled,
            'fault': self.fault,
            'position_steps': self.position_steps,
            'microstepping': self.microstepping,
            'pulses_per_revolution': self._pulses_per_revolution(),
            'en_active_high': self.en_active_high,
            'backend': 'pigpio-dma-wave',
        }

    def _log_startup_configuration(self) -> None:
        print(
            f"{self.DRIVER_NAME}: DMA wave stepping, "
            f"microstepping={self.microstepping} (verify TB6600 DIP matches config), "
            f"pulses/rev={self._pulses_per_revolution()}, "
            f"max_speed_rpm={self.max_speed_rpm}"
        )
        if self.microstepping != 16:
            print(
                f"{self.DRIVER_NAME}: WARNING microstepping is {self.microstepping}; "
                "config default is 16 — shaft RPM will be wrong if DIP switches differ."
            )

    def set_microstepping(self, microstepping: int) -> int:
        requested = int(microstepping)
        if requested not in self.SUPPORTED_MICROSTEPPING:
            raise ValueError(
                "Unsupported microstepping value. "
                f"Expected one of {list(self.SUPPORTED_MICROSTEPPING)}, got {requested}."
            )
        with self._lock:
            self.microstepping = requested
            return self.microstepping

    @staticmethod
    def _send_pulses_wave(
        pi: "pigpio.pi",
        step_pin: int,
        frequency_hz: float,
        pulse_count: int,
    ) -> None:
        """Send step pulses using pigpio DMA-timed waves."""
        if pulse_count <= 0:
            return
        frequency_hz = max(1.0, float(frequency_hz))
        period_us = max(4, int(round(1_000_000.0 / frequency_hz)))
        high_us = max(2, period_us // 2)
        low_us = max(2, period_us - high_us)
        base_pair = [
            pigpio.pulse(1 << step_pin, 0, high_us),  # type: ignore[union-attr]
            pigpio.pulse(0, 1 << step_pin, low_us),  # type: ignore[union-attr]
        ]
        remaining = int(pulse_count)
        while remaining > 0:
            chunk = min(TB6600Driver._WAVE_CHUNK_PULSES, remaining)
            pi.wave_clear()
            pi.wave_add_generic(base_pair * chunk)
            wave_id = pi.wave_create()
            if wave_id < 0:
                raise RuntimeError(f"pigpio wave_create failed with code {wave_id}")
            pi.wave_send_once(wave_id)
            while pi.wave_tx_busy():
                time.sleep(0.001)
            pi.wave_delete(wave_id)
            remaining -= chunk

    @staticmethod
    def _sleep_precise(delay_seconds: float) -> None:
        if delay_seconds <= 0:
            return
        if delay_seconds >= 0.0005:
            time.sleep(delay_seconds)
            return
        target = time.perf_counter() + delay_seconds
        while time.perf_counter() < target:
            time.sleep(0)

    def _pulses_per_revolution(self) -> int:
        return int(self.steps_per_revolution) * int(self.microstepping)

    def _resolve_speed_rpm(self, speed_rpm: Optional[float]) -> float:
        rpm = float(self.max_speed_rpm if speed_rpm is None else speed_rpm)
        max_rpm = max(0.1, float(self.max_speed_rpm))
        return max(0.1, min(rpm, max_rpm))

    def _frequency_from_rpm(self, rpm: float) -> float:
        return (float(rpm) / 60.0) * float(self._pulses_per_revolution())

    def _en_on_level_logical(self) -> int:
        return 1 if self.en_active_high else 0

    def _en_off_level_logical(self) -> int:
        return 0 if self.en_active_high else 1

    def step(
        self,
        num_steps: int,
        speed_rpm: Optional[float] = None,
        ramp_seconds: Optional[float] = None,
        start_rpm: Optional[float] = None,
    ) -> int:
        """Move the motor by ``num_steps`` microsteps using DMA wave pulses."""
        if num_steps == 0:
            return 0

        self.stop_continuous()

        with self._lock:
            if not self.is_initialized or not self.enabled or not self._using_pigpio():
                return 0

            pi = self._pi
            assert pi is not None
            direction = 1 if num_steps > 0 else -1
            remaining = abs(num_steps)

            target_rpm = self._resolve_speed_rpm(speed_rpm)
            applied_ramp_seconds = (
                self.ramp_seconds if ramp_seconds is None else max(0.0, float(ramp_seconds))
            )
            applied_start_rpm = self.ramp_start_rpm if start_rpm is None else float(start_rpm)
            applied_start_rpm = max(0.1, min(applied_start_rpm, target_rpm))

            self._write_pin(self.pin_dir, 1 if direction > 0 else 0)
            time.sleep(0.000002)

            if applied_ramp_seconds > 0:
                target_hz = self._frequency_from_rpm(target_rpm)
                ramp_steps = max(1, int(round(applied_ramp_seconds * target_hz)))
            else:
                ramp_steps = 0

            ramp_steps = min(ramp_steps, remaining)
            cruise_steps = remaining - ramp_steps

            if ramp_steps > 0:
                ramp_blocks = min(50, ramp_steps)
                for block in range(ramp_blocks):
                    start_idx = (block * ramp_steps) // ramp_blocks
                    end_idx = ((block + 1) * ramp_steps) // ramp_blocks
                    block_pulses = end_idx - start_idx
                    if block_pulses <= 0:
                        continue
                    alpha = (block + 1) / float(ramp_blocks)
                    block_rpm = applied_start_rpm + (target_rpm - applied_start_rpm) * alpha
                    self._send_pulses_wave(
                        pi, self.pin_step, self._frequency_from_rpm(block_rpm), block_pulses
                    )
                    self.position_steps += direction * block_pulses

            if cruise_steps > 0:
                self._send_pulses_wave(
                    pi,
                    self.pin_step,
                    self._frequency_from_rpm(target_rpm),
                    cruise_steps,
                )
                self.position_steps += direction * cruise_steps

            if self.disable_on_idle:
                self._write_pin(self.pin_enable, self._en_off_level_logical())
                self.enabled = False

            return direction * remaining

    def move_to(self, target_steps: int, speed_rpm: Optional[float] = None) -> int:
        delta = target_steps - self.position_steps
        return self.step(delta, speed_rpm=speed_rpm)

    def home(self, speed_rpm: Optional[float] = None) -> int:
        return self.move_to(0, speed_rpm=speed_rpm)

    def set_position(self, position_steps: int) -> None:
        with self._lock:
            self.position_steps = position_steps

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
        with self._lock:
            if not self._continuous_thread or not self._continuous_thread.is_alive():
                return
            self._continuous_target_rpm = self._resolve_speed_rpm(speed_rpm)

    def stop_continuous(self) -> None:
        with self._lock:
            self._stop_continuous_locked()

    def _stop_continuous_locked(self) -> None:
        self._continuous_stop_event.set()
        if self._using_pigpio() and self.is_initialized:
            try:
                pi = self._pi
                assert pi is not None
                pi.wave_clear()
                pi.write(self.pin_step, 0)
            except Exception:
                pass
        thread = self._continuous_thread
        if thread and thread.is_alive():
            thread.join(timeout=0.5)
        self._continuous_thread = None
        self._continuous_target_rpm = 0.0
        self._continuous_current_rpm = 0.0

    def _continuous_loop(self, ramp_seconds: float) -> None:
        """Background loop: DMA wave pulse chunks at the current target RPM."""
        pi = self._pi
        assert pi is not None

        ramp_duration = max(0.0, float(ramp_seconds))
        if ramp_duration > 0:
            ramp_rate_rpm_per_s = max(1.0, float(self.max_speed_rpm)) / ramp_duration
        else:
            ramp_rate_rpm_per_s = float("inf")

        chunk_seconds = self._CONTINUOUS_CHUNK_SECONDS

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
        try:
            pi.write(self.pin_dir, 1 if current_direction > 0 else 0)
            time.sleep(0.000002)
            while not self._continuous_stop_event.is_set():
                direction, target_rpm = current_state()
                if direction != current_direction:
                    current_direction = direction
                    pi.wave_clear()
                    pi.write(self.pin_step, 0)
                    pi.write(self.pin_dir, 1 if current_direction > 0 else 0)
                    time.sleep(0.000002)
                current_rpm = advance_ramp(target_rpm)
                frequency_hz = max(1.0, self._frequency_from_rpm(current_rpm))
                pulse_count = max(1, int(round(frequency_hz * chunk_seconds)))
                chunk_start = time.perf_counter()
                self._send_pulses_wave(pi, self.pin_step, frequency_hz, pulse_count)
                elapsed = time.perf_counter() - chunk_start
                sleep_remaining = chunk_seconds - elapsed
                if sleep_remaining > 0:
                    self._sleep_precise(sleep_remaining)
        finally:
            try:
                pi.wave_clear()
                pi.write(self.pin_step, 0)
            except Exception:
                pass


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
