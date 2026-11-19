"""Fetch today's conditions for a place from Open-Meteo (free, no API key)
and print the farm advisory produced by advisory.py. Standard library only.

Usage:
    python fetch_weather.py "Bengaluru"
    python fetch_weather.py --lat 12.97 --lon 77.59
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, Tuple

from advisory import render_advisory

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
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


def fetch_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """Current temperature, humidity and wind, plus today's total rainfall."""
    return _get_json(FORECAST_URL, {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "daily": "precipitation_sum",
        "forecast_days": 1,
        "timezone": "auto",
    })


def readings_from_forecast(data: Dict[str, Any]) -> Dict[str, float]:
    """Map an Open-Meteo forecast response to the four advisory inputs.

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


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Weather advisory for a place.")
    parser.add_argument("place", nargs="?", help="place name, e.g. \"Bengaluru\"")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    args = parser.parse_args(argv[1:])

    try:
        if args.lat is not None and args.lon is not None:
            lat, lon, label = args.lat, args.lon, f"{args.lat}, {args.lon}"
        elif args.place:
            lat, lon, label = geocode(args.place)
        else:
            parser.error("give a place name, or both --lat and --lon")

        readings = readings_from_forecast(fetch_forecast(lat, lon))
        print(f"Advisory for {label}")
        print(f"Readings: {readings}")
        print()
        print(render_advisory(readings))
    except (ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
