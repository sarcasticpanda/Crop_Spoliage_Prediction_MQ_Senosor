import json
import unittest
from pathlib import Path

import pandas as pd

from crop_prototype.edition2_simulation_v3 import (
    CLASSES, FEATURES, OUT_ROOT, DATA_ROOT, predict_saved,
)

ROOT = Path(__file__).resolve().parents[1]


class Edition2V3Checks(unittest.TestCase):
    def test_crop_rows_have_unique_sample_time_and_all_simulated_classes(self):
        for crop in ("tomato", "potato", "banana"):
            path = DATA_ROOT / crop / "simulated_v3" / f"{crop}_source_informed_3state_SIMULATED.csv"
            df = pd.read_csv(path)
            self.assertFalse(df.duplicated(["sim_sample_id", "storage_age_days_SIM"]).any())
            self.assertEqual(df["sim_sample_id"].nunique(), 100)
            self.assertEqual(set(df["quality_state_SIM"].unique()), set(CLASSES))

    def test_fixed_group_splits_keep_sample_trajectories_together(self):
        for crop in ("tomato", "potato", "banana"):
            split = json.loads((OUT_ROOT / f"{crop}_split.json").read_text(encoding="utf-8"))
            self.assertTrue(set(split["train_sample_ids"]).isdisjoint(split["test_sample_ids"]))
            self.assertEqual(len(split["train_sample_ids"]), 80)
            self.assertEqual(len(split["test_sample_ids"]), 20)

    def test_predictor_sets_exclude_labels_and_identifiers(self):
        forbidden = {"quality_state_SIM", "sim_sample_id", "sim_observation_id",
                     "storage_scenario_SIM", "label_origin", "data_origin"}
        for cols in FEATURES.values():
            self.assertTrue(forbidden.isdisjoint(cols))

    def test_saved_prediction_runs_and_missing_input_is_rejected(self):
        example = ROOT / "examples" / "edition2_v3_prediction_input.json"
        result = predict_saved(example)
        self.assertEqual(result["label"], "SIMULATION ONLY")
        self.assertEqual(set(result["state_probabilities_SIM"]), set(CLASSES))
        payload = json.loads(example.read_text(encoding="utf-8"))
        payload.pop(FEATURES["combined"][0])
        tmp = ROOT / ".docx_review" / "incomplete_v3_input.json"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "Missing required predictor inputs"):
                predict_saved(tmp)
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
