"""Focused simulator diagnostics using the existing fixed lot split.

These are exploratory stress/ablation results. The held-out simulator lots have
already been used for v1 evaluation, and the corruption sizes are standardized
fractions of training spread rather than measured device tolerances.
"""
from __future__ import annotations

import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import xgboost
from joblib import dump, load
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, precision_score, recall_score
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import BASE_COLUMNS, CURRENT_SENSOR_COLUMNS, DEPLOYMENT_FEATURES, ENV_COLUMNS, MQ_COLUMNS, feature_sets
from .metrics import LABELS, summarize
from .modeling import SEED, _align_proba, _pipeline
from .survival import make_risk_intervals
from .validation import saved_split


def _calibration_summary(y, probabilities, bins=10):
    y = np.asarray(y)
    p = np.asarray(probabilities)
    output = {}
    for j, label in enumerate(LABELS):
        values = p[:, j]
        actual = (y == label).astype(int)
        edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))
        rows = []
        weighted_gap = 0.0
        for i in range(max(0, len(edges) - 1)):
            mask = (values >= edges[i]) & (values <= edges[i + 1] if i == len(edges) - 2 else values < edges[i + 1])
            if mask.any():
                mp, obs = float(values[mask].mean()), float(actual[mask].mean())
                weighted_gap += float(mask.mean()) * abs(mp - obs)
                rows.append({"n": int(mask.sum()), "mean_probability": mp, "observed_fraction": obs})
        output[label] = {"ece": float(weighted_gap), "bins": rows}
    return output


def _binary_calibration(y, p, bins=5):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    result = []
    for i in range(max(0, len(edges) - 1)):
        mask = (p >= edges[i]) & (p <= edges[i + 1] if i == len(edges) - 2 else p < edges[i + 1])
        if mask.any():
            result.append({"n": int(mask.sum()), "mean_predicted": float(p[mask].mean()),
                           "observed_fraction": float(y[mask].mean())})
    return result


def _score_classifier(y, p, crops, lots):
    pred = np.asarray(LABELS)[np.argmax(p, axis=1)]
    result = summarize(np.asarray(y), pred, p, np.asarray(crops), np.asarray(lots))
    result["calibration_by_class"] = _calibration_summary(y, p)
    return result


def _test_lot_scores(model, frame, cols, y):
    p = _align_proba(model, frame[cols])
    return _score_classifier(y, p, frame.crop.to_numpy(), frame.sim_lot_id.to_numpy()), p


def _stress_frame(test, train, cols, shift_fraction, noise_fraction, rng):
    altered = test[cols].copy()
    numeric = [c for c in cols if c not in ("crop", "storage_age_days")]
    scale = train[numeric].std(axis=0, ddof=0).replace(0, 0.0).fillna(0.0)
    # Persistent group offset mimics a device/batch shift; row noise mimics
    # measurement variation. Values remain in simulator units and are not
    # claims about real hardware tolerances.
    lot_ids = test.sim_lot_id.to_numpy()
    unique_lots = pd.unique(lot_ids)
    offsets = {lot: rng.normal(0, shift_fraction, len(numeric)) for lot in unique_lots}
    row_noise = rng.normal(0, noise_fraction, size=(len(test), len(numeric)))
    group_noise = np.vstack([offsets[lot] for lot in lot_ids])
    altered[numeric] = altered[numeric].astype(float).to_numpy() + (group_noise + row_noise) * scale.to_numpy()
    return altered


def _hazard_pipeline_for_features(model, cols):
    categorical = [c for c in cols if c == "crop"]
    numeric = [c for c in cols if c not in categorical]
    prep = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler())]), numeric),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                          ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ])
    return Pipeline([("prep", prep), ("model", model)])


def run_diagnostics(df: pd.DataFrame, out_dir="artifacts", noise_seed=SEED + 333):
    out = Path(out_dir)
    diag_dir = out / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    train_idx, test_idx = saved_split(df)
    train, test = df.iloc[train_idx].copy(), df.iloc[test_idx].copy()
    if set(train.sim_lot_id) & set(test.sim_lot_id):
        raise AssertionError("Starting lots overlap in diagnostic split")
    train_lots = set(train.sim_lot_id)
    test_lots = set(test.sim_lot_id)
    y_test = test.status_SIM.to_numpy()
    families = feature_sets(df)

    # Check exact reproduction of the saved full combined estimators, then score
    # every saved feature family on the same held-out rows.
    classifier_results = {}
    loaded_models = {}
    for family in ("environment_only", "mq_only", "combined"):
        cols = families[family]
        for model_name in ("random_forest", "xgboost"):
            model = load(out / f"{family}__{model_name}.joblib")
            loaded_models[(family, model_name)] = model
            score, prob = _test_lot_scores(model, test, cols, y_test)
            classifier_results[f"{family}__{model_name}"] = score

    # Class-specific missed spoiled readings and the number of affected paths
    # and starting lots. This is about current status, not future risk.
    xgb_cols = families["combined"]
    xgb_p = _align_proba(loaded_models[("combined", "xgboost")], test[xgb_cols])
    xgb_pred = np.asarray(LABELS)[np.argmax(xgb_p, axis=1)]
    missed_mask = (test.status_SIM.to_numpy() == "spoiled") & (xgb_pred != "spoiled")
    missed = {}
    for crop in sorted(test.crop.unique()):
        cmask = missed_mask & (test.crop.to_numpy() == crop)
        missed[crop] = {"missed_spoiled_readings": int(cmask.sum()),
                        "affected_paths": int(test.loc[cmask, "sim_trajectory_id"].nunique()),
                        "affected_starting_lots": int(test.loc[cmask, "sim_lot_id"].nunique()),
                        "total_spoiled_readings": int(((test.crop == crop) & (test.status_SIM == "spoiled")).sum())}

    # Early warning: only inspect intervals whose current state is still
    # acceptable. Predict whether the next inspection is the first spoiled one.
    risk = make_risk_intervals(df)
    risk_test = risk[risk.sim_lot_id.isin(test_lots)].copy()
    status_lookup = df.set_index(["sim_trajectory_id", "storage_age_days"]).status_SIM
    keys = pd.MultiIndex.from_frame(risk_test[["sim_trajectory_id", "storage_age_days"]])
    risk_test["current_status"] = status_lookup.reindex(keys).to_numpy()
    early = risk_test[risk_test.current_status == "acceptable"].copy()
    hazard = load(out / "discrete_hazard_xgboost.joblib")
    full_hazard = hazard
    hazard_cols = [*families["combined"], "interval_days"]
    phat = hazard.predict_proba(early[hazard_cols])[:, 1]
    target = early.event_next.to_numpy(dtype=int)
    first_spoiled_from_acceptable = {"definition": "Current status is acceptable; target is first spoiled check at the next inspection.",
        "n_intervals": len(early), "independent_lots": int(early.sim_lot_id.nunique()),
        "event_intervals": int(target.sum()), "event_rate": float(target.mean()),
        "brier": float(brier_score_loss(target, phat)),
        "log_loss": float(log_loss(target, np.column_stack([1 - phat, phat]), labels=[0, 1])),
        "average_precision": float(average_precision_score(target, phat)) if target.sum() else None,
        "threshold_0_5_precision": float(precision_score(target, phat >= .5, zero_division=0)),
        "threshold_0_5_recall": float(recall_score(target, phat >= .5, zero_division=0)),
        "threshold_0_5_missed_event_intervals": int(((target == 1) & (phat < .5)).sum()),
        "calibration_bins": _binary_calibration(target, phat), "per_crop": {}}
    for crop in sorted(early.crop.unique()):
        mask = early.crop.to_numpy() == crop
        yc, pc = target[mask], phat[mask]
        first_spoiled_from_acceptable["per_crop"][crop] = {"intervals": int(mask.sum()), "events": int(yc.sum()),
            "event_rate": float(yc.mean()), "brier": float(brier_score_loss(yc, pc)),
            "mean_predicted": float(pc.mean()), "threshold_0_5_recall": float(recall_score(yc, pc >= .5, zero_division=0)),
            "missed_event_intervals": int(((yc == 1) & (pc < .5)).sum())}

    # In the simulator, paths pass through warning before spoiled, so no
    # acceptable-at-start interval jumps directly to the first spoiled check.
    # Evaluate the actual early-warning question separately: next status leaves
    # acceptable (warning or spoiled) versus remains acceptable.
    trajectory_order = df.sort_values(["sim_trajectory_id", "storage_age_days"], kind="stable").copy()
    trajectory_groups = trajectory_order.groupby("sim_trajectory_id", sort=False)
    trajectory_order["next_status"] = trajectory_groups.status_SIM.shift(-1)
    trajectory_order["interval_days"] = trajectory_groups.storage_age_days.shift(-1) - trajectory_order.storage_age_days
    transition = trajectory_order[(trajectory_order.status_SIM == "acceptable") & trajectory_order.next_status.notna()].copy()
    transition["leave_acceptable_next"] = (transition.next_status != "acceptable").astype(int)
    transition_train = transition[transition.sim_lot_id.isin(train_lots)]
    transition_test = transition[transition.sim_lot_id.isin(test_lots)]
    # The primary early-warning model follows the same full combined feature
    # contract as the v1 status and hazard pipelines. A smaller current-only
    # model is evaluated separately below as an input-availability ablation.
    transition_cols = families["combined"] + ["interval_days"]
    transition_y = transition_train.leave_acceptable_next.to_numpy(dtype=int)
    transition_test_y = transition_test.leave_acceptable_next.to_numpy(dtype=int)
    transition_models = {
        "crop_specific_baseline": None,
        "discrete_logistic": _hazard_pipeline_for_features(LogisticRegression(max_iter=1500), transition_cols),
        "discrete_xgboost": _hazard_pipeline_for_features(clone(full_hazard.named_steps["model"]), transition_cols),
    }
    leave_acceptable = {"definition": "Use only rows currently labeled acceptable. Event means the next inspection is warning or spoiled.",
        "train_lots": len(set(transition_train.sim_lot_id)), "test_lots": len(set(transition_test.sim_lot_id)),
        "train_intervals": len(transition_train), "train_events": int(transition_y.sum()),
        "test_intervals": len(transition_test), "test_events": int(transition_test_y.sum()),
        "test_event_rate": float(transition_test_y.mean()), "models": {}, "per_crop": {}}
    transition_predictions = {}
    for name, model in transition_models.items():
        if model is None:
            baseline_by_crop = transition_train.groupby("crop").leave_acceptable_next.mean().to_dict()
            pred = transition_test.crop.map(baseline_by_crop).to_numpy(dtype=float)
            model_record = {"kind": "training event fraction by crop"}
        else:
            model.fit(transition_train[transition_cols], transition_y)
            pred = model.predict_proba(transition_test[transition_cols])[:, 1]
            dump(model, diag_dir / f"early_warning_leave_acceptable__{name}.joblib")
            model_record = {"kind": "trained classifier", "hyperparameters": model.named_steps["model"].get_params()}
        transition_predictions[name] = pred
        model_record.update({"brier": float(brier_score_loss(transition_test_y, pred)),
            "log_loss": float(log_loss(transition_test_y, np.column_stack([1 - pred, pred]), labels=[0, 1])),
            "average_precision": float(average_precision_score(transition_test_y, pred)),
            "mean_predicted": float(pred.mean()), "observed_fraction": float(transition_test_y.mean()),
            "threshold_0_5_precision": float(precision_score(transition_test_y, pred >= .5, zero_division=0)),
            "threshold_0_5_recall": float(recall_score(transition_test_y, pred >= .5, zero_division=0)),
            "threshold_0_5_missed_events": int(((transition_test_y == 1) & (pred < .5)).sum()),
            "calibration_bins": _binary_calibration(transition_test_y, pred)})
        leave_acceptable["models"][name] = model_record
        for crop in sorted(transition_test.crop.unique()):
            cmask = transition_test.crop.to_numpy() == crop
            cy, cp = transition_test_y[cmask], pred[cmask]
            leave_acceptable["per_crop"].setdefault(crop, {})[name] = {
                "intervals": int(cmask.sum()), "events": int(cy.sum()),
                "event_rate": float(cy.mean()), "brier": float(brier_score_loss(cy, cp)),
                "mean_predicted": float(cp.mean()),
                "threshold_0_5_recall": float(recall_score(cy, cp >= .5, zero_division=0)),
                "missed_events_at_0_5": int(((cy == 1) & (cp < .5)).sum())}

    # Select an alert threshold using only 5-fold out-of-fold predictions from
    # training lots. The aim is at least 80% event recall; test labels do not set
    # the threshold. This exposes the expected false-alert tradeoff.
    oof_probability = np.full(len(transition_train), np.nan)
    group_cv = GroupKFold(n_splits=5)
    for fold_train, fold_valid in group_cv.split(transition_train, transition_y, groups=transition_train.sim_lot_id):
        fold_model = _hazard_pipeline_for_features(LogisticRegression(max_iter=1500), transition_cols)
        fold_model.fit(transition_train.iloc[fold_train][transition_cols], transition_y[fold_train])
        oof_probability[fold_valid] = fold_model.predict_proba(transition_train.iloc[fold_valid][transition_cols])[:, 1]
    if np.isnan(oof_probability).any():
        raise AssertionError("Grouped out-of-fold early-warning predictions are incomplete")
    threshold_target_recall = 0.80
    eligible = []
    for threshold in np.unique(oof_probability):
        recall = recall_score(transition_y, oof_probability >= threshold, zero_division=0)
        if recall >= threshold_target_recall:
            eligible.append(float(threshold))
    alert_threshold = max(eligible) if eligible else 0.0
    logistic_test_p = transition_predictions["discrete_logistic"]
    alert = logistic_test_p >= alert_threshold
    leave_acceptable["training_only_alert_threshold"] = {
        "selection": "Highest 5-fold grouped out-of-fold logistic threshold with at least 80% recall on training transitions.",
        "target_recall": threshold_target_recall, "threshold": alert_threshold,
        "oof_recall": float(recall_score(transition_y, oof_probability >= alert_threshold, zero_division=0)),
        "test_precision": float(precision_score(transition_test_y, alert, zero_division=0)),
        "test_recall": float(recall_score(transition_test_y, alert, zero_division=0)),
        "test_alert_fraction": float(alert.mean()), "test_missed_events": int(((transition_test_y == 1) & ~alert).sum()),
        "test_false_alerts": int(((transition_test_y == 0) & alert).sum()),
        "threshold_was_selected_without_test_labels": True}

    # Exploratory feature ablations. Hyperparameters are fixed to the selected
    # full-feature models; no selection is performed on the test labels.
    env_without_derived = [c for c in families["combined"] if c not in ("DewPoint(°C)", "HeatIndex(°C)")]
    no_history = [c for c in families["combined"] if not c.startswith("past_")]
    no_aux_env = [c for c in families["combined"] if c not in (
        "Pressure(hPa)", "AQI", "Gas (kOhms)", "Altitude(m)", "DewPoint(°C)", "HeatIndex(°C)")]
    raw_deployable = BASE_COLUMNS + ["Temperature(°C)", "Humidity(%)"] + MQ_COLUMNS
    no_mq2 = [c for c in families["combined"] if c != "MQ2_response_index_SIM"]
    ablation_sets = {"full": families["combined"], "no_derived_dew_heat": env_without_derived,
        "no_history_summaries": no_history, "no_aux_aerosense_fields": no_aux_env,
        "raw_temp_rh_plus_nine_mq": raw_deployable, "current_environment_and_nine_mq": DEPLOYMENT_FEATURES,
        "without_MQ2": no_mq2}
    ablations = {}
    for ablation, cols in ablation_sets.items():
        ablations[ablation] = {}
        for model_name in ("random_forest", "xgboost"):
            if ablation == "full":
                model = loaded_models[("combined", model_name)]
            else:
                model_path = diag_dir / f"ablation_{ablation}__{model_name}.joblib"
                cached = load(model_path) if model_path.exists() else None
                if cached is not None and list(cached.named_steps["prep"].feature_names_in_) == cols:
                    model = cached
                else:
                    model = _pipeline(cols, clone(loaded_models[("combined", model_name)].named_steps["model"]))
                    model.fit(train[cols], train.status_SIM.map({x: i for i, x in enumerate(LABELS)}).to_numpy())
                    dump(model, model_path)
            score, _ = _test_lot_scores(model, test, cols, y_test)
            ablations[ablation][model_name] = {"macro_f1": score["macro_f1"],
                "spoiled_recall": score["per_class"]["spoiled"]["recall"],
                "log_loss": score["log_loss"], "multiclass_brier": score["multiclass_brier"],
                "feature_count": len(cols), "features": cols}

    # Correlations are descriptive and use training rows only.
    numeric = [c for c in families["combined"] if c != "crop"]
    corr = train[numeric].corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    pairs = upper.stack().sort_values(ascending=False).head(15)
    redundancy = [{"feature_a": a, "feature_b": b, "absolute_correlation": float(v)} for (a, b), v in pairs.items()]

    # Standardized test-only sensor perturbations. These are assumptions for a
    # sensitivity check, not estimated physical noise for the MQ hardware.
    stress = {"assumption": "Feature-wise Gaussian perturbations scaled to training standard deviation. A fixed offset is shared by all rows in each starting lot; independent noise is added per row. Labels and split are unchanged. This is a synthetic stress proxy, not a hardware calibration.", "levels": {}}
    rng = np.random.default_rng(noise_seed)
    for label, shift, noise in (("mild_shift_noise", .10, .05), ("stronger_shift_noise", .25, .10)):
        stress["levels"][label] = {}
        altered = _stress_frame(test, train, families["combined"], shift, noise, rng)
        for model_name in ("random_forest", "xgboost"):
            model = loaded_models[("combined", model_name)]
            p = _align_proba(model, altered)
            score = _score_classifier(y_test, p, test.crop.to_numpy(), test.sim_lot_id.to_numpy())
            stress["levels"][label][model_name] = {"macro_f1": score["macro_f1"],
                "spoiled_recall": score["per_class"]["spoiled"]["recall"],
                "log_loss": score["log_loss"], "multiclass_brier": score["multiclass_brier"]}

    # Save a model pair with a simple inference contract: crop, age, the eight
    # current AeroSense fields, and all nine MQ response indices. It needs no
    # hidden simulator fields, initial inspection, or history summaries.
    deployable_status = {}
    label_map = {label: i for i, label in enumerate(LABELS)}
    for model_name in ("random_forest", "xgboost"):
        model = _pipeline(DEPLOYMENT_FEATURES,
                          clone(loaded_models[("combined", model_name)].named_steps["model"]))
        model.fit(train[DEPLOYMENT_FEATURES], train.status_SIM.map(label_map).to_numpy())
        dump(model, diag_dir / f"deployable_status__{model_name}.joblib")
        score, _ = _test_lot_scores(model, test, DEPLOYMENT_FEATURES, y_test)
        deployable_status[model_name] = {"macro_f1": score["macro_f1"],
            "spoiled_recall": score["per_class"]["spoiled"]["recall"],
            "log_loss": score["log_loss"], "multiclass_brier": score["multiclass_brier"],
            "per_crop": score["per_crop"], "features": DEPLOYMENT_FEATURES,
            "source_hyperparameters": loaded_models[("combined", model_name)].named_steps["model"].get_params()}

    hazard_train = risk[risk.sim_lot_id.isin(train_lots)].copy()
    hazard_test = risk[risk.sim_lot_id.isin(test_lots)].copy()
    deployable_hazard_cols = DEPLOYMENT_FEATURES + ["interval_days"]
    deployable_hazard = _hazard_pipeline_for_features(clone(full_hazard.named_steps["model"]), deployable_hazard_cols)
    deployable_hazard.fit(hazard_train[deployable_hazard_cols], hazard_train.event_next.astype(int))
    dump(deployable_hazard, diag_dir / "deployable_discrete_hazard_xgboost.joblib")
    hh = deployable_hazard.predict_proba(hazard_test[deployable_hazard_cols])[:, 1]
    deployable_hazard_report = {"all_test_intervals": {"n": len(hazard_test),
        "events": int(hazard_test.event_next.sum()), "brier": float(brier_score_loss(hazard_test.event_next, hh)),
        "mean_predicted": float(hh.mean()), "observed_fraction": float(hazard_test.event_next.mean())},
        "features": deployable_hazard_cols,
        "note": "Same grouped split and training rows as the primary hazard model, but it uses current sensor fields only plus interval length."}
    hazard_test_keys = pd.MultiIndex.from_frame(hazard_test[["sim_trajectory_id", "storage_age_days"]])
    current_early_mask = status_lookup.reindex(hazard_test_keys).to_numpy() == "acceptable"
    deployable_early = hazard_test.loc[current_early_mask]
    dep_phat = deployable_hazard.predict_proba(deployable_early[deployable_hazard_cols])[:, 1]
    deployable_hazard_report["currently_acceptable_test_intervals"] = {
        "n": len(deployable_early), "events": int(deployable_early.event_next.sum()),
        "brier": float(brier_score_loss(deployable_early.event_next, dep_phat)),
        "mean_predicted": float(dep_phat.mean()), "observed_fraction": float(deployable_early.event_next.mean())}

    # Crop-specific training-support bands use the full primary feature schema.
    # These are not validated hardware limits or hard rejection rules.
    support = {}
    for crop in sorted(train.crop.unique()):
        group = train[train.crop == crop]
        support[crop] = {}
        for column in families["combined"]:
            if column == "crop":
                continue
            if group[column].notna().sum() == 0:
                continue
            lo, hi = group[column].quantile([.01, .99]).astype(float)
            support[crop][column] = {"p01": lo, "p99": hi}
    support_payload = {"provenance": "SIMULATION ONLY; training-lot 1st/99th percentile support bands, not real device limits.",
        "features": families["combined"], "crop_ranges": support}
    (diag_dir / "deployment_support.json").write_text(json.dumps(support_payload, indent=2), encoding="utf-8")

    report = {"provenance": "SIMULATION ONLY; exploratory diagnostics on the existing fixed v1 test lots.",
        "versions": {"python": platform.python_version(), "pandas": pd.__version__,
                     "numpy": np.__version__, "sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
        "split": {"train_lots": len(train_lots), "test_lots": len(test_lots), "train_rows": len(train), "test_rows": len(test),
                  "overlap": len(train_lots & test_lots), "test_ids_unchanged": True},
        "saved_model_reproduction": classifier_results,
        "current_status_missed_spoiled": missed,
        "first_spoiled_from_currently_acceptable": first_spoiled_from_acceptable,
        "early_warning_leaving_acceptable_state": leave_acceptable,
        "feature_ablations_fixed_hyperparameters": {"note": "Fit on the saved training lots and scored on the fixed test lots. These are exploratory comparisons, not a new untouched benchmark; model hyperparameters were held fixed to the full combined selections.", "results": ablations},
        "current_reading_only_ablation_models": {"status": deployable_status, "discrete_xgboost_hazard": deployable_hazard_report,
            "note": "Secondary feature-availability ablation only. The full combined models remain the primary models.",
            "input_contract": "crop, storage age in days, eight current AeroSense fields, nine MQ response indices, and next-inspection interval in days.",
            "support_file": "deployment_support.json"},
        "training_feature_correlations": redundancy,
        "sensor_shift_stress_test": stress}
    (diag_dir / "diagnostics_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
