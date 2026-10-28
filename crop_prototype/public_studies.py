"""Separate, source-specific exploratory models for public real datasets.

These experiments never feed the simulator-trained five-crop models. In
particular, the tomato task predicts the published storage-scenario label,
not crop quality or time-to-failure.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss, recall_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from xgboost import XGBClassifier


TOMATO_ZIP = Path(".review_data/tomato_sensor_laboratory.zip")
TOMATO_MEMBER = "Sensor and Laboratory Data/Dataframe_ML_complete.csv"
TOMATO_CONTINUOUS_MEMBER = "Sensor and Laboratory Data/Dataframe_continous.csv"
TARGET = "Storage Scenario"
CLASSES = ["Tc", "Trt", "Trtd"]
MQ_FEATURES = ["MQ2", "MQ3_1", "MQ3_10", "MQ4", "MQ5", "MQ6", "MQ8", "MQ9", "MQ135", "MQ136", "MQ137", "MQ138"]
PAIRED_FEATURES = MQ_FEATURES + ["minitial", "mcurrent", "L", "a", "b"]


def _models(n_classes: int):
    return {
        "majority": DummyClassifier(strategy="prior"),
        "random_forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(n_estimators=400, min_samples_leaf=2, class_weight="balanced_subsample",
                                   max_features="sqrt", random_state=19, n_jobs=1),
        ),
        "xgboost": make_pipeline(
            SimpleImputer(strategy="median"),
            XGBClassifier(n_estimators=100, max_depth=2, learning_rate=0.04, min_child_weight=2,
                          subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, reg_alpha=0.1,
                          objective="multi:softprob", num_class=n_classes, eval_metric="mlogloss",
                          random_state=19, n_jobs=1),
        ),
        "svc": make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(),
            SVC(C=1.0, kernel="rbf", probability=True, class_weight="balanced", random_state=19),
        ),
    }


def _multiclass_brier(y_idx: np.ndarray, probabilities: np.ndarray, n_classes: int) -> float:
    truth = np.eye(n_classes)[y_idx]
    return float(np.mean(np.sum((truth - probabilities) ** 2, axis=1)))


def _normalise_probabilities(probabilities: np.ndarray) -> np.ndarray:
    probabilities = np.clip(np.asarray(probabilities, dtype=float), 0.0, None)
    totals = probabilities.sum(axis=1, keepdims=True)
    if not np.isfinite(probabilities).all() or np.any(totals <= 0):
        raise ValueError("A fitted model returned invalid class probabilities")
    return probabilities / totals


def train_public_tomato(zip_path=TOMATO_ZIP, out_dir="artifacts/public_tomato") -> dict:
    """Evaluate source-defined tomato scenario task with whole-day holdout CV."""
    zip_path = Path(zip_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        frame = pd.read_csv(archive.open(TOMATO_MEMBER), sep=";")
        continuous = pd.read_csv(archive.open(TOMATO_CONTINUOUS_MEMBER), sep=";")

    required = {"Sample ID", TARGET, "Storage Day", *PAIRED_FEATURES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Tomato source is missing expected columns: " + ", ".join(missing))
    if frame[list(required)].isna().any().any():
        raise ValueError("Tomato ML table has missing values in target, grouping, or selected predictors; review source before training")
    if sorted(frame[TARGET].unique().tolist()) != sorted(CLASSES):
        raise ValueError("Unexpected source target classes; refusing to silently remap the target")

    # The paper's random-sampling table has one row per sampled tomato. IDs are
    # recycled across scenarios, so Sample ID alone is not a unique key. Each
    # scenario/sample pair occurs once. The continuous table is kept as an
    # external test cohort and is evaluated at its first recorded day only.
    frame["sample_key"] = frame[TARGET].astype(str) + "_" + frame["Sample ID"].astype(str)
    if frame["sample_key"].duplicated().any():
        raise ValueError("Repeated sample/scenario keys found; random-sample CV is not safe")
    y_text = frame[TARGET].astype(str).to_numpy()
    encoder = LabelEncoder().fit(CLASSES)
    y = encoder.transform(y_text)
    class_order = encoder.classes_.tolist()
    groups = frame["Storage Day"].to_numpy()
    splitter = LeaveOneGroupOut()
    n_classes = len(class_order)
    all_rows = []
    predictions_doc = []
    fold_manifest = []
    external_results = []
    external_predictions = []
    continuous["sample_key"] = continuous[TARGET].astype(str) + "_" + continuous["Sample ID"].astype(str)
    continuous_required = {"Sample ID", TARGET, "Storage Day", *PAIRED_FEATURES}
    if continuous_required - set(continuous.columns):
        raise ValueError("Tomato continuous table lacks fields needed for the external test")
    if continuous[list(continuous_required)].isna().any().any():
        raise ValueError("Tomato continuous table has missing target or predictor values")
    if continuous.duplicated(["sample_key", "Storage Day"]).any():
        raise ValueError("Duplicate continuous tomato/sample-time rows found")
    first_day = continuous["Storage Day"].min()
    external = continuous.loc[continuous["Storage Day"].eq(first_day)].copy()
    if len(external) != 9 or external["sample_key"].nunique() != 9:
        raise ValueError("Expected one first-day record for each of nine continuous tomato series")
    external_y = encoder.transform(external[TARGET].astype(str).to_numpy())

    for feature_set, features in (("mq_12", MQ_FEATURES), ("paired_mq_weight_color_17", PAIRED_FEATURES)):
        x = frame[features].astype(float)
        for model_name, estimator in _models(n_classes).items():
            oof = np.full((len(frame), n_classes), np.nan)
            fold_metrics = []
            for fold, (train_idx, test_idx) in enumerate(splitter.split(x, y, groups), start=1):
                model = estimator
                model.fit(x.iloc[train_idx], y[train_idx])
                probs = _normalise_probabilities(model.predict_proba(x.iloc[test_idx]))
                oof[test_idx] = probs
                predicted = np.argmax(probs, axis=1)
                fold_metrics.append({
                    "held_out_day": int(groups[test_idx][0]), "n_test": int(len(test_idx)),
                    "macro_f1": float(f1_score(y[test_idx], predicted, average="macro", zero_division=0)),
                    "accuracy": float(accuracy_score(y[test_idx], predicted)),
                })
            if not np.isfinite(oof).all():
                raise AssertionError("Leave-one-storage-day-out evaluation did not predict every sample exactly once")
            pred = np.argmax(oof, axis=1)
            recalls = recall_score(y, pred, labels=np.arange(n_classes), average=None, zero_division=0)
            metrics = {
                "data_label": "REAL TOMATO STUDY; storage-scenario classification, not spoilage status",
                "feature_set": feature_set,
                "model": model_name,
                "n_rows": int(len(frame)),
                "n_independent_sample_scenario_units": int(frame["sample_key"].nunique()),
                "validation_protocol": "leave-one-storage-day-out; every row from the held-out day is excluded from training",
                "held_out_groups": "Storage Day; all records from one sampling day stay out together",
                "n_folds": int(len(fold_metrics)),
                "features": features,
                "classes": class_order,
                "accuracy_oof": float(accuracy_score(y, pred)),
                "macro_f1_oof": float(f1_score(y, pred, average="macro", zero_division=0)),
                "log_loss_oof": float(log_loss(y, oof, labels=np.arange(n_classes))),
                "multiclass_brier_oof": _multiclass_brier(y, oof, n_classes),
                "per_class_recall_oof": {class_order[i]: float(recalls[i]) for i in range(n_classes)},
                "confusion_matrix_oof_true_rows_predicted_columns": confusion_matrix(y, pred, labels=np.arange(n_classes)).tolist(),
                "folds": fold_metrics,
                "note": "Exploratory source-specific score from 52 samples in one study run. No days-to-spoilage or acceptable/warning/spoiled endpoint is present.",
            }
            all_rows.append(metrics)
            fold_manifest.append({"feature_set": feature_set, "model": model_name, "folds": fold_metrics})
            for i, (_, row) in enumerate(frame.iterrows()):
                predictions_doc.append({
                    "feature_set": feature_set, "model": model_name,
                    "sample_key": row["sample_key"], "storage_day_held_out": int(row["Storage Day"]),
                    "true_storage_scenario": y_text[i],
                    "predicted_storage_scenario": class_order[int(pred[i])],
                    **{f"p_{class_order[j]}": float(oof[i, j]) for j in range(n_classes)},
                })

            # The source study used stratified sample-level folds. Preserve
            # that comparison, but report it beside the stricter unseen-day
            # result because environmental/storage day is a shared condition.
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=19)
            sample_oof = np.full((len(frame), n_classes), np.nan)
            sample_folds = []
            for fold, (train_idx, test_idx) in enumerate(skf.split(x, y), start=1):
                fold_model = estimator
                fold_model.fit(x.iloc[train_idx], y[train_idx])
                fold_probs = _normalise_probabilities(fold_model.predict_proba(x.iloc[test_idx]))
                sample_oof[test_idx] = fold_probs
                sample_pred = np.argmax(fold_probs, axis=1)
                sample_folds.append({
                    "fold": fold, "n_test": int(len(test_idx)),
                    "macro_f1": float(f1_score(y[test_idx], sample_pred, average="macro", zero_division=0)),
                    "accuracy": float(accuracy_score(y[test_idx], sample_pred)),
                })
            sample_pred = np.argmax(sample_oof, axis=1)
            sample_recalls = recall_score(y, sample_pred, labels=np.arange(n_classes), average=None, zero_division=0)
            all_rows.append({
                **{k: v for k, v in metrics.items() if k not in {"held_out_groups", "n_folds", "accuracy_oof", "macro_f1_oof", "log_loss_oof", "multiclass_brier_oof", "per_class_recall_oof", "confusion_matrix_oof_true_rows_predicted_columns", "folds"}},
                "validation_protocol": "5-fold stratified sample-level CV; unique scenario/sample rows; storage days can occur in both train and validation",
                "n_folds": 5,
                "accuracy_oof": float(accuracy_score(y, sample_pred)),
                "macro_f1_oof": float(f1_score(y, sample_pred, average="macro", zero_division=0)),
                "log_loss_oof": float(log_loss(y, sample_oof, labels=np.arange(n_classes))),
                "multiclass_brier_oof": _multiclass_brier(y, sample_oof, n_classes),
                "per_class_recall_oof": {class_order[i]: float(sample_recalls[i]) for i in range(n_classes)},
                "confusion_matrix_oof_true_rows_predicted_columns": confusion_matrix(y, sample_pred, labels=np.arange(n_classes)).tolist(),
                "folds": sample_folds,
                "note": "Sample-level internal CV matches the source study's split style. It is less demanding than holding out entire storage days and is not an independent external test.",
            })
            # Save a full-data estimator only as a reusable demonstration model.
            # Reported metrics above are all out-of-day predictions, not these fits.
            full_model = estimator
            full_model.fit(x, y)
            dump({"model": full_model, "features": features, "class_order": class_order,
                  "target": TARGET, "source": "Zenodo 15469472 / Dataframe_ML_complete.csv",
                  "label": "REAL TOMATO STUDY; scenario classifier only"}, out / f"{feature_set}__{model_name}.joblib")
            ext_probs = _normalise_probabilities(full_model.predict_proba(external[features].astype(float)))
            ext_pred = np.argmax(ext_probs, axis=1)
            ext_recalls = recall_score(external_y, ext_pred, labels=np.arange(n_classes), average=None, zero_division=0)
            external_results.append({
                "feature_set": feature_set, "model": model_name,
                "validation_protocol": "independent continuous-sampling cohort; one day-3 record from each of 9 tomatoes",
                "n_independent_tomatoes": int(external["sample_key"].nunique()), "n_rows": int(len(external)),
                "accuracy": float(accuracy_score(external_y, ext_pred)),
                "macro_f1": float(f1_score(external_y, ext_pred, average="macro", zero_division=0)),
                "log_loss": float(log_loss(external_y, ext_probs, labels=np.arange(n_classes))),
                "multiclass_brier": _multiclass_brier(external_y, ext_probs, n_classes),
                "per_class_recall": {class_order[i]: float(ext_recalls[i]) for i in range(n_classes)},
                "confusion_matrix_true_rows_predicted_columns": confusion_matrix(external_y, ext_pred, labels=np.arange(n_classes)).tolist(),
                "note": "Small within-study external cohort; three tomatoes per class. Do not treat nine tomatoes as 90 independent test samples.",
            })
            for i, (_, row) in enumerate(external.iterrows()):
                external_predictions.append({
                    "feature_set": feature_set, "model": model_name, "sample_key": row["sample_key"],
                    "storage_day": int(row["Storage Day"]), "true_storage_scenario": str(row[TARGET]),
                    "predicted_storage_scenario": class_order[int(ext_pred[i])],
                    **{f"p_{class_order[j]}": float(ext_probs[i, j]) for j in range(n_classes)},
                })

    report = {
        "source": "Zenodo 15469472, Sensor and Laboratory Data/Dataframe_ML_complete.csv",
        "source_record": "https://zenodo.org/records/15469472",
        "rows": int(len(frame)),
        "columns": frame.columns.drop("sample_key").tolist(),
        "target_counts": frame[TARGET].value_counts().reindex(CLASSES).to_dict(),
        "samples_by_day_and_scenario": pd.crosstab(frame["Storage Day"], frame[TARGET]).reindex(columns=CLASSES).to_dict("index"),
        "continuous_table_handling": "Used only as an independent test cohort: one earliest day-3 row per tomato (9 tomatoes total). Remaining repeated measurements were excluded from headline metrics to avoid counting repeated rows as independent test samples. This tests storage scenario only.",
        "independent_continuous_test": external_results,
        "modes": all_rows,
        "fixed_model_configurations": {
            "majority": "DummyClassifier(strategy='prior')",
            "random_forest": "400 trees; min_samples_leaf=2; class_weight=balanced_subsample; max_features=sqrt; random_state=19; n_jobs=1",
            "xgboost": "100 trees; max_depth=2; learning_rate=0.04; min_child_weight=2; subsample=0.8; colsample_bytree=0.8; reg_lambda=5; reg_alpha=0.1; random_state=19",
            "svc": "RBF; C=1; class_weight=balanced; probability=True; standard scaling inside each fit; random_state=19",
        },
        "model_selection_warning": "Do not select a deployment winner from these same 52 observations. Use the result only as an exploratory tomato scenario study; collect an independent tomato cohort for final selection.",
    }
    (out / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(predictions_doc).to_csv(out / "oof_predictions.csv", index=False)
    pd.DataFrame(external_predictions).to_csv(out / "continuous_external_test_predictions.csv", index=False)
    demo = frame.iloc[0]
    example_result = next(p for p in predictions_doc
                          if p["feature_set"] == "paired_mq_weight_color_17" and p["model"] == "xgboost"
                          and p["sample_key"] == demo["sample_key"])
    example = {
        "data_label": "REAL TOMATO STUDY ROW; held out by storage day",
        "task": "Storage-scenario classification only; not acceptable/warning/spoiled and not days-to-failure",
        "input_features": {key: float(demo[key]) for key in PAIRED_FEATURES},
        "held_out_storage_day_for_audit_only": int(demo["Storage Day"]),
        "true_storage_scenario": str(demo[TARGET]),
        "predicted_storage_scenario": example_result["predicted_storage_scenario"],
        "probabilities": {key: example_result[f"p_{key}"] for key in class_order},
        "validation": "out-of-fold XGBoost prediction from the leave-one-storage-day-out protocol",
    }
    (out / "heldout_tomato_example.json").write_text(json.dumps(example, indent=2), encoding="utf-8")
    external_demo_row = external.loc[external["sample_key"].eq("Tc_1")].iloc[0]
    external_demo_result = next(p for p in external_predictions
                                if p["feature_set"] == "paired_mq_weight_color_17" and p["model"] == "xgboost"
                                and p["sample_key"] == external_demo_row["sample_key"])
    external_demo = {
        "data_label": "REAL TOMATO STUDY; continuous cohort held out from random-sampling training data",
        "task": "Storage-scenario classification only; not acceptable/warning/spoiled and not days-to-failure",
        "input_features": {key: float(external_demo_row[key]) for key in PAIRED_FEATURES},
        "storage_day": int(external_demo_row["Storage Day"]),
        "true_storage_scenario": str(external_demo_row[TARGET]),
        "predicted_storage_scenario": external_demo_result["predicted_storage_scenario"],
        "probabilities": {key: external_demo_result[f"p_{key}"] for key in class_order},
        "validation": "full-data estimator trained only on 52 random-sampling tomatoes; tested on this separate tracked tomato at day 3",
    }
    (out / "continuous_external_example.json").write_text(json.dumps(external_demo, indent=2), encoding="utf-8")
    return report


def predict_public_tomato(payload: dict, model_name="mq_12__svc", model_dir="artifacts/public_tomato") -> dict:
    """Load a saved tomato model and predict its source-defined scenario class."""
    model_path = Path(model_dir) / f"{model_name}.joblib"
    if not model_path.is_file():
        raise FileNotFoundError(f"Saved tomato model not found: {model_path}. Run the public-tomato command first.")
    bundle = load(model_path)
    features = bundle["features"]
    forbidden = {"Storage Scenario", "Storage Day", "Sample ID", "sample_key", "sim_lot_id", "sim_trajectory_id"}
    supplied_forbidden = forbidden.intersection(payload)
    if supplied_forbidden:
        raise ValueError("Do not pass target, day, sample ID, or lot ID as predictor inputs: " + ", ".join(sorted(supplied_forbidden)))
    missing = [feature for feature in features if feature not in payload or payload[feature] is None]
    if missing:
        raise ValueError("Missing required real-tomato model inputs: " + ", ".join(missing))
    row = {}
    for feature in features:
        try:
            value = float(payload[feature])
        except (TypeError, ValueError):
            raise ValueError(f"Input {feature!r} must be a finite number") from None
        if not np.isfinite(value):
            raise ValueError(f"Input {feature!r} must be a finite number")
        row[feature] = value
    probs = _normalise_probabilities(bundle["model"].predict_proba(pd.DataFrame([row], columns=features)))[0]
    classes = bundle["class_order"]
    return {
        "data_label": "REAL TOMATO STUDY; exploratory scenario classifier",
        "target": bundle["target"],
        "predicted_storage_scenario": classes[int(np.argmax(probs))],
        "scenario_probabilities": {classes[i]: float(probs[i]) for i in range(len(classes))},
        "model_name": model_name,
        "note": "This output identifies the study's storage scenario (Tc, Trt, or Trtd). It is not an acceptable/warning/spoiled prediction or remaining-life estimate.",
    }

