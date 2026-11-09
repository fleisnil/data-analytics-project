import unittest

import numpy as np
import pandas as pd

from src import model_evaluation as evaluation


class EvaluationTest(unittest.TestCase):
    def test_strict_date_boundary_never_breaks_a_batch_at_midnight(self):
        raw = pd.DataFrame({
            evaluation.TIME: pd.to_datetime([
                "2026-09-01T09:00:00Z", "2026-09-01T21:59:00Z",
                "2026-09-01T22:01:00Z", "2026-09-02T12:00:00Z",
                "2026-09-03T12:00:00Z",
            ], utc=True),
            "batch_id": ["day_one", "across_midnight", "across_midnight", "day_two", "day_three"],
        })
        train, test, method = evaluation.chronological_holdout(raw, 0.4)
        self.assertEqual(method, "collection_date")
        self.assertEqual(test[evaluation.DAY].tolist(), ["2026-09-03"])
        self.assertTrue(set(train.batch_id).isdisjoint(test.batch_id))
        self.assertLess(train[evaluation.TIME].max(), test[evaluation.TIME].min())

    def test_same_day_can_split_batches_but_not_one_batch(self):
        data = pd.DataFrame({
            evaluation.TIME: pd.date_range("2026-11-01T10:00:00Z", periods=4, freq="min"),
            "batch_id": ["a", "a", "b", "b"],
        })
        train, test, method = evaluation.chronological_holdout(data, 0.8)
        self.assertEqual(method, "batch_id")
        self.assertEqual(train.batch_id.unique().tolist(), ["a"])
        self.assertEqual(test.batch_id.unique().tolist(), ["b"])
        with self.assertRaisesRegex(ValueError, "without dividing"):
            evaluation.chronological_holdout(data.assign(batch_id="a"), 0.8)

    def test_group_median_uses_training_only_and_falls_back_for_sparse_groups(self):
        train = pd.DataFrame({
            "city": ["A"] * 10 + ["B"],
            evaluation.TARGET: [1.0] * 10 + [20.0],
        })
        test = pd.DataFrame({"city": ["A", "C", "B"], evaluation.TARGET: [-90.0, 100.0, 100.0]})
        values, fallback = evaluation.group_median(train, test)
        np.testing.assert_array_equal(values, [1.0, 1.0, 1.0])
        np.testing.assert_array_equal(fallback, [False, True, True])

    def test_paired_comparison_resamples_dates_and_withholds_short_intervals(self):
        data = pd.DataFrame({
            evaluation.DAY: [f"2026-11-0{i}" for i in range(1, 7)],
            "actual_delay": [0.0] * 6, "pred_a": [1.0] * 6, "pred_b": [3.0] * 6,
        })
        for row in evaluation.paired_day_comparison(data, "a", "b"):
            self.assertEqual(row["status"], "evaluated")
            self.assertEqual((row["difference"], row["ci_low"], row["ci_high"]), (-2.0, -2.0, -2.0))
        for row in evaluation.paired_day_comparison(data.iloc[:4], "a", "b"):
            self.assertEqual(row["status"], "insufficient_test_dates")
            self.assertTrue(np.isnan(row["ci_low"]))
