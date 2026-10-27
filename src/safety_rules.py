"""Pure safety rule evaluation for the spine cooling runtime.

``RULES`` is every check. ``docs/fault-list.html`` is generated from this
table and the fault catalog.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, NamedTuple, Optional

from fault_catalog import FaultCode, Severity, get_fault, stop_priority
from state_machine import State

if TYPE_CHECKING:
    from cooling_tracker import CoolingEffectivenessTracker
    from leak_debounce import LeakDebounceTracker

ACTIVE_STATES = (State.COOLING, State.PUMPING)


@dataclass
class TelemetrySnapshot:
    battery_pct: Optional[float] = None
    fridge_defect: Optional[bool] = None
    usb_logging_enabled: bool = False
    usb_present: Optional[bool] = None
    usb_ejected: bool = False
    usb_free_bytes: Optional[int] = None
    local_free_bytes: Optional[int] = None


@dataclass
class RuleContext:
    current_state: State
    seconds_in_state: float
    sensor_states: dict
    temperatures: dict
    pressures: dict
    pump_running: bool
    compressor_on: bool
    telemetry: TelemetrySnapshot
    config: dict
    cooling_tracker: Optional["CoolingEffectivenessTracker"] = None
    leak_tracker: Optional["LeakDebounceTracker"] = None
    now: float = 0.0


class FaultRule(NamedTuple):
    """One safety check.

    ``when`` is the sentence on the generated fault list.
    ``tools/generate_fault_list.py`` reads this table.
    """

    code: FaultCode
    when: str
    check: Callable[["RuleContext"], bool]


def is_fault_still_active(code: FaultCode, ctx: RuleContext) -> bool:
    """Return True if ``code`` would fire for the given context."""
    return code in evaluate(ctx)


def evaluate(ctx: RuleContext) -> set[FaultCode]:
    """Return every fault whose rule matches this context."""
    return {rule.code for rule in RULES if rule.check(ctx)}


def _alarms(ctx: RuleContext) -> dict:
    return ctx.config.get("alarms", {})


def _check_level_sensors(ctx: RuleContext) -> bool:
    if ctx.current_state not in ACTIVE_STATES:
        return False
    level_low = ctx.sensor_states.get("Level Low", False)
    level_critical = ctx.sensor_states.get("Level Critical", False)
    return not level_low or not level_critical


def _check_cartridge_removed(ctx: RuleContext) -> bool:
    if ctx.current_state not in ACTIVE_STATES:
        return False
    return not ctx.sensor_states.get("Cartridge In Place", False)


def _check_pump_not_closed(ctx: RuleContext) -> bool:
    """Open pump head while the pump is running or the workflow is pumping.

    Cooling with the head open is allowed. Starting the pump is refused
    separately; this rule stops a pump that is already turning.
    """
    label = str(_alarms(ctx).get("pump_closed_label", "Pump Closed"))
    if label not in ctx.sensor_states:
        return False
    if bool(ctx.sensor_states.get(label)):
        return False
    if ctx.pump_running:
        return True
    return ctx.current_state == State.PUMPING


def _check_csf_low_temp(ctx: RuleContext) -> bool:
    if ctx.current_state not in ACTIVE_STATES:
        return False
    alarms = _alarms(ctx)
    label = str(alarms.get("csf_label", "CSF 2"))
    limit = float(alarms.get("csf_low_temp_c", 20.0))
    temp = ctx.temperatures.get(label)
    return temp is not None and float(temp) < limit


def _check_heat_ex_min(ctx: RuleContext) -> bool:
    if ctx.current_state not in ACTIVE_STATES:
        return False
    alarms = _alarms(ctx)
    label = str(alarms.get("heat_ex_label", "Heat Ex"))
    limit = float(alarms.get("heat_ex_min_c", -10.0))
    temp = ctx.temperatures.get(label)
    return temp is not None and float(temp) < limit


def _check_leak(ctx: RuleContext) -> bool:
    # Digital leak sensor (config ``leak_sensor_label``, e.g. GPIO26): the line
    # is held high while dry, and a leak pulls it low. A 0 reading therefore
    # means fluid was detected -> immediate stop. Active in every operational
    # state (skipped during INIT bring-up and while already in ERROR).
    if ctx.current_state in (State.INIT, State.ERROR):
        return False
    alarms = _alarms(ctx)
    if not bool(alarms.get("leak_detection_enabled", True)):
        return False
    sensor_name = str(alarms.get("leak_sensor_label", "Leak Sensor"))
    if sensor_name not in ctx.sensor_states:
        return False
    signal_low = not bool(ctx.sensor_states.get(sensor_name))
    if ctx.leak_tracker is None:
        return signal_low
    # Debounce: require the signal to stay low for the hold time to ignore
    # brief flicker on the line.
    return ctx.leak_tracker.update(signal_low=signal_low, now=ctx.now)


def _check_cooling_ineffective(ctx: RuleContext) -> bool:
    if ctx.cooling_tracker is None:
        return False
    if ctx.current_state not in ACTIVE_STATES:
        return False
    if not ctx.pump_running or not ctx.compressor_on:
        return False
    alarms = _alarms(ctx)
    label = str(alarms.get("csf_label", "CSF 2"))
    csf_temp = ctx.temperatures.get(label)
    timeout_s = float(alarms.get("cooling_ineffective_timeout_s", 600))
    min_delta_c = float(alarms.get("cooling_ineffective_csf_delta_c", 0.2))
    return ctx.cooling_tracker.is_ineffective(
        now=ctx.now,
        csf_temp=float(csf_temp) if csf_temp is not None else None,
        timeout_s=timeout_s,
        min_delta_c=min_delta_c,
    )


def _check_battery_low(ctx: RuleContext) -> bool:
    pct = ctx.telemetry.battery_pct
    if pct is None:
        return False
    alarms = _alarms(ctx)
    threshold = float(alarms.get("battery_low_pct", 20))
    return float(pct) < threshold


def _storage_min_free_bytes(ctx: RuleContext) -> int:
    alarms = _alarms(ctx)
    if alarms.get("storage_min_free_bytes") is not None:
        return max(0, int(alarms["storage_min_free_bytes"]))
    gb = float(alarms.get("storage_min_free_gb", 1.0))
    return max(0, int(gb * 1024 * 1024 * 1024))


def _check_usb_not_present(ctx: RuleContext) -> bool:
    tel = ctx.telemetry
    if not tel.usb_logging_enabled or tel.usb_ejected:
        return False
    return tel.usb_present is False


def _check_sd_storage_low(ctx: RuleContext) -> bool:
    free = ctx.telemetry.local_free_bytes
    if free is None:
        return False
    return int(free) < _storage_min_free_bytes(ctx)


def _check_usb_storage_low(ctx: RuleContext) -> bool:
    tel = ctx.telemetry
    if not tel.usb_logging_enabled or tel.usb_present is not True:
        return False
    if tel.usb_free_bytes is None:
        return False
    return int(tel.usb_free_bytes) < _storage_min_free_bytes(ctx)


def _check_fridge_defect(ctx: RuleContext) -> bool:
    return ctx.telemetry.fridge_defect is True


_DURING_RUN = f"{State.COOLING.value} or {State.PUMPING.value}"

# ``when`` is the line in the generated list. Keep it in step with the check.
RULES: tuple[FaultRule, ...] = (
    FaultRule(
        FaultCode.LEVEL_SENSOR,
        f"{_DURING_RUN}, and Level Low or Level Critical is missing or not OK.",
        _check_level_sensors,
    ),
    FaultRule(
        FaultCode.CARTRIDGE_REMOVED,
        f"{_DURING_RUN}, and Cartridge In Place is missing or off.",
        _check_cartridge_removed,
    ),
    FaultRule(
        FaultCode.PUMP_NOT_CLOSED,
        "The pump-closed switch is present and off, and the pump is running "
        f"or the state is {State.PUMPING.value}.",
        _check_pump_not_closed,
    ),
    FaultRule(
        FaultCode.CSF_LOW_TEMP,
        f"{_DURING_RUN}, and the configured CSF sensor is below the low-temperature limit.",
        _check_csf_low_temp,
    ),
    FaultRule(
        FaultCode.HEAT_EX_TOO_COLD,
        f"{_DURING_RUN}, and the configured heat-exchanger sensor is below the minimum temperature.",
        _check_heat_ex_min,
    ),
    FaultRule(
        FaultCode.LEAK_DETECTED,
        "Leak detection is on, the state is not "
        f"{State.INIT.value} or {State.ERROR.value}, and the leak sensor is present and low. "
        "With a debounce tracker, that low reading must be held.",
        _check_leak,
    ),
    FaultRule(
        FaultCode.COOLING_INEFFECTIVE,
        f"{_DURING_RUN}, with the pump and compressor on, and CSF has not dropped "
        "by the required amount within the timeout.",
        _check_cooling_ineffective,
    ),
    FaultRule(
        FaultCode.BATTERY_LOW,
        "A battery reading is present and below the low-battery threshold.",
        _check_battery_low,
    ),
    FaultRule(
        FaultCode.USB_NOT_PRESENT,
        "USB logging is on, the stick was not ejected, and no stick is present.",
        _check_usb_not_present,
    ),
    FaultRule(
        FaultCode.SD_STORAGE_LOW,
        "Local free space is known and below the storage minimum.",
        _check_sd_storage_low,
    ),
    FaultRule(
        FaultCode.USB_STORAGE_LOW,
        "USB logging is on, a stick is present, and its free space is below the storage minimum.",
        _check_usb_storage_low,
    ),
    FaultRule(
        FaultCode.FRIDGE_DEFECT,
        "The fridge defect flag is set.",
        _check_fridge_defect,
    ),
)


def listed_faults() -> tuple[FaultRule, ...]:
    """Stop faults in latch priority, then message faults in check order."""
    stops = tuple(
        sorted(
            (rule for rule in RULES if get_fault(rule.code).severity == Severity.STOP),
            key=lambda rule: (stop_priority(rule.code), rule.code.value),
        )
    )
    messages = tuple(
        rule for rule in RULES if get_fault(rule.code).severity == Severity.MESSAGE
    )
    return stops + messages
