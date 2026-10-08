import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
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

import model_regression


class RegressionModelTest(
    unittest.TestCase
):
    def make_dataset(
        self,
    ) -> pd.DataFrame:
        rows = []
        cities = [
            "Zürich",
            "Bern",
            "Basel",
            "Lausanne",
        ]
        modes = [
            "rail",
            "bus",
            "tram",
        ]

        for batch in range(20):
            base_time = (
                pd.Timestamp(
                    "2026-09-01 06:00",
                    tz="UTC",
                )
                + pd.Timedelta(
                    hours=6 * batch
                )
            )

            for i in range(12):
                city = cities[
                    (batch + i)
                    % len(cities)
                ]
                mode = modes[
                    i % len(modes)
                ]
                temperature = (
                    10
                    + batch % 8
                    + i * 0.05
                )
                rain = (
                    0.2
                    if batch % 6 == 0
                    else 0.0
                )

                rng = (
                    np.random.default_rng(
                        batch * 100 + i
                    )
                )

                delay = (
                    0.20
                    * (mode == "bus")
                    + 0.05
                    * (
                        temperature
                        - 14
                    )
                    + 0.6 * rain
                    + (
                        2.5
                        if i % 11 == 0
                        else 0
                    )
                    + rng.normal(
                        0,
                        0.25,
                    )
                )

                rows.append(
                    {
                        "batch_id": (
                            f"batch_{batch:02d}"
                        ),
                        "collection_timestamp": (
                            base_time
                            + pd.Timedelta(
                                seconds=i
                            )
                        ).isoformat(),
                        "city": city,
                        "transport_mode": mode,
                        "station_type": (
                            "rail"
                            if mode == "rail"
                            else "local"
                        ),
                        "product_category": (
                            "IC"
                            if mode == "rail"
                            else "local"
                        ),
                        "weekday": (
                            base_time.day_name()
                        ),
                        "hour": (
                            base_time.hour
                        ),
                        "weekend": (
                            base_time.weekday()
                            >= 5
                        ),
                        "temperature_c": (
                            temperature
                        ),
                        "precipitation_mm_10min": (
                            rain
                        ),
                        "relative_humidity_pct": (
                            55
                            + batch % 20
                        ),
                        "wind_speed_kmh_10min": (
                            4 + i % 4
                        ),
                        "wind_gust_kmh": (
                            8 + i % 5
                        ),
                        "station_pressure_hpa": (
                            960
                            + batch % 3
                        ),
                        "estimated_departure": (
                            base_time
                            + pd.Timedelta(
                                minutes=10
                            )
                        ).isoformat(),
                        "is_predicted_delayed_5min": (
                            delay >= 5
                        ),
                        "journey_ref": (
                            f"J{batch}_{i}"
                        ),
                        "predicted_delay_minutes": (
                            delay
                        ),
                    }
                )

        return pd.DataFrame(
            rows
        )

    def test_regression_pipeline_outputs(
        self,
    ):
        df = self.make_dataset()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            table_dir = (
                root / "tables"
            )
            figure_dir = (
                root / "figures"
            )
            model_dir = (
                root / "model"
            )

            outputs = (
                model_regression
                .run_regression_analysis(
                    df,
                    table_dir=table_dir,
                    figure_dir=figure_dir,
                    model_dir=model_dir,
                    random_forest_estimators=25,
                )
            )

            metrics = outputs[
                "model_regression_metrics"
            ]

            self.assertEqual(
                set(
                    metrics["model"]
                ),
                {
                    "median_baseline",
                    "linear_regression",
                    "random_forest",
                },
            )
            self.assertTrue(
                (
                    table_dir
                    / "model_regression_metrics.csv"
                ).exists()
            )
            self.assertTrue(
                (
                    model_dir
                    / "random_forest_regression.joblib"
                ).exists()
            )
            self.assertTrue(
                (
                    figure_dir
                    / "12_regression_model_mae.png"
                ).exists()
            )

            manifest = outputs[
                "model_feature_manifest"
            ]

            estimated_row = manifest[
                manifest["feature"]
                == "estimated_departure"
            ]

            self.assertEqual(
                len(estimated_row),
                1,
            )
            self.assertFalse(
                bool(
                    estimated_row.iloc[
                        0
                    ]["used"]
                )
            )

    def test_time_split_keeps_batches_together(
        self,
    ):
        df = self.make_dataset()
        clean, _, _ = (
            model_regression
            .prepare_dataset(df)
        )

        (
            train,
            test,
            split_method,
        ) = (
            model_regression
            .temporal_split(clean)
        )

        self.assertEqual(
            split_method,
            "batch_id",
        )
        self.assertTrue(
            set(
                train["batch_id"]
            ).isdisjoint(
                set(
                    test["batch_id"]
                )
            )
        )
        self.assertLess(
            train[
                "collection_timestamp"
            ].max(),
            test[
                "collection_timestamp"
            ].min(),
        )


if __name__ == "__main__":
    unittest.main()
