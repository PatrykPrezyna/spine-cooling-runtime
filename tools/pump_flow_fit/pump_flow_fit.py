"""Fit a through-origin line to measured pump RPM -> flow data and save a residual plot.

Measurements live in a CSV so a later calibration can replace the bundled file
or be passed on the command line. This is a development aid. It is not used
at runtime.

    python tools/pump_flow_fit/pump_flow_fit.py
    python tools/pump_flow_fit/pump_flow_fit.py path/to/other.csv
    python tools/pump_flow_fit/pump_flow_fit.py path/to/other.csv --save out.png

The CSV needs columns ``rpm`` and ``flow_ml_per_min``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "pump_flow_data.csv"
DEFAULT_PNG = HERE / "pump_flow_fit.png"
REQUIRED_COLUMNS = ("rpm", "flow_ml_per_min")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit pump RPM to flow (ml/min) from a calibration CSV and save a residual plot.",
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV,
        help=(
            "Calibration CSV with columns rpm and flow_ml_per_min. "
            f"Default: {DEFAULT_CSV.name} next to this script."
        ),
    )
    parser.add_argument(
        "--save",
        type=Path,
        help=(
            "Figure path. Default: pump_flow_fit.png next to the bundled CSV, "
            "or <csv_name>_fit.png next to a different CSV."
        ),
    )
    return parser.parse_args(argv)


def default_png_for(csv_path: Path) -> Path:
    if csv_path.resolve() == DEFAULT_CSV.resolve():
        return DEFAULT_PNG
    return csv_path.with_name(f"{csv_path.stem}_fit.png")


def load_calibration(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
        if missing:
            found = ", ".join(fieldnames) if fieldnames else "(none)"
            raise SystemExit(
                f"CSV is missing required column(s): {', '.join(missing)}.\n"
                f"Found columns: {found}"
            )

        rpm_values: list[float] = []
        flow_values: list[float] = []
        for line_no, row in enumerate(reader, start=2):
            rpm_text = (row.get("rpm") or "").strip()
            flow_text = (row.get("flow_ml_per_min") or "").strip()
            if not rpm_text and not flow_text:
                continue
            try:
                rpm_values.append(float(rpm_text))
                flow_values.append(float(flow_text))
            except ValueError as exc:
                raise SystemExit(
                    f"{csv_path}:{line_no}: expected numeric rpm and flow_ml_per_min"
                ) from exc

    if not rpm_values:
        raise SystemExit(f"CSV contains no calibration rows: {csv_path}")
    return np.asarray(rpm_values, dtype=float), np.asarray(flow_values, dtype=float)


def fit_slope_through_origin(x: np.ndarray, y: np.ndarray) -> float:
    """Least-squares slope for ``y = slope * x`` (no intercept)."""
    return float(np.sum(x * y) / np.sum(x * x))


def plot(
    rpm: np.ndarray,
    flow_ml_per_min: np.ndarray,
    slope: float,
    mse: float,
    rmse: float,
    save: Path,
) -> None:
    predicted = slope * rpm
    residuals = flow_ml_per_min - predicted

    fig, (ax_fit, ax_res) = plt.subplots(
        2, 1, figsize=(9, 8), height_ratios=[3, 2], sharex=True
    )

    line_x = np.linspace(0, rpm.max() * 1.02, 200)
    ax_fit.plot(
        line_x,
        slope * line_x,
        color="#0e6a76",
        lw=2,
        label=f"linear fit: {slope:.4f}·rpm",
    )
    ax_fit.scatter(rpm, flow_ml_per_min, color="#ef4444", zorder=5, label="measured")
    for xr, ym, yp in zip(rpm, flow_ml_per_min, predicted):
        ax_fit.plot([xr, xr], [yp, ym], color="#9ca3af", lw=1, zorder=4)
    ax_fit.set_ylabel("Flow (ml/min)")
    ax_fit.set_title(
        f"Pump flow: measured vs. linear model\n"
        f"MSE = {mse:.3f} (ml/min)²   RMSE = {rmse:.3f} ml/min"
    )
    ax_fit.grid(True, alpha=0.3)
    ax_fit.legend()

    ax_res.axhline(0, color="#0e6a76", lw=1)
    ax_res.scatter(rpm, residuals, color="#ef4444", zorder=5)
    for xr, residual in zip(rpm, residuals):
        ax_res.plot([xr, xr], [0, residual], color="#9ca3af", lw=1)
    ax_res.set_xlabel("Pump speed (RPM)")
    ax_res.set_ylabel("Residual (ml/min)")
    ax_res.grid(True, alpha=0.3)

    fig.tight_layout()
    save.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    csv_path = args.csv_path
    rpm, flow_ml_per_min = load_calibration(csv_path)
    slope = fit_slope_through_origin(rpm, flow_ml_per_min)
    residuals = flow_ml_per_min - slope * rpm
    mse = float(np.mean(residuals**2))
    rmse = float(np.sqrt(mse))
    save = args.save if args.save is not None else default_png_for(csv_path)

    print(f"Loaded {len(rpm)} points from {csv_path}")
    print(f"Linear model: flow_ml_per_min = {slope:.4f} * rpm")
    print(f"            : flow_ml_per_s   = {slope / 60.0:.6f} * rpm")
    print(f"MSE  = {mse:.4f} (ml/min)^2")
    print(f"RMSE = {rmse:.4f} ml/min")
    plot(rpm, flow_ml_per_min, slope, mse, rmse, save)
    print(f"Saved plot to: {save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
