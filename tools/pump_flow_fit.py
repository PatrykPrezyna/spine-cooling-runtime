"""One-off analysis: pump flow calibration vs. the linear model.

Fits a line (through the origin) to the measured ``RPM -> flow`` data used by
the runtime, reports the mean squared error (MSE), and saves a plot showing
the measured points, the fitted line, and the per-point residuals.

This is a development/justification aid -- it is NOT used at runtime. Run it
once to regenerate the figure:

    python tools/pump_flow_fit.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Measured calibration data: pump RPM -> flow (ml/min).
RPM = np.array(
    [2, 5, 11, 15, 20, 30, 40, 50, 60, 90, 120, 200, 240, 300, 390],
    dtype=float,
)
FLOW_ML_PER_MIN = np.array(
    [1.5, 4, 8.5, 11.5, 15.5, 23, 30.5, 38.5, 46.25, 69, 91.75, 156.5, 187.5, 236, 305.5],
    dtype=float,
)

OUTPUT_PNG = Path(__file__).resolve().parent / "pump_flow_fit.png"


def fit_slope_through_origin(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope for ``y = slope * x`` (no intercept)."""
    return float(np.sum(x * y) / np.sum(x * x))


def main() -> None:
    slope = fit_slope_through_origin(RPM, FLOW_ML_PER_MIN)
    predicted = slope * RPM
    residuals = FLOW_ML_PER_MIN - predicted
    mse = float(np.mean(residuals**2))
    rmse = float(np.sqrt(mse))

    print(f"Linear model: flow_ml_per_min = {slope:.4f} * rpm")
    print(f"            : flow_ml_per_s   = {slope / 60.0:.6f} * rpm")
    print(f"MSE  = {mse:.4f} (ml/min)^2")
    print(f"RMSE = {rmse:.4f} ml/min")

    fig, (ax_fit, ax_res) = plt.subplots(
        2, 1, figsize=(9, 8), height_ratios=[3, 2], sharex=True
    )

    # Top: measured points + fitted line.
    line_x = np.linspace(0, RPM.max() * 1.02, 200)
    ax_fit.plot(
        line_x,
        slope * line_x,
        color="#0e6a76",
        lw=2,
        label=f"linear fit: {slope:.4f}·rpm",
    )
    ax_fit.scatter(
        RPM, FLOW_ML_PER_MIN, color="#ef4444", zorder=5, label="measured"
    )
    # Draw residual stems so the deviation at each point is visible.
    for xr, ym, yp in zip(RPM, FLOW_ML_PER_MIN, predicted):
        ax_fit.plot([xr, xr], [yp, ym], color="#9ca3af", lw=1, zorder=4)
    ax_fit.set_ylabel("Flow (ml/min)")
    ax_fit.set_title(
        f"Pump flow: measured vs. linear model\n"
        f"MSE = {mse:.3f} (ml/min)²   RMSE = {rmse:.3f} ml/min"
    )
    ax_fit.grid(True, alpha=0.3)
    ax_fit.legend()

    # Bottom: residuals per RPM.
    ax_res.axhline(0, color="#0e6a76", lw=1)
    ax_res.scatter(RPM, residuals, color="#ef4444", zorder=5)
    for xr, r in zip(RPM, residuals):
        ax_res.plot([xr, xr], [0, r], color="#9ca3af", lw=1)
    ax_res.set_xlabel("Pump speed (RPM)")
    ax_res.set_ylabel("Residual (ml/min)")
    ax_res.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUTPUT_PNG, dpi=120)
    print(f"Saved plot to: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
