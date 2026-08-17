"""Water-loop cooling power from temperature difference and pump flow.

Heat rate:

    P = ṁ · cp · ΔT

``ṁ`` is mass flow of water from the commanded pump volumetric flow
(ml/min) and a configured density. ``cp`` is the specific heat of water.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

WATER_DENSITY_KG_PER_L = 1.0
WATER_CP_J_PER_KG_K = 4184.0

# ml/min → L/s: divide by 60_000. With density in kg/L this is kg/s.
_ML_PER_MIN_TO_L_PER_S = 1.0 / 60000.0


def mass_flow_kg_per_s(
    flow_ml_per_min: float,
    density_kg_per_l: float = WATER_DENSITY_KG_PER_L,
) -> float:
    """Convert volumetric pump flow (ml/min) to water mass flow (kg/s)."""
    return max(0.0, float(flow_ml_per_min)) * _ML_PER_MIN_TO_L_PER_S * float(
        density_kg_per_l
    )


def _as_float(value: Optional[float]) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    return number


def heat_rate_w(
    t_in_c: Optional[float],
    t_out_c: Optional[float],
    flow_ml_per_min: float,
    *,
    density_kg_per_l: float = WATER_DENSITY_KG_PER_L,
    cp_j_per_kg_k: float = WATER_CP_J_PER_KG_K,
) -> float:
    """Heat gained by the fluid (W): ṁ · cp · (T_out − T_in).

    Returns NaN if either temperature is missing.
    """
    t_in = _as_float(t_in_c)
    t_out = _as_float(t_out_c)
    if math.isnan(t_in) or math.isnan(t_out):
        return float("nan")
    return (
        mass_flow_kg_per_s(flow_ml_per_min, density_kg_per_l)
        * float(cp_j_per_kg_k)
        * (t_out - t_in)
    )


def catheter_cooling_power_w(
    t_in_c: Optional[float],
    t_out_c: Optional[float],
    flow_ml_per_min: float,
    *,
    density_kg_per_l: float = WATER_DENSITY_KG_PER_L,
    cp_j_per_kg_k: float = WATER_CP_J_PER_KG_K,
) -> float:
    """Heat picked up by water in the catheter (W).

    Positive when water leaves warmer than it entered (cooling the patient).
    """
    return heat_rate_w(
        t_in_c,
        t_out_c,
        flow_ml_per_min,
        density_kg_per_l=density_kg_per_l,
        cp_j_per_kg_k=cp_j_per_kg_k,
    )


def cartridge_cooling_power_w(
    t_in_c: Optional[float],
    t_out_c: Optional[float],
    flow_ml_per_min: float,
    *,
    density_kg_per_l: float = WATER_DENSITY_KG_PER_L,
    cp_j_per_kg_k: float = WATER_CP_J_PER_KG_K,
) -> float:
    """Heat extracted from water by the cartridge (W).

    Positive when water leaves the cartridge colder than it entered.
    """
    return heat_rate_w(
        t_out_c,
        t_in_c,
        flow_ml_per_min,
        density_kg_per_l=density_kg_per_l,
        cp_j_per_kg_k=cp_j_per_kg_k,
    )


@dataclass(frozen=True)
class CoolingPowerConfig:
    water_density_kg_per_l: float = WATER_DENSITY_KG_PER_L
    water_cp_j_per_kg_k: float = WATER_CP_J_PER_KG_K
    catheter_in_label: str = "Catheter In"
    catheter_out_label: str = "Catheter Out"
    cartridge_in_label: str = "Cartrige In"
    cartridge_out_label: str = "Cartrige Out"

    @classmethod
    def from_config_dict(cls, raw: Optional[dict]) -> "CoolingPowerConfig":
        raw = raw or {}
        return cls(
            water_density_kg_per_l=float(
                raw.get("water_density_kg_per_l", WATER_DENSITY_KG_PER_L)
            ),
            water_cp_j_per_kg_k=float(
                raw.get("water_cp_j_per_kg_k", WATER_CP_J_PER_KG_K)
            ),
            catheter_in_label=str(raw.get("catheter_in_label", "Catheter In")),
            catheter_out_label=str(raw.get("catheter_out_label", "Catheter Out")),
            cartridge_in_label=str(raw.get("cartridge_in_label", "Cartrige In")),
            cartridge_out_label=str(raw.get("cartridge_out_label", "Cartrige Out")),
        )
