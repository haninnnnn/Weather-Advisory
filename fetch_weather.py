"""Fetch today's conditions for a place from Open-Meteo (free, no API key)
and print the farm advisory produced by advisory.py. Standard library only.

Usage:
    python fetch_weather.py "Bengaluru"
    python fetch_weather.py --lat 12.97 --lon 77.59
    python fetch_weather.py "Udupi" --days 7          # 7-day outlook
    python fetch_weather.py "Udupi" --crop rice       # crop-specific advisory
    python fetch_weather.py "Udupi" --export          # save report files
    python fetch_weather.py "Udupi" --export --out-dir reports/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, Tuple

from advisory import render_advisory, build_plan, render_plan
from crop_advisory import CROP_NAMES, build_crop_plan, render_crop_plan

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent.
NOMINATIM_USER_AGENT = "weather-advisory-student-project/1.0"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GOOGLE_KEY_ENV = "GOOGLE_MAPS_API_KEY"
TIMEOUT_S = 15


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def geocode(name: str) -> Tuple[float, float, str]:
    """Return (latitude, longitude, display name) for the best match."""
    data = _get_json(GEOCODE_URL, {"name": name, "count": 1})
    results = data.get("results") or []
    if not results:
        raise ValueError(f"no location found for {name!r}")
    place = results[0]
    return place["latitude"], place["longitude"], place.get("name", name)


def parse_google_response(data: Dict[str, Any], name: str) -> Tuple[float, float, str]:
    """Read the top result from a Google Geocoding API response."""
    if data.get("status") != "OK" or not data.get("results"):
        raise ValueError(f"Google found no location for {name!r} (status {data.get('status')})")
    top = data["results"][0]
    loc = top["geometry"]["location"]
    return loc["lat"], loc["lng"], top.get("formatted_address", name)


def geocode_google(name: str, api_key: str) -> Tuple[float, float, str]:
    """Look a place up with the Google Geocoding API. Needs an API key."""
    data = _get_json(GOOGLE_GEOCODE_URL, {"address": name, "key": api_key})
    return parse_google_response(data, name)


def parse_nominatim_response(results: list, name: str) -> Tuple[float, float, str]:
    """Read the top result from an OpenStreetMap Nominatim search response."""
    if not results:
        raise ValueError(f"OpenStreetMap found no location for {name!r}")
    top = results[0]
    return float(top["lat"]), float(top["lon"]), top.get("display_name", name)


def geocode_osm(name: str) -> Tuple[float, float, str]:
    """Look a place up with OpenStreetMap Nominatim. Free, no key, rate-limited."""
    params = urllib.parse.urlencode({"q": name, "format": "json", "limit": 1})
    req = urllib.request.Request(
        NOMINATIM_URL + "?" + params,
        headers={"User-Agent": NOMINATIM_USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        results = json.load(resp)
    return parse_nominatim_response(results, name)


def fetch_forecast(lat: float, lon: float, days: int = 1) -> Dict[str, Any]:
    """Current temperature, humidity and wind, plus daily rainfall totals.

    When days > 1 the response includes multi-day daily summaries used by
    readings_from_forecast_day() to build a week-ahead outlook.
    """
    return _get_json(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "daily": (
            "precipitation_sum,temperature_2m_max,temperature_2m_min,"
            "relative_humidity_2m_max,wind_speed_10m_max"
        ),
        "forecast_days": min(days, 7),
        "timezone": "auto",
    })


def readings_from_forecast(data: Dict[str, Any]) -> Dict[str, float]:
    """Map an Open-Meteo forecast response to the four advisory inputs.

    Uses current conditions for temperature, humidity and wind, and
    today's daily precipitation sum for rainfall.
    Open-Meteo defaults to °C, km/h and mm, which match advisory.py's units.
    """
    current = data["current"]
    rain_today = data["daily"]["precipitation_sum"][0]
    return {
        "temperature_c": current["temperature_2m"],
        "rainfall_mm": rain_today if rain_today is not None else 0.0,
        "humidity_pct": current["relative_humidity_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
    }


def readings_from_forecast_day(data: Dict[str, Any], day_index: int) -> Dict[str, float]:
    """Map a single day from a multi-day Open-Meteo forecast to advisory inputs.

    Uses daily max values for temperature, humidity and wind so the advisory
    reflects the worst conditions expected that day.
    """
    daily = data["daily"]
    rain = daily["precipitation_sum"][day_index]
    temp = daily.get("temperature_2m_max", daily.get("temperature_2m_min", [None]))[day_index]
    # Fallback: if max temp is missing, use current for today, else skip
    if temp is None:
        temp = data["current"]["temperature_2m"] if day_index == 0 else 25.0
    humid = daily.get("relative_humidity_2m_max", [None] * 7)[day_index]
    if humid is None:
        humid = data["current"]["relative_humidity_2m"] if day_index == 0 else 60.0
    wind = daily.get("wind_speed_10m_max", [None] * 7)[day_index]
    if wind is None:
        wind = data["current"]["wind_speed_10m"] if day_index == 0 else 10.0
    return {
        "temperature_c": float(temp),
        "rainfall_mm": float(rain) if rain is not None else 0.0,
        "humidity_pct": float(humid),
        "wind_speed_kmh": float(wind),
    }


def render_weekly_outlook(data: Dict[str, Any], label: str, crop_key: str | None = None) -> str:
    """Render a brief GO/CAUTION/AVOID table for each forecast day."""
    daily = data["daily"]
    dates = daily.get("time", [])
    n_days = len(dates)
    lines = [f"7-Day Outlook for {label}", ""]
    day_labels = ["Today", "Tomorrow"] + [f"Day {i+1}" for i in range(2, n_days)]
    for i in range(n_days):
        date_str = dates[i] if dates else f"Day {i}"
        dlabel = day_labels[i] if i < len(day_labels) else date_str
        readings = readings_from_forecast_day(data, i)
        if crop_key:
            from crop_advisory import build_crop_plan, render_crop_plan
            cp = build_crop_plan(readings, crop_key)
            counts = cp.base_plan.counts()
        else:
            plan = build_plan(readings)
            counts = plan.counts()
        summary = (f"{counts['GO']} go, {counts['CAUTION']} caution, "
                   f"{counts['AVOID']} avoid")
        rain = readings["rainfall_mm"]
        temp = readings["temperature_c"]
        lines.append(f"  {dlabel} ({date_str}): {temp:g} °C, {rain:g} mm — {summary}")
    return "\n".join(lines)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Weather advisory for a place.")
    parser.add_argument("place", nargs="?", help="place name, e.g. \"Bengaluru\"")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--google", action="store_true",
                        help=f"look the place up with Google Maps (needs ${GOOGLE_KEY_ENV})")
    parser.add_argument("--osm", action="store_true",
                        help="look the place up with OpenStreetMap (free, no key)")
    parser.add_argument("--days", type=int, default=1, choices=range(1, 8), metavar="N",
                        help="number of forecast days to show (1–7, default 1)")
    parser.add_argument("--crop", choices=CROP_NAMES, default=None,
                        help="optional crop for crop-specific advisory notes")
    parser.add_argument("--export", action="store_true",
                        help="save the advisory as text and JSON files")
    parser.add_argument("--out-dir", default=".", metavar="DIR",
                        help="directory for exported files (used with --export)")
    args = parser.parse_args(argv[1:])

    try:
        if args.lat is not None and args.lon is not None:
            lat, lon, label = args.lat, args.lon, f"{args.lat}, {args.lon}"
        elif args.place and args.google:
            key = os.environ.get(GOOGLE_KEY_ENV)
            if not key:
                parser.error(f"set the {GOOGLE_KEY_ENV} environment variable to use --google")
            lat, lon, label = geocode_google(args.place, key)
        elif args.place and args.osm:
            lat, lon, label = geocode_osm(args.place)
        elif args.place:
            lat, lon, label = geocode(args.place)
        else:
            parser.error("give a place name, or both --lat and --lon")

        forecast = fetch_forecast(lat, lon, days=args.days)
        readings = readings_from_forecast(forecast)

        print(f"Advisory for {label}")
        print(f"Readings: {readings}")
        print()

        # Today's full advisory (with optional crop layer)
        if args.crop:
            from crop_advisory import build_crop_plan, render_crop_plan
            cp = build_crop_plan(readings, args.crop)
            print(render_crop_plan(cp))
        else:
            print(render_advisory(readings))

        # Multi-day outlook
        if args.days > 1:
            print()
            print(render_weekly_outlook(forecast, label, crop_key=args.crop))

        # Export
        if args.export:
            from advisory_export import export
            written = export(readings, crop_key=args.crop, out_dir=args.out_dir)
            print()
            for fmt, path in written.items():
                print(f"Exported ({fmt}): {path}")

    except (ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
