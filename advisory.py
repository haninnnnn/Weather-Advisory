"""Automated Weather Advisory Text Generator (rule-based NLG).

NLP PBL project #6 (SDG 2 - Zero Hunger, SDG 13 - Climate Action).

Objectives:
1. Process temperature, rainfall, humidity and wind-speed data.
2. Generate advisory messages with rule-based NLG.
3. Present clear advisories to support agricultural planning.

Usage:
    python advisory.py '{"temperature_c": 37, "rainfall_mm": 0, "humidity_pct": 22, "wind_speed_kmh": 30}'
    python advisory.py weather.json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

# Thresholds are illustrative defaults. An agronomist should tune them for the region.
COLD_C = 10.0          # at or below: cold stress
HEAT_C = 35.0          # at or above: heat stress
DRY_MM = 2.0           # below: dry
HEAVY_MM = 20.0        # at or above: heavy rain
VERY_HEAVY_MM = 50.0   # at or above: very heavy rain
HUMID_HIGH_PCT = 80.0  # at or above: fungal disease risk
HUMID_LOW_PCT = 30.0   # at or below: fast moisture loss
WIND_STRONG_KMH = 25.0 # at or above: spray drift

GO, CAUTION, AVOID = "GO", "CAUTION", "AVOID"

# field name -> (min, max) accepted physical range
FIELD_RANGES: Dict[str, tuple] = {
    "temperature_c": (-60.0, 60.0),
    "rainfall_mm": (0.0, 1000.0),
    "humidity_pct": (0.0, 100.0),
    "wind_speed_kmh": (0.0, 300.0),
}


# ---- Objective 1: process the readings -----------------------------------

def validate(data: Dict[str, Any]) -> Dict[str, float]:
    """Check that every field is present, numeric and in range."""
    if not isinstance(data, dict):
        raise ValueError("weather data must be a JSON object")
    clean: Dict[str, float] = {}
    for field, (lo, hi) in FIELD_RANGES.items():
        if field not in data:
            raise ValueError(f"missing field: {field}")
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} must be a number, got {value!r}")
        if not lo <= value <= hi:
            raise ValueError(f"{field}={value} is outside the range {lo}..{hi}")
        clean[field] = float(value)
    return clean


def classify(v: Dict[str, float]) -> Dict[str, str]:
    """Turn each raw reading into a category the rules can reason about."""
    t, r, h, w = v["temperature_c"], v["rainfall_mm"], v["humidity_pct"], v["wind_speed_kmh"]
    if r >= VERY_HEAVY_MM:
        rain = "very_heavy"
    elif r >= HEAVY_MM:
        rain = "heavy"
    elif r < DRY_MM:
        rain = "dry"
    else:
        rain = "moderate"
    return {
        "temperature": "cold" if t <= COLD_C else "heat" if t >= HEAT_C else "comfortable",
        "rainfall": rain,
        "humidity": "high" if h >= HUMID_HIGH_PCT else "low" if h <= HUMID_LOW_PCT else "moderate",
        "wind": "strong" if w >= WIND_STRONG_KMH else "calm",
    }


# ---- Objective 2: rule-based NLG -----------------------------------------

@dataclass(frozen=True)
class Activity:
    name: str
    status: str  # GO, CAUTION or AVOID
    reason: str


def _irrigation(v: Dict[str, float], c: Dict[str, str]) -> Activity:
    name, t, r, h = "Irrigation", v["temperature_c"], v["rainfall_mm"], v["humidity_pct"]
    if c["rainfall"] in ("heavy", "very_heavy"):
        return Activity(name, AVOID,
                        f"Heavy rain ({r:g} mm) already supplies water. Irrigating now wastes "
                        "water and can waterlog the field.")
    needs = []
    if c["rainfall"] == "dry":
        needs.append(f"only {r:g} mm of rain")
    if c["temperature"] == "heat":
        needs.append(f"temperature is {t:g} °C")
    if c["humidity"] == "low":
        needs.append(f"humidity is {h:g}%")
    if needs:
        return Activity(name, GO, "Crops are losing water fast: " + "; ".join(needs)
                        + ". Irrigate early morning or evening.")
    return Activity(name, CAUTION, f"Rain of {r:g} mm and moderate conditions. Check soil "
                                   "moisture before irrigating.")


def _spraying(v: Dict[str, float], c: Dict[str, str]) -> Activity:
    name, t, r, w = "Pesticide or herbicide spraying", v["temperature_c"], v["rainfall_mm"], v["wind_speed_kmh"]
    if c["wind"] == "strong":
        return Activity(name, AVOID, f"Wind of {w:g} km/h will carry spray onto neighbouring "
                                     "fields and away from the crop.")
    if c["rainfall"] != "dry":
        return Activity(name, AVOID, f"Rain of {r:g} mm will wash the spray off before it works.")
    if c["temperature"] == "heat":
        return Activity(name, CAUTION, f"At {t:g} °C spray dries quickly and can scorch leaves. "
                                       "Spray early morning or late evening.")
    return Activity(name, GO, "Calm and dry. Good conditions for spraying at the label dose.")


def _fertilizer(v: Dict[str, float], c: Dict[str, str]) -> Activity:
    name, t, r = "Fertilizer application", v["temperature_c"], v["rainfall_mm"]
    if c["rainfall"] in ("heavy", "very_heavy"):
        return Activity(name, AVOID, f"Heavy rain ({r:g} mm) will wash fertilizer out of the "
                                     "root zone.")
    if c["rainfall"] == "moderate":
        return Activity(name, CAUTION, f"Rain of {r:g} mm may wash some fertilizer away. Apply "
                                       "only if more rain is not expected today.")
    if c["temperature"] == "heat":
        return Activity(name, CAUTION, f"At {t:g} °C fertilizer can burn roots on dry soil. "
                                       "Water it in after applying.")
    return Activity(name, GO, "Dry soil and calm weather. Apply, then water in lightly.")


def _field_work(v: Dict[str, float], c: Dict[str, str]) -> Activity:
    name, t, r = "Field work (weeding, harvesting)", v["temperature_c"], v["rainfall_mm"]
    if c["rainfall"] in ("heavy", "very_heavy"):
        return Activity(name, AVOID, f"Heavy rain ({r:g} mm) waterlogs fields and makes them "
                                     "unsafe to work.")
    if c["temperature"] == "heat":
        return Activity(name, CAUTION, f"At {t:g} °C, work in the early morning and take "
                                       "frequent breaks.")
    if c["rainfall"] == "moderate":
        return Activity(name, CAUTION, f"Rain of {r:g} mm makes fields slippery. Start on the "
                                       "drier plots.")
    return Activity(name, GO, "Good conditions for weeding and harvesting.")


def _sowing(v: Dict[str, float], c: Dict[str, str]) -> Activity:
    name, t, r = "Sowing or transplanting", v["temperature_c"], v["rainfall_mm"]
    if c["rainfall"] == "very_heavy":
        return Activity(name, AVOID, f"Very heavy rain ({r:g} mm) washes seed out and waterlogs "
                                     "the seedbed.")
    if c["temperature"] == "cold":
        return Activity(name, AVOID, f"At {t:g} °C seed germinates slowly and young seedlings "
                                     "are easily chilled.")
    if c["temperature"] == "heat":
        return Activity(name, CAUTION, f"At {t:g} °C seedbeds dry out quickly. Water the "
                                       "seedbed after sowing.")
    if c["rainfall"] == "heavy":
        return Activity(name, CAUTION, f"Heavy rain ({r:g} mm) can crust the seedbed. Sow once "
                                       "the soil has drained.")
    return Activity(name, GO, "Soil temperature and moisture suit sowing or transplanting.")


ACTIVITY_RULES: tuple = (_irrigation, _spraying, _fertilizer, _field_work, _sowing)


def _alerts(v: Dict[str, float], c: Dict[str, str]) -> List[str]:
    out: List[str] = []
    t, r, w = v["temperature_c"], v["rainfall_mm"], v["wind_speed_kmh"]
    if c["temperature"] == "heat":
        out.append(f"Heat stress ({t:g} °C): irrigate in the early morning or evening and shade "
                   "seedlings and young plants.")
    if c["temperature"] == "cold":
        out.append(f"Cold stress ({t:g} °C): protect young plants from cold, for example by "
                   "covering them at night.")
    if c["rainfall"] == "very_heavy":
        out.append(f"Very heavy rain ({r:g} mm): check field drainage and do not apply fertilizer.")
    if c["wind"] == "strong":
        out.append(f"Strong wind ({w:g} km/h): do not spray pesticides or herbicides, because "
                   "drift wastes product and harms nearby crops.")
    return out


def _notes(v: Dict[str, float], c: Dict[str, str]) -> List[str]:
    out: List[str] = []
    if c["humidity"] == "high":
        out.append(f"High humidity ({v['humidity_pct']:g}%) raises the risk of fungal disease. "
                   "Scout crops for leaf spots and mildew.")
    return out


# ---- Objective 3: present a plan for planning ----------------------------

@dataclass(frozen=True)
class Plan:
    alerts: List[str]
    activities: List[Activity]
    notes: List[str]

    def counts(self) -> Dict[str, int]:
        return {s: sum(1 for a in self.activities if a.status == s) for s in (GO, CAUTION, AVOID)}


def build_plan(data: Dict[str, Any]) -> Plan:
    v = validate(data)
    c = classify(v)
    rules: List[Callable] = list(ACTIVITY_RULES)
    return Plan(alerts=_alerts(v, c),
                activities=[rule(v, c) for rule in rules],
                notes=_notes(v, c))


def render_plan(plan: Plan) -> str:
    counts = plan.counts()
    lines: List[str] = []
    if plan.alerts:
        lines.append("ALERTS")
        lines += [f"- {a}" for a in plan.alerts]
        lines.append("")
    lines.append(f"PLAN FOR TODAY ({counts[GO]} go, {counts[CAUTION]} with care, "
                 f"{counts[AVOID]} to avoid)")
    for a in plan.activities:
        lines.append(f"- {a.name}: {a.status}. {a.reason}")
    if plan.notes:
        lines += ["", "NOTES"] + [f"- {n}" for n in plan.notes]
    return "\n".join(lines)


def render_advisory(data: Dict[str, Any]) -> str:
    """Full advisory as plain text, for the command line and fetch_weather.py."""
    return render_plan(build_plan(data))


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    arg = argv[1]
    try:
        if arg.endswith(".json"):
            with open(arg, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(arg)
        print(render_advisory(data))
    except (ValueError, OSError) as exc:  # json.JSONDecodeError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))