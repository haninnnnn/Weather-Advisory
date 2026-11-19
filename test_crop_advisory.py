"""Tests for crop_advisory.py and advisory_export.py."""

import json
import os
import tempfile
import unittest

from crop_advisory import (
    CROP_NAMES, CROPS, build_crop_plan, crop_notes, render_crop_plan,
)
from advisory_export import export, _plan_to_dict, _plan_to_text

NORMAL = {"temperature_c": 25, "rainfall_mm": 5, "humidity_pct": 55, "wind_speed_kmh": 10}


def with_(**changes):
    data = dict(NORMAL)
    data.update(changes)
    return data


# ---------------------------------------------------------------------------
# crop_advisory tests
# ---------------------------------------------------------------------------

class CropCatalogueTests(unittest.TestCase):
    def test_all_expected_crops_present(self):
        for key in ("rice", "wheat", "maize", "tomato", "groundnut", "sugarcane"):
            self.assertIn(key, CROPS)

    def test_unknown_crop_raises(self):
        with self.assertRaisesRegex(ValueError, "unknown crop"):
            crop_notes(NORMAL, "banana")


class CropTemperatureTests(unittest.TestCase):
    def test_wheat_too_hot_gets_note(self):
        # wheat optimal high is 25 °C; 32 °C is above it
        notes = crop_notes(with_(temperature_c=32), "wheat")
        self.assertTrue(any("heat stress" in n.lower() for n in notes),
                        f"expected heat note, got: {notes}")

    def test_rice_in_range_no_temp_note(self):
        # 28 °C is within rice optimal range (22–35 °C)
        notes = crop_notes(with_(temperature_c=28, rainfall_mm=6), "rice")
        self.assertFalse(any("grows best" in n for n in notes),
                         f"unexpected temp note: {notes}")

    def test_cold_wheat_gets_suboptimal_note(self):
        # wheat optimal low is 10 °C; 5 °C is below it
        notes = crop_notes(with_(temperature_c=5), "wheat")
        self.assertTrue(any("grows best" in n for n in notes))


class CropRainTests(unittest.TestCase):
    def test_tomato_waterlogging_note_on_heavy_rain(self):
        notes = crop_notes(with_(rainfall_mm=25), "tomato")
        self.assertTrue(any("waterlogging" in n for n in notes))

    def test_rice_no_waterlogging_note(self):
        # rice is not waterlog-sensitive
        notes = crop_notes(with_(rainfall_mm=25), "rice")
        self.assertFalse(any("waterlogging" in n for n in notes))

    def test_drought_sensitive_crop_gets_irrigation_note(self):
        # tomato drought_sensitive=True, min_rain=2.0; 0 mm should trigger note
        notes = crop_notes(with_(rainfall_mm=0), "tomato")
        self.assertTrue(any("irrigate" in n.lower() for n in notes))


class CropHumidityTests(unittest.TestCase):
    def test_wheat_fungal_note_above_threshold(self):
        # wheat fungal_risk_humidity = 70 %; 72 % should trigger a note
        notes = crop_notes(with_(humidity_pct=72), "wheat")
        self.assertTrue(any("fungal" in n.lower() for n in notes))

    def test_rice_no_fungal_note_at_74_pct(self):
        # rice threshold is 75 %; 74 % should NOT trigger
        notes = crop_notes(with_(humidity_pct=74), "rice")
        self.assertFalse(any("fungal" in n.lower() for n in notes))


class CropPlanTests(unittest.TestCase):
    def test_render_includes_crop_name(self):
        cp = build_crop_plan(NORMAL, "maize")
        text = render_crop_plan(cp)
        self.assertIn("Maize", text)

    def test_render_includes_base_plan(self):
        cp = build_crop_plan(NORMAL, "rice")
        text = render_crop_plan(cp)
        self.assertIn("PLAN FOR TODAY", text)

    def test_crop_specific_section_shown_when_notes_exist(self):
        # hot dry conditions should produce crop-specific notes for tomato
        cp = build_crop_plan(with_(temperature_c=34, rainfall_mm=0), "tomato")
        text = render_crop_plan(cp)
        self.assertIn("CROP-SPECIFIC NOTES", text)


# ---------------------------------------------------------------------------
# advisory_export tests
# ---------------------------------------------------------------------------

class ExportDictTests(unittest.TestCase):
    def test_dict_has_required_keys(self):
        d = _plan_to_dict(NORMAL)
        for key in ("generated_at", "readings", "classifications", "alerts",
                    "activities", "notes", "summary"):
            self.assertIn(key, d)

    def test_activities_have_name_status_reason(self):
        d = _plan_to_dict(NORMAL)
        for act in d["activities"]:
            self.assertIn("name", act)
            self.assertIn("status", act)
            self.assertIn("reason", act)

    def test_crop_key_adds_crop_section(self):
        d = _plan_to_dict(NORMAL, crop_key="rice")
        self.assertIn("crop", d)
        self.assertEqual(d["crop"]["key"], "rice")

    def test_no_crop_key_no_crop_section(self):
        d = _plan_to_dict(NORMAL)
        self.assertNotIn("crop", d)


class ExportTextTests(unittest.TestCase):
    def test_text_contains_advisory_header(self):
        text = _plan_to_text(NORMAL)
        self.assertIn("AUTOMATED WEATHER ADVISORY", text)

    def test_text_with_crop_contains_crop_name(self):
        text = _plan_to_text(NORMAL, crop_key="rice")
        self.assertIn("Rice", text)


class ExportFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_both_files_written(self):
        written = export(NORMAL, out_dir=self.tmp, fmt="both")
        self.assertIn("json", written)
        self.assertIn("txt", written)
        self.assertTrue(os.path.isfile(written["json"]))
        self.assertTrue(os.path.isfile(written["txt"]))

    def test_json_file_is_valid_json(self):
        written = export(NORMAL, out_dir=self.tmp, fmt="json")
        with open(written["json"], encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("activities", data)

    def test_txt_only(self):
        written = export(NORMAL, out_dir=self.tmp, fmt="txt")
        self.assertNotIn("json", written)
        self.assertIn("txt", written)

    def test_json_only(self):
        written = export(NORMAL, out_dir=self.tmp, fmt="json")
        self.assertNotIn("txt", written)
        self.assertIn("json", written)

    def test_creates_out_dir_if_missing(self):
        new_dir = os.path.join(self.tmp, "nested", "reports")
        export(NORMAL, out_dir=new_dir, fmt="txt")
        self.assertTrue(os.path.isdir(new_dir))


if __name__ == "__main__":
    unittest.main()
