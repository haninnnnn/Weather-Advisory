"""Export a weather advisory to JSON or plain-text files.

Usage:
    python advisory_export.py '{"temperature_c":32,"rainfall_mm":8,"humidity_pct":75,"wind_speed_kmh":12}'
    python advisory_export.py weather.json --crop rice --out-dir reports/
    python advisory_export.py weather.json --format txt
    python advisory_export.py weather.json --format json
    python advisory_export.py weather.json --format both   (default)

Output files are named advisory_YYYYMMDD_HHMMSS.txt / .json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, Optional

from advisory import build_plan, render_plan, validate, classify
from crop_advisory import CROP_NAMES, build_crop_plan, render_crop_plan


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _plan_to_dict(data: Dict[str, Any], crop_key: Optional[str] = None) -> Dict[str, Any]:
    """Turn an advisory plan (and optional crop layer) into a plain dict."""
    v = validate(data)
    c = classify(v)
    base = build_plan(data)

    result: Dict[str, Any] = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "readings": v,
        "classifications": c,
        "alerts": base.alerts,
        "activities": [
            {"name": a.name, "status": a.status, "reason": a.reason}
            for a in base.activities
        ],
        "notes": base.notes,
        "summary": base.counts(),
    }

    if crop_key:
        from crop_advisory import CROPS, crop_notes
        cp_notes = crop_notes(data, crop_key)
        result["crop"] = {
            "key": crop_key,
            "name": CROPS[crop_key].name,
            "notes": cp_notes,
        }

    return result


def _plan_to_text(data: Dict[str, Any], crop_key: Optional[str] = None) -> str:
    """Render the full advisory as a plain-text report."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "=" * 60,
        "AUTOMATED WEATHER ADVISORY",
        f"Generated: {ts}",
        "=" * 60,
        "",
    ]
    if crop_key:
        cp = build_crop_plan(data, crop_key)
        lines.append(render_crop_plan(cp))
    else:
        lines.append(render_plan(build_plan(data)))
    lines += [
        "",
        "=" * 60,
        "Thresholds are illustrative defaults.",
        "Consult a local agronomist before acting on this advice.",
        "=" * 60,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def export(
    data: Dict[str, Any],
    crop_key: Optional[str] = None,
    out_dir: str = ".",
    fmt: str = "both",
) -> Dict[str, str]:
    """Write advisory file(s) and return a dict of {format: filepath}."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    written: Dict[str, str] = {}

    if fmt in ("json", "both"):
        path = os.path.join(out_dir, f"advisory_{stamp}.json")
        payload = _plan_to_dict(data, crop_key)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        written["json"] = path

    if fmt in ("txt", "both"):
        path = os.path.join(out_dir, f"advisory_{stamp}.txt")
        text = _plan_to_text(data, crop_key)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        written["txt"] = path

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Export a weather advisory to file.")
    parser.add_argument("input", help="JSON string or .json file path")
    parser.add_argument("--crop", choices=CROP_NAMES, default=None,
                        help="optional crop for crop-specific notes")
    parser.add_argument("--out-dir", default=".", metavar="DIR",
                        help="directory to write output files (created if needed)")
    parser.add_argument("--format", choices=["json", "txt", "both"], default="both",
                        dest="fmt", help="output format (default: both)")
    args = parser.parse_args(argv[1:])

    try:
        if args.input.endswith(".json"):
            with open(args.input, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = json.loads(args.input)

        written = export(data, crop_key=args.crop, out_dir=args.out_dir, fmt=args.fmt)
        for fmt, path in written.items():
            print(f"Written ({fmt}): {path}")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
