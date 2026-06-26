"""Unit tests for safety rule evaluation."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import FaultCode  # noqa: E402
from leak_debounce import LeakDebounceTracker  # noqa: E402
from safety_rules import (  # noqa: E402
    RuleContext,
    TelemetrySnapshot,
    evaluate,
    is_fault_still_active,
)
from state_machine import State  # noqa: E402


def _ctx(
    *,
    state: State = State.PUMPING,
    temperatures: dict | None = None,
    sensor_states: dict | None = None,
    pressures: dict | None = None,
    telemetry: TelemetrySnapshot | None = None,
    config: dict | None = None,
    leak_tracker: LeakDebounceTracker | None = None,
    now: float = 0.0,
) -> RuleContext:
    return RuleContext(
        current_state=state,
        seconds_in_state=0.0,
        sensor_states=sensor_states or {
            "Cartridge In Place": True,
            "Level Low": True,
            "Level Critical": True,
        },
        temperatures=temperatures or {},
        pressures=pressures or {},
        pump_running=True,
        compressor_on=False,
        telemetry=telemetry or TelemetrySnapshot(),
        config=config or {"alarms": {"csf_label": "CSF", "csf_low_temp_c": 28.0}},
        cooling_tracker=None,
        leak_tracker=leak_tracker,
        now=now,
    )


class SafetyRulesTests(unittest.TestCase):
    def test_csf_low_temp_active(self) -> None:
        active = evaluate(_ctx(temperatures={"CSF": 27.9}))
        self.assertIn(FaultCode.CSF_LOW_TEMP, active)

    def test_csf_low_temp_idle(self) -> None:
        active = evaluate(_ctx(state=State.READY, temperatures={"CSF": 27.9}))
        self.assertNotIn(FaultCode.CSF_LOW_TEMP, active)

    def test_csf_at_limit(self) -> None:
        active = evaluate(_ctx(temperatures={"CSF": 28.0}))
        self.assertNotIn(FaultCode.CSF_LOW_TEMP, active)

    def test_csf_fault_still_active_for_ack_check(self) -> None:
        ctx = _ctx(temperatures={"CSF": 27.0})
        self.assertTrue(is_fault_still_active(FaultCode.CSF_LOW_TEMP, ctx))

    def test_csf_fault_cleared_for_ack_check(self) -> None:
        ctx = _ctx(temperatures={"CSF": 29.0})
        self.assertFalse(is_fault_still_active(FaultCode.CSF_LOW_TEMP, ctx))

    def test_cartridge_removed_during_operation(self) -> None:
        active = evaluate(
            _ctx(
                sensor_states={
                    "Cartridge In Place": False,
                    "Level Low": True,
                    "Level Critical": True,
                }
            )
        )
        self.assertIn(FaultCode.CARTRIDGE_REMOVED, active)

    def test_cartridge_removed_ignored_when_ready(self) -> None:
        active = evaluate(
            _ctx(
                state=State.READY,
                sensor_states={
                    "Cartridge In Place": False,
                    "Level Low": True,
                    "Level Critical": True,
                },
            )
        )
        self.assertNotIn(FaultCode.CARTRIDGE_REMOVED, active)

    def test_level_sensor_fault(self) -> None:
        active = evaluate(
            _ctx(
                sensor_states={
                    "Cartridge In Place": True,
                    "Level Low": False,
                    "Level Critical": True,
                }
            )
        )
        self.assertIn(FaultCode.LEVEL_SENSOR, active)

    def test_battery_stub_inactive(self) -> None:
        active = evaluate(_ctx(telemetry=TelemetrySnapshot()))
        self.assertNotIn(FaultCode.BATTERY_LOW, active)

    def test_battery_low_active(self) -> None:
        active = evaluate(
            _ctx(telemetry=TelemetrySnapshot(battery_pct=15.0))
        )
        self.assertIn(FaultCode.BATTERY_LOW, active)

    def test_heat_ex_too_cold(self) -> None:
        config = {
            "alarms": {
                "heat_ex_label": "Heat Ex",
                "heat_ex_min_c": -10.0,
            }
        }
        active = evaluate(_ctx(temperatures={"Heat Ex": -10.5}, config=config))
        self.assertIn(FaultCode.HEAT_EX_TOO_COLD, active)

    def test_leak_detected_when_sensor_low(self) -> None:
        active = evaluate(
            _ctx(
                state=State.PUMPING,
                sensor_states={"Leak Sensor": False},
            )
        )
        self.assertIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_clear_when_sensor_high(self) -> None:
        active = evaluate(
            _ctx(
                state=State.PUMPING,
                sensor_states={"Leak Sensor": True},
            )
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_detected_in_cooling(self) -> None:
        active = evaluate(
            _ctx(
                state=State.COOLING,
                sensor_states={"Leak Sensor": False},
            )
        )
        self.assertIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_not_checked_during_init(self) -> None:
        active = evaluate(
            _ctx(
                state=State.INIT,
                sensor_states={"Leak Sensor": False},
            )
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_debounce_ignores_brief_flicker(self) -> None:
        tracker = LeakDebounceTracker(hold_s=0.5)
        # Signal drops low but not yet for the full hold time.
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": False}, leak_tracker=tracker, now=0.0)
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": False}, leak_tracker=tracker, now=0.3)
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)
        # A high reading clears the pending leak (flicker rejected).
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": True}, leak_tracker=tracker, now=0.4)
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": False}, leak_tracker=tracker, now=0.6)
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_debounce_fires_after_hold(self) -> None:
        tracker = LeakDebounceTracker(hold_s=0.5)
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": False}, leak_tracker=tracker, now=0.0)
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)
        # Stayed low continuously past the hold time.
        active = evaluate(
            _ctx(sensor_states={"Leak Sensor": False}, leak_tracker=tracker, now=0.5)
        )
        self.assertIn(FaultCode.LEAK_DETECTED, active)

    def test_leak_ignored_when_sensor_absent(self) -> None:
        active = evaluate(
            _ctx(
                state=State.PUMPING,
                sensor_states={
                    "Cartridge In Place": True,
                    "Level Low": True,
                    "Level Critical": True,
                },
            )
        )
        self.assertNotIn(FaultCode.LEAK_DETECTED, active)


if __name__ == "__main__":
    unittest.main()
