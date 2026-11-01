"""Source-informed, explicitly synthetic three-state crop demonstration.

This generator does NOT create measured crop samples or validated spoilage
labels. Public tomato/banana MQ recordings only anchor response scale and
between-session variation. Potato MQ values are generated independently.
Environment, longitudinal trajectories, latent deterioration, and labels are
simulated. All evaluation splits hold out whole simulated sample trajectories.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, brier_score_loss, classification_report,
                             confusion_matrix, f1_score, log_loss, recall_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

try:
    from xgboost import XGBClassifier
except ImportError:  # pragma: no cover - environment-specific diagnostic
    XGBClassifier = None

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dataset_edition_2"
OUT_ROOT = ROOT / "artifacts" / "edition2_simulation_v3"
SEED = 20261102
N_LOTS_PER_CROP = 100
CLASSES = ["acceptable", "warning", "high_risk"]
MQ = ["MQ2", "MQ3", "MQ4", "MQ5", "MQ6", "MQ7", "MQ8", "MQ9", "MQ135"]
MQ_FEATURES = [f"{name}_response_SIM" for name in MQ]
ENV_FEATURES = ["storage_age_days_SIM", "temperature_C_SIM", "relative_humidity_pct_SIM"]
FEATURES = {"environment_only": ENV_FEATURES, "mq_only": MQ_FEATURES,
            "combined": ENV_FEATURES + MQ_FEATURES}

# Published postharvest recommendations inform scenario centers only; these
# are not spoilage thresholds. Crop stage/use assumptions are fixed here.
PROFILES = {
    "tomato": {"temp": 13.75, "rh": 92.5, "days": 14, "step": 2,
               "stage": "mature_green_assumption", "source": "UC Davis tomato produce facts"},
    "potato": {"temp": 7.0, "rh": 96.5, "days": 56, "step": 8,
               "stage": "table_potato_assumption", "source": "UC Davis potato produce facts"},
    "banana": {"temp": 13.5, "rh": 92.5, "days": 21, "step": 3,
               "stage": "mature_green_assumption", "source": "UC Davis banana produce facts"},
}
SCENARIOS = {
    "near_recommended": (0.0, 0.0),
    "warm_excursion": (5.0, -2.0),
    "cold_excursion": (-4.0, 1.0),
    "low_humidity": (1.0, -14.0),
    "high_humidity": (1.0, 5.0),
}


def _source_session_medians(crop: str) -> tuple[np.ndarray | None, list[str]]:
    folder = DATA_ROOT / crop / "original" / f"zenodo_exact_nine_mq_{crop}_recordings" / "AllSmaples-Report"
    vectors, names = [], []
    if not folder.is_dir():
        return None, names
    for path in sorted(folder.glob("*.csv")):
        frame = pd.read_csv(path)
        if not set(MQ).issubset(frame.columns):
            continue
        vals = frame[MQ].apply(pd.to_numeric, errors="coerce").dropna()
        if len(vals):
            vectors.append(vals.median(axis=0).to_numpy(float))
            names.append(path.stem)
    return (np.asarray(vectors) if vectors else None), names


def _response_anchor(crop: str) -> tuple[np.ndarray, np.ndarray, str, list[str]]:
    sessions, names = _source_session_medians(crop)
    if sessions is not None and len(sessions):
        return sessions.mean(axis=0), np.maximum(sessions.std(axis=0, ddof=0), sessions.mean(axis=0) * .04), \
            "source_session_medians_plus_synthetic_perturbation", names
    # Potato has no potato MQ file in the audited archive. Use only a generic
    # scale prior between available produce recordings; it is not potato data.
    tomato, tnames = _source_session_medians("tomato")
    banana, bnames = _source_session_medians("banana")
    if tomato is None or banana is None:
        # Fallback stays explicit and is not represented as hardware data.
        center = np.array([75, 260, 95, 90, 95, 65, 230, 85, 950], dtype=float)
        spread = np.maximum(center * .15, 5)
        return center, spread, "generic_simulated_response_prior_no_potato_measurement", []
    pool = np.vstack([tomato, banana])
    center = np.median(pool, axis=0)
    spread = np.maximum(np.std(pool, axis=0), center * .08)
    return center, spread, "generic_tomato_banana_scale_prior_not_potato_measurement", tnames + bnames


def _make_crop(crop: str, profile: dict, rng: np.random.Generator) -> pd.DataFrame:
    anchor, spread, mq_basis, session_names = _response_anchor(crop)
    rows = []
    days = np.arange(0, profile["days"] + 1, profile["step"], dtype=float)
    sensitivity = rng.normal([.08, .12, .05, .08, .09, .04, .1, .07, .14],
                             [.05, .07, .04, .05, .06, .04, .06, .05, .08])
    for i in range(N_LOTS_PER_CROP):
        sample_id = f"{crop.upper()}-V3-SIM-{i+1:04d}"
        scenario = list(SCENARIOS)[int(rng.integers(0, len(SCENARIOS)))]
        temp_shift, rh_shift = SCENARIOS[scenario]
        temp_base = profile["temp"] + temp_shift + rng.normal(0, 1.1)
        rh_base = profile["rh"] + rh_shift + rng.normal(0, 2.3)
        susceptibility = rng.normal(0.0, .10)
        initial = rng.beta(2.2, 7.0) * .34
        # Draw from measured recording-level medians (five sessions only),
        # never from raw seconds as if they were independent samples.
        session_jitter = rng.normal(0, spread * .25)
        base_mq = np.maximum(0, anchor + session_jitter + rng.normal(0, spread * .22))
        temp_prev, rh_prev = temp_base, rh_base
        cumulative_stress = 0.0
        for age in days:
            temp = .72 * temp_prev + .28 * temp_base + rng.normal(0, .65)
            rh = .72 * rh_prev + .28 * rh_base + rng.normal(0, 1.4)
            rh = float(np.clip(rh, 45, 99))
            temp_prev, rh_prev = temp, rh
            temp_stress = max(0, abs(temp - profile["temp"]) - 2.0) / 8.0
            rh_stress = max(0, abs(rh - profile["rh"]) - 5.0) / 30.0
            instantaneous = min(1.5, temp_stress + rh_stress)
            cumulative_stress += instantaneous / max(1, len(days))
            age_fraction = age / profile["days"] if profile["days"] else 0
            severity = np.clip(initial + .35 * age_fraction + .90 * cumulative_stress
                               + susceptibility * age_fraction + rng.normal(0, .025), 0, 1)
            state = "acceptable" if severity < .32 else ("warning" if severity < .58 else "high_risk")
            # Cross-sensitive response patterns: crop-agnostic stochastic
            # channel effects, not concentrations and not calibrated gas IDs.
            current = base_mq * (1 + sensitivity * severity)
            current += rng.normal(0, np.maximum(spread * .08, anchor * .012), size=len(MQ))
            row = {
                "sim_sample_id": sample_id,
                "sim_observation_id": f"{sample_id}-T{int(age):03d}",
                "crop": crop,
                "crop_stage_SIM": profile["stage"],
                "storage_scenario_SIM": scenario,
                "storage_age_days_SIM": float(age),
                "temperature_C_SIM": round(float(temp), 2),
                "relative_humidity_pct_SIM": round(rh, 2),
                "quality_state_SIM": state,
                "data_origin": "SIMULATED_SOURCE_INFORMED_NOT_MEASURED",
                "label_origin": "SIMULATED_LATENT_STATE_THRESHOLD_NOT_INSPECTION",
                "label_rule_version_SIM": "v3_thresholds_0.38_0.68",
                "mq_source_basis_SIM": mq_basis,
                "environment_profile_reference": profile["source"],
            }
            row.update({f"{name}_response_SIM": round(float(value), 2)
                        for name, value in zip(MQ, np.maximum(current, 0))})
            rows.append(row)
    return pd.DataFrame(rows), session_names


def _model(model_name: str, seed: int):
    if model_name == "random_forest":
        est = RandomForestClassifier(n_estimators=400, min_samples_leaf=3,
                                     max_features="sqrt", class_weight="balanced_subsample",
                                     random_state=seed, n_jobs=-1)
    else:
        if XGBClassifier is None:
            raise RuntimeError("XGBoost is missing from this environment; install requirements.txt")
        est = XGBClassifier(n_estimators=300, max_depth=3, learning_rate=.04,
                            min_child_weight=4, subsample=.85, colsample_bytree=.85,
                            reg_lambda=2.0, objective="multi:softprob", eval_metric="mlogloss",
                            num_class=3, random_state=seed, n_jobs=4)
    return make_pipeline(SimpleImputer(strategy="median"), est)


def generate_and_train() -> dict:
    rng = np.random.default_rng(SEED)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    result = {
        "interpretation": "All generated data, labels, and scores are SIMULATION ONLY; not real crop accuracy.",
        "version": "edition2_simulation_v3", "seed": SEED, "lots_per_crop": N_LOTS_PER_CROP,
        "observations_per_lot": 8, "split": "80/20 by sim_sample_id within crop; all times kept together",
        "label_thresholds_SIM": {"acceptable": "latent severity < 0.32", "warning": "0.32 to < 0.58", "high_risk": ">= 0.58"},
        "models": {}, "crops": {},
    }
    for crop, profile in PROFILES.items():
        frame, session_names = _make_crop(crop, profile, rng)
        out_dir = DATA_ROOT / crop / "simulated_v3"
        out_dir.mkdir(parents=True, exist_ok=True)
        csv = out_dir / f"{crop}_source_informed_3state_SIMULATED.csv"
        frame.to_csv(csv, index=False)
        ids = sorted(frame["sim_sample_id"].unique())
        terminal = frame.sort_values("storage_age_days_SIM").groupby("sim_sample_id").tail(1)
        terminal_state = terminal.set_index("sim_sample_id")["quality_state_SIM"].reindex(ids)
        train_ids, test_ids = train_test_split(ids, test_size=.2, random_state=SEED,
                                               stratify=terminal_state.to_numpy())
        tr = frame.sim_sample_id.isin(train_ids)
        te = frame.sim_sample_id.isin(test_ids)
        assert not set(frame.loc[tr, "sim_sample_id"]) & set(frame.loc[te, "sim_sample_id"])
        assert not frame.duplicated(["sim_sample_id", "storage_age_days_SIM"]).any()
        crop_info = {"rows": len(frame), "lots": len(ids), "train_lots": len(train_ids),
                     "test_lots": len(test_ids), "class_counts": frame.quality_state_SIM.value_counts().to_dict(),
                     "mq_source_files_used_as_session_scale_anchors": session_names,
                     "csv": str(csv.relative_to(ROOT)), "models": {}}
        if crop == "tomato":
            example = frame.loc[te, ["crop"] + FEATURES["combined"]].iloc[0].to_dict()
            example["model"] = "xgboost"
            example["feature_set"] = "combined"
            (ROOT / "examples" / "edition2_v3_prediction_input.json").write_text(
                json.dumps(example, indent=2), encoding="utf-8")
        ytr = frame.loc[tr, "quality_state_SIM"].map({c: j for j, c in enumerate(CLASSES)}).to_numpy()
        yte = frame.loc[te, "quality_state_SIM"].map({c: j for j, c in enumerate(CLASSES)}).to_numpy()
        for feature_set, cols in FEATURES.items():
            Xtr, Xte = frame.loc[tr, cols], frame.loc[te, cols]
            for model_name in ("random_forest", "xgboost"):
                model = _model(model_name, SEED)
                model.fit(Xtr, ytr)
                probs = model.predict_proba(Xte)
                # XGB/RF estimator classes are encoded in integer class order.
                pred = model.predict(Xte).astype(int)
                cm = confusion_matrix(yte, pred, labels=[0, 1, 2]).tolist()
                report = classification_report(yte, pred, labels=[0, 1, 2],
                                               target_names=CLASSES, output_dict=True, zero_division=0)
                key = f"{crop}__{feature_set}__{model_name}"
                metrics = {"macro_f1": float(f1_score(yte, pred, average="macro")),
                           "accuracy": float(accuracy_score(yte, pred)),
                           "spoiled_recall": float(recall_score(yte, pred, labels=[2], average="macro", zero_division=0)),
                           "log_loss": float(log_loss(yte, probs, labels=[0, 1, 2])),
                           "multiclass_brier": float(np.mean(np.sum((probs - np.eye(3)[yte]) ** 2, axis=1))),
                           "class_recall": {c: float(report[c]["recall"]) for c in CLASSES},
                           "confusion_matrix_true_rows_pred_columns": cm,
                           "features": cols, "test_lots": len(test_ids), "test_rows": int(te.sum())}
                model_path = OUT_ROOT / f"{key}.joblib"
                joblib.dump(model, model_path)
                metrics["model"] = str(model_path.relative_to(ROOT))
                result["models"][key] = metrics
                crop_info["models"][f"{feature_set}__{model_name}"] = metrics
        result["crops"][crop] = crop_info
        (OUT_ROOT / f"{crop}_split.json").write_text(json.dumps({"train_sample_ids": sorted(train_ids),
                                                                   "test_sample_ids": sorted(test_ids)}, indent=2), encoding="utf-8")
    (OUT_ROOT / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    metadata = {
        "status": "SIMULATED_ONLY", "purpose": "schema and pipeline demonstration",
        "not_realism_score": "No percentage of closeness to reality is claimed.",
        "environment": "Scenario centers informed by UC Davis crop guidance; generated environmental paths are synthetic.",
        "mq": "Tomato/banana daily-session medians anchor response distributions only; no cross-study row join. Potato has no measured MQ source; its MQ is generic-scale synthetic.",
        "labels": "Acceptable/warning/high_risk thresholds are simulator thresholds on a hidden degradation variable, not measured inspections or validated produce cutoffs.",
        "future_real_data": "Apply a written crop-specific independent inspection rubric to real lots; validate on held-out real lots before any real-accuracy claim.",
    }
    (OUT_ROOT / "assumptions.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return result


def predict_saved(input_path: Path) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    crop = str(payload.get("crop", "")).lower()
    feature_set = str(payload.get("feature_set", "combined"))
    model_name = str(payload.get("model", "xgboost"))
    if crop not in PROFILES:
        raise ValueError(f"crop must be one of: {', '.join(PROFILES)}")
    if feature_set not in FEATURES:
        raise ValueError(f"feature_set must be one of: {', '.join(FEATURES)}")
    if model_name not in {"random_forest", "xgboost"}:
        raise ValueError("model must be random_forest or xgboost")
    missing = [name for name in FEATURES[feature_set] if payload.get(name) is None]
    if missing:
        raise ValueError("Missing required predictor inputs: " + ", ".join(missing))
    model_path = OUT_ROOT / f"{crop}__{feature_set}__{model_name}.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Saved model not found: {model_path}; run this module without --predict first")
    model = joblib.load(model_path)
    x = pd.DataFrame([{key: float(payload[key]) for key in FEATURES[feature_set]}])
    probs = model.predict_proba(x)[0]
    predicted = CLASSES[int(np.argmax(probs))]
    return {"label": "SIMULATION ONLY", "crop": crop, "predicted_state_SIM": predicted,
            "state_probabilities_SIM": {name: float(probs[i]) for i, name in enumerate(CLASSES)},
            "model": model_name, "feature_set": feature_set,
            "note": "Generated labels and learned patterns are simulator assumptions, not inspected crop quality."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train or use the source-informed, SIMULATED three-crop models")
    parser.add_argument("--predict", type=Path, help="load a saved model and score an explicit JSON input")
    args = parser.parse_args()
    if args.predict:
        print(json.dumps(predict_saved(args.predict), indent=2))
    else:
        print(json.dumps(generate_and_train(), indent=2))
