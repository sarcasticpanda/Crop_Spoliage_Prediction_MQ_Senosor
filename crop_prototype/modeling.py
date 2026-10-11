from __future__ import annotations
from pathlib import Path
import json, platform, random
import numpy as np
import pandas as pd
import sklearn, xgboost
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from .data import feature_sets
from .metrics import LABELS, summarize

SEED = 20261012

def grouped_holdout(df: pd.DataFrame, test_size=0.2, seed=SEED):
    # Each starting lot belongs to one crop. Split complete groups within crop
    # strata to keep per-crop test support balanced.
    test_groups = set()
    for crop_index, crop in enumerate(sorted(df.crop.unique())):
        groups = np.array(sorted(df.loc[df.crop == crop, "sim_lot_id"].unique()))
        _, crop_test = train_test_split(groups, test_size=test_size, random_state=seed + crop_index)
        test_groups.update(crop_test.tolist())
    test_mask = df.sim_lot_id.isin(test_groups).to_numpy()
    test_idx = np.flatnonzero(test_mask)
    train_idx = np.flatnonzero(~test_mask)
    train_groups = set(df.iloc[train_idx].sim_lot_id)
    test_groups = set(df.iloc[test_idx].sim_lot_id)
    if train_groups & test_groups:
        raise AssertionError("Starting lots leaked across train/test split")
    return train_idx, test_idx

def _pipeline(cols, model):
    cats = [c for c in cols if c == "crop"]
    nums = [c for c in cols if c not in cats]
    prep = ColumnTransformer([
        ("num", SimpleImputer(strategy="median", add_indicator=True), nums),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), cats),
    ])
    return Pipeline([("prep", prep), ("model", model)])

def _align_proba(model, X):
    p = model.predict_proba(X)
    classes = list(model.named_steps["model"].classes_)
    out = np.zeros((len(X), len(LABELS)))
    for i, label in enumerate(classes):
        name = LABELS[int(label)] if isinstance(label, (int, np.integer)) else label
        out[:, LABELS.index(name)] = p[:, i]
    return out / np.clip(out.sum(axis=1, keepdims=True), 1e-12, None)

def train_status(df: pd.DataFrame, out_dir="artifacts", include_initial=False):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    train_idx, test_idx = grouped_holdout(df)
    train, test = df.iloc[train_idx], df.iloc[test_idx]
    inner_train_rel, inner_val_rel = grouped_holdout(train, test_size=0.2, seed=SEED + 1)
    inner_train, inner_val = train.iloc[inner_train_rel], train.iloc[inner_val_rel]
    if set(inner_train.sim_lot_id) & set(inner_val.sim_lot_id):
        raise AssertionError("Starting lots leaked across internal train/validation split")
    features = feature_sets(df, include_initial=include_initial)
    encode = {label: index for index, label in enumerate(LABELS)}
    ytr, yte = train.status_SIM.map(encode), test.status_SIM.map(encode)
    model_specs = {
        "majority": lambda: DummyClassifier(strategy="prior"),
        "random_forest": lambda: RandomForestClassifier(n_estimators=220, min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=-1, random_state=SEED),
        "xgboost": lambda: XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.06, subsample=0.85, colsample_bytree=0.85, reg_lambda=2, objective="multi:softprob", eval_metric="mlogloss", tree_method="hist", n_jobs=-1, random_state=SEED),
    }
    results, fitted, validation = [], {}, []
    for feat_name, cols in features.items():
        for model_name, factory in model_specs.items():
            selected_estimators = None
            # Grouped validation is wholly inside the outer training partition.
            validation_model = _pipeline(cols, factory())
            y_inner_train = inner_train.status_SIM.map(encode)
            y_inner_val = inner_val.status_SIM.map(encode)
            if model_name == "xgboost":
                # Pipeline.fit does not transform eval_set automatically. Fit the
                # training-fold preprocessor first, then let XGBoost log validation
                # loss during each boosting round.
                x_inner_train = validation_model.named_steps["prep"].fit_transform(inner_train[cols])
                x_inner_val = validation_model.named_steps["prep"].transform(inner_val[cols])
                validation_estimator = validation_model.named_steps["model"]
                validation_estimator.set_params(early_stopping_rounds=30)
                validation_estimator.fit(
                    x_inner_train, y_inner_train,
                    eval_set=[(x_inner_val, y_inner_val)], verbose=25,
                )
                val_pred = validation_estimator.predict(x_inner_val)
                selected_estimators = int(validation_estimator.best_iteration) + 1
            else:
                validation_model.fit(inner_train[cols], y_inner_train)
                val_pred = validation_model.predict(inner_val[cols])
            validation.append({"feature_set": feat_name, "model": model_name,
                               "validation_rows": len(inner_val), "validation_lots": inner_val.sim_lot_id.nunique(),
                               "selected_xgboost_rounds": selected_estimators,
                               "macro_f1": float(__import__("sklearn.metrics", fromlist=["f1_score"]).f1_score(
                                   y_inner_val, val_pred, labels=list(range(len(LABELS))), average="macro", zero_division=0))})
            final_estimator = factory()
            if model_name == "xgboost" and selected_estimators is not None:
                final_estimator.set_params(n_estimators=selected_estimators)
            pipe = _pipeline(cols, final_estimator)
            pipe.fit(train[cols], ytr)
            pred = pipe.predict(test[cols])
            prob = _align_proba(pipe, test[cols])
            result = summarize(yte.map({v:k for k,v in encode.items()}).to_numpy(),
                               np.asarray([LABELS[int(v)] for v in pred]), prob, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
            result.update({"feature_set": feat_name, "model": model_name, "include_initial_inspection": include_initial, "train_rows": len(train), "train_lots": train.sim_lot_id.nunique(), "test_lots": test.sim_lot_id.nunique(), "test_status_counts": test.status_SIM.value_counts().to_dict()})
            results.append(result)
            fitted[f"{feat_name}__{model_name}"] = pipe
    for key, model in fitted.items(): dump(model, Path(out_dir) / f"{key}.joblib")
    split = {"seed": SEED, "train_lots": sorted(train.sim_lot_id.unique()), "test_lots": sorted(test.sim_lot_id.unique()), "train_rows": len(train), "test_rows": len(test),
             "inner_train_lots": sorted(inner_train.sim_lot_id.unique()), "inner_validation_lots": sorted(inner_val.sim_lot_id.unique())}
    payload = {"warning": "SIMULATION ONLY: reconstruction of simulator assumptions, not validated crop accuracy.", "python": platform.python_version(), "pandas": pd.__version__, "sklearn": sklearn.__version__, "xgboost": xgboost.__version__, "seed": SEED, "split": split, "grouped_validation": validation, "results": results}
    Path(out_dir, "status_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame([{k: r[k] for k in ("feature_set", "model", "include_initial_inspection", "macro_f1", "accuracy", "log_loss", "multiclass_brier", "rows", "independent_lots")}
                  for r in results]).to_csv(Path(out_dir, "model_comparison.csv"), index=False)
    return payload, fitted, (train_idx, test_idx)
