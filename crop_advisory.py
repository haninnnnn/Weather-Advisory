"""Crop-specific advisory layer for the Weather Advisory Generator.

Extends the base advisory with rules tuned to individual crops.
Supported crops: rice, wheat, maize, tomato, groundnut, sugarcane.

Usage (command line):
    python crop_advisory.py rice '{"temperature_c": 32, "rainfall_mm": 8, "humidity_pct": 75, "wind_speed_kmh": 12}'
    python crop_advisory.py wheat weather.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

from advisory import (
    AVOID, CAUTION, GO,
    Activity, Plan, build_plan, classify, render_plan, validate,
)

# ---------------------------------------------------------------------------
# Crop catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CropProfile:
    name: str                      # display name
    optimal_temp_low: float        # °C  — below this is suboptimal
    optimal_temp_high: float       # °C  — above this is suboptimal
    min_rain_mm: float             # seasonal daily minimum to maintain yield
    waterlog_risk: bool            # True  → sensitive to standing water
    drought_sensitive: bool        # True  → wilts fast when dry
    fungal_risk_humidity: float    # % — disease risk threshold for this crop


CROPS: Dict[str, CropProfile] = {
    "rice": CropProfile(
        name="Rice (Paddy)",
        optimal_temp_low=22.0, optimal_temp_high=35.0,
        min_rain_mm=5.0, waterlog_risk=False,  # tolerates flooding
        drought_sensitive=True, fungal_risk_humidity=75.0,
    ),
    "wheat": CropProfile(
        name="Wheat",
        optimal_temp_low=10.0, optimal_temp_high=25.0,
        min_rain_mm=1.0, waterlog_risk=True,
        drought_sensitive=False, fungal_risk_humidity=70.0,
    ),
    "maize": CropProfile(
        name="Maize (Corn)",
        optimal_temp_low=18.0, optimal_temp_high=32.0,
        min_rain_mm=2.5, waterlog_risk=True,
        drought_sensitive=True, fungal_risk_humidity=80.0,
    ),
    "tomato": CropProfile(
        name="Tomato",
        optimal_temp_low=18.0, optimal_temp_high=30.0,
        min_rain_mm=2.0, waterlog_risk=True,
        drought_sensitive=True, fungal_risk_humidity=70.0,
    ),
    "groundnut": CropProfile(
        name="Groundnut (Peanut)",
        optimal_temp_low=22.0, optimal_temp_high=35.0,
        min_rain_mm=2.0, waterlog_risk=True,
        drought_sensitive=False, fungal_risk_humidity=85.0,
    ),
    "sugarcane": CropProfile(
        name="Sugarcane",
        optimal_temp_low=20.0, optimal_temp_high=38.0,
        min_rain_mm=3.0, waterlog_risk=False,
        drought_sensitive=True, fungal_risk_humidity=80.0,
    ),
}

CROP_NAMES = list(CROPS.keys())


# ---------------------------------------------------------------------------
# Crop-specific rules
# ---------------------------------------------------------------------------

def _crop_temperature_note(v: Dict[str, float], crop: CropProfile) -> str | None:
    t = v["temperature_c"]
    if t < crop.optimal_temp_low:
        return (f"{crop.name} grows best above {crop.optimal_temp_low} °C. "
                f"At {t:g} °C growth slows and yield may fall.")
    if t > crop.optimal_temp_high:
        return (f"{crop.name} grows best below {crop.optimal_temp_high} °C. "
                f"At {t:g} °C heat stress reduces grain or fruit set.")
    return None


def _crop_rain_note(v: Dict[str, float], crop: CropProfile) -> str | None:
    r = v["rainfall_mm"]
    if r < crop.min_rain_mm and crop.drought_sensitive:
        return (f"{crop.name} is drought-sensitive. With only {r:g} mm today, "
                "irrigate to maintain soil moisture around the root zone.")
    if r >= 20.0 and crop.waterlog_risk:
        return (f"{crop.name} is sensitive to waterlogging. "
                f"Check drainage channels urgently — {r:g} mm risks standing water.")
    return None


def _crop_humidity_note(v: Dict[str, float], crop: CropProfile) -> str | None:
    h = v["humidity_pct"]
    if h >= crop.fungal_risk_humidity:
        return (f"Humidity of {h:g}% exceeds the threshold for {crop.name} "
                f"({crop.fungal_risk_humidity:.0f}%). Scout for fungal lesions and apply "
                "a registered fungicide if symptoms appear.")
    return None


def crop_notes(data: Dict[str, Any], crop_key: str) -> List[str]:
    """Return crop-specific advisory notes for the validated readings."""
    if crop_key not in CROPS:
        raise ValueError(f"unknown crop {crop_key!r}. Choose from: {', '.join(CROP_NAMES)}")
    v = validate(data)
    crop = CROPS[crop_key]
    notes: List[str] = []
    for fn in (_crop_temperature_note, _crop_rain_note, _crop_humidity_note):
        note = fn(v, crop)
        if note:
            notes.append(note)
    return notes


# ---------------------------------------------------------------------------
# Combined plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CropPlan:
    crop: CropProfile
    base_plan: Plan
    crop_notes: List[str]


def build_crop_plan(data: Dict[str, Any], crop_key: str) -> CropPlan:
    """Build the base advisory plan and append crop-specific notes."""
    base = build_plan(data)
    cn = crop_notes(data, crop_key)
    return CropPlan(crop=CROPS[crop_key], base_plan=base, crop_notes=cn)


def render_crop_plan(cp: CropPlan) -> str:
    lines = [f"Crop: {cp.crop.name}", ""]
    lines.append(render_plan(cp.base_plan))
    if cp.crop_notes:
        lines += ["", f"CROP-SPECIFIC NOTES FOR {cp.crop.name.upper()}"]
        lines += [f"- {n}" for n in cp.crop_notes]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        print(f"Available crops: {', '.join(CROP_NAMES)}")
        return 2
    crop_key, arg = argv[1], argv[2]
    try:
        if arg.endswith(".json"):
            with open(arg, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(arg)
        cp = build_crop_plan(data, crop_key)
        print(render_crop_plan(cp))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
