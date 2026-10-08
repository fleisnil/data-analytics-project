import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(
    0,
    str(
        Path(__file__)
        .resolve()
        .parents[1]
        / "src"
    ),
)

import statistics_analysis


class StatisticsAnalysisTest(
    unittest.TestCase
):
    def make_dataset(self) -> pd.DataFrame:
        rows = []

        for i in range(24):
            city = (
                "Zürich"
                if i < 12
                else "Bern"
            )
            mode = [
                "bus",
                "rail",
                "tram",
            ][i % 3]

            weather_group = (
                i // 3
            )
            timestamp = (
                pd.Timestamp(
                    "2026-10-01 08:00",
                    tz="UTC",
                )
                + pd.Timedelta(
                    hours=weather_group
                )
            )

            delay = [
                0.0,
                0.5,
                1.0,
                2.0,
                6.0,
                8.0,
            ][i % 6]

            rows.append(
                {
                    "city": city,
                    "transport_mode": mode,
                    "predicted_delay_minutes": (
                        delay
                    ),
                    "is_predicted_delayed_5min": (
                        delay >= 5
                    ),
                    "reference_timestamp": (
                        timestamp.isoformat()
                    ),
                    "temperature_c": (
                        10 + weather_group
                    ),
                    "precipitation_mm_10min": (
                        0.2
                        if weather_group % 3 == 0
                        else 0.0
                    ),
                    "relative_humidity_pct": (
                        70 - weather_group
                    ),
                    "wind_speed_kmh_10min": (
                        3 + weather_group
                    ),
                    "wind_gust_kmh": (
                        6 + weather_group
                    ),
                }
            )

        return pd.DataFrame(rows)

    def test_statistics_tables_created(
        self,
    ):
        df = self.make_dataset()

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            tables = (
                statistics_analysis
                .create_statistics_tables(
                    df,
                    output_dir,
                )
            )

            self.assertEqual(
                len(
                    tables[
                        "stats_delay_threshold_sensitivity"
                    ]
                ),
                5,
            )
            self.assertEqual(
                len(
                    tables[
                        "stats_group_tests"
                    ]
                ),
                2,
            )
            self.assertIn(
                "within_city_centered",
                set(
                    tables[
                        "stats_weather_correlations"
                    ]["scope"]
                ),
            )
            self.assertTrue(
                (
                    output_dir
                    / "stats_chi_square.csv"
                ).exists()
            )
            self.assertTrue(
                (
                    output_dir
                    / "stats_weather_correlations.csv"
                ).exists()
            )

    def test_weather_aggregation_reduces_duplicates(
        self,
    ):
        df = self.make_dataset()

        aggregated = (
            statistics_analysis
            .aggregate_for_weather_tests(
                df
            )
        )

        self.assertLess(
            len(aggregated),
            len(df),
        )
        self.assertIn(
            "observations",
            aggregated.columns,
        )


if __name__ == "__main__":
    unittest.main()
