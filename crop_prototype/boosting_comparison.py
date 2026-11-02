"""Nested, lot-grouped comparison of XGBoost and LightGBM.

All tuning is restricted to each outer training fold. The saved 100-lot
holdout is not read or scored by this experiment.
"""
from __future__ import annotations

import json
import platform
from pathlib import Path

import lightgbm
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.metrics import f1_score, recall_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

from .data import feature_sets
from .metrics import LABELS
from .modeling import SEED, _pipeline
from .validation import saved_split


def _factories():
    common = {
        "n_estimators": 240,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "reg_lambda": 2.0,
    }
    return {
        "xgboost": (
            lambda: XGBClassifier(
                **common, max_depth=4, min_child_weight=1,
                objective="multi:softprob", eval_metric="mlogloss",
                tree_method="hist", n_jobs=4, random_state=SEED,
            ),
            {"model__max_depth": [3, 5]},
        ),
        "lightgbm": (
            lambda: LGBMClassifier(
                n_estimators=common["n_estimators"],
                learning_rate=common["learning_rate"],
                subsample=common["subsample"],
                colsample_bytree=common["colsample_bytree"],
                reg_lambda=common["reg_lambda"],
                objective="multiclass", num_class=len(LABELS),
                max_depth=-1, num_leaves=15, min_child_samples=20,
                verbosity=-1, n_jobs=4, random_state=SEED,
            ),
            {"model__num_leaves": [7, 15, 31]},
        ),
    }


def _scores(y_true, probabilities):
    predicted = np.asarray(LABELS)[np.argmax(probabilities, axis=1)]
    y_index = np.asarray([LABELS.index(label) for label in y_true], dtype=int)
    correct_probability = probabilities[np.arange(len(y_index)), y_index]
    return {
        "macro_f1": float(f1_score(y_true, predicted, labels=LABELS, average="macro", zero_division=0)),
        "spoiled_recall": float(recall_score(y_true, predicted, labels=LABELS, average=None,
                                             zero_division=0)[LABELS.index("spoiled")]),
        "log_loss": float(-np.log(np.clip(correct_probability, 1e-15, 1.0)).mean()),
        "multiclass_brier": float(np.mean(np.sum(
            (probabilities - np.eye(len(LABELS))[y_index]) ** 2, axis=1
        ))),
    }


def compare_boosting(df: pd.DataFrame, out_dir="artifacts") -> dict:
    """Run nested 5x3 GroupKFold using only the original 400 training lots."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_idx, _ = saved_split(df)
    train = df.iloc[train_idx].copy().reset_index(drop=True)
    cols = feature_sets(df)["combined"]
    X = train[cols]
    y = train.status_SIM.to_numpy()
    groups = train.sim_lot_id.to_numpy()
    label_to_int = {label: i for i, label in enumerate(LABELS)}
    y_int = np.asarray([label_to_int[label] for label in y])

    outer = GroupKFold(n_splits=5)
    report = {
        "warning": "SIMULATION ONLY: results measure simulator reconstruction, not validated crop accuracy.",
        "evaluation": "Nested 5-fold grouped CV on the original 400 training lots only; saved 100-lot holdout was not used for fitting, tuning, or scoring.",
        "group": "sim_lot_id",
        "feature_set": "combined",
        "features": cols,
        "train_lots": int(train.sim_lot_id.nunique()),
        "train_rows": int(len(train)),
        "outer_folds": 5,
        "inner_folds": 3,
        "probability_calibration": "No post-hoc calibration; native class probabilities scored out-of-fold.",
        "versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                     "xgboost": xgboost.__version__, "lightgbm": lightgbm.__version__},
        "models": {},
    }

    for model_name, (factory, grid) in _factories().items():
        oof_probabilities = np.zeros((len(train), len(LABELS)), dtype=float)
        fold_results = []
        for fold, (fit_idx, valid_idx) in enumerate(outer.split(X, y_int, groups), start=1):
            fold_train, fold_valid = train.iloc[fit_idx], train.iloc[valid_idx]
            fold_cols = cols
            search = GridSearchCV(
                estimator=_pipeline(fold_cols, factory()),
                param_grid=grid,
                scoring="f1_macro",
                cv=GroupKFold(n_splits=3),
                n_jobs=1,
                refit=True,
                verbose=0,
                return_train_score=False,
            )
            search.fit(
                fold_train[fold_cols],
                y_int[fit_idx],
                groups=fold_train.sim_lot_id.to_numpy(),
            )
            fitted = search.best_estimator_
            raw = fitted.predict_proba(fold_valid[fold_cols])
            estimator_classes = fitted.named_steps["model"].classes_
            probs = np.zeros((len(valid_idx), len(LABELS)), dtype=float)
            for class_col, numeric_class in enumerate(estimator_classes):
                probs[:, int(numeric_class)] = raw[:, class_col]
            oof_probabilities[valid_idx] = probs
            fold_metrics = _scores(y[valid_idx], probs)
            fold_results.append({
                "fold": fold,
                "train_lots": int(fold_train.sim_lot_id.nunique()),
                "validation_lots": int(fold_valid.sim_lot_id.nunique()),
                "train_rows": int(len(fold_train)),
                "validation_rows": int(len(fold_valid)),
                "best_params": search.best_params_,
                "inner_cv_macro_f1": float(search.best_score_),
                "metrics": fold_metrics,
            })
            print(f"{model_name} outer fold {fold}/5: "
                  f"inner macro-F1={search.best_score_:.4f}; "
                  f"outer macro-F1={fold_metrics['macro_f1']:.4f}; "
                  f"spoiled recall={fold_metrics['spoiled_recall']:.4f}; "
                  f"best={search.best_params_}", flush=True)

        pooled = _scores(y, oof_probabilities)
        per_crop = {}
        for crop in sorted(train.crop.unique()):
            mask = train.crop.to_numpy() == crop
            per_crop[crop] = _scores(y[mask], oof_probabilities[mask])
        report["models"][model_name] = {
            "folds": fold_results,
            "pooled_oof_metrics": pooled,
            "fold_macro_f1_mean": float(np.mean([f["metrics"]["macro_f1"] for f in fold_results])),
            "fold_macro_f1_sd": float(np.std([f["metrics"]["macro_f1"] for f in fold_results], ddof=1)),
            "per_crop_oof_metrics": per_crop,
            "selected_parameters_by_outer_fold": [f["best_params"] for f in fold_results],
        }

    report_path = out / "boosting_comparison.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = []
    for model_name, result in report["models"].items():
        row = {"model": model_name, **result["pooled_oof_metrics"],
               "fold_macro_f1_mean": result["fold_macro_f1_mean"],
               "fold_macro_f1_sd": result["fold_macro_f1_sd"],
               "train_lots": report["train_lots"], "train_rows": report["train_rows"]}
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / "boosting_comparison.csv", index=False)
    report["results_file"] = str(report_path)
    return report
