"""Local browser interface for checking readings with the saved full-input models."""
from __future__ import annotations

import argparse
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .data import DEFAULT_CSV, FORBIDDEN_PREDICTORS
from .inference import CROPS, OPTIONAL_MODEL_INPUTS, UNIT_RANGES, load_prediction_models, predict_payload, predict_status_mode
from .survival import SURVIVAL_FEATURES, predict_survival_path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
PAGE = Path(__file__).resolve().parent / "web" / "index.html"
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
UPLOADS: dict[str, pd.DataFrame] = {}
UPLOAD_LOCK = threading.Lock()
MODELS = None


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if pd.isna(value):
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _required_model_columns():
    return list(MODELS["status"].named_steps["prep"].feature_names_in_)


def _is_forbidden_predictor_source(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    blocked = ("status", "inspection_label", "inspection_status", "inspection_result", "inspection_quality",
               "inspection_type", "inspection_id", "defect", "failure", "event_observed", "remaining_days",
               "quality_label", "quality_grade", "quality_status", "target", "label", "post_failure",
               "sim_lot_id", "trajectory_id", "scenario", "timestamp",
               "date", "time", "data_origin", "initial_inspection")
    return str(name) in FORBIDDEN_PREDICTORS or any(token in normalized for token in blocked)


def _audit_frame(frame: pd.DataFrame) -> dict:
    required = _required_model_columns()
    present = [c for c in required if c in frame.columns]
    missing_columns = [c for c in required if c not in frame.columns]
    missing_required = [c for c in missing_columns if c not in OPTIONAL_MODEL_INPUTS]
    missing_optional = [c for c in missing_columns if c in OPTIONAL_MODEL_INPUTS]
    required_without_crop = [c for c in required if c != "crop"]
    incomplete = {}
    invalid_numeric = {}
    out_of_basic_range = {}
    for col in present:
        if col == "crop":
            continue
        if col in required_without_crop:
            incomplete[col] = int(frame[col].isna().sum())
            numeric = pd.to_numeric(frame[col], errors="coerce")
            invalid_numeric[col] = int((frame[col].notna() & numeric.isna()).sum())
            if col in UNIT_RANGES:
                low, high, _ = UNIT_RANGES[col]
                out_of_basic_range[col] = int(((numeric < low) | (numeric > high)).sum())
    time_report = None
    date_col = next((c for c in frame.columns if str(c).strip().lower() == "date"), None)
    time_col = next((c for c in frame.columns if str(c).strip().lower() == "time"), None)
    timestamp_col = next((c for c in frame.columns if str(c).strip().lower() in {"timestamp", "datetime", "timestamp_utc", "parsed_timestamp"}), None)
    if timestamp_col:
        stamps = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True)
    elif date_col and time_col:
        stamps = pd.to_datetime(frame[date_col].astype(str) + " " + frame[time_col].astype(str), errors="coerce", utc=True)
    else:
        stamps = None
    if stamps is not None:
        ordered = stamps.dropna().sort_values()
        gaps = ordered.diff().dropna().dt.total_seconds() / 60
        time_report = {
            "timestamp_column": timestamp_col or f"{date_col} + {time_col}",
            "valid_timestamps": int(stamps.notna().sum()),
            "invalid_timestamps": int(stamps.isna().sum()),
            "duplicate_timestamps": int(stamps.dropna().duplicated().sum()),
            "gaps_over_30_minutes": int((gaps > 30).sum()),
            "largest_gap_minutes": float(gaps.max()) if len(gaps) and np.isfinite(gaps.max()) else None,
        }
    key_report = None
    if {"sim_trajectory_id", "storage_age_days"}.issubset(frame.columns):
        key_report = {
            "duplicate_trajectory_time_keys": int(frame.duplicated(["sim_trajectory_id", "storage_age_days"]).sum()),
            "strictly_increasing_within_trajectory": bool(frame.groupby("sim_trajectory_id", sort=False)["storage_age_days"].apply(lambda s: s.is_monotonic_increasing).all()),
        }
    origin = sorted(frame["data_origin"].dropna().astype(str).unique().tolist()) if "data_origin" in frame else []
    simulated = bool(any("SIM" in x.upper() for x in origin))
    return {
        "rows": int(len(frame)), "columns": int(len(frame.columns)),
        "matched_model_fields": present, "missing_model_fields": missing_columns,
        "missing_required_model_fields": missing_required,
        "missing_optional_model_fields": missing_optional,
        "missing_values_in_present_model_fields": incomplete,
        "invalid_numeric_values": invalid_numeric,
        "out_of_basic_sensor_range": out_of_basic_range,
        "blocked_predictor_sources": [c for c in frame.columns if _is_forbidden_predictor_source(c)],
        "timestamp_audit": time_report, "trajectory_key_audit": key_report,
        "data_origin_values": origin,
        "simulated_flag_detected": simulated,
        "note": "No fields were created or joined. Missing paired sensor/history fields must be collected; an AeroSense-only row cannot be scored by the combined model.",
    }


def _validation_summary() -> dict:
    status_path = ARTIFACTS / "status_metrics.json"
    survival_path = ARTIFACTS / "survival_metrics.json"
    diagnostics_path = ARTIFACTS / "diagnostics" / "diagnostics_metrics.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    survival = json.loads(survival_path.read_text(encoding="utf-8")) if survival_path.exists() else {}
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {}
    scores = status.get("results", [])
    cv_by_model = {item.get("model"): item for item in status.get("grouped_validation", []) if item.get("feature_set") == "combined"}
    combined = [r for r in scores if r.get("feature_set") == "combined"]
    selected = next((r for r in combined if r.get("model") == "xgboost"), {})
    early = diagnostics.get("early_warning_leaving_acceptable_state", {})
    split = status.get("split", {})
    return _json_safe({
        "label": "SIMULATION ONLY",
        "split": {"training_lots": len(split.get("train_lots", [])), "held_out_lots": len(split.get("test_lots", [])),
                  "training_rows": split.get("train_rows"), "held_out_rows": split.get("test_rows"),
                  "lot_overlap": len(set(split.get("train_lots", [])) & set(split.get("test_lots", [])))},
        "status_models": [{"model": r.get("model"), "macro_f1": r.get("macro_f1"), "spoiled_recall": r.get("per_class", {}).get("spoiled", {}).get("recall"),
                           "log_loss": r.get("log_loss"), "brier": r.get("multiclass_brier"),
                           "grouped_cv": cv_by_model.get(r.get("model"))} for r in combined],
        "validation_design": {"folds": 5, "group": "sim_lot_id", "calibration": "No post-hoc probability calibration; preprocessing and tuning stay inside training folds."},
        "holdout_note": "The fixed simulated test lots have also been examined in exploratory diagnostics. Use a fresh independent real-lot test set for final accuracy claims.",
        "status_by_crop": selected.get("per_crop", {}),
        "survival_by_crop": survival.get("per_crop_event_censoring", {}),
        "early_warning": {name: {"brier": item.get("brier"), "average_precision": item.get("average_precision"), "mean_predicted": item.get("mean_predicted"), "observed_fraction": item.get("observed_fraction")}
                          for name, item in early.get("models", {}).items()},
        "early_warning_threshold": early.get("training_only_alert_threshold"),
        "survival_warning": survival.get("warning"),
        "status_warning": status.get("warning"),
        "metrics_available": bool(scores),
    })


class WebHandler(BaseHTTPRequestHandler):
    server_version = "StoredCropLocal/1.0"

    def log_message(self, fmt, *args):
        print("[web] " + fmt % args)

    def _write(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value):
        body = json.dumps(_json_safe(value), allow_nan=False).encode("utf-8")
        self._write(status, body, "application/json; charset=utf-8")

    def _body_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES:
            raise ValueError("Request exceeds the 32 MB limit")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/api/health":
            self._json(200, {"ready": MODELS is not None, "model_files": {p.name: p.is_file() for p in [
                ARTIFACTS / "combined__xgboost.joblib", ARTIFACTS / "discrete_hazard_xgboost.joblib",
                ARTIFACTS / "diagnostics" / "early_warning_leave_acceptable__discrete_logistic.joblib"]},
                "simulated_rows_available": (ROOT / DEFAULT_CSV).is_file(), "validation": _validation_summary()})
        elif parsed.path == "/api/validation":
            self._json(200, _validation_summary())
        elif parsed.path == "/api/demo":
            demo = ROOT / "examples" / "simulated_prediction_input.json"
            self._json(200, json.loads(demo.read_text(encoding="utf-8")))
        elif parsed.path == "/api/row":
            query = parse_qs(parsed.query)
            token = query.get("token", [""])[0]
            try:
                index = int(query.get("index", ["-1"])[0])
            except ValueError:
                index = -1
            with UPLOAD_LOCK:
                frame = UPLOADS.get(token)
                if frame is None or index < 0 or index >= len(frame):
                    self._json(404, {"error": "Uploaded file or row not found"})
                    return
                row = frame.iloc[index].to_dict()
            self._json(200, {"index": index, "row": _json_safe(row)})
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/predict":
                payload = self._body_json()
                feature_mode = payload.pop("feature_mode", "combined")
                if feature_mode == "combined":
                    self._json(200, predict_payload(payload, ARTIFACTS, MODELS))
                else:
                    self._json(200, predict_status_mode(payload, feature_mode, ARTIFACTS, MODELS))
                return
            if parsed.path == "/api/upload":
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_UPLOAD_BYTES:
                    raise ValueError("Choose a non-empty CSV smaller than 32 MB")
                filename = self.headers.get("X-Filename", "sensor-readings.csv")
                if not filename.lower().endswith(".csv"):
                    raise ValueError("Upload CSV files. Export an Excel workbook to CSV first.")
                raw = self.rfile.read(length)
                try:
                    frame = pd.read_csv(pd.io.common.BytesIO(raw), encoding="utf-8-sig", low_memory=False)
                except Exception as exc:
                    raise ValueError(f"CSV could not be read: {exc}") from None
                if frame.empty:
                    raise ValueError("CSV contains no data rows")
                if len(frame.columns) > 300:
                    raise ValueError("CSV has too many columns (maximum 300)")
                token = uuid.uuid4().hex
                with UPLOAD_LOCK:
                    if len(UPLOADS) >= 5:
                        UPLOADS.pop(next(iter(UPLOADS)))
                    UPLOADS[token] = frame
                preview = frame.head(30).copy()
                preview.insert(0, "_row_index", range(len(preview)))
                self._json(200, {"token": token, "filename": Path(filename).name,
                    "columns": list(frame.columns), "audit": _audit_frame(frame),
                    "preview": _json_safe(preview.where(pd.notna(preview), None).to_dict(orient="records"))})
                return
            if parsed.path == "/api/predict-row":
                payload = self._body_json()
                token, index = payload.get("token"), int(payload.get("index", -1))
                feature_mode = payload.get("feature_mode", "combined")
                model_key = {"combined": "status", "environment_only": "environment_status", "mq_only": "mq_status"}.get(feature_mode)
                if model_key is None:
                    raise ValueError("feature_mode must be combined, environment_only, or mq_only")
                model_fields = list(MODELS[model_key].named_steps["prep"].feature_names_in_)
                with UPLOAD_LOCK:
                    frame = UPLOADS.get(token)
                    if frame is None or index < 0 or index >= len(frame):
                        self._json(404, {"error": "Uploaded file or row not found"})
                        return
                    row = frame.iloc[index].to_dict()
                mapping = payload.get("mapping", {})
                forbidden = [source for source in mapping.values() if source and _is_forbidden_predictor_source(source)]
                if forbidden:
                    raise ValueError("Target, inspection, ID, scenario, and timestamp fields cannot be mapped as model inputs: " + ", ".join(forbidden))
                row_payload = {field: row.get(mapping.get(field, field)) for field in model_fields}
                row_payload["crop"] = payload.get("crop") or row_payload.get("crop")
                interval = payload.get("next_inspection_interval_days")
                if feature_mode == "combined":
                    row_payload["next_inspection_interval_days"] = interval
                    result = predict_payload(row_payload, ARTIFACTS, MODELS)
                else:
                    result = predict_status_mode(row_payload, feature_mode, ARTIFACTS, MODELS)
                self._json(200, result)
                return
            if parsed.path == "/api/predict-csv":
                payload = self._body_json()
                token = payload.get("token")
                feature_mode = payload.get("feature_mode", "combined")
                model_key = {"combined": "status", "environment_only": "environment_status", "mq_only": "mq_status"}.get(feature_mode)
                if model_key is None:
                    raise ValueError("feature_mode must be combined, environment_only, or mq_only")
                model_fields = list(MODELS[model_key].named_steps["prep"].feature_names_in_)
                mapping = payload.get("mapping", {})
                crop_fallback = str(payload.get("crop_fallback", "")).strip().lower()
                interval_column = payload.get("interval_column") or ""
                with UPLOAD_LOCK:
                    frame = UPLOADS.get(token)
                    if frame is None:
                        self._json(404, {"error": "Uploaded file not found; upload it again"})
                        return
                    frame = frame.copy()
                forbidden = [source for source in mapping.values() if source and _is_forbidden_predictor_source(source)]
                if forbidden:
                    raise ValueError("Target, inspection, ID, scenario, and timestamp fields cannot be predictors: " + ", ".join(forbidden))
                if interval_column and interval_column not in frame.columns:
                    raise ValueError("The selected inspection interval column is not in the CSV")
                if crop_fallback and crop_fallback not in CROPS:
                    raise ValueError("crop_fallback must be wheat, maize, potato, onion, or spinach")
                output_rows = []
                for row_index, source_row in frame.iterrows():
                    row_payload = {}
                    for field in model_fields:
                        source = mapping.get(field, field)
                        row_payload[field] = source_row.get(source) if source and source in frame.columns else None
                    if not row_payload.get("crop"):
                        row_payload["crop"] = crop_fallback or None
                    interval_value = source_row.get(interval_column) if interval_column else None
                    try:
                        if feature_mode == "combined" and interval_value is not None and not pd.isna(interval_value) and str(interval_value).strip():
                            row_payload["next_inspection_interval_days"] = interval_value
                            result = predict_payload(row_payload, ARTIFACTS, MODELS)
                        else:
                            result = predict_status_mode(row_payload, feature_mode, ARTIFACTS, MODELS)
                        probs = result.get("status_probabilities", {})
                        output_rows.append({
                            "source_row": int(row_index), "label": "SIMULATION ONLY", "feature_mode": feature_mode,
                            "crop": result.get("crop"), "storage_age_days": result.get("storage_age_days"),
                            "predicted_status": result.get("predicted_status"),
                            "p_acceptable": probs.get("acceptable"), "p_warning": probs.get("warning"), "p_spoiled": probs.get("spoiled"),
                            "next_inspection_interval_days": result.get("next_inspection_interval_days"),
                            "p_leave_acceptable_next_check": result.get("probability_next_check_leaves_acceptable_state"),
                            "p_first_spoiled_by_next_check": result.get("probability_first_spoiled_inspection_by_next_check"),
                            "error": "",
                        })
                    except (ValueError, TypeError) as exc:
                        output_rows.append({"source_row": int(row_index), "label": "SIMULATION ONLY", "feature_mode": feature_mode,
                                            "crop": row_payload.get("crop"), "storage_age_days": row_payload.get("storage_age_days"),
                                            "predicted_status": "", "p_acceptable": "", "p_warning": "", "p_spoiled": "",
                                            "next_inspection_interval_days": interval_value, "p_leave_acceptable_next_check": "",
                                            "p_first_spoiled_by_next_check": "", "error": str(exc)})
                result_frame = pd.DataFrame(output_rows)
                body = result_frame.to_csv(index=False).encode("utf-8-sig")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="simulation_only_predictions.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/project":
                payload = self._body_json()
                token = payload.get("token")
                mapping = payload.get("mapping", {})
                forbidden = [source for source in mapping.values() if source and _is_forbidden_predictor_source(source)]
                if forbidden:
                    raise ValueError("Target, inspection, ID, scenario, and timestamp fields cannot be future predictors: " + ", ".join(forbidden))
                interval_column = payload.get("interval_column")
                if interval_column and _is_forbidden_predictor_source(interval_column):
                    raise ValueError("Choose an observed future-interval duration column, not a target, identifier, scenario, or timestamp")
                with UPLOAD_LOCK:
                    frame = UPLOADS.get(token)
                    if frame is None:
                        self._json(404, {"error": "Uploaded future-path file not found"})
                        return
                    future = frame.copy()
                columns = {field: mapping.get(field, field) for field in SURVIVAL_FEATURES}
                missing = [field for field, source in columns.items()
                           if source not in future.columns and field not in OPTIONAL_MODEL_INPUTS]
                if not interval_column or interval_column not in future.columns:
                    missing.append("interval_days (select a future interval column)")
                if missing:
                    raise ValueError("Future path needs explicit values for: " + ", ".join(missing))
                mapped_sources = [source for field, source in columns.items() if source in future.columns]
                if len(set(mapped_sources)) != len(mapped_sources):
                    raise ValueError("Map each model field to its own source column")
                future = future.rename(columns={source: field for field, source in columns.items() if source in future.columns})
                for optional in OPTIONAL_MODEL_INPUTS:
                    if optional not in future:
                        future[optional] = np.nan
                future["interval_days"] = pd.to_numeric(frame[interval_column], errors="coerce")
                needed = SURVIVAL_FEATURES + ["interval_days"]
                for column in [c for c in SURVIVAL_FEATURES if c != "crop"]:
                    future[column] = pd.to_numeric(future[column], errors="coerce")
                blank = {c: int(future[c].isna().sum()) for c in needed
                         if c not in OPTIONAL_MODEL_INPUTS and future[c].isna().any()}
                if blank:
                    raise ValueError("Future path has blank values; no current values were copied: " + json.dumps(blank))
                numeric_needed = [c for c in needed if c != "crop"]
                if not np.isfinite(future[numeric_needed].drop(columns=list(OPTIONAL_MODEL_INPUTS), errors="ignore").to_numpy(dtype=float)).all():
                    raise ValueError("Future path contains non-finite required numeric values")
                if len(future) < 1 or not np.isfinite(future.interval_days).all() or (future.interval_days <= 0).any():
                    raise ValueError("Future path needs one or more rows with positive interval_days")
                if (future.storage_age_days < 0).any():
                    raise ValueError("Future storage_age_days values must be non-negative")
                if not future.storage_age_days.is_monotonic_increasing or future.storage_age_days.duplicated().any():
                    raise ValueError("Future path rows must be in strictly increasing storage_age_days order")
                if future.crop.astype(str).str.lower().nunique() != 1:
                    raise ValueError("Every future row in one path must use the same crop")
                if future.crop.astype(str).str.lower().iloc[0] not in CROPS:
                    raise ValueError("Future path crop must be wheat, maize, potato, onion, or spinach")
                for column, (low, high, unit) in UNIT_RANGES.items():
                    if column in future and (((future[column] < low) | (future[column] > high)).any()):
                        raise ValueError(f"Future {column} values are outside the basic {unit} range [{low}, {high}]")
                future["crop"] = future.crop.astype(str).str.lower()
                report = predict_survival_path(MODELS["first_spoiled"], future[needed])
                report.update({"label": "SIMULATED FUTURE-PATH PROJECTION", "explicit_future_rows": int(len(future)),
                               "future_values_reused_from_current": False,
                               "note": "Conditional simulator projection from the explicitly uploaded future environment, history, and nine MQ channels. No sensor values were copied forward. This is not causal evidence that a storage change extends real shelf life."})
                self._json(200, report)
                return
            self._json(404, {"error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Prediction service error: {exc}"})


def main():
    global MODELS
    global ARTIFACTS
    parser = argparse.ArgumentParser(description="Run the local stored-crop model checking interface")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only by default")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--artifacts", default=str(ARTIFACTS))
    args = parser.parse_args()
    ARTIFACTS = Path(args.artifacts).resolve()
    MODELS = load_prediction_models(ARTIFACTS)
    server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    print(f"Stored crop model check is ready: http://{args.host}:{args.port}")
    print("Model status: SIMULATION ONLY. Uploaded CSV files stay in server memory and are not written to disk.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping local model check.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
