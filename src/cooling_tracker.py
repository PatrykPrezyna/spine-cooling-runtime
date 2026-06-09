"""Tracks CSF temperature change while pump and compressor are both running."""

from typing import Optional


class CoolingEffectivenessTracker:
    """Detects when cooling runs for a long time without lowering CSF."""

    def __init__(self) -> None:
        self._active = False
        self._start_time: Optional[float] = None
        self._start_csf_c: Optional[float] = None

    def tick(
        self,
        *,
        pump: bool,
        compressor: bool,
        csf_temp: Optional[float],
        now: float,
    ) -> None:
        if pump and compressor and csf_temp is not None:
            if not self._active:
                self._active = True
                self._start_time = now
                self._start_csf_c = csf_temp
            return

        self._active = False
        self._start_time = None
        self._start_csf_c = None

    def is_ineffective(
        self,
        *,
        now: float,
        csf_temp: Optional[float],
        timeout_s: float,
        min_delta_c: float,
    ) -> bool:
        if not self._active or self._start_time is None or self._start_csf_c is None:
            return False
        if csf_temp is None:
            return False
        if now - self._start_time < timeout_s:
            return False
        return (self._start_csf_c - csf_temp) < min_delta_c
