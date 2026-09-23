import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

import database


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)

        self.db_path = root / "test.sqlite"
        self.schema_path = root / "schema.sql"
        self.schema_path.write_text(
            Path("sql/schema.sql").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        self.transport = pd.DataFrame(
            [
                {
                    "operating_day": "2026-09-22",
                    "journey_ref": "J1",
                    "station_id": "S1",
                    "station_name": "Zürich HB",
                    "station_type": "rail",
                    "city": "Zürich",
                    "transport_mode": "rail",
                    "product_category": "InterCity",
                    "public_code": "IC5",
                    "line": "IC5",
                    "train_number": "500",
                    "origin": "Bern",
                    "destination": "Zürich",
                    "collection_timestamp": "2026-09-22T12:05:00Z",
                    "scheduled_departure": "2026-09-22T12:15:00Z",
                    "estimated_departure": "2026-09-22T12:21:00Z",
                    "predicted_delay_minutes": 6.0,
                    "minutes_until_departure": 10.0,
                    "is_predicted_delayed_5min": True,
                    "hour": 14,
                    "weekday": "Tuesday",
                    "weekend": False,
                },
                {
                    "operating_day": "2026-09-22",
                    "journey_ref": "J2",
                    "station_id": "S2",
                    "station_name": "Bern",
                    "station_type": "rail",
                    "city": "Bern",
                    "transport_mode": "rail",
                    "product_category": "InterCity",
                    "public_code": "IC1",
                    "line": "IC1",
                    "train_number": "700",
                    "origin": "Zürich",
                    "destination": "Bern",
                    "collection_timestamp": "2026-09-22T12:05:00Z",
                    "scheduled_departure": "2026-09-22T12:15:00Z",
                    "estimated_departure": "2026-09-22T12:16:00Z",
                    "predicted_delay_minutes": 1.0,
                    "minutes_until_departure": 10.0,
                    "is_predicted_delayed_5min": False,
                    "hour": 14,
                    "weekday": "Tuesday",
                    "weekend": False,
                },
            ]
        )

        self.weather = pd.DataFrame(
            [
                {
                    "city": "Zürich",
                    "weather_station_abbr": "SMA",
                    "weather_station_name": "Zürich / Fluntern",
                    "reference_timestamp": "2026-09-22T12:00:00Z",
                    "temperature_c": 18.4,
                    "precipitation_mm_10min": 0.0,
                    "relative_humidity_pct": 38.3,
                    "wind_speed_kmh_10min": 10.4,
                    "wind_gust_kmh": 20.0,
                    "station_pressure_hpa": 960.0,
                },
                {
                    "city": "Zürich",
                    "weather_station_abbr": "SMA",
                    "weather_station_name": "Zürich / Fluntern",
                    "reference_timestamp": "2026-09-22T12:10:00Z",
                    "temperature_c": 19.0,
                    "precipitation_mm_10min": 0.0,
                    "relative_humidity_pct": 37.0,
                    "wind_speed_kmh_10min": 11.0,
                    "wind_gust_kmh": 21.0,
                    "station_pressure_hpa": 960.5,
                },
                {
                    "city": "Bern",
                    "weather_station_abbr": "BER",
                    "weather_station_name": "Bern / Zollikofen",
                    "reference_timestamp": "2026-09-22T12:00:00Z",
                    "temperature_c": 19.8,
                    "precipitation_mm_10min": 0.0,
                    "relative_humidity_pct": 40.0,
                    "wind_speed_kmh_10min": 15.1,
                    "wind_gust_kmh": 25.0,
                    "station_pressure_hpa": 955.0,
                },
            ]
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_validate_and_sql_join(self):
        database.create_database(
            transport=self.transport,
            weather=self.weather,
            database_path=self.db_path,
            schema_path=self.schema_path,
        )

        report = database.validate_database(self.db_path)

        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(report["transport_rows"], 2)
        self.assertEqual(report["weather_rows"], 3)
        self.assertEqual(report["joined_rows"], 2)
        self.assertEqual(report["weather_matched_rows"], 2)

        with sqlite3.connect(self.db_path) as connection:
            zurich = connection.execute(
                """
                SELECT
                    weather_reference_timestamp,
                    temperature_c,
                    weather_time_gap_minutes
                FROM transport_weather_joined
                WHERE city = 'Zürich';
                """
            ).fetchone()

        # The 12:10 weather row is in the future relative to the 12:05
        # transport observation. The SQL join must use 12:00 instead.
        self.assertEqual(
            zurich[0],
            "2026-09-22 12:00:00",
        )
        self.assertAlmostEqual(zurich[1], 18.4)
        self.assertAlmostEqual(zurich[2], 5.0, places=2)


if __name__ == "__main__":
    unittest.main()
