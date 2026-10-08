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

import final_results


class FinalResultsTest(
    unittest.TestCase
):
    def test_group_improvement_table(
        self,
    ):
        metrics = pd.DataFrame(
            [
                {
                    "city": "Bern",
                    "model": "median_baseline",
                    "observations": 100,
                    "mae": 0.50,
                    "rmse": 1.0,
                    "r2": 0.0,
                },
                {
                    "city": "Bern",
                    "model": "gradient_boosting_mae",
                    "observations": 100,
                    "mae": 0.40,
                    "rmse": 0.9,
                    "r2": 0.1,
                },
                {
                    "city": "Zürich",
                    "model": "median_baseline",
                    "observations": 120,
                    "mae": 0.80,
                    "rmse": 1.2,
                    "r2": 0.0,
                },
                {
                    "city": "Zürich",
                    "model": "gradient_boosting_mae",
                    "observations": 120,
                    "mae": 0.60,
                    "rmse": 1.0,
                    "r2": 0.2,
                },
            ]
        )

        result = (
            final_results
            .group_improvement_table(
                metrics,
                "city",
                "gradient_boosting_mae",
            )
        )

        self.assertEqual(
            list(result["city"]),
            ["Zürich", "Bern"],
        )
        self.assertAlmostEqual(
            float(
                result.loc[
                    result["city"]
                    == "Bern",
                    "mae_improvement_pct",
                ].iloc[0]
            ),
            20.0,
        )

    def test_presentation_figure_created(
        self,
    ):
        city = pd.DataFrame(
            {
                "city": [
                    "Bern",
                    "Zürich",
                ],
                "mae_improvement_pct": [
                    20.0,
                    10.0,
                ],
            }
        )
        mode = pd.DataFrame(
            {
                "transport_mode": [
                    "rail",
                    "bus",
                ],
                "mae_improvement_pct": [
                    15.0,
                    8.0,
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            final_results.plot_group_improvements(
                city,
                mode,
                output_dir,
            )

            self.assertTrue(
                (
                    output_dir
                    / "16_mae_improvement_by_city_and_mode.png"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
