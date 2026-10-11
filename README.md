# Stored crop quality prototype

> **SIMULATION ONLY.** This project uses made-up sensor readings, inspections, and dates. Its scores do not show how accurate the models will be on real crops.

The data covers five crops. It has 500 simulated starting lots (100 per crop), six storage paths per lot, and 40 readings per path. The nine MQ channels are response readings. They are not exact gas measurements. An audit found zero exact duplicate rows, but the six paths reuse each simulated starting lot. The 120,000 rows are repeated simulator observations, not 120,000 independent samples. See [DATASET_REVIEW.md](DATASET_REVIEW.md).

## Data summary

The ZIP includes the CSV, `READ_ME_FIRST.md`, a summary file, a workbook, and the simulator code. The CSV has 120,000 rows and 42 columns. It has 24,000 rows per crop, 500 starting lots, and 3,000 paths.

There are 37,884 acceptable, 44,199 warning, and 37,917 spoiled readings. Failure information is missing for 985 paths that were still acceptable at the end of monitoring. Grain moisture is missing for all 72,000 vegetable readings. Readings are in time order within each path.

See [RESULTS.md](RESULTS.md) for model scores and evaluation details. The real AeroSense workbook is kept separate. No simulated crop lot or label is added to it.

An additional, separate **assumption-driven synthetic v2** dataset is available for pipeline experiments. It has one generated path per simulated lot and pairs synthetic environment/MQ readings with synthetic inspections by construction. It is still not measured crop data and cannot establish real accuracy. See [SIMULATION_V2.md](SIMULATION_V2.md) for assumptions, actual v2 scores, and commands.

For a faculty-ready overview and a short presenter guide, see [PAPER_DRAFT.md](PAPER_DRAFT.md) and [DEMO_GUIDE.md](DEMO_GUIDE.md). The manuscript is explicitly a simulator audit plus a separate exploratory tomato storage-scenario study; it does not claim real crop-quality validation.

An additional three-crop Edition 2 V3 simulation is now available for tomato, table potato, and banana. It has 100 generated sample trajectories per crop with eight time points each and `acceptable / warning / high_risk` simulator labels. Tomato/banana MQ recording summaries are used only as response-scale anchors; potato MQ is generic-scale synthetic. Models are trained separately per crop with whole-trajectory holdouts. This is still simulator-only and does not validate values or labels on real produce. See [SIMULATION_V3_README.md](data/dataset_edition_2/SIMULATION_V3_README.md). Generate/train with `.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation_v3`; load a saved three-crop model with `.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation_v3 --predict examples\edition2_v3_prediction_input.json`.

See [NEXT_48_HOURS.md](NEXT_48_HOURS.md) for the research decision, source limitations, near-term work sequence, and minimum real paired-data schema.

See [REAL_DATA_AUDIT.md](REAL_DATA_AUDIT.md) for the audited public source downloads, their actual targets and keys, and a safe source-informed simulation plan. Raw downloads and extracted source copies are under `data/real_sources/`; they remain separate and are not cross-joined.

## Install (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Commands

Run these from the project folder:

```powershell
# Start the local browser interface (saved models; no retraining on launch)
.\.venv\Scripts\python.exe -m crop_prototype.web

# Inspect the data
.\.venv\Scripts\python.exe -m crop_prototype.cli inspect

# Generate v2, then train/evaluate into separate folders (v1 remains intact)
.\.venv\Scripts\python.exe -m crop_prototype.cli generate-v2 --output data\simulated_paired_v2.csv --lots-per-crop 100 --seed 20261031
.\.venv\Scripts\python.exe -m crop_prototype.cli train --data data\simulated_paired_v2.csv --out artifacts_v2
.\.venv\Scripts\python.exe -m crop_prototype.cli survival --data data\simulated_paired_v2.csv --out artifacts_v2
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_v2_prediction_input.json --out artifacts_v2
# Optional browser interface using v2 saved models
.\.venv\Scripts\python.exe -m crop_prototype.web --artifacts artifacts_v2

# Run a separate real-tomato storage-scenario study (not crop-spoilage prediction)
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato

# Score an explicit real-tomato MQ input with the saved standalone scenario model
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato-predict --input examples\public_tomato_mq_input.json --model mq_12__svc

# Train the status models
.\.venv\Scripts\python.exe -m crop_prototype.cli train

# Tune and score the combined models on the fixed test lots
.\.venv\Scripts\python.exe -m crop_prototype.cli validate

# Compare XGBoost and LightGBM with nested lot-grouped CV on the original 400 training lots
# This comparison does not score or tune on the fixed 100-lot holdout
.\.venv\Scripts\python.exe -m crop_prototype.cli compare-boosting

# Add whole-lot confidence intervals
.\.venv\Scripts\python.exe -m crop_prototype.cli bootstrap

# Compare models with the starting inspection field
.\.venv\Scripts\python.exe -m crop_prototype.cli initial-inspection --out artifacts_with_initial

# Train and score the survival models
.\.venv\Scripts\python.exe -m crop_prototype.cli survival

# Make one example prediction from saved models; this does not retrain them
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_prediction_input.json

# Optional: inspect a real AeroSense workbook by itself
.\.venv\Scripts\python.exe -m crop_prototype.cli aerosense --workbook "AeroSense Device 2(1).xlsx"

# Run the focused checks
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The local interface opens at `http://127.0.0.1:8765`. Its manual form and CSV batch scorer offer combined, environment-only, and nine-MQ-only status modes using saved models; CSV rows receive per-row errors if required fields are missing. Combined status plus next-inspection risk requires both modalities on the same row and an explicit interval. Separate files are not automatically joined: only combine readings after matching the same lot and time using a verified key and stated time tolerance. The interface also has a CSV importer with column mapping and timestamp/data completeness checks, a held-out validation view, and an optional explicit future-path projection. Uploaded CSV contents stay in server memory while the server runs and are discarded when it stops. It binds to loopback by default and has no live serial/MQ hardware connection. Excel workbooks must first be exported to CSV.

The combined crop + environment + nine-MQ models currently use the simulated five-crop dataset only. The real potato storage workbook has environmental history but no paired MQ readings or potato quality labels, so it is not joined to the MQ archive. The strongest potato rot e-nose studies found so far provide raw sample records only on request; see [DATASET_REVIEW.md](DATASET_REVIEW.md) and the copy-ready [potato data request](POTATO_DATA_REQUEST.md). A real combined potato model can be trained only if sample-level MQ, temperature/humidity, and independently assigned potato labels are supplied with joinable IDs.

When an eligible real paired CSV is available, run `python -m crop_prototype.cli audit-paired --input path\to\paired.csv` before training. The audit expects one crop and one study per file, all nine MQ response fields, the AeroSense environmental fields, lot/sample/storage-unit IDs, sensor and inspection timestamps, quality label, and the inspection method. It reports timestamp match gaps, duplicate sample/inspection keys, missingness, labels, and independent group counts. It does not join files or infer missing values. It checks schema and consistency only; it cannot prove provenance or replace grouped model validation. See `crop_prototype/paired_data.py` for the canonical field names.

Combined prediction requires crop, storage age, next inspection interval, the model's current AeroSense environment fields, all nine MQ response indices, and the three through-current history values. Environment-only and MQ-only modes require only the fields used by that saved model. Grain moisture and lot mass are optional and use the saved preprocessing pipeline's training medians when absent. The file inspector reports incomplete AeroSense-only files; it does not synthesize paired MQ or history records. Predictions remain marked **SIMULATION ONLY**.

For future-path projections, upload a separate CSV with one row per future interval. Each row must explicitly contain crop, age, environmental and history fields, all nine future MQ values, and a positive interval duration column. The app will not reuse the current reading as a future row. Projection results are conditional simulator outputs, not causal estimates of cooling benefits.

The saved split has 400 training lots and 100 test lots. Every path and reading from a starting lot stays in the same group. The test lots are kept fixed. Model tuning uses five grouped folds from the training lots. Preprocessing is fitted inside each fold. No probability calibration step is used.

The status models compare environment readings, MQ readings, and both together. They do not use status labels, inspection results, failure targets, IDs, scenario names, fictional dates, or readings after the current time. History fields include readings up to the current time only.

## Making a prediction

The input JSON must include crop, storage age, all current environment fields, all nine MQ readings, the three history fields, and the number of days until the next inspection. Use the exact field names in the example JSON. Grain moisture and lot mass may be left null. If you use the model trained with starting inspection, provide `initial_inspection_defect_pct_SIM` too.

If a required value is missing, the command reports it. It does not invent sensor values. The result gives probabilities for acceptable, warning, and spoiled, plus the chance of a spoiled inspection by the next check. It does not give a made-up number of days left. Every result is marked **SIMULATION ONLY**.

## Survival and future paths

A survival event means the first simulated `spoiled` inspection. A warning is not a survival event. Failed readings are known to fall inside a recorded inspection interval. A path that is still acceptable when monitoring ends is censored; it is not given a fake failure date. Survival predictors come from the start of each inspection interval, and readings after failure are left out.

Calendar checks are chosen using training data only. The held-out hazard score covers one inspection interval. The AFT score estimates failure by a calendar day. Neither score supports guessing between inspection times. Hazard AUC is not a days-left score.

Future-path predictions need future environment readings and all nine future MQ readings for every period. The project does not forecast these values or reuse today's MQ readings. A projection does not prove that cooling causes a longer storage life.

## Data needed for a real study

For each reading, record a stable study ID, lot ID, crop, storage path, device IDs, UTC timestamp, storage age, AeroSense readings with units, and all nine MQ readings from the same lot at the same time. Record sensor setup and calibration.

For each inspection, record its time, assessor, method, measured defects, and quality label. Record the last acceptable and first unacceptable inspections, or the end of monitoring if the lot never fails. Use independent lots for model testing. Do not match unrelated rows; set a time tolerance before joining sensors and leave unmatched readings unmatched.

The real-data studies reviewed for this project remain separate. None provides paired AeroSense, nine-MQ, and inspected failure histories for all five crops. See [DATASET_REVIEW.md](DATASET_REVIEW.md).

The separate `public-tomato` command evaluates the actual `Storage Scenario` label in the released 52-row tomato sample table, then checks one day-3 record from each of nine separately tracked tomatoes. It does not call that label freshness or spoilage. It writes grouped and sample-level CV results, out-of-fold predictions, the independent-cohort predictions, a held-out example, and standalone saved estimators to `artifacts/public_tomato/`. The input table has 12 Rs/R0 channels plus weight/color measurements; it has no AeroSense temperature/RH fields and no MQ7, so this experiment is not the same schema as the five-crop model. `public-tomato-predict` loads a standalone saved model and requires its exact input features; it predicts the tomato dataset's scenario label only. These real-tomato model files are not loaded by the simulator browser interface.

The source archive is kept locally under the git-ignored `.review_data/` folder. To download it again:

```powershell
New-Item -ItemType Directory -Force .review_data | Out-Null
Invoke-WebRequest -Uri "https://zenodo.org/records/15469472/files/Sensor%20and%20Laboratory%20Data.zip?download=1" -OutFile ".review_data\tomato_sensor_laboratory.zip"
```

## Jupyter result notebooks

Open `notebooks/01_saved_results.ipynb` to review the saved accuracy, macro F1, spoiled recall, probability scores, per-crop results, and survival horizon metrics. Open `notebooks/02_saved_model_prediction.ipynb` for a prediction from saved model files and the required input schema. Open `notebooks/03_public_tomato_study.ipynb` for the separate real-tomato scenario experiment and its small held-out cohort check. The first two notebooks show simulator results clearly; notebook 03 labels the actual source task and does not call it spoilage prediction.

To open them from PowerShell (install Jupyter once if it is not already available):

```powershell
.\.venv\Scripts\python.exe -m pip install notebook
.\.venv\Scripts\jupyter.exe notebook notebooks\01_saved_results.ipynb
```

