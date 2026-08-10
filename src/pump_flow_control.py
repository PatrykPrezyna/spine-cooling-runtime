"""Closed-loop pump flow control from CSF temperature error.

During active pumping:

- ``error = CSF - set_temp`` (°C; positive means CSF is warmer than target)
- ``error > full_speed_error_c`` → command max flow
- ``0 < error ≤ full_speed_error_c`` → simple PID mapped into [min, max] flow
- ``error ≤ 0`` → hold at minimum flow (still circulating during cooling)

Flow is commanded in ml/min; callers convert to stepper RPM with the
calibrated ``pump_flow_ml_per_min_per_rpm`` slope.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class PumpFlowControlConfig:
    max_flow_ml_per_min: float = 100.0
    min_flow_ml_per_min: float = 10.0
    full_speed_error_c: float = 0.5
    kp: float = 180.0
    ki: float = 40.0
    kd: float = 5.0
    integral_limit: float = 2.0


class PumpFlowController:
    """Compute commanded pump flow (ml/min) from CSF vs setpoint."""

    def __init__(self, config: Optional[PumpFlowControlConfig] = None):
        self.config = config or PumpFlowControlConfig()
        self._integral = 0.0
        self._prev_error: Optional[float] = None
        self._prev_time: Optional[float] = None
        self._last_flow_ml_per_min = float(self.config.min_flow_ml_per_min)

    @classmethod
    def from_config_dict(cls, raw: Optional[dict]) -> "PumpFlowController":
        raw = raw or {}
        cfg = PumpFlowControlConfig(
            max_flow_ml_per_min=float(raw.get("max_flow_ml_per_min", 100.0)),
            min_flow_ml_per_min=float(raw.get("min_flow_ml_per_min", 10.0)),
            full_speed_error_c=float(raw.get("full_speed_error_c", 0.5)),
            kp=float(raw.get("kp", 180.0)),
            ki=float(raw.get("ki", 40.0)),
            kd=float(raw.get("kd", 5.0)),
            integral_limit=float(raw.get("integral_limit", 2.0)),
        )
        if cfg.max_flow_ml_per_min < cfg.min_flow_ml_per_min:
            cfg.max_flow_ml_per_min = cfg.min_flow_ml_per_min
        if cfg.full_speed_error_c <= 0:
            cfg.full_speed_error_c = 0.5
        return cls(cfg)

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = None
        self._prev_time = None
        self._last_flow_ml_per_min = float(self.config.min_flow_ml_per_min)

    @property
    def last_flow_ml_per_min(self) -> float:
        return self._last_flow_ml_per_min

    def compute(
        self,
        csf_temp_c: float,
        set_temp_c: float,
        *,
        now_s: Optional[float] = None,
    ) -> float:
        """Return commanded flow in ml/min for the current temperature error."""
        cfg = self.config
        error = float(csf_temp_c) - float(set_temp_c)
        now = time.monotonic() if now_s is None else float(now_s)

        if self._prev_time is None:
            dt = 0.0
        else:
            dt = max(0.0, now - self._prev_time)
        self._prev_time = now

        if error > cfg.full_speed_error_c:
            self._integral = 0.0
            self._prev_error = error
            self._last_flow_ml_per_min = cfg.max_flow_ml_per_min
            return self._last_flow_ml_per_min

        if error <= 0.0:
            self._integral = 0.0
            self._prev_error = error
            self._last_flow_ml_per_min = cfg.min_flow_ml_per_min
            return self._last_flow_ml_per_min

        # PID only inside (0, full_speed_error_c].
        if dt > 0.0:
            self._integral += error * dt
            limit = abs(cfg.integral_limit)
            self._integral = max(-limit, min(limit, self._integral))

        derivative = 0.0
        if self._prev_error is not None and dt > 0.0:
            derivative = (error - self._prev_error) / dt
        self._prev_error = error

        # Bias at min flow so error→0 holds circulation; P term scales up to max.
        pid = cfg.kp * error + cfg.ki * self._integral + cfg.kd * derivative
        flow = cfg.min_flow_ml_per_min + pid
        flow = max(cfg.min_flow_ml_per_min, min(cfg.max_flow_ml_per_min, flow))
        self._last_flow_ml_per_min = flow
        return flow


def flow_ml_per_min_to_rpm(flow_ml_per_min: float, slope_ml_per_min_per_rpm: float) -> int:
    """Convert commanded flow to nearest stepper RPM using the linear calibration."""
    slope = float(slope_ml_per_min_per_rpm)
    if slope <= 0:
        return 1
    rpm = float(flow_ml_per_min) / slope
    return max(1, int(round(rpm)))
