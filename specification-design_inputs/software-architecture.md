# Runtime architecture

```mermaid
flowchart LR
    touch[/Touchscreen/]
    cfg[(config.yaml)]

    subgraph guiLane ["GUI thread"]
        screen[AppWindow]
        app[CoolingRuntime]
        timer[UI timer]
    end

    subgraph senseLane ["Sensing"]
        factory{{Hardware factory}}
        gpio[GPIO sensors]
        therm[Thermistors]
        pressure[Pressure]
        flowMeter[Flow meter]
        worker[IO worker thread]
    end

    subgraph controlLane ["Control"]
        safety[Safety rules]
        machine[State machine]
        pump[Pump flow control]
        plate[Compressor control]
        stepper[Pump stepper thread]
        relay[Compressor GPIO]
    end

    subgraph logLane ["Session logs"]
        recorder[Session recorder]
        sensorLog[(Sensor CSV)]
        pressureLog[(Pressure CSV)]
        statusLog[(Status CSV)]
        usb[USB mirror thread]
    end

    touch -->|Operates| screen
    screen -->|Commands| app
    timer -->|10 Hz| app
    cfg -->|Limits| app
    cfg -->|Pins| factory
    factory -->|Real or sim| gpio
    factory -->|Real or sim| therm
    factory -->|Real or sim| pressure
    factory -->|Real or sim| flowMeter
    factory -->|Real or sim| stepper
    gpio -->|Digital| worker
    therm -->|Celsius| worker
    pressure -->|UI rate| worker
    flowMeter -->|ml per min| worker
    worker -->|Readings| app
    worker -->|Sensor row callback| recorder
    pressure -->|100 Hz| recorder
    app -->|Snapshot| safety
    safety -->|Stop or warn| machine
    machine -->|Start or stop| pump
    app -->|CSF error| pump
    pump -->|RPM| stepper
    machine -->|Enable| plate
    app -->|Plate temp| plate
    plate -->|On or off| relay
    app -->|State| screen
    app -->|State changes| recorder
    recorder -->|10 Hz| sensorLog
    recorder -->|100 Hz file| pressureLog
    recorder -->|Events| statusLog
    recorder -->|Copies| usb
```

# Threads

| Thread | Owns |
|--------|------|
| GUI | `AppWindow`, `CoolingRuntime`, the state machine, pump and compressor decisions |
| IO worker | Sensor reads, and the sensor-CSV callback |
| Stepper | Step pulses, through pigpio. The control loop only sets RPM and run or stop |
| Pressure capture | The pressure CSV, at `sensors.pressure.capture_rate_hz` (100 Hz unless config changes it) |
| USB mirror | Copying new log bytes onto the stick |