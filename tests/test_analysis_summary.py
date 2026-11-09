import tempfile
import unittest
from pathlib import Path

from src.project_workflow import SUMMARY, write_summary


class AnalysisSummaryTest(unittest.TestCase):
    def test_brief_reads_main_results_and_only_writes_the_summary(self):
        fixtures = {
            "data/processed/analysis_dataset.csv":
                "operating_day,station_id,city,transport_mode\n"
                "2026-10-01,S1,Bern,bus\n2026-10-02,S2,Zürich,rail\n",
            "results/tables/data_integration_report.csv":
                "metric,value\nselected_unique_journey_stops,2\nojp_raw_rows,10\n"
                "weather_match_rate_pct,50\nweather_matched_rows,1\nweather_unmatched_rows,1\n",
            "results/tables/model_holdout_benchmarks.csv":
                "model,mae,rmse,r2,mean_error_pred_minus_target,test_dates\n"
                "gradient_boosting_mae,0.1234,0.2,-0.2,-0.1,6\n",
            "results/tables/model_split_summary.csv":
                "split,rows,split_method\ntrain,14,collection_date\ntest,6,collection_date\n",
            "results/tables/model_selection_summary.csv":
                "best_model,selected_by\ngradient_boosting_mae,expanding_development_dates\n",
            "results/tables/model_paired_comparisons.csv":
                "model,reference,metric,difference,ci_low,ci_high,test_dates\n"
                "gradient_boosting_mae,group_median,mae,-0.03,,,2\n"
                "random_forest,random_forest_no_weather,mae,0.01,-0.04,0.05,6\n",
            "results/tables/model_temporal_validation.csv":
                "fold,model,train_last_date,validation_first_date,validation_last_date,validation_rows,mae\n"
                "1,gradient_boosting_mae,2026-09-01,2026-09-02,2026-09-03,8,0.33\n"
                "1,group_median,2026-09-01,2026-09-02,2026-09-03,8,0.32\n",
            "results/figures/12_regression_model_mae.png": "fixture chart",
            "results/figures/old.png": "older chart",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, contents in fixtures.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(contents, encoding="utf-8")
            figure = root / "results/figures/12_regression_model_mae.png"
            write_summary(root, [figure], "fixture timestamp")
            brief = (root / SUMMARY).read_text(encoding="utf-8")
            for expected in (
                "2 observed operating days", "50.00%", "0.1234", "Not available",
                "-0.0400 to 0.0500", "0.3300", "0.3200",
                "## Does weather add predictive information?",
                "## Stability across later periods", "![Holdout model MAE]",
            ):
                self.assertIn(expected, brief)
            self.assertNotIn("old.png", brief)
            self.assertNotIn("ols_associations", brief)
            for name, contents in fixtures.items():
                self.assertEqual((root / name).read_text(encoding="utf-8"), contents)
