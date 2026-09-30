import tempfile
import unittest
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
    ),
)

import eda


class EdaTest(unittest.TestCase):
    def test_tables_and_figures_are_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_path = (
                root / "analysis_dataset.csv"
            )
            figure_dir = root / "figures"
            table_dir = root / "tables"

            rows = []
            cities = ["Zürich", "Bern"]
            modes = ["rail", "bus"]

            for i in range(12):
                delay = [
                    -0.5,
                    0.0,
                    1.0,
                    2.0,
                    6.0,
                    8.0,
                ][i % 6]

                departure = pd.Timestamp(
                    "2026-09-29 06:00",
                    tz="Europe/Zurich",
                ) + pd.Timedelta(
                    hours=i * 2
                )

                rows.append(
                    {
                        "city": cities[i % 2],
                        "transport_mode": (
                            modes[i % 2]
                        ),
                        "predicted_delay_minutes": (
                            delay
                        ),
                        "collection_timestamp": (
                            departure
                            - pd.Timedelta(
                                minutes=10
                            )
                        )
                        .tz_convert("UTC")
                        .isoformat(),
                        "scheduled_departure": (
                            departure
                            .tz_convert("UTC")
                            .isoformat()
                        ),
                        "scheduled_departure_local": (
                            departure.isoformat()
                        ),
                        "date": (
                            departure
                            .date()
                            .isoformat()
                        ),
                        "hour": departure.hour,
                        "weekday": (
                            departure.day_name()
                        ),
                        "is_predicted_delayed_5min": (
                            delay >= 5
                        ),
                        "temperature_c": 12 + i,
                        "precipitation_mm_10min": (
                            0.0
                            if i < 6
                            else 0.2
                        ),
                        "relative_humidity_pct": (
                            50 + i
                        ),
                        "wind_speed_kmh_10min": (
                            5 + i % 3
                        ),
                        "wind_gust_kmh": (
                            10 + i % 4
                        ),
                        "station_pressure_hpa": (
                            960 + i % 2
                        ),
                        "weather_matched": True,
                        "weather_time_gap_minutes": (
                            5.0
                        ),
                    }
                )

            pd.DataFrame(
                rows
            ).to_csv(
                data_path,
                index=False,
            )

            df = (
                eda.load_analysis_dataset(
                    data_path
                )
            )
            tables = (
                eda.create_summary_tables(
                    df,
                    table_dir,
                )
            )
            eda.create_figures(
                df,
                figure_dir,
            )

            self.assertEqual(
                len(df),
                12,
            )
            self.assertIn(
                "eda_overview",
                tables,
            )
            self.assertTrue(
                (
                    table_dir
                    / "eda_city_mode_summary.csv"
                ).exists()
            )
            self.assertTrue(
                (
                    figure_dir
                    / "01_delay_distribution.png"
                ).exists()
            )
            self.assertTrue(
                (
                    figure_dir
                    / "11_sample_balance_city_mode.png"
                ).exists()
            )
            self.assertGreaterEqual(
                len(
                    list(
                        figure_dir.glob(
                            "*.png"
                        )
                    )
                ),
                9,
            )


if __name__ == "__main__":
    unittest.main()
