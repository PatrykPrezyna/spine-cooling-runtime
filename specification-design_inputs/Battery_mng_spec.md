# Low Battery Detection and Alarm Threshold Specification

## 1. Purpose

This specification defines the low-battery alarm thresholds for the battery-powered operation of the device utilizing a K2 Energy K2B24V11EB 24 V Lithium Iron Phosphate (LiFePO₄) battery pack with integrated Battery Management System (BMS).

The objective is to ensure sufficient warning is provided to the operator before battery depletion could impair device performance or result in an unexpected shutdown.

---

## 2. Battery Characteristics

| Parameter | Value |
|------------|---------|
| Battery Type | Lithium Iron Phosphate (LiFePO₄) |
| Nominal Voltage | 25.6 V |
| Capacity | 11.25 Ah |
| Stored Energy | Approximately 288 Wh |
| Integrated Protection | Battery Management System (BMS) |

The selected battery chemistry exhibits a relatively flat discharge curve, resulting in battery voltage remaining nearly constant over a large portion of the discharge cycle and decreasing rapidly near end-of-discharge. Consequently, battery voltage alone is not considered a reliable indicator of remaining operating time.

---

## 3. System Load Assumptions

The battery supplies the following major loads:

- Air compressor (8.3 A continuous)
- Peristaltic pump
- Stepper motor
- Raspberry Pi controller
- Cooling fan(s)
- Sensors and associated electronics

Estimated peak continuous power consumption:

| Load Condition | Estimated Power |
|---------------|----------------|
| Compressor Only | ~200 W |
| Full System Operation | 220-240 W |

Based on the battery energy capacity of approximately 288 Wh, expected operating duration under maximum load is approximately 60-75 minutes.

---

## 4. Design Requirements

### BR-001 Battery Runtime Reserve

The system shall provide the operator with a minimum of 10 minutes of remaining operational time following activation of a critical low-battery alarm.

### BR-002 Operator Notification

The system shall provide both visual and audible indication of low battery conditions.

### BR-003 Protection Against Unexpected Shutdown

The system shall enter a controlled safe state prior to battery depletion or BMS disconnect.

### BR-004 End-of-Discharge Margin

Battery alarms shall be generated before the battery reaches the minimum operating voltage required for stable operation of the compressor, control electronics, and safety functions.

---

## 5. Alarm Threshold Selection Rationale

### 5.1 Remaining Energy Requirement

Assumptions:

- Maximum system power = 240 W
- Required warning duration = 10 minutes

Required reserve energy:

```
240 W × (10/60 h) = 40 Wh
```

Required reserve capacity:

```
40 Wh / 25.6 V = 1.56 Ah
```

Percentage of total battery capacity:

```
1.56 Ah / 11.25 Ah = 13.9%
```

Accordingly, the critical low-battery alarm is based on approximately 15% remaining battery capacity, providing margin for battery aging, temperature variation, and measurement uncertainty.

---

## 6. Battery Monitoring Strategy

### Preferred Method: Remaining Runtime Estimation

The system shall determine battery status using:

- Battery voltage measurement
- Battery current measurement
- Coulomb counting
- Real-time power consumption calculation

Remaining runtime shall be estimated as:

```
Remaining Runtime = Remaining Battery Energy / Current Power Consumption
```

The calculated remaining runtime shall be the primary criterion for battery alarm generation.

---

## 7. Alarm Thresholds

### Runtime-Based Thresholds (Primary)

| Alarm Level | Threshold | Operator Action |
|------------|------------|----------------|
| Low Battery Warning | ≤ 15 minutes remaining | Connect external power source |
| Critical Battery Alarm | ≤ 10 minutes remaining | Immediate operator intervention required |
| Safe-State Activation | ≤ 5 minutes remaining | System prepares controlled shutdown |

### Voltage-Based Thresholds (Secondary Safety Limits)

Voltage measurements shall be performed under normal operating load.

| Alarm Level | Battery Voltage | System Action |
|------------|----------------|---------------|
| Advisory Warning | ≤ 25.0 V | Visual warning displayed |
| Critical Alarm | ≤ 24.5 V | Audible and visual alarm activated |
| Safe-State Threshold | ≤ 24.0 V | Controlled shutdown preparation initiated |
| BMS Cutoff Region | < 23.0 V | Normal operation not guaranteed |

---

## 8. Human Factors Considerations

The selected alarm thresholds are intended to:

- Provide sufficient time for operator response
- Prevent unexpected loss of therapy or functionality
- Mitigate risks associated with battery depletion
- Support safe transition to external power

The warning period shall exceed the time required for a user to obtain and connect the external power supply under normal use conditions.

---

## 9. Risk Control Measures

| Hazard | Risk Control |
|----------|-------------|
| Unexpected battery depletion | Low battery alarm |
| Device shutdown during operation | Minimum 10-minute reserve time |
| Loss of monitoring or therapy | Controlled safe-state transition |
| Aged battery reduced capacity | 15% reserve capacity margin |
| Voltage collapse near end of discharge | Runtime-based alarm strategy |

---

## 10. Verification Requirements

Verification testing shall demonstrate:

1. Critical battery alarm activation with at least 10 minutes of remaining operation under worst-case load conditions.
2. Alarm functionality at beginning-of-life and end-of-life battery conditions.
3. Correct operation following reduction of battery capacity to 80% of nominal capacity.
4. Continued operation of essential functions throughout the warning period.
5. Controlled shutdown prior to battery BMS low-voltage protection activation.

---

## 11. Engineering Recommendation

For this system architecture, remaining runtime calculation shall be the primary battery monitoring method.

Voltage thresholds shall serve as secondary safety limits only.

The design target is:

- Low Battery Warning: 15 minutes remaining runtime
- Critical Battery Alarm: 10 minutes remaining runtime
- Safe-State Activation: 5 minutes remaining runtime

This approach provides a more reliable indication of available operating time than voltage-only monitoring and reduces the probability of unexpected system shutdown during operation.