# Automated Weather Advisory Text Generator

**NLP PBL Project #6** | SDG 2 – Zero Hunger | SDG 13 – Climate Action

A rule-based natural language generator that converts structured weather data
(temperature, rainfall, humidity, wind speed) into actionable agricultural
advisory messages. No training data or external API key required.

---

## Objectives and where they are met

| Objective | Implementation |
|---|---|
| 1. Process temperature, rainfall, humidity and wind-speed data | `validate()` checks presence, type and range. `classify()` maps each reading to a category (cold/comfortable/heat, dry/moderate/heavy/very heavy, low/moderate/high humidity, calm/strong wind). |
| 2. Generate advisory messages with rule-based NLG | Five activity rules (irrigation, spraying, fertilizer, field work, sowing) each produce a GO / CAUTION / AVOID status and a sentence built from templates. Crop-specific notes extend this with per-crop thresholds. Alerts and general notes follow the same approach. |
| 3. Present clear advisories to support agricultural planning | `render_plan()` produces a plain-text summary with an alert block, activity-by-activity plan and notes. The HTML app renders the same information as a styled table, with a 7-day outlook and crop selector. `advisory_export.py` saves the full advisory as JSON or plain text. |

---

## Project files

| File | Purpose |
|---|---|
| `advisory.py` | Core: validation, classification, five activity rules, plan builder and text renderer |
| `crop_advisory.py` | Crop-specific advisory layer for rice, wheat, maize, tomato, groundnut, sugarcane |
| `advisory_export.py` | Export the advisory to a timestamped `.json` or `.txt` file |
| `fetch_weather.py` | Fetches live readings from Open-Meteo; supports 7-day outlook, crop flag and export flag |
| `advisory_app.html` | Self-contained browser UI: readings form, crop selector, 7-day outlook table, dark mode, print button |
| `test_advisory.py` | Unit tests for the core advisory (all three objectives) |
| `test_fetch_weather.py` | Unit tests for the Open-Meteo and geocoding response parsers |
| `test_crop_advisory.py` | Unit tests for crop-specific notes and export functionality |
| `requirements.txt` | No third-party packages needed (standard library only) |

Python 3.8+ is required.

---

## Quick start

### Enter readings manually

```
python advisory.py '{"temperature_c": 37, "rainfall_mm": 0, "humidity_pct": 22, "wind_speed_kmh": 30}'
```

### Crop-specific advisory

```
python crop_advisory.py rice '{"temperature_c": 32, "rainfall_mm": 8, "humidity_pct": 75, "wind_speed_kmh": 12}'
python crop_advisory.py wheat weather.json
```

Supported crops: `rice`, `wheat`, `maize`, `tomato`, `groundnut`, `sugarcane`

### Fetch live weather for a place

```
python fetch_weather.py "Udupi"
python fetch_weather.py "Udupi" --days 7            # 7-day outlook
python fetch_weather.py "Udupi" --crop rice         # crop-specific advisory
python fetch_weather.py "Udupi" --export            # save advisory files
python fetch_weather.py "Udupi" --export --out-dir reports/

python fetch_weather.py --osm "Udupi"              # OpenStreetMap geocoding
python fetch_weather.py --google "Udupi"           # Google Maps (needs GOOGLE_MAPS_API_KEY)
python fetch_weather.py --lat 13.34 --lon 74.75    # exact coordinates
```

### Export an advisory to file

```
python advisory_export.py '{"temperature_c":32,"rainfall_mm":8,"humidity_pct":75,"wind_speed_kmh":12}'
python advisory_export.py weather.json --crop rice --out-dir reports/
python advisory_export.py weather.json --format json
python advisory_export.py weather.json --format txt
```

Output files are named `advisory_YYYYMMDD_HHMMSS.json` / `.txt`.

### Browser UI

Open `advisory_app.html` in any browser:
- Enter readings manually or fetch live weather by place name or GPS.
- Select a crop for extra crop-specific notes.
- View a **7-day outlook table** (after a live weather fetch).
- Toggle dark / light mode (preference is saved).
- Print the advisory with the 🖨️ button.

---

## Running all tests

```
python -m unittest -v test_advisory test_fetch_weather test_crop_advisory
```

Expected: **48 tests, 0 failures**.

---

## Rules and thresholds

### Base thresholds (`advisory.py`)

| Reading | Category | Threshold |
|---|---|---|
| Temperature | cold | ≤ 10 °C |
| Temperature | heat stress | ≥ 35 °C |
| Rainfall | dry | < 2 mm |
| Rainfall | moderate | 2 – 19.9 mm |
| Rainfall | heavy | ≥ 20 mm |
| Rainfall | very heavy | ≥ 50 mm |
| Humidity | low | ≤ 30 % |
| Humidity | high | ≥ 80 % |
| Wind speed | strong | ≥ 25 km/h |

### Activity status rules

| Activity | AVOID | CAUTION | GO |
|---|---|---|---|
| Irrigation | heavy / very heavy rain | moderate conditions | dry, hot or low humidity |
| Spraying | strong wind or any rain | heat | calm and dry |
| Fertilizer | heavy / very heavy rain | moderate rain or heat | dry / light rain |
| Field work | heavy / very heavy rain | heat or moderate rain | otherwise |
| Sowing | very heavy rain or cold | heat or heavy rain | otherwise |

### Crop-specific thresholds (`crop_advisory.py`)

| Crop | Optimal °C | Waterlog risk | Drought sensitive | Fungal RH |
|---|---|---|---|---|
| Rice | 22 – 35 | No | Yes | 75 % |
| Wheat | 10 – 25 | Yes | No | 70 % |
| Maize | 18 – 32 | Yes | Yes | 80 % |
| Tomato | 18 – 30 | Yes | Yes | 70 % |
| Groundnut | 22 – 35 | Yes | No | 85 % |
| Sugarcane | 20 – 38 | No | Yes | 80 % |

> All thresholds are illustrative defaults. Confirm them with a local agronomist before using in practice.

---

## Data sources

`fetch_weather.py` and the web UI use [Open-Meteo](https://open-meteo.com/) for forecasts — free, no API key needed. Units are °C, mm and km/h, which match the advisory rules. Rainfall is the daily total, not the current-hour rate.

---

## SDG alignment

| Goal | Connection |
|---|---|
| **SDG 2 – Zero Hunger** | Helps smallholder farmers make better planting, irrigation and crop-protection decisions, reducing losses and supporting food security. |
| **SDG 13 – Climate Action** | Advisories for extreme weather (heat stress, very heavy rain, strong wind) help farmers adapt to climate variability. |
