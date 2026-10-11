import unittest
import json
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
from crop_prototype.data import DEFAULT_CSV, load_simulated, feature_sets, FORBIDDEN_PREDICTORS, validate_simulated
from crop_prototype.modeling import grouped_holdout
from crop_prototype.survival import make_risk_intervals, predict_survival_path, SURVIVAL_FEATURES, aft_interval_bounds, _censor_survival_before, _training_only_horizon


class PrototypeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_simulated(DEFAULT_CSV)

    def test_unique_trajectory_time_keys(self):
        self.assertFalse(self.df.duplicated(["sim_trajectory_id", "storage_age_days"]).any())

    def test_utf8_schema_and_predictor_families(self):
        self.assertIn("Temperature(°C)", self.df.columns)
        for cols in feature_sets(self.df).values():
            self.assertTrue(set(cols).issubset(self.df.columns))
            self.assertFalse(set(cols) & FORBIDDEN_PREDICTORS)

    def test_source_order_is_chronological(self):
        trajectory = self.df.sim_trajectory_id.iloc[0]
        idx = self.df.index[self.df.sim_trajectory_id == trajectory][:2]
        broken = self.df.copy()
        broken.loc[idx] = broken.loc[idx[::-1]].to_numpy()
        with self.assertRaises(ValueError):
            validate_simulated(broken)

    def test_grouped_split_keeps_lots_intact(self):
        tr, te = grouped_holdout(self.df)
        self.assertFalse(set(self.df.iloc[tr].sim_lot_id) & set(self.df.iloc[te].sim_lot_id))

    def test_saved_holdout_ids_are_preserved(self):
        from crop_prototype.validation import saved_split
        tr, te = saved_split(self.df)
        saved = json.loads(Path("artifacts/status_metrics.json").read_text(encoding="utf-8"))["split"]
        self.assertEqual(set(self.df.iloc[te].sim_lot_id), set(saved["test_lots"]))
        self.assertEqual(set(self.df.iloc[tr].sim_lot_id), set(saved["train_lots"]))

    def test_features_exclude_targets_and_ids(self):
        for columns in feature_sets(self.df).values():
            self.assertFalse(set(columns) & FORBIDDEN_PREDICTORS)

    def test_censoring_and_failure_intervals(self):
        risk = make_risk_intervals(self.df)
        censored = risk[risk.right_censored]
        failed = risk[~risk.right_censored]
        self.assertGreater(len(censored), 0)
        self.assertEqual(int(censored.event_next.sum()), 0)
        self.assertTrue((failed.recorded_failure_upper_days > failed.recorded_failure_lower_days).all())
        self.assertTrue(set(risk.event_next.unique()) <= {0, 1})
        # No risk row may be at or after its trajectory's first failed check.
        self.assertTrue((failed.storage_age_days < failed.recorded_failure_upper_days).all())

    def test_hazard_landmark_uses_start_readings_and_excludes_post_failure(self):
        from crop_prototype.data import ENV_COLUMNS, MQ_COLUMNS
        risk = make_risk_intervals(self.df)
        sample = risk.iloc[0]
        source = self.df[(self.df.sim_trajectory_id == sample.sim_trajectory_id) &
                         (self.df.storage_age_days == sample.storage_age_days)].iloc[0]
        for column in [*ENV_COLUMNS, *MQ_COLUMNS, "past_mean_temp_C_SIM", "past_mean_rh_pct_SIM",
                       "past_hot_degree_days_SIM"]:
            if column in sample.index:
                self.assertEqual(sample[column], source[column])
        event_rows = risk[~risk.right_censored]
        self.assertTrue((event_rows.storage_age_days < event_rows.recorded_failure_upper_days).all())
        for column in ("event_observed_SIM", "remaining_days_to_first_failed_check_SIM", "post_failure_SIM"):
            self.assertNotIn(column, SURVIVAL_FEATURES)

    def test_censored_trajectories_have_no_fabricated_failure_time(self):
        risk = make_risk_intervals(self.df)
        censored = risk[risk.right_censored]
        self.assertTrue(censored.recorded_failure_upper_days.isna().all())
        self.assertTrue(censored.recorded_failure_lower_days.isna().all())
        self.assertFalse(censored.event_next.astype(bool).any())
        self.assertTrue((censored.interval_days > 0).all())
        first = self.df.sort_values(["sim_trajectory_id", "storage_age_days"]).drop_duplicates("sim_trajectory_id")
        lower, upper = aft_interval_bounds(first)
        censored_first = ~first.event_observed_SIM.astype(bool).to_numpy()
        self.assertTrue(pd.Series(upper[censored_first]).map(lambda x: x == float("inf")).all())
        self.assertTrue((lower[censored_first] == first.loc[censored_first, "observed_followup_days_SIM"].to_numpy()).all())
        self.assertEqual(_censor_survival_before([39, 39, 39], [True, True, True], 14), 1.0)

    def test_horizon_is_training_event_quantile_rounded_to_cadence(self):
        q25, horizon = _training_only_horizon([5, 8, 8, 9, 20, 100], 7)
        self.assertEqual(q25, 8.0)
        self.assertEqual(horizon, 14.0)
        with self.assertRaises(ValueError):
            _training_only_horizon([], 7)

    def test_history_summaries_include_current_but_not_future_rows(self):
        from crop_prototype.data import ENV_COLUMNS
        one = self.df[self.df.sim_trajectory_id == self.df.sim_trajectory_id.iloc[0]].sort_values("storage_age_days")
        temperatures = one[ENV_COLUMNS[0]].to_numpy()
        humidities = one[ENV_COLUMNS[1]].to_numpy()
        np.testing.assert_allclose(one.past_mean_temp_C_SIM, np.cumsum(temperatures) / np.arange(1, len(one) + 1), atol=0.02)
        np.testing.assert_allclose(one.past_mean_rh_pct_SIM, np.cumsum(humidities) / np.arange(1, len(one) + 1), atol=0.02)

    def test_future_sensor_changes_do_not_change_current_landmark(self):
        from crop_prototype.data import ENV_COLUMNS, MQ_COLUMNS
        lot_rows = self.df[self.df.sim_trajectory_id == self.df.sim_trajectory_id.iloc[0]].sort_values("storage_age_days")
        trajectory = lot_rows.sim_trajectory_id.iloc[0]
        changed = self.df.copy()
        idx = changed.index[(changed.sim_trajectory_id == trajectory) & (changed.storage_age_days > 0)]
        changed.loc[idx, ENV_COLUMNS[0]] = 9999
        changed.loc[idx, MQ_COLUMNS[0]] = -9999
        original_risk = make_risk_intervals(self.df)
        changed_risk = make_risk_intervals(changed)
        original = original_risk[(original_risk.sim_trajectory_id == trajectory) & (original_risk.storage_age_days == 0)].iloc[0]
        altered = changed_risk[(changed_risk.sim_trajectory_id == trajectory) & (changed_risk.storage_age_days == 0)].iloc[0]
        self.assertEqual(original[ENV_COLUMNS[0]], altered[ENV_COLUMNS[0]])
        self.assertEqual(original[MQ_COLUMNS[0]], altered[MQ_COLUMNS[0]])

    def test_survival_projection_requires_explicit_path(self):
        class FixedHazard:
            def predict_proba(self, x):
                import numpy as np
                return np.tile([0.6, 0.4], (len(x), 1))
        row = {c: self.df.iloc[0][c] for c in SURVIVAL_FEATURES}
        path = pd.DataFrame([{**row, "interval_days": 2.0}, {**row, "interval_days": 3.0}])
        result = predict_survival_path(FixedHazard(), path)
        self.assertEqual(result["median_time_to_event_days_within_path"], 5.0)
        with self.assertRaises(ValueError):
            predict_survival_path(FixedHazard(), path.drop(columns=["MQ2_response_index_SIM"]))

    def test_user_prediction_reports_missing_required_inputs(self):
        from crop_prototype.cli import predict_from_input
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text('{"crop":"wheat"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing required current inputs"):
                predict_from_input(path, "artifacts")


if __name__ == "__main__":
    unittest.main()
