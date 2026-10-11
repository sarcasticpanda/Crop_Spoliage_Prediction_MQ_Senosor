from __future__ import annotations
import argparse, json
from pathlib import Path
from .data import DEFAULT_CSV, load_simulated, load_aerosense_real
from .modeling import train_status
from .boosting_comparison import compare_boosting
from .survival import train_survival
from .validation import evaluate_and_tune, bootstrap_saved_holdout, compare_initial_inspection
from .diagnostics import run_diagnostics
from .inference import predict_payload
from .public_studies import train_public_tomato, predict_public_tomato
from .paired_data import audit_paired_csv
from .simulation_v2 import write_v2

def inspect(path):
    df = load_simulated(path)
    ret = {"rows": len(df), "columns": len(df.columns), "columns_list": list(df.columns),
           "data_origin": df.data_origin.value_counts(dropna=False).to_dict(),
           "rows_per_crop": df.crop.value_counts().sort_index().to_dict(),
           "unique_lots": int(df.sim_lot_id.nunique()), "lots_per_crop": df.groupby("crop").sim_lot_id.nunique().to_dict(),
           "unique_trajectories": int(df.sim_trajectory_id.nunique()), "trajectories_per_crop": df.groupby("crop").sim_trajectory_id.nunique().to_dict(),
           "status_counts": df.status_SIM.value_counts().to_dict(),
           "missing_values": df.isna().sum().loc[lambda s:s.gt(0)].to_dict(),
           "storage_age_range_days": df.groupby("crop").storage_age_days.agg(["min","max"]).to_dict("index"),
           "time_order": "strictly increasing within every trajectory"}
    return ret

def predict_from_input(input_path, out_dir):
    """Load saved models and predict from explicit current/history inputs."""
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    output = predict_payload(payload, out_dir)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    Path(out_dir, "prediction.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))

def main():
    parser = argparse.ArgumentParser(prog="crop-prototype", description="Simulation-only stored crop research prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    paired = sub.add_parser("audit-paired", help="preflight a real, already-matched crop sensor/inspection CSV")
    paired.add_argument("--input", required=True, help="canonical CSV with one row per matched sensor/inspection record")
    paired.add_argument("--out", default="artifacts/real_paired_audit.json")
    paired.add_argument("--max-pair-gap-seconds", type=float, default=300.0)
    v2 = sub.add_parser("generate-v2", help="write a separate assumption-driven synthetic paired dataset")
    v2.add_argument("--output", default="data/simulated_paired_v2.csv")
    v2.add_argument("--lots-per-crop", type=int, default=100)
    v2.add_argument("--seed", type=int, default=20261031)
    for name in ("inspect", "train", "evaluate", "predict", "survival", "validate", "bootstrap", "initial-inspection", "aerosense", "diagnose", "compare-boosting", "public-tomato", "public-tomato-predict"):
        p = sub.add_parser(name)
        p.add_argument("--data", default=str(DEFAULT_CSV))
        p.add_argument("--out", default="artifacts")
        p.add_argument("--initial-inspection", action="store_true", help="include the initial inspection measurement as a feature")
        if name == "predict": p.add_argument("--input", required=True, help="JSON file with one explicit current reading")
        if name == "aerosense": p.add_argument("--workbook", required=True)
        if name == "public-tomato": p.add_argument("--source-zip", default=".review_data/tomato_sensor_laboratory.zip")
        if name == "public-tomato-predict":
            p.add_argument("--input", required=True, help="JSON with explicit numeric input features for one tomato")
            p.add_argument("--model", default="mq_12__svc", help="saved model filename stem under artifacts/public_tomato")
    args = parser.parse_args()
    if args.command == "audit-paired":
        report = audit_paired_csv(args.input, args.max_pair_gap_seconds)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return
    if args.command == "aerosense":
        raw, report = load_aerosense_real(args.workbook)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        Path(args.out, "aerosense_data_quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        raw.loc[raw.parsed_timestamp.isna()].to_csv(Path(args.out, "aerosense_invalid_timestamps.csv"), index=False)
        print(json.dumps(report, indent=2)); return
    if args.command == "generate-v2":
        print(json.dumps(write_v2(args.output, args.lots_per_crop, args.seed), indent=2)); return
    if args.command == "predict":
        predict_from_input(args.input, args.out)
        return
    if args.command == "public-tomato":
        report = train_public_tomato(args.source_zip, Path(args.out) / "public_tomato")
        print(json.dumps({"source": report["source"], "rows": report["rows"],
                          "target_counts": report["target_counts"], "output_dir": str(Path(args.out) / "public_tomato"),
                          "scores": [{"feature_set": m["feature_set"], "model": m["model"],
                                      "validation_protocol": m["validation_protocol"],
                                      "macro_f1_oof": m["macro_f1_oof"], "accuracy_oof": m["accuracy_oof"],
                                      "log_loss_oof": m["log_loss_oof"], "multiclass_brier_oof": m["multiclass_brier_oof"]}
                                     for m in report["modes"]],
                          "independent_continuous_test": [{"feature_set": m["feature_set"], "model": m["model"],
                                                            "n_independent_tomatoes": m["n_independent_tomatoes"],
                                                            "macro_f1": m["macro_f1"], "accuracy": m["accuracy"],
                                                            "log_loss": m["log_loss"], "multiclass_brier": m["multiclass_brier"]}
                                                           for m in report["independent_continuous_test"]]}, indent=2))
        return
    if args.command == "public-tomato-predict":
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = predict_public_tomato(payload, args.model, Path(args.out) / "public_tomato")
        Path(args.out, "public_tomato").mkdir(parents=True, exist_ok=True)
        Path(args.out, "public_tomato", "prediction.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return
    df = load_simulated(args.data)
    if args.command == "inspect":
        print(json.dumps(inspect(args.data), indent=2)); return
    if args.command == "survival":
        print(json.dumps(train_survival(df, args.out), indent=2)); return
    if args.command == "validate":
        print(json.dumps(evaluate_and_tune(df, args.out), indent=2)); return
    if args.command == "bootstrap":
        print(json.dumps(bootstrap_saved_holdout(df, args.out), indent=2)); return
    if args.command == "initial-inspection":
        print(json.dumps(compare_initial_inspection(df, args.out), indent=2)); return
    if args.command == "diagnose":
        print(json.dumps(run_diagnostics(df, args.out), indent=2)); return
    if args.command == "compare-boosting":
        print(json.dumps(compare_boosting(df, args.out), indent=2)); return
    payload, fitted, _ = train_status(df, args.out, include_initial=args.initial_inspection)
    print(json.dumps({"warning": payload["warning"], "split": {
            "train_lots": len(payload["split"]["train_lots"]), "test_lots": len(payload["split"]["test_lots"]),
            "train_rows": payload["split"]["train_rows"], "test_rows": payload["split"]["test_rows"]},
            "metrics_file": str(Path(args.out) / "status_metrics.json"),
            "scores": [{"feature_set": x["feature_set"], "model": x["model"], "macro_f1": x["macro_f1"],
                        "log_loss": x["log_loss"], "multiclass_brier": x["multiclass_brier"]} for x in payload["results"]]}, indent=2))

if __name__ == "__main__": main()
