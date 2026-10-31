"""Generate an assumption-driven synthetic paired crop sensor dataset.

This generator creates no observed measurements. The sensor channels are
dimensionless response indices, and all simulated labels are generated from
the synthetic inspection process below. It deliberately creates one path per
synthetic lot (no counterfactual path branching).
"""
from __future__ import annotations

from pathlib import Path
import json
import math
import numpy as np
import pandas as pd

from .data import MQ_COLUMNS

SEED = 20261031
CROPS = {
    "wheat": {"ages": np.linspace(0, 273, 40), "tref": 15.0, "rh_ref": 60.0,
              "rate": 0.00068, "moisture": 12.2, "moisture_risk": 13.5},
    "maize": {"ages": np.linspace(0, 273, 40), "tref": 15.0, "rh_ref": 60.0,
              "rate": 0.00082, "moisture": 12.8, "moisture_risk": 13.5},
    "potato": {"ages": np.linspace(0, 78, 40), "tref": 7.0, "rh_ref": 90.0,
               "rate": 0.0056, "moisture": np.nan, "moisture_risk": np.nan},
    "onion": {"ages": np.linspace(0, 78, 40), "tref": 4.0, "rh_ref": 65.0,
                        "rate": 0.0054, "moisture": np.nan, "moisture_risk": np.nan},
    "spinach": {"ages": np.linspace(0, 9.75, 40), "tref": 4.0, "rh_ref": 92.0,
                "rate": 0.068, "moisture": np.nan, "moisture_risk": np.nan},
}

# Scenario envelopes are illustrative, not recommendations or measured storage
# settings. Each independent simulated lot receives exactly one scenario.
SCENARIOS = {
    "cool_stable": (-1.0, -2.0),
    "recommended_range": (0.0, 0.0),
    "ambient_stable": (5.0, -4.0),
    "warm_dry": (10.0, -14.0),
    "warm_humid": (10.0, 13.0),
    "variable_excursion": (6.0, 1.0),
}

# Fictional relative sensor-response signatures. These encode broad
# cross-sensitivity/crop differences without pretending to identify gases.
SENSITIVITY = {
    "wheat": [0.72, 0.43, 0.48, 0.66, 0.37, 0.49, 0.34, 0.42, 0.81],
    "maize": [0.76, 0.45, 0.53, 0.69, 0.40, 0.46, 0.37, 0.47, 0.78],
    "potato": [0.78, 0.82, 0.40, 0.57, 0.66, 0.38, 0.37, 0.73, 0.86],
    "onion": [0.64, 0.55, 0.38, 0.52, 0.72, 0.41, 0.34, 0.68, 0.84],
    "spinach": [0.62, 0.78, 0.43, 0.70, 0.59, 0.42, 0.37, 0.71, 0.88],
}
MQ_IDS = (2, 3, 4, 5, 6, 7, 8, 9, 135)


def _dew_point(temp_c: float, rh: float) -> float:
    rh = float(np.clip(rh, 1, 100))
    a, b = 17.625, 243.04
    g = math.log(rh / 100.0) + (a * temp_c) / (b + temp_c)
    return b * g / (a - g)


def _environment(rng, crop, cfg, scenario, age, t_state, rh_state):
    t_off, rh_off = SCENARIOS[scenario]
    # Slow room drift plus autocorrelated, reading-level sensor variation.
    t_mean = cfg["tref"] + 3.5 + t_off + 1.3 * math.sin(age / max(float(cfg["ages"][-1]), 1) * 2 * math.pi)
    rh_mean = cfg["rh_ref"] + rh_off + 2.0 * math.sin(age / max(float(cfg["ages"][-1]), 1) * 2 * math.pi + 0.8)
    t_state = 0.78 * t_state + rng.normal(0, 1.05)
    rh_state = 0.76 * rh_state + rng.normal(0, 3.1)
    if scenario == "variable_excursion":
        phase = int(age / max(float(cfg["ages"][-1]), 1) * 6)
        t_mean += (5.0 if phase % 2 else -2.5)
        rh_mean += (8.0 if phase % 2 else -5.0)
    temp = float(np.clip(t_mean + t_state, -1.5, 41.0))
    rh = float(np.clip(rh_mean + rh_state, 35.0, 99.5))
    # Independent simulated AeroSense-like response fields. Device firmware
    # implementations are not claimed to be reproduced.
    pressure = float(rng.normal(1012.0, 5.0))
    gas_kohms = float(np.clip(rng.lognormal(math.log(8.0) - 0.012 * max(temp - 20, 0), 0.20), 1.0, 35.0))
    aqi = float(np.clip(24 + 0.45 * max(rh - 70, 0) + 1.1 * max(temp - 25, 0) + rng.normal(0, 8), 0, 200))
    altitude = float(np.clip(rng.normal(180, 12), 100, 260))
    dew = float(_dew_point(temp, rh) + rng.normal(0, 0.35))
    heat = float(temp + max(0, temp - 20) * max(0, rh - 40) * 0.004)
    grain_moisture = np.nan
    if crop in {"wheat", "maize"}:
        grain_moisture = float(np.clip(cfg["moisture"] + (rh - 60) * 0.035 + rng.normal(0, 0.35), 8.0, 19.0))
    return {
        "Temperature(°C)": temp, "Humidity(%)": rh, "Pressure(hPa)": pressure,
        "AQI": aqi, "Gas (kOhms)": gas_kohms, "Altitude(m)": altitude,
        "DewPoint(°C)": dew, "HeatIndex(°C)": heat,
        "grain_moisture_pct_SIM": grain_moisture,
    }, t_state, rh_state


def generate_v2(lots_per_crop: int = 100, seed: int = SEED) -> tuple[pd.DataFrame, dict]:
    """Return one-path-per-lot paired synthetic records and generation metadata."""
    if lots_per_crop < 25:
        raise ValueError("Use at least 25 lots per crop so grouped evaluation is meaningful.")
    rng = np.random.default_rng(seed)
    rows = []
    lot_index = 0
    for crop, cfg in CROPS.items():
        ages = np.asarray(cfg["ages"], dtype=float)
        scenario_names = list(SCENARIOS)
        scenario_draw = np.tile(np.arange(len(scenario_names)), int(np.ceil(lots_per_crop / len(scenario_names))))[:lots_per_crop]
        rng.shuffle(scenario_draw)
        for local_i in range(lots_per_crop):
            lot_index += 1
            lot_id = f"V2_{crop}_{local_i + 1:04d}"
            traj_id = f"{lot_id}_path01"
            scenario = scenario_names[int(scenario_draw[local_i])]
            susceptibility = float(rng.lognormal(0, 0.24))
            initial_damage = float(rng.beta(1.5, 30.0))
            initial_defect = float(np.clip(initial_damage * 35 + rng.normal(0, 0.6), 0, 12))
            lot_mass = float(rng.lognormal(math.log(120 if crop in {"wheat", "maize"} else 18), 0.22))
            damage = max(0.0, initial_damage)
            t_state, rh_state = rng.normal(0, 1), rng.normal(0, 2)
            past_t, past_rh, past_hot = [], [], 0.0
            drift = rng.normal(0, 0.025, len(MQ_IDS))
            mq_baseline = rng.uniform(18, 44, len(MQ_IDS))
            mq_gain = np.asarray(SENSITIVITY[crop]) * rng.lognormal(0, 0.18, len(MQ_IDS))
            previous_defect = 0.0
            path_rows = []

            for k, age in enumerate(ages):
                dt = 0.0 if k == 0 else float(age - ages[k - 1])
                env, t_state, rh_state = _environment(rng, crop, cfg, scenario, float(age), t_state, rh_state)
                temp = env["Temperature(°C)"]
                rh = env["Humidity(%)"]
                grain_moisture = env["grain_moisture_pct_SIM"]
                # Assumption-driven damage process: temperature, crop-specific
                # moisture stress, lot susceptibility, and random shocks.
                temp_factor = math.exp(np.clip(0.055 * (temp - cfg["tref"]), -1.2, 1.8))
                rh_stress = 1 + 0.018 * max(rh - cfg["rh_ref"], 0) + 0.004 * max(cfg["rh_ref"] - rh, 0)
                moisture_stress = 1.0
                if crop in {"wheat", "maize"}:
                    moisture_stress += 0.12 * max(float(grain_moisture) - cfg["moisture_risk"], 0)
                increment = cfg["rate"] * dt * temp_factor * rh_stress * moisture_stress * susceptibility
                increment *= float(rng.lognormal(-0.5 * 0.14**2, 0.14)) if dt else 0.0
                damage = float(np.clip(damage + increment, 0, 1.2))

                # Inspection error is separate from sensor error; enforce a
                # nondecreasing measured defect trajectory for a coherent
                # first-unacceptable event in this synthetic example.
                defect = float(np.clip(damage * 38 + rng.normal(0, 0.75), 0, 100))
                defect = max(previous_defect, defect)
                previous_defect = defect
                status = "acceptable" if defect < 7 else ("warning" if defect < 15 else "spoiled")

                # A volatile-response surrogate rises with latent deterioration,
                # but gets lot calibration offsets, temperature/RH effects,
                # sensor-specific drift, cross-channel noise, and read noise.
                volatile_state = max(0, damage) ** 1.15
                env_cross = 0.08 * (temp - cfg["tref"]) / 10 + 0.10 * (rh - cfg["rh_ref"]) / 20
                mq_values = {}
                for j, mq_id in enumerate(MQ_IDS):
                    cross = sum(mq_gain[h] * volatile_state for h in range(len(MQ_IDS)) if h != j) * 0.045
                    value = mq_baseline[j] + 36 * mq_gain[j] * volatile_state + cross
                    value += env_cross * (2.5 + mq_id % 5) + drift[j] * float(age)
                    value += rng.normal(0, 3.2 + 0.05 * value)
                    mq_values[f"MQ{mq_id}_response_index_SIM"] = float(np.clip(value, 0, 100))

                past_t.append(temp)
                past_rh.append(rh)
                past_hot += max(0, temp - cfg["tref"]) * dt
                timestamp = pd.Timestamp("2031-01-01T00:00:00Z") + pd.to_timedelta(float(age), unit="D")
                row = {
                    "data_origin": "SIMULATED_V2_ASSUMPTION_DRIVEN",
                    "crop": crop, "crop_group": "grain" if crop in {"wheat", "maize"} else "vegetable",
                    "sim_lot_id": lot_id, "sim_trajectory_id": traj_id, "scenario_SIM": scenario,
                    "sim_timestamp_utc": timestamp.isoformat(), "storage_age_days": float(age),
                    "Date": timestamp.date().isoformat(), "Time": timestamp.time().isoformat(),
                    **env, "lot_mass_kg_SIM": lot_mass,
                    "initial_inspection_defect_pct_SIM": initial_defect,
                    "past_mean_temp_C_SIM": float(np.mean(past_t)),
                    "past_mean_rh_pct_SIM": float(np.mean(past_rh)),
                    "past_hot_degree_days_SIM": float(past_hot), **mq_values,
                    "inspection_defect_type_SIM": "simulated_quality_decline" if defect >= 7 else "none",
                    "inspection_defect_pct_SIM": defect, "status_SIM": status,
                    "_damage_latent": damage,
                }
                path_rows.append(row)

            failures = [r["storage_age_days"] for r in path_rows if r["status_SIM"] == "spoiled"]
            event = bool(failures)
            end = float(failures[0]) if event else float(ages[-1])
            end_idx = next((i for i, r in enumerate(path_rows) if r["storage_age_days"] == end), len(path_rows) - 1)
            start = float(ages[max(0, end_idx - 1)])
            if event and start == end:
                start = max(0.0, end - float(ages[1] - ages[0]))
            for r in path_rows:
                age = r["storage_age_days"]
                r["failure_interval_start_days_SIM"] = start if event else np.nan
                r["failure_interval_end_days_SIM"] = end if event else np.nan
                r["event_observed_SIM"] = int(event)
                r["observed_followup_days_SIM"] = end
                r["remaining_days_to_first_failed_check_SIM"] = max(0.0, end - age) if event else np.nan
                r["post_failure_SIM"] = bool(event and age >= end)
                del r["_damage_latent"]
                rows.append(r)

    df = pd.DataFrame(rows)
    # Ensure the v1-compatible AeroSense-like column order and all nine MQ fields.
    expected = [
        "data_origin", "crop", "crop_group", "sim_lot_id", "sim_trajectory_id", "scenario_SIM",
        "sim_timestamp_utc", "storage_age_days", "Date", "Time", "Temperature(°C)", "Humidity(%)",
        "Pressure(hPa)", "AQI", "Gas (kOhms)", "Altitude(m)", "DewPoint(°C)", "HeatIndex(°C)",
        "grain_moisture_pct_SIM", "lot_mass_kg_SIM", "initial_inspection_defect_pct_SIM",
        "past_mean_temp_C_SIM", "past_mean_rh_pct_SIM", "past_hot_degree_days_SIM",
        *MQ_COLUMNS, "inspection_defect_type_SIM", "inspection_defect_pct_SIM", "status_SIM",
        "failure_interval_start_days_SIM", "failure_interval_end_days_SIM", "event_observed_SIM",
        "observed_followup_days_SIM", "remaining_days_to_first_failed_check_SIM", "post_failure_SIM",
    ]
    df = df[expected].sort_values(["sim_lot_id", "storage_age_days"], kind="stable").reset_index(drop=True)
    summary = {
        "dataset_name": "synthetic_paired_crop_sensor_v2",
        "data_origin": "SIMULATED_V2_ASSUMPTION_DRIVEN",
        "seed": int(seed), "lots_per_crop": int(lots_per_crop), "rows": int(len(df)),
        "columns": int(len(df.columns)), "unique_simulated_lots": int(df.sim_lot_id.nunique()),
        "unique_simulated_trajectories": int(df.sim_trajectory_id.nunique()),
        "paths_per_lot": 1, "rows_per_crop": df.crop.value_counts().sort_index().astype(int).to_dict(),
        "lots_per_crop_actual": df.groupby("crop").sim_lot_id.nunique().astype(int).to_dict(),
        "scenario_lots_by_crop": {
            crop: {str(scenario): int(count) for scenario, count in group.drop_duplicates("sim_lot_id").scenario_SIM.value_counts().items()}
            for crop, group in df.groupby("crop")
        },
        "status_counts": df.status_SIM.value_counts().sort_index().astype(int).to_dict(),
        "event_censored_by_crop": {c: {"events": int(g.groupby("sim_lot_id").event_observed_SIM.first().sum()),
                                       "censored": int((1 - g.groupby("sim_lot_id").event_observed_SIM.first()).sum())}
                                   for c, g in df.groupby("crop")},
        "age_ranges_days": {c: [float(g.storage_age_days.min()), float(g.storage_age_days.max())]
                            for c, g in df.groupby("crop")},
        "synthetic_assumptions": [
            "One generated storage trajectory per unique simulated lot; there are no branched counterfactual paths.",
            "Temperature, relative humidity, crop susceptibility, and inspection noise are generated from stated distributions, not measured paired data.",
            "Nine MQ fields are dimensionless response indices with synthetic cross-sensitivity, calibration offsets, drift, and noise; they are not gas concentrations or calibrated real-device outputs.",
            "AeroSense-named fields are illustrative synthetic values and do not reproduce or validate the AeroSense firmware.",
            "Synthetic status is derived from the generated inspection defect percentage using assumed thresholds: acceptable <7%, warning 7-<15%, spoiled >=15%; these are not crop standards.",
            "Failure/censoring targets are generated from these synthetic inspections and cannot validate true crop shelf life.",
            "The fictional timestamps exist for schema compatibility only and must never be model inputs.",
        ],
    }
    return df, summary


def write_v2(output_csv: str | Path, lots_per_crop: int = 100, seed: int = SEED) -> dict:
    out = Path(output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df, summary = generate_v2(lots_per_crop=lots_per_crop, seed=seed)
    df.to_csv(out, index=False)
    summary["csv_path"] = str(out)
    summary_path = out.with_name("summary_v2.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
