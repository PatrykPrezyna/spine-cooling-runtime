"""Plot ``heat_ex_c`` and ``csf_c`` from a sensor-log CSV over a selected time range.

The script expects CSVs produced by the spine-cooling runtime, with at least
these columns:

    timestamp, ..., heat_ex_c, csf_c, ...

``timestamp`` is parsed as ISO-8601 (e.g. ``2026-05-04T16:12:26.496456``).

Examples
--------
Plot the whole file:

    python plot_temps.py data/csv/sensor_log_20260504_161226.csv

Plot a sub-range (any datetime-ish string pandas understands works):

    python plot_temps.py data/csv/sensor_log.csv --start "2026-05-04 16:12:30" --end "2026-05-04 16:13:00"

Plot the last 30 seconds and save to PNG without opening a window:

    python plot_temps.py data/csv/sensor_log.csv --last 30s --save out.png --no-show
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


REQUIRED_COLUMNS = ("timestamp", "heat_ex_c", "csf_c")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot heat_ex_c and csf_c from a sensor-log CSV.",
    )
    parser.add_argument("csv_path", type=Path, help="Path to the CSV file.")
    parser.add_argument(
        "--start",
        help="Start of the time window (e.g. '2026-05-04 16:12:30'). Defaults to the first row.",
    )
    parser.add_argument(
        "--end",
        help="End of the time window. Defaults to the last row.",
    )
    parser.add_argument(
        "--last",
        help=(
            "Convenience: plot only the last N of data, e.g. '30s', '5min', '1h'. "
            "Ignored when --start is given."
        ),
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="If set, write the figure to this path (PNG/SVG/PDF inferred from extension).",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open an interactive window (useful with --save).",
    )
    return parser.parse_args(argv)


def load_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(
            f"CSV is missing required column(s): {', '.join(missing)}.\n"
            f"Found columns: {', '.join(df.columns)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        raise SystemExit("CSV contains no parseable timestamp rows.")
    return df


def select_window(
    df: pd.DataFrame,
    start: str | None,
    end: str | None,
    last: str | None,
) -> pd.DataFrame:
    ts = df["timestamp"]
    lo = ts.min()
    hi = ts.max()

    if start is not None:
        lo = pd.to_datetime(start)
    elif last is not None:
        try:
            delta = pd.Timedelta(last)
        except ValueError as exc:
            raise SystemExit(f"Could not parse --last {last!r}: {exc}") from exc
        lo = hi - delta

    if end is not None:
        hi = pd.to_datetime(end)

    if lo > hi:
        raise SystemExit(f"Empty window: start ({lo}) is after end ({hi}).")

    window = df[(ts >= lo) & (ts <= hi)].copy()
    if window.empty:
        raise SystemExit(
            f"No samples between {lo} and {hi}. "
            f"File covers {ts.min()} .. {ts.max()}."
        )
    return window


def plot(df: pd.DataFrame, csv_path: Path, save: Path | None, show: bool) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(df["timestamp"], df["heat_ex_c"], label="Heat Ex (°C)", color="tab:red")
    ax.plot(df["timestamp"], df["csf_c"], label="CSF (°C)", color="tab:blue")

    ax.set_title(f"Heat Ex & CSF — {csv_path.name}")
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

    span = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
    if span <= pd.Timedelta(minutes=2):
        fmt = mdates.DateFormatter("%H:%M:%S")
    elif span <= pd.Timedelta(hours=2):
        fmt = mdates.DateFormatter("%H:%M")
    else:
        fmt = mdates.DateFormatter("%Y-%m-%d %H:%M")
    ax.xaxis.set_major_formatter(fmt)
    fig.autofmt_xdate()
    fig.tight_layout()

    if save is not None:
        save.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save, dpi=150)
        print(f"Saved figure to {save}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    df = load_csv(args.csv_path)
    window = select_window(df, args.start, args.end, args.last)

    print(
        f"Plotting {len(window)} samples from {window['timestamp'].iloc[0]} "
        f"to {window['timestamp'].iloc[-1]}"
    )
    plot(window, args.csv_path, save=args.save, show=not args.no_show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
