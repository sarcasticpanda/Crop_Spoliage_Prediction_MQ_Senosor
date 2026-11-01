"""Audit downloaded real-data sources without joining unrelated studies.

Run from the project root with:
    .\.venv\Scripts\python.exe data\real_sources\audit_sources.py

This script writes a source inventory only. It never creates labels, simulated
measurements, lot IDs, or cross-study joins.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
OUTPUT = ROOT / "source_audit.json"
MQ_COLUMNS = [f"MQ{i}" for i in (2, 3, 4, 5, 6, 7, 8, 9, 135)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def audit_nine_mq() -> dict:
    folder = EXTRACTED / "zenodo_17285312_nine_mq" / "AllSmaples-Report"
    recordings = []
    all_rows = 0
    for path in sorted(folder.glob("*.csv")):
        frame = pd.read_csv(path)
        tick = pd.to_numeric(frame.get("Ticks"), errors="coerce")
        match = re.match(r"^(.*?)(?:\s+D([1-5]))?\.csv$", path.name, flags=re.I)
        crop = match.group(1).strip() if match else path.stem
        day = int(match.group(2)) if match and match.group(2) else None
        span_seconds = (tick.max() - tick.min()) / 1000 if tick.notna().any() else None
        sensor_cols = [column for column in MQ_COLUMNS if column in frame.columns]
        record = {
            "file": path.name,
            "crop_or_mixture_from_filename": crop,
            "day_from_filename_only": day,
            "rows_raw": len(frame),
            "channels_present": sensor_cols,
            "all_nine_channels_present": set(sensor_cols) == set(MQ_COLUMNS),
            "missing_cells": int(frame.isna().sum().sum()),
            "duplicate_rows": int(frame.duplicated().sum()),
            "zero_all_sensor_rows": int(frame[sensor_cols].eq(0).all(axis=1).sum()) if sensor_cols else None,
            "tick_start": jsonable(tick.min()),
            "tick_end": jsonable(tick.max()),
            "tick_span_seconds": round(float(span_seconds), 2) if span_seconds is not None else None,
            "median_tick_step_ms": round(float(tick.diff().median()), 3) if tick.notna().any() else None,
        }
        recordings.append(record)
        all_rows += len(frame)
    tomato = [r for r in recordings if r["crop_or_mixture_from_filename"].lower() == "tomato"]
    return {
        "source": "Zenodo 17285312 Food Freshness Electronic Nose Dataset",
        "url": "https://zenodo.org/records/17285312",
        "recording_file_count": len(recordings),
        "raw_point_count": all_rows,
        "tomato_day_file_count": len(tomato),
        "tomato_day_file_rows": sum(r["rows_raw"] for r in tomato),
        "all_files_have_exact_nine_channels": all(r["all_nine_channels_present"] for r in recordings),
        "limitations": [
            "Each CSV is a short raw sensor recording, not an independent per-lot inspection row.",
            "Files named D1-D5 provide day-like filenames, but the archive does not provide a stable physical-lot ID or an inspected spoilage target.",
            "The source describes room-temperature measurement; it has no paired temperature/RH history.",
            "The 3-minute high-frequency rows must not be treated as thousands of independent fruit samples.",
        ],
        "recordings": recordings,
    }


def audit_tomato() -> dict:
    folder = EXTRACTED / "zenodo_15469472_tomato" / "Sensor and Laboratory Data"
    result = {
        "source": "Zenodo 15469472 Tomato e-nose, image and laboratory data",
        "url": "https://zenodo.org/records/15469472",
        "tables": {},
    }
    for path in sorted(folder.glob("*.csv")):
        frame = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        id_scenario = frame.groupby("Storage Scenario")["Sample ID"].nunique().to_dict()
        result["tables"][path.name] = {
            "rows": len(frame),
            "columns": list(frame.columns),
            "missing_by_column": {str(k): int(v) for k, v in frame.isna().sum().items()},
            "unique_numeric_ids": int(frame["Sample ID"].nunique()),
            "scenario_sample_counts": {str(k): int(v) for k, v in id_scenario.items()},
            "storage_scenarios": {str(k): int(v) for k, v in frame["Storage Scenario"].value_counts().items()},
            "storage_days": sorted(int(v) for v in frame["Storage Day"].dropna().unique()),
            "distinct_scenario_id_keys": int(frame[["Storage Scenario", "Sample ID"]].drop_duplicates().shape[0]),
        }
    result["interpretation"] = [
        "The 12 Rs/R0 channels, weight and colour are measured on sampled tomatoes.",
        "The prediction target used in the current project is storage scenario, not independently inspected acceptable/warning/spoiled status or time-to-failure.",
        "No AeroSense-style temperature/RH time history is supplied; the channel set is not the project's exact nine MQ channels.",
        "Use the continuous table for descriptive repeated histories only; group using scenario plus sample ID and respect its very small number of tracked tomatoes.",
    ]
    return result


def audit_potato() -> dict:
    import openpyxl

    folder = EXTRACTED / "mendeley_potato_environment" / "Active evaporative cooling by ultrasonic humidific"
    data_path = folder / "IoT_Data_Consolidee_17noeuds.xlsx"
    frame = pd.read_excel(data_path, sheet_name="Data")
    ts = pd.to_datetime(frame["Timestamp"], errors="coerce")
    data = {
        "source": "Mendeley potato storage environment archive",
        "url": "https://data.mendeley.com/datasets/sbwxmtpj47/1",
        "environment_table": {
            "rows": len(frame),
            "columns": list(frame.columns),
            "missing_by_column": {str(k): int(v) for k, v in frame.isna().sum().items()},
            "invalid_timestamp_rows": int(ts.isna().sum()),
            "timestamp_start": jsonable(ts.min()),
            "timestamp_end": jsonable(ts.max()),
            "storage_modes": {str(k): int(v) for k, v in frame["Mode_Stockage"].value_counts(dropna=False).items()},
            "campaigns": {str(k): int(v) for k, v in frame["Campagne"].value_counts(dropna=False).items()},
            "sensor_nodes": int(frame["Noeud_Source"].nunique(dropna=True)),
            "unique_timestamps": int(ts.nunique(dropna=True)),
            "unique_timestamp_node_pairs": int(frame.assign(_ts=ts).drop_duplicates(["_ts", "Noeud_Source"]).shape[0]),
        },
        "quality_workbook": {
            "file": "Figures_Data_Fig3_a_Fig11.xlsx",
            "sheets": openpyxl.load_workbook(folder / "Figures_Data_Fig3_a_Fig11.xlsx", read_only=True, data_only=True).sheetnames,
            "limitation": "Quality values are summarized by figure/campaign/mode; no verified timestamped join to the IoT row-level history or lot inspection labels is supplied.",
        },
        "interpretation": [
            "Useful real potato environmental histories across storage modes and campaigns.",
            "No MQ readings are included.",
            "Do not use storage mode as a spoilage label; it is an environment/treatment category.",
            "A simulator may sample whole measured environmental paths, but any generated MQ and labels must remain marked synthetic.",
        ],
    }
    return data


def audit_environment_csv(filename: str, source_name: str, url: str, label_note: str) -> dict:
    path = RAW / filename
    frame = pd.read_csv(path)
    normalized = frame.copy()
    normalized.columns = [str(c).strip() for c in normalized.columns]
    data = {
        "source": source_name,
        "url": url,
        "rows": len(frame),
        "columns": list(frame.columns),
        "missing_by_column": {str(k): int(v) for k, v in frame.isna().sum().items()},
        "exact_duplicate_rows": int(frame.duplicated().sum()),
        "no_timestamp_or_lot_key": not any("time" in str(c).lower() or "date" in str(c).lower() or "lot" in str(c).lower() or "sample" in str(c).lower() for c in frame.columns),
        "categories": {},
        "label_note": label_note,
    }
    for col in frame.columns:
        if frame[col].nunique(dropna=False) <= 30:
            data["categories"][str(col)] = {str(k): int(v) for k, v in frame[col].value_counts(dropna=False).items()}
    return data


def main() -> None:
    inventory = []
    for path in sorted(RAW.iterdir()):
        if path.is_file():
            inventory.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    report = {
        "audit_scope": "Public source files only. No sources are joined and no synthetic values are added.",
        "raw_files": inventory,
        "nine_mq": audit_nine_mq(),
        "tomato_sensor_lab": audit_tomato(),
        "potato_environment": audit_potato(),
        "environment_fruit_conditions": audit_environment_csv(
            "github_environment_fruit_spoilage_Dataset.csv",
            "Mendeley czz68d9fwj.1 environment conditions CSV mirrored on GitHub",
            "https://data.mendeley.com/datasets/czz68d9fwj/1",
            "The source record defines Good/Bad as optimal/suboptimal storage conditions, not inspected fruit spoilage.",
        ),
        "intellistore": audit_environment_csv(
            "github_intellistore_environment_Dataset.csv",
            "IntelliStore environment and spoilage-labelled CSV",
            "https://github.com/shivamsingha/aiot-food-storage/tree/main/datasets",
            "The CSV uses a Spoiled field but has no timestamp or lot/sample ID; independent label provenance and repeated-measure grouping cannot be audited from the released table alone.",
        ),
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=jsonable), encoding="utf-8")
    print(OUTPUT)
    print("Raw archive hashes and per-source schema/count checks written; no joins or labels were created.")


if __name__ == "__main__":
    main()
