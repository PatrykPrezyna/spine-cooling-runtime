"""Static fault definitions for the spine cooling runtime."""

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    STOP = "stop"
    MESSAGE = "message"


class FaultCode(Enum):
    LEVEL_SENSOR = "LEVEL_SENSOR"
    CARTRIDGE_REMOVED = "CARTRIDGE_REMOVED"
    CSF_LOW_TEMP = "CSF_LOW_TEMP"
    IO_READ_FAILURE = "IO_READ_FAILURE"
    BATTERY_LOW = "BATTERY_LOW"
    FRIDGE_DEFECT = "FRIDGE_DEFECT"
    LEAK_DETECTED = "LEAK_DETECTED"
    HEAT_EX_TOO_COLD = "HEAT_EX_TOO_COLD"
    COOLING_INEFFECTIVE = "COOLING_INEFFECTIVE"


@dataclass(frozen=True)
class FaultDef:
    code: FaultCode
    message: str
    severity: Severity
    ack_required: bool


FAULTS: dict[FaultCode, FaultDef] = {
    FaultCode.LEVEL_SENSOR: FaultDef(
        FaultCode.LEVEL_SENSOR,
        "Level sensor failure detected",
        Severity.STOP,
        True,
    ),
    FaultCode.CARTRIDGE_REMOVED: FaultDef(
        FaultCode.CARTRIDGE_REMOVED,
        "Cartridge removed during operation",
        Severity.STOP,
        True,
    ),
    FaultCode.CSF_LOW_TEMP: FaultDef(
        FaultCode.CSF_LOW_TEMP,
        "CSF low temp",
        Severity.STOP,
        True,
    ),
    FaultCode.IO_READ_FAILURE: FaultDef(
        FaultCode.IO_READ_FAILURE,
        "Sensor read failure",
        Severity.STOP,
        True,
    ),
    FaultCode.BATTERY_LOW: FaultDef(
        FaultCode.BATTERY_LOW,
        "Battery low",
        Severity.MESSAGE,
        False,
    ),
    FaultCode.FRIDGE_DEFECT: FaultDef(
        FaultCode.FRIDGE_DEFECT,
        "Fridge defect",
        Severity.STOP,
        True,
    ),
    FaultCode.LEAK_DETECTED: FaultDef(
        FaultCode.LEAK_DETECTED,
        "Leak detected",
        Severity.STOP,
        True,
    ),
    FaultCode.HEAT_EX_TOO_COLD: FaultDef(
        FaultCode.HEAT_EX_TOO_COLD,
        "Heat exchanger too cold",
        Severity.STOP,
        True,
    ),
    FaultCode.COOLING_INEFFECTIVE: FaultDef(
        FaultCode.COOLING_INEFFECTIVE,
        "Cooling ineffective",
        Severity.STOP,
        True,
    ),
}

_STOP_PRIORITY: dict[FaultCode, int] = {
    FaultCode.IO_READ_FAILURE: 0,
    FaultCode.LEVEL_SENSOR: 1,
    FaultCode.CARTRIDGE_REMOVED: 2,
    FaultCode.FRIDGE_DEFECT: 3,
    FaultCode.LEAK_DETECTED: 4,
    FaultCode.CSF_LOW_TEMP: 5,
    FaultCode.HEAT_EX_TOO_COLD: 6,
    FaultCode.COOLING_INEFFECTIVE: 7,
}


def get_fault(code: FaultCode) -> FaultDef:
    return FAULTS[code]


def stop_priority(code: FaultCode) -> int:
    return _STOP_PRIORITY.get(code, 99)
