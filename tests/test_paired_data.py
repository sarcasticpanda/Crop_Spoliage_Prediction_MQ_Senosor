import tempfile
import unittest
from pathlib import Path

import pandas as pd

from crop_prototype.paired_data import ENV_COLUMNS, MQ_COLUMNS, REQUIRED_COLUMNS, audit_paired_csv


def example_table():
    rows = []
    for i, lot in enumerate(("L1", "L2")):
        row = {column: 1.0 for column in ENV_COLUMNS + MQ_COLUMNS}
        row.update({
            "study_id": "potato-study", "crop": "potato", "lot_id": lot,
            "sample_id": f"sample-{i}", "storage_unit_id": f"box-{i}",
            "sensor_timestamp_utc": "2026-01-01T00:00:00Z",
            "inspection_timestamp_utc": "2026-01-01T00:01:00Z",
            "quality_label": "normal", "quality_method": "blinded visual rubric",
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


class PairedDataAuditChecks(unittest.TestCase):
    def audit_frame(self, frame, max_pair_gap_seconds=300):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paired.csv"
            frame.to_csv(path, index=False)
            return audit_paired_csv(path, max_pair_gap_seconds)

    def test_matching_single_crop_paired_data_is_schema_ready(self):
        report = self.audit_frame(example_table())
        self.assertTrue(report["ready_for_training"])
        self.assertEqual(report["unique_lots_by_crop"]["potato"], 2)
        self.assertEqual(report["rows_over_pair_tolerance"], 0)

    def test_unmatched_sensor_time_is_blocked(self):
        frame = example_table()
        frame.loc[0, "sensor_timestamp_utc"] = "2026-01-01T01:00:00Z"
        report = self.audit_frame(frame, max_pair_gap_seconds=300)
        self.assertFalse(report["ready_for_training"])
        self.assertIn("sensor/inspection time gap exceeds the declared tolerance or is invalid", report["blocking_issues"])

    def test_cross_crop_pooling_is_blocked(self):
        frame = example_table()
        frame.loc[1, "crop"] = "tomato"
        report = self.audit_frame(frame)
        self.assertFalse(report["ready_for_training"])
        self.assertIn("file must contain one crop; keep crop studies separate", report["blocking_issues"])

    def test_duplicate_sample_inspection_key_is_blocked(self):
        frame = example_table()
        frame.loc[1, "sample_id"] = frame.loc[0, "sample_id"]
        frame.loc[1, "inspection_timestamp_utc"] = frame.loc[0, "inspection_timestamp_utc"]
        report = self.audit_frame(frame)
        self.assertFalse(report["ready_for_training"])
        self.assertEqual(report["duplicate_sample_inspection_key_rows"], 2)

    def test_missing_sensor_channel_is_reported_and_blocked_if_entirely_empty(self):
        frame = example_table()
        frame["mq7_response"] = float("nan")
        report = self.audit_frame(frame)
        self.assertFalse(report["ready_for_training"])
        self.assertEqual(report["missing_feature_values"]["mq7_response"], 2)

    def test_missing_required_column_returns_actionable_report(self):
        frame = example_table().drop(columns=["temperature_c"])
        report = self.audit_frame(frame)
        self.assertFalse(report["ready_for_training"])
        self.assertIn("temperature_c", report["missing_required_columns"])


if __name__ == "__main__":
    unittest.main()
