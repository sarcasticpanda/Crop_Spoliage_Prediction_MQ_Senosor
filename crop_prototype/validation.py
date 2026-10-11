"""Grouped status validation and fixed-lot holdout evaluation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.base import clone
from sklearn.metrics import f1_score
from xgboost import XGBClassifier

from .data import feature_sets
from .metrics import LABELS, summarize
from .modeling import SEED, _align_proba, _pipeline


def saved_split(df: pd.DataFrame, metrics_path: str | Path = "artifacts/status_metrics.json"):
    """Return row indices for the original, immutable 400/100 lot split."""
    saved = json.loads(Path(metrics_path).read_text(encoding="utf-8"))["split"]
    train_lots, test_lots = set(saved["train_lots"]), set(saved["test_lots"])
    current_lots = set(df.sim_lot_id.unique())
    if train_lots & test_lots or train_lots | test_lots != current_lots:
        raise ValueError("Saved lot split no longer exactly covers the input dataset")
    train_idx = np.flatnonzero(df.sim_lot_id.isin(train_lots).to_numpy())
    test_idx = np.flatnonzero(df.sim_lot_id.isin(test_lots).to_numpy())
    return train_idx, test_idx


def _models():
    return {
        "random_forest": (
            lambda: RandomForestClassifier(n_estimators=180, class_weight="balanced_subsample",
                                           n_jobs=-1, random_state=SEED),
            {"model__max_features": ["sqrt", 0.75], "model__min_samples_leaf": [2]},
        ),
        "xgboost": (
            lambda: XGBClassifier(n_estimators=220, learning_rate=0.06, max_depth=4,
                                  subsample=0.85, colsample_bytree=0.85, reg_lambda=2,
                                  objective="multi:softprob", eval_metric="mlogloss",
                                  tree_method="hist", n_jobs=-1, random_state=SEED),
            {"model__max_depth": [4, 6], "model__min_child_weight": [1]},
        ),
    }


def _bootstrap_lot_ci(y, p, crops, lots, replicates=1000, seed=SEED + 77):
    """Paired cluster bootstrap: resample whole starting lots and all their rows."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y)
    p = np.asarray(p)
    crops = np.asarray(crops)
    lots = np.asarray(lots)
    unique_lots = np.unique(lots)
    row_indices = {lot: np.flatnonzero(lots == lot) for lot in unique_lots}
    scores = np.empty(replicates)
    for b in range(replicates):
        sampled = rng.choice(unique_lots, size=len(unique_lots), replace=True)
        idx = np.concatenate([row_indices[lot] for lot in sampled])
        scores[b] = f1_score(y[idx], np.asarray(LABELS)[np.argmax(p[idx], axis=1)], labels=LABELS,
                             average="macro", zero_division=0)
    return np.quantile(scores, [0.025, 0.975]).tolist()


def _metric_values(y, p):
    y = np.asarray(y)
    y_index = np.asarray([LABELS.index(v) for v in y], dtype=int)
    pred_index = np.argmax(p, axis=1)
    confusion = np.bincount(len(LABELS) * y_index + pred_index, minlength=len(LABELS) ** 2).reshape(len(LABELS), len(LABELS))
    tp = np.diag(confusion).astype(float)
    denom = confusion.sum(axis=1) + confusion.sum(axis=0)
    class_f1 = np.divide(2 * tp, denom, out=np.zeros_like(tp), where=denom > 0)
    brier = np.mean(np.sum((p - np.eye(len(LABELS))[y_index]) ** 2, axis=1))
    logloss = -np.log(np.clip(p[np.arange(len(y_index)), y_index], 1e-15, 1.0)).mean()
    spoiled_recall = tp[LABELS.index("spoiled")] / max(confusion.sum(axis=1)[LABELS.index("spoiled")], 1)
    return {"macro_f1": float(class_f1.mean()), "spoiled_recall": float(spoiled_recall),
            "log_loss": float(logloss), "multiclass_brier": float(brier)}


def bootstrap_saved_holdout(df: pd.DataFrame, out_dir="artifacts", replicates=500):
    """Add whole-lot bootstrap CIs to the already-trained fixed-holdout metrics."""
    out = Path(out_dir)
    report_path = out / "advanced_status_metrics.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _, test_idx = saved_split(df)
    test = df.iloc[test_idx]
    feature_cols = feature_sets(df)
    configurations = {"environment_only__random_forest": ("test_feature_families", feature_cols["environment_only"]),
                      "environment_only__xgboost": ("test_feature_families", feature_cols["environment_only"]),
                      "mq_only__random_forest": ("test_feature_families", feature_cols["mq_only"]),
                      "mq_only__xgboost": ("test_feature_families", feature_cols["mq_only"]),
                      "combined__random_forest": ("combined", feature_cols["combined"]),
                      "combined__xgboost": ("combined", feature_cols["combined"])}
    predictions = {}
    for key, (section, cols) in configurations.items():
        family, model_name = key.split("__")
        model = load(out / f"{key}.joblib")
        prob = _align_proba(model, test[cols])
        predictions[key] = prob
        result = (report[section][model_name] if section == "combined" else report[section][key])
        draws = {metric: [] for metric in ("macro_f1", "spoiled_recall", "log_loss", "multiclass_brier")}
        rng = np.random.default_rng(SEED + 900 + len(predictions))
        lot_rows = {lot: np.flatnonzero(test.sim_lot_id.to_numpy() == lot) for lot in test.sim_lot_id.unique()}
        unique_lots = np.asarray(list(lot_rows))
        y = test.status_SIM.to_numpy()
        for _ in range(replicates):
            sample = rng.choice(unique_lots, size=len(unique_lots), replace=True)
            idx = np.concatenate([lot_rows[lot] for lot in sample])
            values = _metric_values(y[idx], prob[idx])
            for metric, value in values.items():
                draws[metric].append(value)
        result["test_cluster_bootstrap_95_ci"] = {metric: np.quantile(vals, [0.025, 0.975]).tolist()
                                                   for metric, vals in draws.items()}

    # Paired delta intervals use the same lot resample for each model in a draw.
    metrics = ("macro_f1", "spoiled_recall", "log_loss", "multiclass_brier")
    delta = {metric: [] for metric in metrics}
    rng = np.random.default_rng(SEED + 901)
    lots = test.sim_lot_id.to_numpy()
    lot_rows = {lot: np.flatnonzero(lots == lot) for lot in np.unique(lots)}
    unique_lots = np.asarray(list(lot_rows))
    y = test.status_SIM.to_numpy()
    for _ in range(replicates):
        sample = rng.choice(unique_lots, size=len(unique_lots), replace=True)
        idx = np.concatenate([lot_rows[lot] for lot in sample])
        rf = _metric_values(y[idx], predictions["combined__random_forest"][idx])
        xgb = _metric_values(y[idx], predictions["combined__xgboost"][idx])
        for metric in metrics:
            delta[metric].append(xgb[metric] - rf[metric])
    report["paired_test_xgboost_minus_random_forest_ci95"] = {
        metric: np.quantile(values, [0.025, 0.975]).tolist() for metric, values in delta.items()}
    report["bootstrap"] = {"unit": "sim_lot_id", "replicates": replicates,
                           "resampling": "Each draw samples 100 starting lots with replacement and includes every held-out path and reading for each sampled lot.",
                           "paired": True}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def compare_initial_inspection(df: pd.DataFrame, out_dir="artifacts_with_initial"):
    """Fit matched combined models with the deployable initial inspection field."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base_dir = Path("artifacts")
    train_idx, test_idx = saved_split(df)
    train, test = df.iloc[train_idx], df.iloc[test_idx]
    cols = feature_sets(df, include_initial=True)["combined"]
    y_train = train.status_SIM.map({label: i for i, label in enumerate(LABELS)}).to_numpy()
    results = {}
    for name in ("random_forest", "xgboost"):
        base = load(base_dir / f"combined__{name}.joblib")
        model = _pipeline(cols, clone(base.named_steps["model"]))
        model.fit(train[cols], y_train)
        p = _align_proba(model, test[cols])
        pred = np.asarray(LABELS)[np.argmax(p, axis=1)]
        results[name] = summarize(test.status_SIM.to_numpy(), pred, p, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
        results[name]["initial_inspection_included"] = True
        results[name]["hyperparameters"] = model.named_steps["model"].get_params()
        results[name]["test_macro_f1_cluster_bootstrap_95_ci"] = _bootstrap_lot_ci(
            test.status_SIM.to_numpy(), p, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
        dump(model, out / f"combined__{name}.joblib")
    payload = {"warning": "SIMULATION ONLY: initial defect values are simulator-generated inputs.",
        "comparison": "Same saved 400/100 lots and selected model hyperparameters as the no-initial combined models; refit on training lots with initial inspection added. Hyperparameters were selected by grouped CV without this field.",
        "train_lots": train.sim_lot_id.nunique(), "test_lots": test.sim_lot_id.nunique(), "results": results}
    (out / "initial_inspection_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def evaluate_and_tune(df: pd.DataFrame, out_dir="artifacts", metrics_path="artifacts/status_metrics.json"):
    """Tune combined models only on 400 saved training lots, then test once."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_idx, test_idx = saved_split(df, metrics_path)
    train, test = df.iloc[train_idx].copy(), df.iloc[test_idx].copy()
    expected_test = set(json.loads(Path(metrics_path).read_text(encoding="utf-8"))["split"]["test_lots"])
    if set(test.sim_lot_id.unique()) != expected_test:
        raise AssertionError("The fixed held-out starting-lot set changed")

    cols = feature_sets(df)["combined"]
    label_to_int = {label: i for i, label in enumerate(LABELS)}
    y_train = train.status_SIM.map(label_to_int).to_numpy()
    y_test = test.status_SIM.to_numpy()
    groups = train.sim_lot_id.to_numpy()
    cv = GroupKFold(n_splits=5)
    outcomes, fitted, holdout = {}, {}, {}
    for name, (factory, grid) in _models().items():
        search = GridSearchCV(_pipeline(cols, factory()), grid, scoring="f1_macro", cv=cv,
                              n_jobs=1, refit=True, return_train_score=False, verbose=1)
        search.fit(train[cols], y_train, groups=groups)
        # All preprocessing lives inside the estimator pipeline, so each CV fold
        # fits its imputers/encoders only on that fold's four training groups.
        best = search.best_estimator_
        probabilities = _align_proba(best, test[cols])
        predictions = np.asarray(LABELS)[np.argmax(probabilities, axis=1)]
        result = summarize(y_test, predictions, probabilities, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
        fold_scores = [float(search.cv_results_[f"split{i}_test_score"][search.best_index_]) for i in range(5)]
        grid_results = []
        for i, params in enumerate(search.cv_results_["params"]):
            grid_results.append({"params": params, "fold_macro_f1": [float(search.cv_results_[f"split{k}_test_score"][i]) for k in range(5)],
                                 "mean_macro_f1": float(search.cv_results_["mean_test_score"][i]),
                                 "std_macro_f1": float(search.cv_results_["std_test_score"][i])})
        result.update({"model": name, "feature_set": "combined", "cv_best_params": search.best_params_,
                       "cv_fold_macro_f1": fold_scores, "cv_macro_f1_mean": float(np.mean(fold_scores)),
                       "cv_macro_f1_std": float(np.std(fold_scores, ddof=1)),
                       "cv_candidates": grid_results, "test_lots": int(test.sim_lot_id.nunique())})
        result["test_macro_f1_cluster_bootstrap_95_ci"] = _bootstrap_lot_ci(
            y_test, probabilities, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
        fitted[name] = best
        holdout[name] = {"probabilities": probabilities, "result": result}
        dump(best, out / f"combined__{name}.joblib")
        outcomes[name] = result

    # Paired difference bootstrap on the same resampled lot IDs/rows.
    y = y_test
    lots = test.sim_lot_id.to_numpy()
    unique_lots = np.unique(lots)
    row_indices = {lot: np.flatnonzero(lots == lot) for lot in unique_lots}
    rng = np.random.default_rng(SEED + 78)
    delta = []
    rf_p = holdout["random_forest"]["probabilities"]
    xgb_p = holdout["xgboost"]["probabilities"]
    for _ in range(1000):
        sampled = rng.choice(unique_lots, size=len(unique_lots), replace=True)
        idx = np.concatenate([row_indices[lot] for lot in sampled])
        rf_f1 = f1_score(y[idx], np.asarray(LABELS)[np.argmax(rf_p[idx], axis=1)], labels=LABELS,
                         average="macro", zero_division=0)
        xgb_f1 = f1_score(y[idx], np.asarray(LABELS)[np.argmax(xgb_p[idx], axis=1)], labels=LABELS,
                          average="macro", zero_division=0)
        delta.append(xgb_f1 - rf_f1)
    paired_delta_ci = np.quantile(delta, [0.025, 0.975]).tolist()

    # Re-score all existing feature-family artifacts on the exact same untouched
    # test lots; this both audits saved metrics and exposes per-crop performance.
    feature_results = {}
    for family in ("environment_only", "mq_only"):
        for name in ("random_forest", "xgboost"):
            path = out / f"{family}__{name}.joblib"
            if not path.exists():
                continue
            model = load(path)
            family_cols = feature_sets(df)[family]
            probabilities = _align_proba(model, test[family_cols])
            predictions = np.asarray(LABELS)[np.argmax(probabilities, axis=1)]
            key = f"{family}__{name}"
            feature_results[key] = summarize(y_test, predictions, probabilities, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
            feature_results[key]["test_macro_f1_cluster_bootstrap_95_ci"] = _bootstrap_lot_ci(
                y_test, probabilities, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
            feature_results[key]["feature_set"] = family
            feature_results[key]["model"] = name

    payload = {
        "warning": "SIMULATION ONLY: reconstruction of simulator assumptions, not validated crop accuracy.",
        "split": {"source": str(metrics_path), "train_lots": int(train.sim_lot_id.nunique()),
                  "test_lots": int(test.sim_lot_id.nunique()), "test_ids_unchanged": True,
                  "train_rows": len(train), "test_rows": len(test)},
        "cv": {"folds": 5, "group": "sim_lot_id", "tuning": "Grid search inside GroupKFold training partition; preprocessing fit inside each pipeline fold.",
               "probability_calibration": "No post-hoc calibration applied; native probabilities scored on independent fixed test lots."},
        "combined": outcomes,
        "paired_test_xgboost_minus_random_forest_macro_f1_ci95": paired_delta_ci,
        "test_feature_families": feature_results,
    }
    (out / "advanced_status_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload

