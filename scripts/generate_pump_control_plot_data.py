"""Generate closed-loop pump control scenario data for visualization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pump_flow_control import PumpFlowControlConfig, PumpFlowController

T_COOLANT = 18.0
T_BODY = 37.0
TAU_COOL_S = 45.0
BODY_LEAK_PER_S = 0.015


def plant_step(temp_c: float, flow: float, dt: float) -> float:
    flow_frac = max(0.0, min(1.0, flow / 100.0))
    d_cool = (T_COOLANT - temp_c) / TAU_COOL_S * flow_frac
    d_warm = (T_BODY - temp_c) * BODY_LEAK_PER_S * (1.0 - flow_frac)
    return temp_c + (d_cool + d_warm) * dt


def simulate(name: str, t0: float, setpoints: list[tuple[float, float]], duration_s: float = 180.0, dt: float = 1.0):
    ctrl = PumpFlowController()
    ctrl.reset()
    temp = float(t0)
    t = 0.0
    rows = []
    sp_i = 0
    set_temp = setpoints[0][1]
    while t <= duration_s + 1e-9:
        while sp_i + 1 < len(setpoints) and t >= setpoints[sp_i + 1][0]:
            sp_i += 1
            set_temp = setpoints[sp_i][1]
        flow = ctrl.compute(temp, set_temp, now_s=t)
        rows.append(
            {
                "t": round(t, 1),
                "temp": round(temp, 3),
                "flow": round(flow, 2),
                "set": set_temp,
                "error": round(temp - set_temp, 3),
            }
        )
        temp = plant_step(temp, flow, dt)
        t += dt
    return {"name": name, "rows": rows}


def simulate_disturbance() -> dict:
    ctrl = PumpFlowController()
    ctrl.reset()
    temp = 32.0
    set_temp = 32.0
    rows = []
    dt = 1.0
    for step in range(0, 181):
        t = step * dt
        if abs(t - 60.0) < 1e-9:
            temp += 0.8
        flow = ctrl.compute(temp, set_temp, now_s=t)
        rows.append(
            {
                "t": round(t, 1),
                "temp": round(temp, 3),
                "flow": round(flow, 2),
                "set": set_temp,
                "error": round(temp - set_temp, 3),
            }
        )
        temp = plant_step(temp, flow, dt)
    return {"name": "Warm disturbance +0.8 C at t=60s", "rows": rows}


def main() -> None:
    scenarios = [
        simulate("Large cooldown 37 to 32 C", 37.0, [(0, 32.0)], 240),
        simulate("Near-band start 32.4 to 32 C", 32.4, [(0, 32.0)], 120),
        simulate("Already at setpoint 32 C", 32.0, [(0, 32.0)], 60),
        simulate("Setpoint step 34 to 32 at t=90s", 34.0, [(0, 34.0), (90, 32.0)], 240),
        simulate_disturbance(),
    ]

    ctrl_map = []
    for i in range(-10, 31):
        err = i / 20.0
        ctrl = PumpFlowController(PumpFlowControlConfig(ki=0.0, kd=0.0))
        flow = ctrl.compute(32.0 + err, 32.0, now_s=0.0)
        ctrl_map.append({"error": round(err, 2), "flow": round(flow, 2)})

    out = {
        "plant": {
            "description": (
                "First-order plant: cools toward 18°C with strength ∝ flow/100; "
                "body leak toward 37°C when flow is low."
            ),
            "tau_cool_s": TAU_COOL_S,
            "t_coolant": T_COOLANT,
            "t_body": T_BODY,
        },
        "controller": {
            "max": 100,
            "min": 10,
            "band": 0.5,
            "kp": 180,
            "ki": 40,
            "kd": 5,
        },
        "map": ctrl_map,
        "scenarios": scenarios,
    }
    out_path = Path(__file__).resolve().parents[1] / "data" / "pump_control_scenarios.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {out_path}")
    for s in scenarios:
        r = s["rows"]
        print(
            f"{s['name']}: n={len(r)} T0={r[0]['temp']} Tend={r[-1]['temp']} "
            f"flow0={r[0]['flow']} flow_end={r[-1]['flow']}"
        )


if __name__ == "__main__":
    main()
