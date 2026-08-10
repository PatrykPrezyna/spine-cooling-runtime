"""Save static matplotlib plots for pump flow control scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "pump_control_scenarios.json"
OUT_DIR = ROOT / "data" / "plots"


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Controller map
    fig, ax = plt.subplots(figsize=(8, 4.5))
    xs = [p["error"] for p in data["map"]]
    ys = [p["flow"] for p in data["map"]]
    ax.plot(xs, ys, color="#2563eb", lw=2, label="Commanded flow")
    ax.axhline(100, color="#b45309", ls="--", lw=1, label="Max 100 ml/min")
    ax.axhline(10, color="#6b7280", ls="--", lw=1, label="Min 10 ml/min")
    ax.axvline(0.5, color="#9ca3af", ls=":", lw=1)
    ax.axvline(0.0, color="#9ca3af", ls=":", lw=1)
    ax.set_xlabel("CSF error (CSF - set) [C]")
    ax.set_ylabel("Flow [ml/min]")
    ax.set_title("Controller map: error to flow (P-only snapshot)")
    ax.set_ylim(0, 110)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    map_path = OUT_DIR / "pump_control_map.png"
    fig.savefig(map_path, dpi=140)
    plt.close(fig)

    # 2) Scenario grid: temp + flow
    scenarios = data["scenarios"]
    n = len(scenarios)
    fig, axes = plt.subplots(n, 2, figsize=(11, 2.6 * n), sharex=False)
    if n == 1:
        axes = [axes]
    for i, sc in enumerate(scenarios):
        t = [r["t"] for r in sc["rows"]]
        temp = [r["temp"] for r in sc["rows"]]
        flow = [r["flow"] for r in sc["rows"]]
        setp = [r["set"] for r in sc["rows"]]
        ax_t, ax_f = axes[i]
        ax_t.plot(t, temp, color="#dc2626", lw=1.6, label="CSF")
        ax_t.plot(t, setp, color="#6b7280", lw=1.2, ls="--", label="Set")
        ax_t.set_ylabel("Temp [C]")
        ax_t.set_title(sc["name"], loc="left", fontsize=10)
        ax_t.grid(True, alpha=0.3)
        if i == 0:
            ax_t.legend(loc="upper right", fontsize=8)
        ax_f.plot(t, flow, color="#2563eb", lw=1.6, label="Flow")
        ax_f.axhline(100, color="#b45309", ls="--", lw=0.8)
        ax_f.axhline(10, color="#6b7280", ls="--", lw=0.8)
        ax_f.set_ylabel("Flow [ml/min]")
        ax_f.set_ylim(0, 110)
        ax_f.grid(True, alpha=0.3)
        if i == n - 1:
            ax_t.set_xlabel("Time [s]")
            ax_f.set_xlabel("Time [s]")
    fig.suptitle(
        "Closed-loop: control input = flow, plant output = CSF temp",
        fontsize=12,
        y=0.995,
    )
    fig.tight_layout()
    scen_path = OUT_DIR / "pump_control_scenarios.png"
    fig.savefig(scen_path, dpi=140)
    plt.close(fig)

    print(f"Wrote {map_path}")
    print(f"Wrote {scen_path}")


if __name__ == "__main__":
    main()
