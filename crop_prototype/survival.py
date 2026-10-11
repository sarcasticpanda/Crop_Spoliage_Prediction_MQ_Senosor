from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from xgboost import XGBClassifier
from scipy.special import ndtr
from .data import ENV_COLUMNS, MQ_COLUMNS, BASE_COLUMNS
from .modeling import SEED

SURVIVAL_FEATURES = BASE_COLUMNS + ENV_COLUMNS + MQ_COLUMNS

def predict_survival_path(model, future_path: pd.DataFrame) -> dict:
    """Project period hazards along an explicit future covariate path.

    Each row is a future interval's start state and must contain crop, storage
    age, all current/past device/history fields, all nine MQ channels, and a
    positive interval_days value. This deliberately requires the caller to
    supply future covariates; today's MQ values are never silently copied ahead.
    """
    cols = SURVIVAL_FEATURES + ["interval_days"]
    missing = sorted(set(cols) - set(future_path.columns))
    if missing:
        raise ValueError(f"Future path is missing required inputs: {missing}")
    if future_path.empty or (future_path.interval_days <= 0).any():
        raise ValueError("Future path must contain at least one positive-duration interval")
    hazards = model.predict_proba(future_path[cols])[:, 1]
    durations = future_path.interval_days.to_numpy(dtype=float)
    survival_after = np.cumprod(1.0 - hazards)
    median_index = next((i for i, value in enumerate(survival_after) if value <= 0.5), None)
    median_days = float(durations[:median_index + 1].sum()) if median_index is not None else None
    survival_before = np.r_[1.0, survival_after[:-1]]
    return {
        "periods": [{"period": int(i + 1), "interval_days": float(durations[i]), "hazard": float(hazards[i]),
                     "cumulative_failure_probability": float(1.0 - survival_after[i])} for i in range(len(hazards))],
        "median_time_to_event_days_within_path": median_days,
        "restricted_mean_time_to_event_days_within_path": float(np.sum(survival_before * durations)),
        "note": "Conditional simulator projection along the caller-supplied future path; not a causal intervention estimate or validated crop shelf life.",
    }

def _prep_model(model):
    cats = ["crop"]
    nums = [c for c in SURVIVAL_FEATURES if c not in cats]
    prep = ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]), nums),
        ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), cats),
    ])
    return Pipeline([("prep", prep), ("model", model)])

def make_risk_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """Create one row per observed at-risk inspection interval.

    The failed interval is explicitly retained as [failure_start, failure_end].
    Discrete hazard labels the interval containing the first failed inspection as
    an event; the exact event time remains interval-censored in the source.
    Censored trajectories contribute only observed event-free intervals.
    """
    ordered = df.sort_values(["sim_trajectory_id", "storage_age_days"], kind="stable").copy()
    grouped = ordered.groupby("sim_trajectory_id", sort=False)
    ordered["_next_age"] = grouped.storage_age_days.shift(-1)
    # The model's landmark is the current row; its outcome is the next inspection.
    risk = ordered[ordered._next_age.notna()].copy()
    observed = risk.event_observed_SIM.astype(bool)
    if (observed & (risk.failure_interval_start_days_SIM.isna() | risk.failure_interval_end_days_SIM.isna() |
                    (risk.failure_interval_end_days_SIM <= risk.failure_interval_start_days_SIM))).any():
        raise ValueError("Observed failures require a valid recorded interval")
    risk = risk[(~observed) | (risk.storage_age_days < risk.failure_interval_end_days_SIM)].copy()
    risk["interval_days"] = risk._next_age - risk.storage_age_days
    risk["event_next"] = (risk.event_observed_SIM.astype(bool) &
                          (risk._next_age >= risk.failure_interval_end_days_SIM)).astype(int)
    risk["recorded_failure_lower_days"] = risk.failure_interval_start_days_SIM
    risk["recorded_failure_upper_days"] = risk.failure_interval_end_days_SIM
    risk["right_censored"] = ~risk.event_observed_SIM.astype(bool)
    return risk[SURVIVAL_FEATURES + ["sim_lot_id", "sim_trajectory_id", "interval_days", "event_next",
                                     "recorded_failure_lower_days", "recorded_failure_upper_days", "right_censored"]]


def aft_interval_bounds(trajectories: pd.DataFrame):
    """Build interval-censored event targets and right-censored follow-up bounds."""
    event = trajectories.event_observed_SIM.astype(bool).to_numpy()
    lower = np.where(event, trajectories.failure_interval_start_days_SIM,
                     trajectories.observed_followup_days_SIM).astype(float)
    upper = np.where(event, trajectories.failure_interval_end_days_SIM, np.inf).astype(float)
    if np.any(~np.isfinite(lower)) or np.any(lower < 0) or np.any(upper <= lower):
        raise ValueError("AFT targets require positive follow-up and valid event intervals")
    return lower, upper

def _first_rows(df):
    return (df.sort_values(["sim_trajectory_id", "storage_age_days"], kind="stable")
              .drop_duplicates("sim_trajectory_id").copy())


def _training_only_horizon(event_endpoints, cadence: float) -> tuple[float, float]:
    """Select Q25 of training event endpoints, rounded up to a supported check."""
    values = np.asarray(event_endpoints, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values) or not np.isfinite(cadence) or cadence <= 0:
        raise ValueError("Horizon selection needs finite training event endpoints and positive cadence")
    q25 = float(np.quantile(values, 0.25))
    horizon = float(np.ceil((q25 - 1e-9) / cadence) * cadence)
    return q25, horizon


def _censor_survival_before(times, censored, horizon):
    """Kaplan-Meier estimate of G(h-), where censoring is the event of interest."""
    times = np.asarray(times, dtype=float)
    censored = np.asarray(censored, dtype=bool)
    g = 1.0
    for t in np.sort(np.unique(times[censored & (times < horizon)])):
        at_risk = int(np.sum(times >= t))
        d = int(np.sum(censored & (times == t)))
        if at_risk:
            g *= 1.0 - d / at_risk
    return float(g)


def _ipcw_brier(test_first, event_probability, horizon, train_first):
    """IPCW Brier for event by a fixed calendar horizon with interval labels.

    Ambiguous interval events that straddle the horizon and observations censored
    before the horizon are omitted. In this bundle's first-inspection horizons,
    all test trajectories are observed through the horizon, so censoring weights
    are one; the explicit estimator keeps this valid if support changes later.
    """
    n = len(test_first)
    prob = np.asarray(event_probability, dtype=float)
    y = np.zeros(n, dtype=float)
    weights = np.zeros(n, dtype=float)
    times = train_first.observed_followup_days_SIM.to_numpy(dtype=float)
    censored = ~train_first.event_observed_SIM.astype(bool).to_numpy()
    gh = _censor_survival_before(times, censored, horizon)
    for i, row in enumerate(test_first.itertuples(index=False)):
        failed = bool(row.event_observed_SIM)
        if failed and float(row.failure_interval_end_days_SIM) <= horizon:
            event_time = float(row.failure_interval_end_days_SIM)
            g = _censor_survival_before(times, censored, event_time)
            if g > 0:
                y[i], weights[i] = 1.0, 1.0 / g
        elif failed and float(row.failure_interval_start_days_SIM) < horizon < float(row.failure_interval_end_days_SIM):
            continue
        elif float(row.observed_followup_days_SIM) >= horizon:
            if gh > 0:
                y[i], weights[i] = 0.0, 1.0 / gh
    known = weights > 0
    if not known.any():
        return {"brier": None, "known_fraction": 0.0, "censor_survival_at_horizon": gh}
    brier = float(np.sum(weights[known] * (y[known] - prob[known]) ** 2) / int(known.sum()))
    return {"brier": brier, "known_fraction": float(known.mean()), "censor_survival_at_horizon": gh}


def _calibration(y, p, bins=5):
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    rows = []
    for i in range(bins):
        mask = (p >= edges[i]) & (p <= edges[i + 1] if i == bins - 1 else p < edges[i + 1])
        if mask.any():
            rows.append({"n": int(mask.sum()), "mean_predicted_event_probability": float(p[mask].mean()),
                         "observed_event_fraction": float(y[mask].mean())})
    return rows


def train_survival(df: pd.DataFrame, out_dir="artifacts"):
    """Fit grouped discrete hazards and evaluate only supported first-check horizons."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from .validation import saved_split
    # Use the status split saved beside this run. Falling back to the v1
    # artifacts directory makes survival fail on a separately generated v2 CSV.
    train_idx, test_idx = saved_split(df, out / "status_metrics.json")
    train_lots, test_lots = set(df.iloc[train_idx].sim_lot_id), set(df.iloc[test_idx].sim_lot_id)
    risk = make_risk_intervals(df)
    tr = risk[risk.sim_lot_id.isin(train_lots)].copy()
    te = risk[risk.sim_lot_id.isin(test_lots)].copy()
    train_first = _first_rows(df[df.sim_lot_id.isin(train_lots)])
    test_first = _first_rows(df[df.sim_lot_id.isin(test_lots)])
    train_initial_risk = _first_rows(tr)
    test_initial_risk = _first_rows(te)
    cols = SURVIVAL_FEATURES + ["interval_days"]
    outcomes = {}
    models = {
        "discrete_hazard_logistic": _prep_model(LogisticRegression(max_iter=1500, class_weight="balanced", random_state=SEED)),
        "discrete_hazard_xgboost": _prep_model(XGBClassifier(n_estimators=220, max_depth=4, learning_rate=0.05,
            subsample=.85, colsample_bytree=.85, reg_lambda=3, objective="binary:logistic",
            eval_metric="logloss", tree_method="hist", n_jobs=-1, random_state=SEED)),
    }
    test_interval_probabilities = {}
    for name, model in models.items():
        model.fit(tr[cols], tr.event_next.astype(int))
        phat = model.predict_proba(te[cols])[:, 1]
        test_interval_probabilities[name] = phat
        outcomes[name] = {"all_observed_at_risk_intervals": {
            "n": len(te), "event_intervals": int(te.event_next.sum()),
            "brier": float(brier_score_loss(te.event_next, phat)),
            "auc": float(roc_auc_score(te.event_next, phat)) if te.event_next.nunique() == 2 else None,
            "note": "Conditional next-inspection discrimination only; AUC is not days-left accuracy."}}
        dump(model, out / f"{name}.joblib")

    # Select a supported calendar checkpoint using training data only: the 25th
    # percentile of recorded event endpoints, rounded up to the crop's inspection
    # cadence. Test outcomes are not used to choose the evaluation horizon.
    calendar_horizons = {}
    for crop in sorted(test_first.crop.unique()):
        trf = train_first[train_first.crop == crop]
        tef = test_first[test_first.crop == crop]
        cadence = float(test_initial_risk.loc[test_initial_risk.crop == crop, "interval_days"].median())
        train_events = trf.loc[trf.event_observed_SIM.astype(bool), "failure_interval_end_days_SIM"]
        if train_events.empty:
            raise ValueError(f"No training events available to select a supported horizon for {crop}")
        q25_event_endpoint, horizon = _training_only_horizon(train_events, cadence)
        start_day = horizon - cadence
        train_landmark = tr[(tr.crop == crop) & np.isclose(tr.storage_age_days, start_day)]
        test_landmark = te[(te.crop == crop) & np.isclose(te.storage_age_days, start_day)]
        if train_landmark.empty or test_landmark.empty:
            raise ValueError(f"No supported at-risk rows for {crop} at {start_day} days")
        true_event = test_landmark.event_next.to_numpy(dtype=int)
        baseline_p = float(train_landmark.event_next.mean())
        horizon_result = {"calendar_horizon_day": horizon, "landmark_start_day": start_day,
                          "horizon_selection": {"rule": "Training-only 25th percentile of recorded event endpoints, rounded up to the crop inspection cadence.",
                              "training_event_endpoint_q25_days": q25_event_endpoint,
                              "selected_without_test_outcomes": True},
                          "interval_days": cadence, "test_at_risk_lots_paths": len(test_landmark),
                          "test_events_in_interval": int(true_event.sum()),
                          "test_trajectory_events_by_horizon": int((tef.event_observed_SIM.astype(bool) & (tef.failure_interval_end_days_SIM <= horizon)).sum()),
                          "test_right_censored_trajectories": int((~tef.event_observed_SIM.astype(bool)).sum()),
                          "censoring_note": "Hazard scores cover a fully observed next-inspection interval; no included row is censored before its next inspection. AFT uses IPCW at the stated absolute horizon."}
        base_p = np.full(len(test_landmark), baseline_p)
        horizon_result["crop_specific_baseline"] = {
            "brier": float(np.mean((true_event - base_p) ** 2)), "censor_survival_at_horizon": 1.0,
            "known_fraction": 1.0,
            "calibration": {"mean_predicted": float(base_p.mean()), "observed_fraction": float(true_event.mean())},
            "calibration_bins": _calibration(true_event, base_p)}
        for name, model in models.items():
            prob = model.predict_proba(test_landmark[cols])[:, 1]
            horizon_result[name] = {"brier": float(np.mean((true_event - prob) ** 2)),
                "censor_survival_at_horizon": 1.0, "known_fraction": 1.0,
                "calibration": {"mean_predicted": float(prob.mean()), "observed_fraction": float(true_event.mean())},
                "calibration_bins": _calibration(true_event, prob)}
        calendar_horizons[crop] = horizon_result

    # AFT comparison preserves interval events and right-censored trajectories.
    aft_result = {"available": False}
    try:
        af = train_first
        vf = test_first
        prep = ColumnTransformer([
            ("num", SimpleImputer(strategy="median", add_indicator=True), [c for c in SURVIVAL_FEATURES if c != "crop"]),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore"))]), ["crop"]),
        ])
        xa, xv = prep.fit_transform(af[SURVIVAL_FEATURES]), prep.transform(vf[SURVIVAL_FEATURES])
        import xgboost as xgb_lib
        dtrain, dtest = xgb_lib.DMatrix(xa), xgb_lib.DMatrix(xv)
        lower, upper = aft_interval_bounds(af)
        dtrain.set_float_info("label_lower_bound", lower)
        dtrain.set_float_info("label_upper_bound", upper)
        booster = xgb_lib.train({"objective": "survival:aft", "eval_metric": "aft-nloglik",
            "aft_loss_distribution": "normal", "aft_loss_distribution_scale": 1.0,
            "tree_method": "hist", "max_depth": 4, "eta": .04, "seed": SEED, "nthread": -1}, dtrain, num_boost_round=250)
        mu = booster.predict(dtest, output_margin=True)
        pred_days = np.exp(np.clip(mu, -30, 30))
        event = vf.event_observed_SIM.astype(bool).to_numpy()
        lo = vf.failure_interval_start_days_SIM.to_numpy(dtype=float)[event]
        hi = vf.failure_interval_end_days_SIM.to_numpy(dtype=float)[event]
        error_to_interval = np.maximum(lo - pred_days[event], 0) + np.maximum(pred_days[event] - hi, 0)
        aft_result = {"test_trajectories": len(vf), "test_observed_events": int(event.sum()),
            "test_right_censored": int((~event).sum()),
            "observed_failure_interval_distance_days": {"median": float(np.median(error_to_interval)),
                "mae": float(np.mean(error_to_interval)),
                "limitation": "Only observed failures; prediction is compared with an interval, not an exact event day. Censored cases are not timed-error cases."},
            "per_crop_event_censoring": {}}
        for crop in sorted(vf.crop.unique()):
            mask = vf.crop.to_numpy() == crop
            aft_result["per_crop_event_censoring"][crop] = {"test_trajectories": int(mask.sum()),
                "events": int((event & mask).sum()), "censored": int((~event & mask).sum())}
            horizon = calendar_horizons[crop]["calendar_horizon_day"]
            event_p = ndtr(np.log(max(horizon, 1e-12)) - mu[mask])
            # Normal AFT: failure probability = Phi((log(t)-mu)/scale), scale=1.
            rows_test = vf.loc[mask].copy()
            rows_train = af[af.crop == crop].copy()
            aft_result.setdefault("calendar_horizon_ipcw_brier", {})[crop] = _ipcw_brier(rows_test, event_p, horizon, rows_train)
            aft_result.setdefault("calendar_horizon_calibration", {})[crop] = {
                "mean_predicted_event_probability": float(event_p.mean()),
                "observed_event_fraction_by_horizon": float(((rows_test.event_observed_SIM.astype(bool)) & (rows_test.failure_interval_end_days_SIM <= horizon)).mean())}
        dump({"preprocessor": prep, "booster": booster}, out / "xgboost_aft.joblib")
    except Exception as exc:
        aft_result = {"available": False, "error": str(exc)}

    event_counts = {}
    for crop in sorted(df.crop.unique()):
        for split_name, rows in (("train", train_first), ("test", test_first)):
            subset = rows[rows.crop == crop]
            event_counts.setdefault(crop, {})[split_name] = {"trajectories": len(subset),
                "events": int(subset.event_observed_SIM.astype(bool).sum()),
                "right_censored": int((~subset.event_observed_SIM.astype(bool)).sum())}
    payload = {"warning": "SIMULATION ONLY: no result is validated crop shelf-life performance.",
        "split": {"train_lots": len(train_lots), "test_lots": len(test_lots),
                  "test_ids_unchanged": True, "risk_rows_train": len(tr), "risk_rows_test": len(te)},
        "per_crop_event_censoring": event_counts,
        "discrete_hazard_all_interval_metrics": outcomes,
        "crop_specific_calendar_horizons": calendar_horizons,
        "xgboost_aft_interval_censored": aft_result,
        "construction": "Each hazard row's predictors are the current interval-start readings and through-current history. Rows at/after the recorded failure upper bound are excluded; the event is attributed to the recorded inspection interval. Censored trajectories contribute only observed event-free intervals.",
        "horizon_note": "For each crop, the absolute calendar endpoint is selected using only training-lot observed event endpoints: their 25th percentile rounded up to that crop's inspection cadence. The held-out evaluation uses a single supported next-inspection interval starting one cadence earlier; it does not use future rows as predictors or claim interpolation between inspections. AFT Brier evaluates baseline predictions by the same absolute horizon with IPCW. Future-path projections remain separate and require explicit future environment and all nine MQ channels."}
    (out / "survival_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
