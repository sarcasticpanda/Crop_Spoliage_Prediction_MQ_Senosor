"""Shared prediction path used by the CLI and local web application."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import load


OPTIONAL_MODEL_INPUTS = {"grain_moisture_pct_SIM", "lot_mass_kg_SIM"}
CROPS = {"wheat", "maize", "potato", "onion", "spinach"}
UNIT_RANGES = {
    "Humidity(%)": (0.0, 100.0, "%"),
    "Temperature(\u00b0C)": (-50.0, 85.0, "\u00b0C"),
    "DewPoint(\u00b0C)": (-100.0, 85.0, "\u00b0C"),
    "HeatIndex(\u00b0C)": (-50.0, 100.0, "\u00b0C"),
    "Pressure(hPa)": (300.0, 1200.0, "hPa"),
    "Gas (kOhms)": (0.0, float("inf"), "kOhms"),
    "Altitude(m)": (-500.0, 10000.0, "m"),
    "AQI": (0.0, float("inf"), "device-defined AQI scale"),
    "grain_moisture_pct_SIM": (0.0, 100.0, "%"),
    "lot_mass_kg_SIM": (0.0, float("inf"), "kg"),
    "past_mean_temp_C_SIM": (-50.0, 85.0, "\u00b0C"),
    "past_mean_rh_pct_SIM": (0.0, 100.0, "%"),
    "past_hot_degree_days_SIM": (0.0, float("inf"), "\u00b0C\u00b7days"),
}


def load_prediction_models(out_dir="artifacts"):
    out = Path(out_dir)
    paths = {
        "status": out / "combined__xgboost.joblib",
        "environment_status": out / "environment_only__xgboost.joblib",
        "mq_status": out / "mq_only__xgboost.joblib",
        "first_spoiled": out / "discrete_hazard_xgboost.joblib",
        "leave_acceptable": out / "diagnostics" / "early_warning_leave_acceptable__discrete_logistic.joblib",
    }
    missing = [str(path) for key, path in paths.items()
               if key != "leave_acceptable" and not path.is_file()]
    if missing:
        raise FileNotFoundError("Saved models missing: " + ", ".join(missing))
    models = {key: load(path) for key, path in paths.items() if path.is_file()}
    models.setdefault("leave_acceptable", None)
    return models


def predict_status_mode(payload: dict, feature_mode="combined", out_dir="artifacts", models=None) -> dict:
    """Predict status with one saved feature family; never infer absent readings."""
    modes = {
        "combined": "status",
        "environment_only": "environment_status",
        "mq_only": "mq_status",
    }
    if feature_mode not in modes:
        raise ValueError("feature_mode must be combined, environment_only, or mq_only")
    models = models or load_prediction_models(out_dir)
    model = models[modes[feature_mode]]
    feature_columns = list(model.named_steps["prep"].feature_names_in_)
    required = [c for c in feature_columns if c not in OPTIONAL_MODEL_INPUTS]
    missing = [key for key in required if key not in payload or payload.get(key) is None or str(payload.get(key)).strip() == ""]
    if missing:
        raise ValueError("Missing required inputs for this feature mode (no values were inferred): " + ", ".join(missing))
    crop = str(payload["crop"]).strip().lower()
    if crop not in CROPS:
        raise ValueError("crop must be one of: " + ", ".join(sorted(CROPS)))

    row = {"crop": crop}
    for key in feature_columns:
        if key == "crop":
            continue
        value = payload.get(key)
        if value is None and key in OPTIONAL_MODEL_INPUTS:
            row[key] = np.nan
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Input {key!r} must be a finite number") from None
        if not np.isfinite(value):
            raise ValueError(f"Input {key!r} must be a finite number")
        if key == "storage_age_days" and value < 0:
            raise ValueError("storage_age_days must be non-negative")
        if key in UNIT_RANGES:
            low, high, unit = UNIT_RANGES[key]
            if not low <= value <= high:
                raise ValueError(f"Input {key!r} is outside the basic {unit} range [{low}, {high}]")
        if key.startswith("MQ") and value < 0:
            raise ValueError(f"Input {key!r} must be non-negative on the response-index scale")
        row[key] = value

    probabilities = model.predict_proba(pd.DataFrame([{key: row[key] for key in feature_columns}]))[0]
    labels = ["acceptable", "warning", "spoiled"]
    return {
        "label": "SIMULATION ONLY",
        "feature_mode": feature_mode,
        "crop": crop,
        "storage_age_days": row["storage_age_days"],
        "predicted_status": labels[int(np.argmax(probabilities))],
        "status_probabilities": {labels[i]: float(probabilities[i]) for i in range(len(labels))},
        "next_inspection_risk_available": False,
        "note": ("SIMULATION ONLY. This saved model was trained on simulated readings and labels. "
                 + ("Combined-mode risk needs a positive next-inspection interval." if feature_mode == "combined"
                    else "Single-modality output is a status estimate only; no survival model was trained for this mode.")),
    }


def predict_payload(payload: dict, out_dir="artifacts", models=None) -> dict:
    """Predict one explicit reading; missing sensor/history inputs are never imputed here."""
    out = Path(out_dir)
    models = models or load_prediction_models(out)
    model, hazard = models["status"], models["first_spoiled"]
    transition = models.get("leave_acceptable")
    status_cols = list(model.named_steps["prep"].feature_names_in_)
    required = [c for c in status_cols if c not in OPTIONAL_MODEL_INPUTS] + ["next_inspection_interval_days"]
    missing = [key for key in required if payload.get(key) is None or key not in payload]
    if missing:
        raise ValueError("Missing required current inputs (no values were inferred): " + ", ".join(missing))
    crop = str(payload["crop"]).strip().lower()
    if crop not in CROPS:
        raise ValueError("crop must be one of: " + ", ".join(sorted(CROPS)))

    features = {"crop": crop}
    for key in status_cols:
        if key == "crop":
            continue
        raw = payload.get(key)
        if raw is None and key in OPTIONAL_MODEL_INPUTS:
            features[key] = np.nan
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Input {key!r} must be a finite number") from None
        if not np.isfinite(value):
            raise ValueError(f"Input {key!r} must be a finite number")
        if key == "storage_age_days" and value < 0:
            raise ValueError("Input 'storage_age_days' must be non-negative")
        if key in UNIT_RANGES:
            low, high, unit = UNIT_RANGES[key]
            if not low <= value <= high:
                raise ValueError(f"Input {key!r} is outside the basic {unit} range [{low}, {high}]")
        if key.startswith("MQ") and value < 0:
            raise ValueError(f"Input {key!r} must be non-negative on the response-index scale")
        features[key] = value

    try:
        interval_days = float(payload["next_inspection_interval_days"])
    except (TypeError, ValueError):
        raise ValueError("Input 'next_inspection_interval_days' must be a positive number of days") from None
    if not np.isfinite(interval_days) or interval_days <= 0:
        raise ValueError("Input 'next_inspection_interval_days' must be a positive number of days")

    row = pd.DataFrame([{column: features[column] for column in status_cols}])
    probabilities = model.predict_proba(row)[0]
    labels = ["acceptable", "warning", "spoiled"]
    predicted_status = labels[int(np.argmax(probabilities))]
    hazard_cols = list(hazard.named_steps["prep"].feature_names_in_)
    interval_features = {**features, "interval_days": interval_days}
    absent = [column for column in hazard_cols if column not in interval_features]
    if absent:
        raise ValueError("Saved survival model needs additional inputs: " + ", ".join(absent))
    hazard_row = pd.DataFrame([{column: interval_features[column] for column in hazard_cols}])
    spoiled_risk = float(hazard.predict_proba(hazard_row)[0, 1]) if predicted_status != "spoiled" else None
    transition_risk = (float(transition.predict_proba(hazard_row)[0, 1])
                       if predicted_status == "acceptable" and transition is not None else None)

    warnings = []
    support_file = out / "diagnostics" / "deployment_support.json"
    if support_file.is_file():
        support = json.loads(support_file.read_text(encoding="utf-8"))["crop_ranges"].get(crop, {})
        for key, value in features.items():
            if key == "crop" or pd.isna(value) or key not in support:
                continue
            limits = support[key]
            if value < limits["p01"] or value > limits["p99"]:
                warnings.append(f"{key} is outside the 1st-99th percentile range in the {crop} training simulation")

    threshold = None
    diagnostic_file = out / "diagnostics" / "diagnostics_metrics.json"
    if diagnostic_file.is_file():
        diagnostic = json.loads(diagnostic_file.read_text(encoding="utf-8"))
        threshold = diagnostic.get("early_warning_leaving_acceptable_state", {}).get("training_only_alert_threshold", {}).get("threshold")
    return {
        "label": "SIMULATION ONLY",
        "crop": crop,
        "storage_age_days": features["storage_age_days"],
        "predicted_status": predicted_status,
        "status_probabilities": {labels[i]: float(probabilities[i]) for i in range(len(labels))},
        "next_inspection_interval_days": interval_days,
        "probability_next_check_leaves_acceptable_state": transition_risk,
        "early_warning_alert_threshold": threshold,
        "early_warning_alert": bool(transition_risk >= threshold) if transition_risk is not None and threshold is not None else None,
        "probability_first_spoiled_inspection_by_next_check": spoiled_risk,
        "remaining_days_estimate": None,
        "warnings": warnings,
        "note": "SIMULATION ONLY. These saved models reconstruct simulator assumptions. Probabilities are conditional on the supplied current/history inputs and next-check interval; no continuous remaining-days estimate is produced.",
    }
