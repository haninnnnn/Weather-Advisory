import unittest

from fetch_weather import parse_google_response, parse_nominatim_response, readings_from_forecast

SAMPLE = {
    "current": {"temperature_2m": 31.4, "relative_humidity_2m": 62, "wind_speed_10m": 18.5},
    "daily": {"precipitation_sum": [4.2]},
}


class ReadingsTests(unittest.TestCase):
    def test_maps_fields(self):
        self.assertEqual(readings_from_forecast(SAMPLE), {
            "temperature_c": 31.4,
            "rainfall_mm": 4.2,
            "humidity_pct": 62,
            "wind_speed_kmh": 18.5,
        })

    def test_null_rain_becomes_zero(self):
        data = {**SAMPLE, "daily": {"precipitation_sum": [None]}}
        self.assertEqual(readings_from_forecast(data)["rainfall_mm"], 0.0)


class GoogleResponseTests(unittest.TestCase):
    GOOD = {
        "status": "OK",
        "results": [{
            "formatted_address": "Bengaluru, Karnataka, India",
            "geometry": {"location": {"lat": 12.9716, "lng": 77.5946}},
        }],
    }

    def test_reads_top_result(self):
        self.assertEqual(parse_google_response(self.GOOD, "Bengaluru"),
                         (12.9716, 77.5946, "Bengaluru, Karnataka, India"))

    def test_zero_results_raises(self):
        with self.assertRaisesRegex(ValueError, "no location"):
            parse_google_response({"status": "ZERO_RESULTS", "results": []}, "nowhere")

    def test_denied_key_raises(self):
        with self.assertRaisesRegex(ValueError, "REQUEST_DENIED"):
            parse_google_response({"status": "REQUEST_DENIED", "results": []}, "x")


class NominatimResponseTests(unittest.TestCase):
    def test_reads_top_result_with_string_coordinates(self):
        results = [{"lat": "12.9791198", "lon": "77.5912997",
                    "display_name": "Bengaluru, Karnataka, India"}]
        self.assertEqual(parse_nominatim_response(results, "Bengaluru"),
                         (12.9791198, 77.5912997, "Bengaluru, Karnataka, India"))

    def test_no_results_raises(self):
        with self.assertRaisesRegex(ValueError, "no location"):
            parse_nominatim_response([], "nowhere")


if __name__ == "__main__":
    unittest.main()
