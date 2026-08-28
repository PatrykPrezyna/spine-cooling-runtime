"""Load a runtime session folder (sensors / pressure / status CSVs).

Filenames follow ``session_log_paths``:

    20260819_150802_sensors.csv
    20260819_150802_pressure_100Hz.csv
    20260819_150802_status_and_errors.csv
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from cooling_power import (
    CoolingPowerConfig,
    cartridge_cooling_power_w,
    catheter_cooling_power_w,
)

STAMP_RE = re.compile(r"^(\d{8}_\d{6})")
SENSORS_SUFFIX = "_sensors.csv"
PRESSURE_SUFFIX = "_pressure_100Hz"
STATUS_SUFFIX = "_status_and_errors.csv"

SKIP_TEMP_COLUMNS = frozenset(
    {
        "timestamp",
        "set_temperature_c",
        "peristaltic_pump_set_speed_rpm",
        "pump_flow_ml_per_s",
        "flow_sensor_ml_per_min",
        "compressor_cooling",
    }
)

KNOWN_LABELS = {
    "tip": "Tip",
    "cartrige_out": "Cartrige Out",
    "cartridge_out": "Cartridge Out",
    "catheter_in": "Catheter In",
    "catheter_out": "Catheter Out",
    "cartrige_in": "Cartrige In",
    "cartridge_in": "Cartridge In",
    "probe_1": "Probe 1",
    "probe_2": "Probe 2",
    "plate": "Plate",
    "pump_in": "Pump In",
    "pump_out": "Pump Out",
    "heat_ex": "Heat Ex",
    "csf": "CSF",
}

DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM = 0.5862
_MAX_PLOT_POINTS = 12000


@dataclass(frozen=True)
class SessionEvent:
    timestamp: float
    event: str
    severity: str
    previous_state: str
    state: str
    fault_code: str
    message: str
    timestamp_text: str


@dataclass
class SessionData:
    stamp: str
    folder: Path
    sensors_path: Optional[Path] = None
    pressure_path: Optional[Path] = None
    status_path: Optional[Path] = None
    temperature_names: list[str] = field(default_factory=list)
    pressure_names: list[str] = field(default_factory=list)
    temperature_samples: list[tuple[float, dict[str, float]]] = field(default_factory=list)
    pressure_samples: list[tuple[float, dict[str, float]]] = field(default_factory=list)
    power_samples: list[tuple[float, dict[str, float]]] = field(default_factory=list)
    events: list[SessionEvent] = field(default_factory=list)
    set_temperature_c: Optional[float] = None
    duration_s: float = 0.0
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None

    @property
    def last_state(self) -> str:
        for event in reversed(self.events):
            if event.state:
                return event.state
        return "Log"

    @property
    def duration_minutes(self) -> float:
        return self.duration_s / 60.0


def csv_slug_to_label(slug: str) -> str:
    """Turn a CSV column slug (without ``_c`` / ``_bar``) into a display name."""
    key = slug.strip().lower()
    if key in KNOWN_LABELS:
        return KNOWN_LABELS[key]
    return " ".join(part.capitalize() for part in key.split("_") if part)


def parse_timestamp(value: str) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _as_float(value: object) -> float:
    if value is None:
        return float("nan")
    text = str(value).strip()
    if text == "":
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def discover_session_files(path: Path) -> tuple[str, Optional[Path], Optional[Path], Optional[Path]]:
    """Resolve a folder or any session CSV to the three sibling files."""
    path = Path(path)
    if path.is_file():
        folder = path.parent
        match = STAMP_RE.match(path.name)
        if match is None:
            raise ValueError(f"Not a session log filename: {path.name}")
        stamp = match.group(1)
    elif path.is_dir():
        folder = path
        stamps = sorted(
            {
                match.group(1)
                for name in (p.name for p in folder.iterdir() if p.is_file())
                for match in [STAMP_RE.match(name)]
                if match is not None
                and (
                    name.endswith(SENSORS_SUFFIX)
                    or PRESSURE_SUFFIX in name
                    or name.endswith(STATUS_SUFFIX)
                )
            }
        )
        if not stamps:
            raise ValueError(f"No session CSVs in {folder}")
        stamp = stamps[-1]
    else:
        raise FileNotFoundError(path)

    sensors = folder / f"{stamp}{SENSORS_SUFFIX}"
    status = folder / f"{stamp}{STATUS_SUFFIX}"
    pressure = _find_pressure_file(folder, stamp)
    return (
        stamp,
        sensors if sensors.is_file() else None,
        pressure,
        status if status.is_file() else None,
    )


def _find_pressure_file(folder: Path, stamp: str) -> Optional[Path]:
    primary = folder / f"{stamp}_pressure_100Hz.csv"
    if primary.is_file():
        return primary
    matches = sorted(folder.glob(f"{stamp}_pressure_100Hz*.csv"))
    return matches[-1] if matches else None


def downsample(entries: list, max_points: int = _MAX_PLOT_POINTS) -> list:
    if max_points <= 0 or len(entries) <= max_points:
        return entries
    step = math.ceil(len(entries) / max_points)
    sampled = entries[::step]
    if sampled[-1] is not entries[-1]:
        sampled.append(entries[-1])
    return sampled


def load_session(
    path: Path,
    *,
    pump_flow_ml_per_min_per_rpm: float = DEFAULT_PUMP_FLOW_ML_PER_MIN_PER_RPM,
    power_config: Optional[CoolingPowerConfig] = None,
    max_plot_points: int = _MAX_PLOT_POINTS,
) -> SessionData:
    stamp, sensors_path, pressure_path, status_path = discover_session_files(Path(path))
    cfg = power_config or CoolingPowerConfig()
    session = SessionData(
        stamp=stamp,
        folder=sensors_path.parent if sensors_path else Path(path),
        sensors_path=sensors_path,
        pressure_path=pressure_path,
        status_path=status_path,
    )

    extras: list[tuple[float, dict[str, float]]] = []
    if sensors_path is not None:
        names, samples, extras, set_temp = _load_sensors_csv(sensors_path)
        session.temperature_names = names
        session.temperature_samples = downsample(samples, max_plot_points)
        session.set_temperature_c = set_temp
        extras = downsample(extras, max_plot_points)

    if pressure_path is not None:
        names, samples = _load_pressure_csv(
            pressure_path, pump_flow_ml_per_min_per_rpm
        )
        session.pressure_names = names
        session.pressure_samples = downsample(samples, max_plot_points)
    elif extras:
        session.pressure_names, session.pressure_samples = _pressure_from_sensors(
            extras
        )

    if extras:
        session.power_samples = _power_from_sensors(extras, cfg)
    elif session.temperature_samples:
        session.power_samples = [
            (ts, {"Catheter": float("nan"), "Cartridge": float("nan")})
            for ts, _values in session.temperature_samples
        ]

    if status_path is not None:
        session.events = _load_status_csv(status_path)

    timestamps = [
        ts
        for series in (
            session.temperature_samples,
            session.pressure_samples,
            [(event.timestamp, None) for event in session.events],
        )
        for ts, _payload in series
    ]
    if timestamps:
        session.start_ts = min(timestamps)
        session.end_ts = max(timestamps)
        session.duration_s = max(0.0, session.end_ts - session.start_ts)
    return session


def series_stats(samples: Iterable[tuple[float, dict[str, float]]], name: str) -> dict[str, float]:
    values = []
    for _ts, row in samples:
        value = row.get(name, float("nan"))
        if value is not None and not math.isnan(value):
            values.append(float(value))
    if not values:
        return {"min": float("nan"), "max": float("nan"), "mean": float("nan")}
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def _load_sensors_csv(
    path: Path,
) -> tuple[
    list[str],
    list[tuple[float, dict[str, float]]],
    list[tuple[float, dict[str, float]]],
    Optional[float],
]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        temp_columns = [
            column
            for column in fieldnames
            if column.endswith("_c") and column not in SKIP_TEMP_COLUMNS
        ]
        pressure_columns = [column for column in fieldnames if column.endswith("_bar")]
        names = [csv_slug_to_label(column[:-2]) for column in temp_columns]
        samples: list[tuple[float, dict[str, float]]] = []
        extras: list[tuple[float, dict[str, float]]] = []
        last_set_temp: Optional[float] = None
        for row in reader:
            ts = parse_timestamp(row.get("timestamp", ""))
            if ts is None:
                continue
            temps = {
                names[index]: _as_float(row.get(column))
                for index, column in enumerate(temp_columns)
            }
            samples.append((ts, temps))
            extra = dict(temps)
            extra["set_temperature_c"] = _as_float(row.get("set_temperature_c"))
            extra["pump_rpm"] = _as_float(row.get("peristaltic_pump_set_speed_rpm"))
            extra["flow_ml_per_s"] = _as_float(row.get("pump_flow_ml_per_s"))
            extra["flow_sensor_ml_per_min"] = _as_float(
                row.get("flow_sensor_ml_per_min")
            )
            extra["compressor_cooling"] = _as_float(row.get("compressor_cooling"))
            for column in pressure_columns:
                extra[csv_slug_to_label(column[:-4])] = _as_float(row.get(column))
            extras.append((ts, extra))
            set_temp = extra["set_temperature_c"]
            if not math.isnan(set_temp):
                last_set_temp = set_temp
    return names, samples, extras, last_set_temp


def _load_pressure_csv(
    path: Path, pump_flow_ml_per_min_per_rpm: float
) -> tuple[list[str], list[tuple[float, dict[str, float]]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        columns = [column for column in fieldnames if column.endswith("_bar")]
        names = [csv_slug_to_label(column[:-4]) for column in columns]
        samples: list[tuple[float, dict[str, float]]] = []
        for row in reader:
            ts = parse_timestamp(row.get("timestamp", ""))
            if ts is None:
                continue
            values = {
                names[index]: _as_float(row.get(column))
                for index, column in enumerate(columns)
            }
            rpm = _as_float(row.get("peristaltic_pump_set_speed_rpm"))
            flow = (
                max(0.0, rpm) * float(pump_flow_ml_per_min_per_rpm)
                if not math.isnan(rpm)
                else float("nan")
            )
            values["Flow"] = flow
            samples.append((ts, values))
    return names, samples


def _pressure_from_sensors(
    extras: list[tuple[float, dict[str, float]]],
) -> tuple[list[str], list[tuple[float, dict[str, float]]]]:
    preferred = ("Pump In", "Pump Out", "Catheter In", "Catheter Out")
    present = [name for name in preferred if any(name in row for _ts, row in extras)]
    if not present:
        return [], []
    samples = []
    for ts, row in extras:
        values = {name: row.get(name, float("nan")) for name in present}
        flow_s = row.get("flow_ml_per_s", float("nan"))
        values["Flow"] = (
            max(0.0, flow_s) * 60.0 if not math.isnan(flow_s) else float("nan")
        )
        samples.append((ts, values))
    return present, samples


def _power_from_sensors(
    extras: list[tuple[float, dict[str, float]]],
    cfg: CoolingPowerConfig,
) -> list[tuple[float, dict[str, float]]]:
    kwargs = {
        "density_kg_per_l": cfg.water_density_kg_per_l,
        "cp_j_per_kg_k": cfg.water_cp_j_per_kg_k,
    }
    samples = []
    for ts, row in extras:
        flow_s = row.get("flow_ml_per_s", float("nan"))
        flow_ml_per_min = (
            max(0.0, flow_s) * 60.0 if not math.isnan(flow_s) else 0.0
        )
        samples.append(
            (
                ts,
                {
                    "Catheter": catheter_cooling_power_w(
                        row.get(cfg.catheter_in_label),
                        row.get(cfg.catheter_out_label),
                        flow_ml_per_min,
                        **kwargs,
                    ),
                    "Cartridge": cartridge_cooling_power_w(
                        row.get(cfg.cartridge_in_label),
                        row.get(cfg.cartridge_out_label),
                        flow_ml_per_min,
                        **kwargs,
                    ),
                },
            )
        )
    return samples


def _load_status_csv(path: Path) -> list[SessionEvent]:
    events: list[SessionEvent] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = row.get("timestamp", "")
            ts = parse_timestamp(text)
            if ts is None:
                continue
            events.append(
                SessionEvent(
                    timestamp=ts,
                    event=str(row.get("event") or ""),
                    severity=str(row.get("severity") or ""),
                    previous_state=str(row.get("previous_state") or ""),
                    state=str(row.get("state") or ""),
                    fault_code=str(row.get("fault_code") or ""),
                    message=str(row.get("message") or ""),
                    timestamp_text=text,
                )
            )
    return events
