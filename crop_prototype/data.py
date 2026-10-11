from __future__ import annotations

from pathlib import Path
import pandas as pd

DEFAULT_CSV = Path("five_crop_120000_simulated_training_bundle/five_crop_120000_ALL_SIMULATED_9MQ.csv")
KEYS = ["sim_trajectory_id", "storage_age_days"]
MQ_COLUMNS = [f"MQ{x}_response_index_SIM" for x in (2, 3, 4, 5, 6, 7, 8, 9, 135)]
ENV_COLUMNS = [
    "Temperature(\u00b0C)", "Humidity(%)", "Pressure(hPa)", "AQI", "Gas (kOhms)",
    "Altitude(m)", "DewPoint(\u00b0C)", "HeatIndex(\u00b0C)", "grain_moisture_pct_SIM",
    "lot_mass_kg_SIM", "past_mean_temp_C_SIM", "past_mean_rh_pct_SIM",
    "past_hot_degree_days_SIM",
]
BASE_COLUMNS = ["crop", "storage_age_days"]
CURRENT_SENSOR_COLUMNS = ENV_COLUMNS[:8]
DEPLOYMENT_FEATURES = BASE_COLUMNS + CURRENT_SENSOR_COLUMNS + MQ_COLUMNS
INITIAL_COLUMN = "initial_inspection_defect_pct_SIM"
FORBIDDEN_PREDICTORS = {
    "status_SIM", "inspection_defect_pct_SIM", "inspection_defect_type_SIM",
    "failure_interval_start_days_SIM", "failure_interval_end_days_SIM",
    "event_observed_SIM", "observed_followup_days_SIM",
    "remaining_days_to_first_failed_check_SIM", "post_failure_SIM",
    "sim_lot_id", "sim_trajectory_id", "scenario_SIM", "data_origin",
    "sim_timestamp_utc", "Date", "Time",
}


def load_simulated(path: str | Path = DEFAULT_CSV) -> pd.DataFrame:
    """Load the simulator CSV without mutating or replacing its raw values."""
    df = pd.read_csv(path, encoding="utf-8", low_memory=False, na_values=["", "NA", "N/A"])
    validate_simulated(df)
    return df


def validate_simulated(df: pd.DataFrame) -> None:
    """Validate unique keys and chronological source row order within trajectories."""
    if df.duplicated(KEYS).any():
        raise ValueError(f"Duplicate trajectory/time keys: {KEYS}")
    if not df.groupby("sim_trajectory_id", sort=False)["storage_age_days"].apply(lambda x: x.is_monotonic_increasing).all():
        raise ValueError("Source row order must increase in storage_age_days within every trajectory")


def feature_sets(df: pd.DataFrame, include_initial: bool = False) -> dict[str, list[str]]:
    """Construct the three requested input families, with optionally deployable initial inspection."""
    base = BASE_COLUMNS.copy()
    env = base + ENV_COLUMNS
    if include_initial:
        env.append(INITIAL_COLUMN)
    sets = {
        "environment_only": env,
        "mq_only": base + MQ_COLUMNS,
        "combined": env + MQ_COLUMNS,
    }
    for name, cols in sets.items():
        unknown = sorted(set(cols) - set(df.columns))
        banned = sorted(set(cols) & FORBIDDEN_PREDICTORS)
        if unknown or banned:
            raise ValueError(f"Invalid features in {name}: unknown={unknown}, leakage={banned}")
    return sets


def load_aerosense_real(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Read a separate real AeroSense workbook and summarize timestamp quality/gaps."""
    raw = pd.read_excel(path)
    date_col = next((c for c in raw.columns if str(c).strip().lower() == "date"), None)
    time_col = next((c for c in raw.columns if str(c).strip().lower() == "time"), None)
    if date_col is None or time_col is None:
        raise ValueError("Expected Date and Time columns in AeroSense workbook")
    stamp = pd.to_datetime(raw[date_col].astype(str).str.strip() + " " + raw[time_col].astype(str).str.strip(), errors="coerce")
    raw["parsed_timestamp"] = stamp
    valid = raw.loc[stamp.notna()].copy().sort_values("parsed_timestamp")
    deltas = valid["parsed_timestamp"].diff().dropna().dt.total_seconds() / 60
    gaps = deltas[deltas > 30]
    valid["session_id"] = (valid["parsed_timestamp"].diff().dt.total_seconds().div(60).gt(30).cumsum() + 1).astype(int)
    sessions = [{"session_id": int(sid), "rows": int(len(g)), "start": str(g.parsed_timestamp.min()), "end": str(g.parsed_timestamp.max())}
                for sid, g in valid.groupby("session_id", sort=True)]
    summary = {
        "rows": len(raw), "invalid_timestamps": int(stamp.isna().sum()),
        "valid_timestamps": int(stamp.notna().sum()), "duplicate_timestamps": int(valid["parsed_timestamp"].duplicated().sum()),
        "timestamp_start": str(valid["parsed_timestamp"].min()) if len(valid) else None,
        "timestamp_end": str(valid["parsed_timestamp"].max()) if len(valid) else None,
        "recording_gap_threshold_minutes": 30, "recording_gaps_over_threshold": int(len(gaps)),
        "largest_gap_minutes": float(gaps.max()) if len(gaps) else None,
        "sessions": sessions,
        "warning": "Standalone environmental log only; no crop/lot, paired MQ array, or quality target was created.",
    }
    return raw, summary
# schema encoding fix
