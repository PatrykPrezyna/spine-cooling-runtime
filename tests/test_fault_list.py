"""The generated fault list matches the catalog and the safety rules."""

import importlib.util
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import FAULTS, FaultCode, Severity, get_fault, stop_priority  # noqa: E402
from safety_rules import (  # noqa: E402
    RULES,
    RuleContext,
    TelemetrySnapshot,
    evaluate,
    listed_faults,
)
from state_machine import State  # noqa: E402

HTML_PATH = PROJECT_ROOT / "docs" / "fault-list.html"
_GENERATED = re.compile(
    r"Generated from src/safety_rules.py and src/fault_catalog.py\. "
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}), version ([0-9A-Za-z._-]+)\."
)


def _runtime_version() -> str:
    spec = importlib.util.spec_from_file_location(
        "spine_cooling_runtime",
        SRC_DIR / "__init__.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load src/__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.__version__)

_ALARMS = {
    "csf_label": "CSF",
    "csf_low_temp_c": 28.0,
    "heat_ex_label": "Heat Ex",
    "heat_ex_min_c": -10.0,
    "leak_detection_enabled": True,
    "leak_sensor_label": "Leak Sensor",
    "pump_closed_label": "Pump Closed",
    "battery_low_pct": 20,
    "storage_min_free_gb": 1.0,
    "cooling_ineffective_timeout_s": 600,
    "cooling_ineffective_csf_delta_c": 0.2,
}


class _AlwaysIneffective:
    def is_ineffective(self, **_kwargs: object) -> bool:
        return True


def _sensors(**changes: bool) -> dict[str, bool]:
    sensors = {
        "Cartridge In Place": True,
        "Level Low": True,
        "Level Critical": True,
        "Pump Closed": True,
        "Leak Sensor": True,
    }
    sensors.update(changes)
    return sensors


def _context(
    *,
    state: State = State.PUMPING,
    sensors: dict[str, bool] | None = None,
    temperatures: dict[str, float] | None = None,
    telemetry: TelemetrySnapshot | None = None,
    pump_running: bool = True,
    compressor_on: bool = False,
    cooling_tracker: object | None = None,
) -> RuleContext:
    return RuleContext(
        current_state=state,
        seconds_in_state=0.0,
        sensor_states=_sensors() if sensors is None else sensors,
        temperatures={"CSF": 37.0, "Heat Ex": 10.0} if temperatures is None else temperatures,
        pressures={},
        pump_running=pump_running,
        compressor_on=compressor_on,
        telemetry=telemetry or TelemetrySnapshot(),
        config={"alarms": dict(_ALARMS)},
        cooling_tracker=cooling_tracker,
        leak_tracker=None,
        now=0.0,
    )


def _trip(code: FaultCode) -> RuleContext:
    healthy = {"CSF": 37.0, "Heat Ex": 10.0}
    if code is FaultCode.LEVEL_SENSOR:
        return _context(sensors=_sensors(**{"Level Low": False}))
    if code is FaultCode.CARTRIDGE_REMOVED:
        return _context(sensors=_sensors(**{"Cartridge In Place": False}))
    if code is FaultCode.PUMP_NOT_CLOSED:
        return _context(sensors=_sensors(**{"Pump Closed": False}))
    if code is FaultCode.CSF_LOW_TEMP:
        return _context(temperatures={"CSF": 27.9, "Heat Ex": 10.0})
    if code is FaultCode.HEAT_EX_TOO_COLD:
        return _context(temperatures={"CSF": 37.0, "Heat Ex": -10.5})
    if code is FaultCode.LEAK_DETECTED:
        return _context(sensors=_sensors(**{"Leak Sensor": False}))
    if code is FaultCode.COOLING_INEFFECTIVE:
        return _context(
            temperatures=healthy,
            compressor_on=True,
            cooling_tracker=_AlwaysIneffective(),
        )
    if code is FaultCode.BATTERY_LOW:
        return _context(telemetry=TelemetrySnapshot(battery_pct=19.9))
    if code is FaultCode.USB_NOT_PRESENT:
        return _context(
            telemetry=TelemetrySnapshot(usb_logging_enabled=True, usb_present=False)
        )
    if code is FaultCode.SD_STORAGE_LOW:
        return _context(telemetry=TelemetrySnapshot(local_free_bytes=0))
    if code is FaultCode.USB_STORAGE_LOW:
        return _context(
            telemetry=TelemetrySnapshot(
                usb_logging_enabled=True,
                usb_present=True,
                usb_free_bytes=0,
            )
        )
    if code is FaultCode.FRIDGE_DEFECT:
        return _context(telemetry=TelemetrySnapshot(fridge_defect=True))
    raise AssertionError(code.value)


def _page() -> ET.Element:
    return ET.fromstring(HTML_PATH.read_text(encoding="utf-8"))


def _field(row: ET.Element, name: str) -> ET.Element:
    for element in row.iter():
        if element.get("data-field") == name:
            return element
    raise AssertionError(name)


def _text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _items(element: ET.Element) -> list[str]:
    return ["".join(item.itertext()) for item in element.iter("li")]


class FaultListTests(unittest.TestCase):
    def test_rules_match_the_catalog(self) -> None:
        codes = [rule.code for rule in RULES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), set(FaultCode))
        self.assertEqual(set(FAULTS), set(FaultCode))
        for code, fault in FAULTS.items():
            self.assertIs(fault.code, code)
            self.assertTrue(fault.message)
            self.assertTrue(fault.causes)
            self.assertTrue(fault.steps)
        for rule in RULES:
            self.assertTrue(rule.when.strip(), msg=rule.code.value)

        stops = [code for code in FaultCode if get_fault(code).severity == Severity.STOP]
        ranks = [stop_priority(code) for code in stops]
        self.assertEqual(len(ranks), len(set(ranks)))
        self.assertTrue(all(rank < 99 for rank in ranks))
        messages = [code for code in FaultCode if get_fault(code).severity == Severity.MESSAGE]
        self.assertTrue(all(stop_priority(code) == 99 for code in messages))

    def test_listed_order(self) -> None:
        listed = listed_faults()
        self.assertEqual({rule.code for rule in listed}, set(FaultCode))
        stops = [rule for rule in listed if get_fault(rule.code).severity == Severity.STOP]
        messages = [rule for rule in listed if get_fault(rule.code).severity == Severity.MESSAGE]
        self.assertEqual(listed, tuple(stops) + tuple(messages))
        self.assertEqual(
            [rule.code for rule in stops],
            sorted((rule.code for rule in stops), key=stop_priority),
        )
        self.assertEqual(
            messages,
            [rule for rule in RULES if get_fault(rule.code).severity == Severity.MESSAGE],
        )

    def test_each_rule_trips_on_its_own(self) -> None:
        self.assertEqual(evaluate(_context()), set())
        for rule in RULES:
            active = evaluate(_trip(rule.code))
            self.assertEqual(active, {rule.code}, msg=rule.code.value)

    def test_html_matches_catalog_and_rules(self) -> None:
        root = _page()
        text = HTML_PATH.read_text(encoding="utf-8")
        self.assertNotIn("No fault code", text)
        self.assertNotIn("latch priority", text)
        stamp = _GENERATED.search(text)
        self.assertIsNotNone(stamp)
        assert stamp is not None
        datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S")
        self.assertEqual(stamp.group(2), _runtime_version())

        rows = [element for element in root.iter("tr") if element.get("data-code")]
        listed = listed_faults()
        self.assertEqual(
            [row.get("data-code") for row in rows],
            [rule.code.value for rule in listed],
        )
        for row, rule in zip(rows, listed):
            fault = get_fault(rule.code)
            label = "Stop" if fault.severity is Severity.STOP else "Message"
            badge = "badge stop" if fault.severity is Severity.STOP else "badge warn"
            self.assertEqual(row.get("data-severity"), fault.severity.value)
            self.assertEqual(row.get("data-ack"), "true" if fault.ack_required else "false")
            self.assertEqual(_text(_field(row, "code")), rule.code.value)
            self.assertEqual(_text(_field(row, "message")), fault.message)
            self.assertEqual(_text(_field(row, "class")), label)
            self.assertEqual(_field(row, "class").find("span").get("class"), badge)
            self.assertEqual(
                _text(_field(row, "acknowledge")),
                "Required" if fault.ack_required else "Not required",
            )
            self.assertEqual(_text(_field(row, "when")), rule.when)
            self.assertEqual(_items(_field(row, "causes")), list(fault.causes))
            self.assertEqual(_items(_field(row, "steps")), list(fault.steps))


if __name__ == "__main__":
    unittest.main()
