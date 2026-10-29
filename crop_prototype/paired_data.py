"""Preflight audit for a genuinely paired real crop sensor/inspection table.

This module does not join records, infer labels, resample times, or train a model.
The input must already represent a documented sensor-to-inspection match.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

MQ_COLUMNS = [f"mq{x}_response" for x in (2, 3, 4, 5, 6, 7, 8, 9, 135)]
ENV_COLUMNS = [
    "temperature_c", "relative_humidity_pct", "pressure_hpa", "aqi",
    "gas_kohms", "altitude_m", "dew_point_c", "heat_index_c",
]
IDENTITY_COLUMNS = ["study_id", "crop", "lot_id", "sample_id", "storage_unit_id"]
TIME_COLUMNS = ["sensor_timestamp_utc", "inspection_timestamp_utc"]
LABEL_COLUMNS = ["quality_label", "quality_method"]
REQUIRED_COLUMNS = IDENTITY_COLUMNS + TIME_COLUMNS + ENV_COLUMNS + MQ_COLUMNS + LABEL_COLUMNS
UNIQUE_KEY = ["study_id", "sample_id", "inspection_timestamp_utc"]


def audit_paired_csv(path: str | Path, max_pair_gap_seconds: float = 300.0) -> dict:
    """Audit canonical one-row-per-inspection paired CSV without modifying it."""
    if max_pair_gap_seconds < 0:
        raise ValueError("max_pair_gap_seconds must be non-negative")
    df = pd.read_csv(path, low_memory=False)
    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        return {
            "input": str(path), "rows": int(len(df)), "columns": list(df.columns),
            "missing_required_columns": missing_columns, "ready_for_training": False,
            "warning": "No data were joined or inferred. Add measured values and documented matching keys before training.",
        }

    empty_id_counts = {
        c: int(df[c].isna().sum() + df[c].astype("string").str.strip().eq("").sum())
        for c in IDENTITY_COLUMNS
    }
    parsed_sensor_time = pd.to_datetime(df["sensor_timestamp_utc"], utc=True, errors="coerce")
    parsed_inspection_time = pd.to_datetime(df["inspection_timestamp_utc"], utc=True, errors="coerce")
    invalid_sensor_time = int(parsed_sensor_time.isna().sum())
    invalid_inspection_time = int(parsed_inspection_time.isna().sum())
    lag_seconds = (parsed_sensor_time - parsed_inspection_time).abs().dt.total_seconds()
    over_tolerance = int(lag_seconds.gt(max_pair_gap_seconds).sum() + lag_seconds.isna().sum())
    normalized_keys = df[UNIQUE_KEY].copy()
    normalized_keys["inspection_timestamp_utc"] = parsed_inspection_time
    duplicate_keys = int(normalized_keys.duplicated(UNIQUE_KEY, keep=False).sum())
    feature_missingness = {c: int(df[c].isna().sum()) for c in ENV_COLUMNS + MQ_COLUMNS}
    label_counts = df["quality_label"].fillna("<missing>").astype(str).value_counts(dropna=False).to_dict()
    label_lot_counts = {
        str(label): int(group["lot_id"].nunique(dropna=True))
        for label, group in df.dropna(subset=["quality_label"]).groupby("quality_label", dropna=False)
    }
    groups_per_crop = df.groupby("crop", dropna=False)["lot_id"].nunique(dropna=True).to_dict()
    storage_units_per_crop = df.groupby("crop", dropna=False)["storage_unit_id"].nunique(dropna=True).to_dict()
    studies = sorted(df["study_id"].dropna().astype(str).unique().tolist())
    crops = sorted(df["crop"].dropna().astype(str).unique().tolist())
    failures = []
    if not len(df):
        failures.append("file has no rows")
    if any(empty_id_counts.values()):
        failures.append("one or more identity/group fields are missing")
    if invalid_sensor_time or invalid_inspection_time:
        failures.append("one or more timestamps are invalid")
    if over_tolerance:
        failures.append("sensor/inspection time gap exceeds the declared tolerance or is invalid")
    if duplicate_keys:
        failures.append("duplicate sample/inspection keys exist")
    blank_quality_label = df["quality_label"].isna() | df["quality_label"].astype("string").str.strip().eq("")
    blank_quality_method = df["quality_method"].isna() | df["quality_method"].astype("string").str.strip().eq("")
    if blank_quality_label.any() or blank_quality_method.any():
        failures.append("quality labels or their inspection method are missing")
    if df["crop"].nunique(dropna=True) != 1:
        failures.append("file must contain one crop; keep crop studies separate")
    if len(studies) != 1:
        failures.append("file must contain one study; do not pool unrelated studies")
    if not any(v >= 2 for v in groups_per_crop.values()):
        failures.append("fewer than two independent lots are available for grouped evaluation")
    if any(df[c].notna().sum() == 0 for c in ENV_COLUMNS + MQ_COLUMNS):
        failures.append("at least one required sensor channel is entirely missing")

    return {
        "input": str(path), "rows": int(len(df)), "columns": list(df.columns),
        "crop_values": crops, "study_ids": studies,
        "quality_label_counts": {str(k): int(v) for k, v in label_counts.items()},
        "independent_lots_by_quality_label": label_lot_counts,
        "unique_lots_by_crop": {str(k): int(v) for k, v in groups_per_crop.items()},
        "unique_storage_units_by_crop": {str(k): int(v) for k, v in storage_units_per_crop.items()},
        "missing_identity_values": empty_id_counts,
        "invalid_sensor_timestamps": invalid_sensor_time,
        "invalid_inspection_timestamps": invalid_inspection_time,
        "pairing_rule": "absolute sensor/inspection timestamp difference",
        "max_pair_gap_seconds": float(max_pair_gap_seconds),
        "rows_over_pair_tolerance": over_tolerance,
        "duplicate_sample_inspection_key_rows": duplicate_keys,
        "missing_feature_values": feature_missingness,
        "ready_for_training": not failures,
        "blocking_issues": failures,
        "cautions": [
            "This audit checks a declared pairing; it cannot prove that source records were joined correctly.",
            "Do not map study-specific quality labels to acceptable/warning/spoiled without an explicit crop-specific rubric.",
            "Readiness is a schema/data-integrity preflight, not evidence of adequate sample size or model validity.",
            "Split by lot_id, and consider a second evaluation grouped by storage_unit_id or acquisition run.",
            "Survival training needs repeated inspections and explicit event/censor follow-up fields; this table alone is not sufficient.",
        ],
    }
