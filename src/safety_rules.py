"""Pure safety rule evaluation for the spine cooling runtime."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from fault_catalog import FaultCode
from state_machine import State

if TYPE_CHECKING:
    from cooling_tracker import CoolingEffectivenessTracker

ACTIVE_STATES = (State.COOLING, State.PUMPING, State.PUMPING_SLOWLY)


@dataclass
class TelemetrySnapshot:
    battery_pct: Optional[float] = None
    fridge_defect: Optional[bool] = None


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
    now: float = 0.0


def is_fault_still_active(code: FaultCode, ctx: RuleContext) -> bool:
    """Return True if ``code`` would fire for the given context."""
    return code in evaluate(ctx)


def evaluate(ctx: RuleContext) -> set[FaultCode]:
    active: set[FaultCode] = set()
    if _check_level_sensors(ctx):
        active.add(FaultCode.LEVEL_SENSOR)
    if _check_cartridge_removed(ctx):
        active.add(FaultCode.CARTRIDGE_REMOVED)
    if _check_csf_low_temp(ctx):
        active.add(FaultCode.CSF_LOW_TEMP)
    if _check_heat_ex_min(ctx):
        active.add(FaultCode.HEAT_EX_TOO_COLD)
    if _check_leak(ctx):
        active.add(FaultCode.LEAK_DETECTED)
    if _check_cooling_ineffective(ctx):
        active.add(FaultCode.COOLING_INEFFECTIVE)
    if _check_battery_low(ctx):
        active.add(FaultCode.BATTERY_LOW)
    if _check_fridge_defect(ctx):
        active.add(FaultCode.FRIDGE_DEFECT)
    return active


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
    sensor_name = str(alarms.get("leak_sensor_label", "Leak Sensor"))
    if sensor_name not in ctx.sensor_states:
        return False
    return not bool(ctx.sensor_states.get(sensor_name))


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


def _check_fridge_defect(ctx: RuleContext) -> bool:
    return ctx.telemetry.fridge_defect is True
