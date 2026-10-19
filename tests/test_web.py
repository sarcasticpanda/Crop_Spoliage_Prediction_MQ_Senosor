import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

from crop_prototype import web
from crop_prototype.inference import load_prediction_models


class WebInterfaceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web.MODELS = load_prediction_models("artifacts")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web.WebHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.demo = json.loads(Path("examples/simulated_prediction_input.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        web.UPLOADS.clear()

    def request(self, path, body=None, content_type="application/json", method=None, headers=None):
        data = body
        if content_type == "application/json" and isinstance(body, dict):
            data = json.dumps(body).encode("utf-8")
        request = Request(self.base + path, data=data, headers={"Content-Type": content_type, **(headers or {})}, method=method)
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_home_and_saved_group_validation_are_available(self):
        with urlopen(self.base + "/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Check a crop lot", response.read())
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ready"])
        self.assertEqual(health["validation"]["split"]["training_lots"], 400)
        self.assertEqual(health["validation"]["split"]["held_out_lots"], 100)
        self.assertEqual(health["validation"]["split"]["lot_overlap"], 0)
        xgb = next(item for item in health["validation"]["status_models"] if item["model"] == "xgboost")
        self.assertEqual(xgb["grouped_cv"]["folds"], 5)
        self.assertEqual(xgb["grouped_cv"]["group"], "sim_lot_id")
        self.assertEqual(len(health["validation"]["status_by_crop"]), 5)

    def test_full_manual_input_returns_model_probabilities_and_risk(self):
        status, result = self.request("/api/predict", self.demo)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["label"], "SIMULATION ONLY")
        self.assertEqual(set(result["status_probabilities"]), {"acceptable", "warning", "spoiled"})
        self.assertAlmostEqual(sum(result["status_probabilities"].values()), 1.0, places=5)
        self.assertIsNotNone(result["probability_next_check_leaves_acceptable_state"])

    def test_missing_reading_is_reported_without_imputation(self):
        status, result = self.request("/api/predict", {"crop": "maize"})
        self.assertEqual(status, 400)
        self.assertIn("no values were inferred", result["error"])

    def test_csv_mapping_scores_a_complete_row_and_flags_incomplete_file(self):
        csv_body = pd.DataFrame([{k: v for k, v in self.demo.items() if not k.startswith("_") and k != "next_inspection_interval_days"}]).to_csv(index=False).encode("utf-8")
        status, upload = self.request("/api/upload", csv_body, "text/csv", headers={"X-Filename": "paired-real-style.csv"})
        self.assertEqual(status, 200, upload)
        self.assertEqual(len(upload["audit"]["matched_model_fields"]), 22)
        self.assertFalse(upload["audit"]["missing_required_model_fields"])
        self.assertEqual(set(upload["audit"]["missing_optional_model_fields"]), {"grain_moisture_pct_SIM", "lot_mass_kg_SIM"})
        status, result = self.request("/api/predict-row", {"token": upload["token"], "index": 0, "crop": "maize", "next_inspection_interval_days": 7})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["label"], "SIMULATION ONLY")

        incomplete = b"crop,Temperature,Humidity,Date,Time\nmaize,20,60,bad-date,12:00:00\n"
        status, partial = self.request("/api/upload", incomplete, "text/csv", headers={"X-Filename": "environment-only.csv"})
        self.assertEqual(status, 200)
        self.assertIn("MQ2_response_index_SIM", partial["audit"]["missing_model_fields"])
        self.assertEqual(partial["audit"]["timestamp_audit"]["invalid_timestamps"], 1)
        status, result = self.request("/api/predict-row", {"token": partial["token"], "index": 0, "crop": "maize", "next_inspection_interval_days": 7})
        self.assertEqual(status, 400)
        self.assertIn("MQ2_response_index_SIM", result["error"])

    def test_future_path_projection_requires_explicit_values(self):
        from crop_prototype.survival import SURVIVAL_FEATURES
        row = {key: self.demo.get(key) for key in SURVIVAL_FEATURES if key in self.demo}
        row["storage_age_days"] = 1
        second = dict(row)
        second["storage_age_days"] = 8
        path = pd.DataFrame([row, second])
        path["interval_days"] = 7
        csv_body = path.to_csv(index=False).encode("utf-8")
        status, upload = self.request("/api/upload", csv_body, "text/csv", headers={"X-Filename": "explicit-future-path.csv"})
        self.assertEqual(status, 200, upload)
        status, projected = self.request("/api/project", {"token": upload["token"], "mapping": {}, "interval_column": "interval_days"})
        self.assertEqual(status, 200, projected)
        self.assertEqual(projected["label"], "SIMULATED FUTURE-PATH PROJECTION")
        self.assertFalse(projected["future_values_reused_from_current"])
        self.assertEqual(len(projected["periods"]), 2)

        status, refused = self.request("/api/project", {"token": upload["token"], "mapping": {}, "interval_column": "missing_interval"})
        self.assertEqual(status, 400)
        self.assertIn("interval_days", refused["error"])

    def test_target_fields_cannot_be_mapped_as_sensor_inputs(self):
        row = {k: v for k, v in self.demo.items() if not k.startswith("_")}
        row["status_SIM"] = "acceptable"
        status, upload = self.request("/api/upload", pd.DataFrame([row]).to_csv(index=False).encode("utf-8"),
                                      "text/csv", headers={"X-Filename": "target-column-check.csv"})
        self.assertEqual(status, 200)
        self.assertIn("status_SIM", upload["audit"]["blocked_predictor_sources"])
        status, result = self.request("/api/predict-row", {
            "token": upload["token"], "index": 0, "crop": "maize", "next_inspection_interval_days": 7,
            "mapping": {"Temperature(°C)": "status_SIM"},
        })
        self.assertEqual(status, 400)
        self.assertIn("cannot be mapped", result["error"])


if __name__ == "__main__":
    unittest.main()
