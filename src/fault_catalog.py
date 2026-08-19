"""Static fault definitions for the spine cooling runtime."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    STOP = "stop"
    MESSAGE = "message"


class FaultCode(Enum):
    LEVEL_SENSOR = "LEVEL_SENSOR"
    CARTRIDGE_REMOVED = "CARTRIDGE_REMOVED"
    CSF_LOW_TEMP = "CSF_LOW_TEMP"
    IO_READ_FAILURE = "IO_READ_FAILURE"
    BATTERY_LOW = "BATTERY_LOW"
    USB_NOT_PRESENT = "USB_NOT_PRESENT"
    SD_STORAGE_LOW = "SD_STORAGE_LOW"
    USB_STORAGE_LOW = "USB_STORAGE_LOW"
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
    causes: tuple[str, ...]
    steps: tuple[str, ...]


GENERIC_CAUSES = (
    "A required sensor or board could not be read.",
    "A cable, connector, or power feed is loose.",
    "The runtime hit an unexpected failure during start-up.",
)
GENERIC_STEPS = (
    "Check sensor cables, boards, and power.",
    "Open expert Status and confirm readings are updating.",
    "Acknowledge the error once the hardware is responding.",
)


def _fault(
    code: FaultCode,
    message: str,
    severity: Severity,
    ack_required: bool,
    causes: tuple[str, ...],
    steps: tuple[str, ...],
) -> FaultDef:
    return FaultDef(code, message, severity, ack_required, causes, steps)


FAULTS: dict[FaultCode, FaultDef] = {
    FaultCode.LEVEL_SENSOR: _fault(
        FaultCode.LEVEL_SENSOR,
        "Level sensor failure detected",
        Severity.STOP,
        True,
        (
            "Coolant level has dropped below a level switch.",
            "The cartridge is not filled enough.",
            "A level switch is stuck, unplugged, or wired incorrectly.",
        ),
        (
            "Inspect the cartridge fill level and top up if it is low.",
            "Check for leaks around the cartridge and tubing.",
            "On expert Status, confirm Level Low and Level Critical both read OK.",
            "Reseat the level-sensor connectors if a switch stays off.",
            "Acknowledge once both level sensors read OK.",
        ),
    ),
    FaultCode.CARTRIDGE_REMOVED: _fault(
        FaultCode.CARTRIDGE_REMOVED,
        "Cartridge removed during operation",
        Severity.STOP,
        True,
        (
            "The cartridge was pulled out or is not fully seated.",
            "The cartridge-in-place switch is not detecting the cartridge.",
            "The switch connector or wiring is loose.",
        ),
        (
            "Fully seat the cartridge until it is locked in place.",
            "On expert Status, confirm Cartridge In Place is ON.",
            "Check the cartridge sensor connector if it stays OFF.",
            "Acknowledge once the cartridge is detected.",
        ),
    ),
    FaultCode.CSF_LOW_TEMP: _fault(
        FaultCode.CSF_LOW_TEMP,
        "CSF low temp",
        Severity.STOP,
        True,
        (
            "Cooling ran longer or harder than intended.",
            "The setpoint is lower than the allowed CSF limit.",
            "The CSF sensor is reading low (poor contact, unplugged, or calibration).",
        ),
        (
            "Check the CSF temperature on the main display.",
            "Raise the setpoint if it is below the intended target.",
            "Confirm the CSF sensor is connected and reading a plausible value.",
            "Wait until CSF is back above the low-temperature limit.",
            "Acknowledge once the temperature is in range.",
        ),
    ),
    FaultCode.IO_READ_FAILURE: _fault(
        FaultCode.IO_READ_FAILURE,
        "Sensor read failure",
        Severity.STOP,
        True,
        (
            "A sensor board, I2C/SPI bus, or cable failed during a read.",
            "A transient communication error interrupted sampling.",
            "On a Pi, the I/O service (pigpio) may not be running.",
        ),
        (
            "Check sensor board power and cables.",
            "Open expert Status and confirm readings update.",
            "If this is a Pi, confirm the I/O service is running.",
            "Acknowledge to return to Ready. The next read will trip again if hardware is still down.",
        ),
    ),
    FaultCode.BATTERY_LOW: _fault(
        FaultCode.BATTERY_LOW,
        "Battery low",
        Severity.MESSAGE,
        False,
        (
            "Supply voltage or reported battery charge is below the warning threshold.",
            "The power source is disconnected or a battery is aging.",
        ),
        (
            "Connect mains power or replace/charge the battery.",
            "Confirm the power lead is fully seated.",
            "Continue only if the warning clears; otherwise stop the session.",
        ),
    ),
    FaultCode.USB_NOT_PRESENT: _fault(
        FaultCode.USB_NOT_PRESENT,
        "USB stick not present",
        Severity.MESSAGE,
        False,
        (
            "No USB stick labeled SPINELOGS is mounted.",
            "The stick was unplugged, not formatted with that label, or failed to mount.",
        ),
        (
            "Insert a USB stick labeled SPINELOGS (exFAT or FAT32).",
            "Wait until Service → Manual Operation shows copying.",
            "Use Eject before removing the stick.",
        ),
    ),
    FaultCode.SD_STORAGE_LOW: _fault(
        FaultCode.SD_STORAGE_LOW,
        "SD card storage below 1 GB",
        Severity.MESSAGE,
        False,
        (
            "The SD card (local logs folder) has less than 1 GB free.",
            "Old session CSVs are filling the card.",
        ),
        (
            "Copy logs off the Pi and delete old files from logs/.",
            "Do not start a long session until more than 1 GB is free.",
        ),
    ),
    FaultCode.USB_STORAGE_LOW: _fault(
        FaultCode.USB_STORAGE_LOW,
        "USB stick storage below 1 GB",
        Severity.MESSAGE,
        False,
        (
            "The USB stick has less than 1 GB free.",
            "Previous session copies are filling the stick.",
        ),
        (
            "Eject the stick, copy files off, and delete old logs.",
            "Reinsert a stick with more than 1 GB free.",
        ),
    ),
    FaultCode.FRIDGE_DEFECT: _fault(
        FaultCode.FRIDGE_DEFECT,
        "Fridge defect",
        Severity.STOP,
        True,
        (
            "The compressor or fridge reported a defect flag.",
            "Coolant is not circulating through the fridge.",
            "The plate is not cooling while the compressor is commanded on.",
        ),
        (
            "On Manual Operation, check whether the compressor is running.",
            "Check the plate / heat-exchanger temperature.",
            "Inspect fridge power and coolant hoses.",
            "Service the fridge if the defect remains.",
            "Acknowledge only after the defect flag is cleared.",
        ),
    ),
    FaultCode.LEAK_DETECTED: _fault(
        FaultCode.LEAK_DETECTED,
        "Leak detected",
        Severity.STOP,
        True,
        (
            "Fluid is on the leak sensor (a real leak).",
            "Splash, condensation, or a wet tray is holding the sensor low.",
            "The leak sensor is stuck low or its pull-up is missing.",
        ),
        (
            "Do not restart cooling until the area is dry.",
            "Inspect the cartridge, catheter, and tubing for leaks.",
            "Dry the leak sensor and the tray.",
            "On expert Status, confirm the leak sensor reads dry.",
            "Acknowledge once the sensor stays dry.",
        ),
    ),
    FaultCode.HEAT_EX_TOO_COLD: _fault(
        FaultCode.HEAT_EX_TOO_COLD,
        "Heat exchanger too cold",
        Severity.STOP,
        True,
        (
            "The compressor is running with little or no coolant flow.",
            "The plate / heat exchanger overcooled.",
            "The plate sensor is reading incorrectly.",
        ),
        (
            "Check the plate / heat-exchanger temperature.",
            "Confirm the pump is circulating coolant.",
            "Allow the plate to warm above the minimum limit.",
            "Check the plate sensor connection if the reading looks wrong.",
            "Acknowledge once the temperature is in range.",
        ),
    ),
    FaultCode.COOLING_INEFFECTIVE: _fault(
        FaultCode.COOLING_INEFFECTIVE,
        "Cooling ineffective",
        Severity.STOP,
        True,
        (
            "The catheter is not placed or has poor thermal contact.",
            "The pump is not delivering enough flow.",
            "The compressor is not cooling the cartridge.",
            "The CSF sensor is not tracking the true temperature.",
        ),
        (
            "Confirm the catheter is placed and connected.",
            "Check pump speed, flow, and pressures on the expert page.",
            "Confirm the compressor is on and the plate is cooling.",
            "Check the CSF sensor reading.",
            "Fix the cause, then acknowledge to return to Ready.",
        ),
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


def operator_help(code: Optional[FaultCode]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return probable causes and recovery steps for a latched fault."""
    if code is None:
        return GENERIC_CAUSES, GENERIC_STEPS
    fault = get_fault(code)
    return fault.causes, fault.steps
