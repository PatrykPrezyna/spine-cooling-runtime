"""Simulated stepper driver (no pigpio, no background thread)."""

from __future__ import annotations

from typing import Optional


class SimStepperDriver:
    """Logs stepper commands instead of driving GPIO."""

    DRIVER_NAME = "SimStepper"

    def __init__(self, config: dict):
        stepper_cfg = config.get("stepper_motor", {})
        self.max_speed_rpm: float = float(stepper_cfg.get("max_speed_rpm", 60))
        self.disable_on_idle: bool = bool(stepper_cfg.get("disable_on_idle", True))
        self.is_initialized = True
        self.enabled = False
        self._continuous_direction: int = 1
        self._continuous_speed_rpm: float = 0.0
        print(f"{self.DRIVER_NAME}: ready (simulation mode)")

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def start_continuous(
        self,
        direction: int = 1,
        speed_rpm: Optional[float] = None,
        ramp_seconds: Optional[float] = None,
        start_rpm: Optional[float] = None,
    ) -> None:
        del ramp_seconds, start_rpm
        self._continuous_direction = 1 if direction >= 0 else -1
        self._continuous_speed_rpm = float(speed_rpm or 0.0)
        self.enabled = True
        print(
            f"{self.DRIVER_NAME}: continuous "
            f"dir={self._continuous_direction} rpm={self._continuous_speed_rpm:.1f}"
        )

    def stop_continuous(self) -> None:
        self._continuous_speed_rpm = 0.0
        if self.disable_on_idle:
            self.enabled = False
        print(f"{self.DRIVER_NAME}: stop continuous")

    def set_continuous_speed(self, speed_rpm: float) -> None:
        self._continuous_speed_rpm = min(float(speed_rpm), self.max_speed_rpm)
        print(f"{self.DRIVER_NAME}: speed -> {self._continuous_speed_rpm:.1f} rpm")

    def cleanup(self) -> None:
        self.enabled = False
        self.is_initialized = False
        print(f"{self.DRIVER_NAME}: cleanup")
