import unittest

from advisory import (AVOID, CAUTION, GO, build_plan, classify, render_advisory,
                      validate)

NORMAL = {"temperature_c": 25, "rainfall_mm": 5, "humidity_pct": 55, "wind_speed_kmh": 10}


def with_(**changes):
    data = dict(NORMAL)
    data.update(changes)
    return data


def status_of(plan, name_prefix):
    return next(a.status for a in plan.activities if a.name.startswith(name_prefix))


def reason_of(plan, name_prefix):
    return next(a.reason for a in plan.activities if a.name.startswith(name_prefix))


# Objective 1: processing
class ProcessingTests(unittest.TestCase):
    def test_missing_field(self):
        data = dict(NORMAL)
        del data["rainfall_mm"]
        with self.assertRaisesRegex(ValueError, "missing field: rainfall_mm"):
            validate(data)

    def test_non_numeric_and_bool_rejected(self):
        with self.assertRaises(ValueError):
            validate(with_(temperature_c="hot"))
        with self.assertRaises(ValueError):
            validate(with_(temperature_c=True))

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            validate(with_(humidity_pct=120))
        with self.assertRaises(ValueError):
            validate(with_(rainfall_mm=-1))

    def test_not_an_object(self):
        with self.assertRaises(ValueError):
            validate([1, 2, 3])

    def test_classification_boundaries(self):
        c = classify(validate(with_(temperature_c=35, rainfall_mm=20, humidity_pct=80,
                                    wind_speed_kmh=25)))
        self.assertEqual(c, {"temperature": "heat", "rainfall": "heavy",
                             "humidity": "high", "wind": "strong"})
        c = classify(validate(with_(temperature_c=10, rainfall_mm=1.9, humidity_pct=30,
                                    wind_speed_kmh=24.9)))
        self.assertEqual(c, {"temperature": "cold", "rainfall": "dry",
                             "humidity": "low", "wind": "calm"})


# Objective 2: rule-based NLG
class RuleTests(unittest.TestCase):
    def test_normal_day_with_light_rain(self):
        # 5 mm is moderate rain: it washes spray off, so spraying waits.
        plan = build_plan(NORMAL)
        self.assertEqual(status_of(plan, "Irrigation"), CAUTION)
        self.assertEqual(status_of(plan, "Pesticide"), AVOID)
        self.assertEqual(status_of(plan, "Fertilizer"), CAUTION)
        self.assertEqual(status_of(plan, "Field work"), CAUTION)
        self.assertEqual(status_of(plan, "Sowing"), GO)
        self.assertEqual(plan.alerts, [])

    def test_calm_dry_day_is_all_go_where_water_is_not_needed(self):
        plan = build_plan(with_(rainfall_mm=0, humidity_pct=55))
        self.assertEqual(status_of(plan, "Pesticide"), GO)
        self.assertEqual(status_of(plan, "Fertilizer"), GO)
        self.assertEqual(status_of(plan, "Field work"), GO)
        self.assertEqual(status_of(plan, "Sowing"), GO)
        self.assertEqual(plan.alerts, [])

    def test_dry_hot_day_needs_irrigation(self):
        plan = build_plan(with_(temperature_c=37, rainfall_mm=0, humidity_pct=22))
        self.assertEqual(status_of(plan, "Irrigation"), GO)
        self.assertIn("only 0 mm of rain", reason_of(plan, "Irrigation"))
        self.assertIn("temperature is 37 °C", reason_of(plan, "Irrigation"))
        self.assertIn("humidity is 22%", reason_of(plan, "Irrigation"))

    def test_heavy_rain_blocks_irrigation_and_fertilizer(self):
        plan = build_plan(with_(rainfall_mm=30))
        self.assertEqual(status_of(plan, "Irrigation"), AVOID)
        self.assertEqual(status_of(plan, "Fertilizer"), AVOID)
        self.assertEqual(status_of(plan, "Sowing"), CAUTION)

    def test_strong_wind_blocks_spraying(self):
        plan = build_plan(with_(wind_speed_kmh=30))
        self.assertEqual(status_of(plan, "Pesticide"), AVOID)
        self.assertIn("Wind of 30 km/h", reason_of(plan, "Pesticide"))

    def test_rain_blocks_spraying_even_when_light(self):
        plan = build_plan(with_(rainfall_mm=2))
        self.assertEqual(status_of(plan, "Pesticide"), AVOID)

    def test_cold_day_blocks_sowing(self):
        plan = build_plan(with_(temperature_c=8))
        self.assertEqual(status_of(plan, "Sowing"), AVOID)
        self.assertEqual(len(plan.alerts), 1)
        self.assertIn("Cold stress", plan.alerts[0])

    def test_heat_gives_caution_for_spraying_and_fieldwork(self):
        plan = build_plan(with_(temperature_c=36, rainfall_mm=0))
        self.assertEqual(status_of(plan, "Pesticide"), CAUTION)
        self.assertEqual(status_of(plan, "Field work"), CAUTION)

    def test_high_humidity_adds_disease_note(self):
        plan = build_plan(with_(humidity_pct=85))
        self.assertTrue(any("fungal disease" in n for n in plan.notes))


# Objective 3: presenting the plan
class PresentationTests(unittest.TestCase):
    def test_alerts_listed_before_plan(self):
        out = render_advisory(with_(wind_speed_kmh=40))
        self.assertLess(out.index("ALERTS"), out.index("PLAN FOR TODAY"))

    def test_plan_summary_counts_match_activities(self):
        plan = build_plan(with_(rainfall_mm=30))
        counts = plan.counts()
        self.assertEqual(sum(counts.values()), 5)
        self.assertIn(f"({counts[GO]} go, {counts[CAUTION]} with care, {counts[AVOID]} to avoid)",
                      render_advisory(with_(rainfall_mm=30)))

    def test_every_activity_appears_once(self):
        out = render_advisory(NORMAL)
        for name in ("Irrigation", "Pesticide", "Fertilizer", "Field work", "Sowing"):
            self.assertEqual(out.count(f"- {name}"), 1)


if __name__ == "__main__":
    unittest.main()