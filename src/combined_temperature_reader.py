"""Merge thermocouple and thermistor temperature readers into one facade."""

from __future__ import annotations

from typing import Any, Dict, Optional


class CombinedTemperatureReader:
    """Expose a single ``read_temperatures`` API over multiple backends."""

    def __init__(self, *readers: Any):
        self._readers = [r for r in readers if r is not None]
        self.last_error: Optional[str] = None

    def _primary_thermocouple(self) -> Any:
        """Return the first backend that looks like a thermocouple reader."""
        for reader in self._readers:
            if hasattr(reader, "_last_raw_temperatures") or hasattr(
                reader, "set_channel_two_point_calibration"
            ):
                return reader
        return self._readers[0] if self._readers else None

    def __getattr__(self, name: str) -> Any:
        # Forward sim/test helpers (e.g. _last_raw_temperatures) to the
        # thermocouple backend so existing tests keep working.
        primary = object.__getattribute__(self, "_primary_thermocouple")()
        if primary is None:
            raise AttributeError(name)
        return getattr(primary, name)

    @property
    def is_initialized(self) -> bool:
        return any(bool(getattr(r, "is_initialized", False)) for r in self._readers)

    def read_temperatures(self) -> Dict[str, float]:
        values: Dict[str, float] = {}
        errors: list[str] = []
        for reader in self._readers:
            if not getattr(reader, "is_initialized", False):
                err = getattr(reader, "last_error", None)
                if err:
                    errors.append(str(err))
                continue
            try:
                values.update(reader.read_temperatures())
            except Exception as exc:
                errors.append(str(exc))
            err = getattr(reader, "last_error", None)
            if err:
                errors.append(str(err))
        self.last_error = "; ".join(errors) if errors and not values else (
            errors[-1] if errors else None
        )
        if not values and errors:
            self.last_error = "; ".join(errors)
        return values

    def get_last_raw_temperatures(self) -> Dict[str, float]:
        values: Dict[str, float] = {}
        for reader in self._readers:
            getter = getattr(reader, "get_last_raw_temperatures", None)
            if getter is None:
                continue
            try:
                values.update(getter())
            except Exception:
                continue
        return values

    def notify_setpoint(
        self,
        set_temperature_c: float,
        compressor_cooling: int = 0,
        pump_running: bool = False,
        pump_speed_rpm: int = 0,
    ) -> None:
        for reader in self._readers:
            notify = getattr(reader, "notify_setpoint", None)
            if notify is not None:
                notify(
                    set_temperature_c,
                    compressor_cooling,
                    pump_running,
                    pump_speed_rpm,
                )

    def set_channel_two_point_calibration(
        self,
        channel: int,
        measured_at_0c: float,
        measured_at_100c: float,
    ):
        last = (False, "No temperature reader supports calibration")
        for reader in self._readers:
            setter = getattr(reader, "set_channel_two_point_calibration", None)
            if setter is None:
                continue
            ok, message = setter(channel, measured_at_0c, measured_at_100c)
            if ok:
                return ok, message
            last = (ok, message)
        return last

    def set_raw_temperature(self, label: str, raw_c: float) -> None:
        for reader in self._readers:
            setter = getattr(reader, "set_raw_temperature", None)
            if setter is not None:
                setter(label, raw_c)

    def release_temperature(self, label: str) -> None:
        for reader in self._readers:
            release = getattr(reader, "release_temperature", None)
            if release is not None:
                release(label)

    def cleanup(self) -> None:
        for reader in self._readers:
            cleanup = getattr(reader, "cleanup", None)
            if cleanup is not None:
                cleanup()
