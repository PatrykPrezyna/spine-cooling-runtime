"""NTC thermistor voltage → temperature conversion.

Divider: ``V = Vref * R / (Rs + R)`` with the thermistor to ground and ``Rs``
as the pull-up. Resistance→°C comes from the manufacturer R–T table
(``10k_Ohm`` on MA300TA103C by default).
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE_CSV = PROJECT_ROOT / "data" / "calibration" / "Thermistor_MA300TA103C.csv"
DEFAULT_R_COL = "10k_Ohm"
DEFAULT_VREF_V = 2.5
DEFAULT_RS_OHM = 100_000.0

_T_COL_ALIASES = ("Temperature_C", "T [celsius]", "T [C]", "T")
_R_COL_ALIASES = ("10k_Ohm", "Resistance_Ohm", "Rnom [ohms]", "Rnom", "R nom")

RtPoint = Tuple[float, float]  # (R_ohm, T_C)


def _norm_col(name: str) -> str:
    return "".join(ch for ch in name.strip().lower() if ch.isalnum())


def _match_col(cells: Sequence[str], *candidates: str) -> Optional[str]:
    by_norm = {_norm_col(cell): cell for cell in cells if str(cell).strip()}
    for candidate in candidates:
        key = _norm_col(candidate)
        if key in by_norm:
            return by_norm[key]
    return None


def resolve_table_path(path: Optional[str | Path] = None) -> Path:
    """Resolve a table path relative to cwd or the project root."""
    if path is None or str(path).strip() == "":
        return DEFAULT_TABLE_CSV
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    from_root = PROJECT_ROOT / candidate
    if from_root.is_file():
        return from_root
    return candidate


def load_rt_table(
    path: Optional[str | Path] = None,
    r_col: str = DEFAULT_R_COL,
    t_col: Optional[str] = None,
) -> list[RtPoint]:
    """Return ``(R_ohm, T_C)`` pairs sorted by descending R (NTC).

    Accepts ``Rnom [ohms]`` / ``T [celsius]`` as well as the MA300 columns.
    """
    table_path = resolve_table_path(path)
    t_candidates = (t_col,) if t_col else _T_COL_ALIASES
    r_candidates = (r_col, *_R_COL_ALIASES)
    with table_path.open(newline="", encoding="utf-8-sig") as f:
        raw_rows = list(csv.reader(f, skipinitialspace=True))

    header_idx: Optional[int] = None
    t_key: Optional[str] = None
    r_key: Optional[str] = None
    for index, cells in enumerate(raw_rows):
        t_key = _match_col(cells, *t_candidates)
        r_key = _match_col(cells, *r_candidates)
        if t_key is not None and r_key is not None:
            header_idx = index
            break
    if header_idx is None or t_key is None or r_key is None:
        raise ValueError(
            f"Thermistor R–T table has no temperature/R columns: {table_path}"
        )

    header = raw_rows[header_idx]
    t_idx = header.index(t_key)
    r_idx = header.index(r_key)
    rows: list[RtPoint] = []
    for cells in raw_rows[header_idx + 1 :]:
        if max(t_idx, r_idx) >= len(cells):
            continue
        try:
            rows.append((float(cells[r_idx]), float(cells[t_idx])))
        except (TypeError, ValueError):
            continue
    if len(rows) < 2:
        raise ValueError(f"Thermistor R–T table needs ≥2 rows: {table_path}")
    rows.sort(key=lambda p: -p[0])
    return rows


@lru_cache(maxsize=8)
def _cached_rt_table(path_str: str, r_col: str) -> Tuple[RtPoint, ...]:
    return tuple(load_rt_table(path_str, r_col=r_col))


def default_rt_table() -> Tuple[RtPoint, ...]:
    return _cached_rt_table(str(DEFAULT_TABLE_CSV), DEFAULT_R_COL)


def voltage_to_r(
    voltage_v: float,
    *,
    vref_v: float = DEFAULT_VREF_V,
    rs_ohm: float = DEFAULT_RS_OHM,
) -> float:
    """Invert ``V = Vref * R / (Rs + R)``."""
    v = float(voltage_v)
    if v <= 0.0:
        return 0.0
    if v >= float(vref_v):
        return float("inf")
    return float(rs_ohm) * v / (float(vref_v) - v)


def r_to_celsius(r_ohm: float, table: Sequence[RtPoint]) -> float:
    """Linear interpolate °C from resistance; extrapolate beyond endpoints."""
    if not table:
        return float("nan")
    pts = list(table)
    r = float(r_ohm)
    if len(pts) == 1:
        return pts[0][1]

    if r >= pts[0][0]:
        a, b = pts[0], pts[1]
    elif r <= pts[-1][0]:
        a, b = pts[-2], pts[-1]
    else:
        a = b = pts[0]
        for left, right in zip(pts, pts[1:]):
            if right[0] <= r <= left[0]:
                a, b = left, right
                break

    r_a, t_a = a
    r_b, t_b = b
    if abs(r_b - r_a) < 1e-12:
        return t_a
    return t_a + (r - r_a) * (t_b - t_a) / (r_b - r_a)


def voltage_to_celsius(
    voltage_v: float,
    table: Optional[Sequence[RtPoint]] = None,
    *,
    vref_v: float = DEFAULT_VREF_V,
    rs_ohm: float = DEFAULT_RS_OHM,
) -> float:
    pts = default_rt_table() if table is None else table
    return r_to_celsius(voltage_to_r(voltage_v, vref_v=vref_v, rs_ohm=rs_ohm), pts)


def millivolts_to_celsius(
    millivolts: float,
    table: Optional[Sequence[RtPoint]] = None,
    *,
    vref_v: float = DEFAULT_VREF_V,
    rs_ohm: float = DEFAULT_RS_OHM,
) -> float:
    return voltage_to_celsius(
        float(millivolts) / 1000.0,
        table,
        vref_v=vref_v,
        rs_ohm=rs_ohm,
    )
