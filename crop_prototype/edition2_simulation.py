"""Create and evaluate a small, explicitly simulated crop sensor demo.

This is a rule-based simulator for a UI/pipeline demonstration, not a model of
validated crop spoilage. Each row is an independent one-time simulated case;
there are no physical lot IDs or repeated trajectories.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dataset_edition_2"
MODEL_ROOT = ROOT / "artifacts" / "edition2_simulation"
SEED = 20261102
N_CASES = 600
MQ = ["MQ2", "MQ3", "MQ4", "MQ5", "MQ6", "MQ7", "MQ8", "MQ9", "MQ135"]

# Approximate operating points used only to design the demo scenarios.
# Tomato is explicitly assumed to be mature-green; potato is table potato.
PROFILES = {
    "tomato": {"temp_c": 13.75, "rh_pct": 92.5, "age_days": 14,
               "temp_sd": 5.2, "rh_sd": 8.0, "ref": "UC Davis tomato postharvest factsheet"},
    "potato": {"temp_c": 7.0, "rh_pct": 96.5, "age_days": 35,
               "temp_sd": 4.5, "rh_sd": 7.5, "ref": "UC Davis potato postharvest factsheet (table use)"},
    "banana": {"temp_c": 13.5, "rh_pct": 92.5, "age_days": 28,
               "temp_sd": 5.0, "rh_sd": 8.0, "ref": "UC Davis banana postharvest factsheet"},
}


def _simulate_crop(crop: str, profile: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = N_CASES
    # Draw a mixture of near-recommended and deliberately stressed conditions.
    stressed = rng.random(n) < 0.48
    temp = rng.normal(profile["temp_c"], np.where(stressed, profile["temp_sd"], 1.1))
    rh = rng.normal(profile["rh_pct"], np.where(stressed, profile["rh_sd"], 2.0))
    rh = np.clip(rh, 45, 99)
    age = rng.integers(0, profile["age_days"] + 1, n)

    # Latent degradation pressure is an explicit simulator assumption. No
    # inspection target exists in the source datasets for this experiment.
    temp_stress = np.maximum(0, np.abs(temp - profile["temp_c"]) - 2.0) / 8.0
    rh_stress = np.maximum(0, np.abs(rh - profile["rh_pct"]) - 4.0) / 25.0
    age_stress = age / profile["age_days"]
    susceptibility = rng.normal(0, 0.13, n)
    latent = np.clip(0.34 * age_stress + 0.34 * temp_stress + 0.20 * rh_stress + susceptibility, 0, 1.3)

    # Simulated ADC-like response indices (not ppm and not a joined sample).
    # For tomato/banana, raw baseline draws come from their separate short
    # nine-MQ recording files. We resample them and perturb them synthetically;
    # no environmental row or label is matched to those recordings. Potato has
    # no public raw MQ file, so its channels are fully simulated.
    sensitivity = np.array([0.44, 0.62, 0.35, 0.39, 0.54, 0.31, 0.29, 0.48, 0.70])
    channel_baseline = np.array([260, 180, 220, 205, 240, 160, 155, 230, 300], dtype=float)
    channel_noise = np.array([20, 19, 18, 20, 21, 17, 17, 19, 24], dtype=float)
    source_dir = DATA_ROOT / crop / "original" / f"zenodo_exact_nine_mq_{crop}_recordings" / "AllSmaples-Report"
    source_rows = []
    if crop in {"tomato", "banana"} and source_dir.is_dir():
        for path in sorted(source_dir.glob("*.csv")):
            raw = pd.read_csv(path)
            if set(MQ).issubset(raw.columns):
                source_rows.append(raw[MQ].apply(pd.to_numeric, errors="coerce").dropna().to_numpy())
    if source_rows:
        source_values = np.concatenate(source_rows, axis=0)
        source_values = source_values[np.isfinite(source_values).all(axis=1)]
        if len(source_values):
            mq = source_values[rng.integers(0, len(source_values), size=n)].astype(float)
            channel_baseline = np.median(source_values, axis=0)
            channel_noise = np.maximum(np.std(source_values, axis=0), 2.0)
        else:
            mq = np.tile(channel_baseline, (n, 1))
    else:
        mq = np.tile(channel_baseline, (n, 1))
    mq += latent[:, None] * sensitivity[None, :] * 120
    mq += rng.normal(0, channel_noise[None, :], size=(n, len(MQ)))
    mq = np.clip(mq, 0, 1023).round(1)

    # Synthetic label, determined by the simulator's latent state. The target
    # is not an inspection and must never be presented as measured spoilage.
    label = np.where(latent >= 0.52, "bad", "good")
    frame = pd.DataFrame({
        "sim_case_id": [f"{crop.upper()}-SIM-{i + 1:04d}" for i in range(n)],
        "crop": crop,
        "storage_age_days_SIM": age,
        "temperature_C_SIM": temp.round(2),
        "relative_humidity_pct_SIM": rh.round(2),
    })
    for j, name in enumerate(MQ):
        frame[f"{name}_response_SIM"] = mq[:, j]
    frame["status_SIM"] = label
    frame["data_origin"] = "SIMULATED_RULE_BASED"
    frame["label_origin"] = "SIMULATED_LATENT_RULE_NOT_INSPECTION"
    return frame


def generate() -> dict:
    rng = np.random.default_rng(SEED)
    metrics: dict[str, object] = {
        "interpretation": "Simulator reconstruction only; not measured crop accuracy.",
        "sensor_note": "Tomato/banana raw MQ readings are resampled and synthetically perturbed without matching to environment or labels; potato MQ values are fully simulated.",
        "seed": SEED,
        "cases_per_crop": N_CASES,
        "split": "stratified row split; each row is an independent synthetic case",
        "models": {},
    }
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)

    for crop, profile in PROFILES.items():
        out_dir = DATA_ROOT / crop / "simulated_v2"
        out_dir.mkdir(parents=True, exist_ok=True)
        df = _simulate_crop(crop, profile, rng)
        csv_path = out_dir / f"{crop}_mq_environment_good_bad_SIMULATED.csv"
        df.to_csv(csv_path, index=False)

        features = ["storage_age_days_SIM", "temperature_C_SIM", "relative_humidity_pct_SIM"]
        features += [f"{ch}_response_SIM" for ch in MQ]
        X = df[features]
        y = df["status_SIM"]
        x_train, x_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=SEED, stratify=y
        )
        model = make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(n_estimators=250, min_samples_leaf=3,
                                   class_weight="balanced", random_state=SEED,
                                   n_jobs=-1),
        )
        model.fit(x_train, y_train)
        pred = model.predict(x_test)
        crop_metrics = {
            "rows": int(len(df)),
            "synthetic_good": int((y == "good").sum()),
            "synthetic_bad": int((y == "bad").sum()),
            "macro_f1": round(float(f1_score(y_test, pred, average="macro")), 4),
            "bad_recall": round(float(recall_score(y_test, pred, pos_label="bad")), 4),
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "csv": str(csv_path.relative_to(ROOT)),
            "model": str((MODEL_ROOT / f"{crop}_random_forest.joblib").relative_to(ROOT)),
            "features": features,
            "target_definition": "good/bad from latent simulator rule; not crop inspection",
        }
        joblib.dump(model, MODEL_ROOT / f"{crop}_random_forest.joblib")
        metrics["models"][crop] = crop_metrics

    (MODEL_ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    results = generate()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
