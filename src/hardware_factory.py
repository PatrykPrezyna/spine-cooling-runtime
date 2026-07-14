"""Build real or simulated hardware components for SensorMonitorApp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from combined_temperature_reader import CombinedTemperatureReader


@dataclass
class HardwareBundle:
    sensor_reader: Any
    thermocouple_reader: Any
    pressure_reader: Any
    stepper_driver: Any


def build_hardware(config: dict, *, simulation: bool) -> HardwareBundle:
    """Return hardware objects used by main.py and the IO worker."""
    if simulation:
        from sim.readers import (
            SimPressureReader,
            SimSensorReader,
            SimThermocoupleReader,
            SimThermistorReader,
        )
        from sim.stepper import SimStepperDriver

        print("Building simulated hardware (--sim)")
        temperature_reader = CombinedTemperatureReader(
            SimThermocoupleReader(config),
            SimThermistorReader(config),
        )
        return HardwareBundle(
            sensor_reader=SimSensorReader(config),
            thermocouple_reader=temperature_reader,
            pressure_reader=SimPressureReader(config),
            stepper_driver=SimStepperDriver(config),
        )

    from ads1115_pressure_reader import ADS1115PressureReader
    from ads1115_thermistor_reader import ADS1115ThermistorReader
    from multi_sensor_reader import MultiSensorReader
    from stepper_driver import STSPIN220Driver
    from thermocouple_reader import ThermocoupleReader

    temperature_reader = CombinedTemperatureReader(
        ThermocoupleReader(config),
        ADS1115ThermistorReader(config),
    )
    return HardwareBundle(
        sensor_reader=MultiSensorReader(config),
        thermocouple_reader=temperature_reader,
        pressure_reader=ADS1115PressureReader(config),
        stepper_driver=STSPIN220Driver(config),
    )
