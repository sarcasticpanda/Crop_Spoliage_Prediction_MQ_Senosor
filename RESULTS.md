# Results and checks

> **SIMULATION ONLY.** These scores show how well the models reproduce this simulator. They are not verified crop-quality accuracy or real shelf-life estimates.

The original v1 results below remain unchanged. A separate assumption-driven v2 dataset has now been generated and trained; its full data assumptions and run results are in [SIMULATION_V2.md](SIMULATION_V2.md), with its models and metric files under `artifacts_v2/`.

## Data check

The ZIP, `READ_ME_FIRST.md`, simulator code, summary, and CSV were inspected. The CSV has 120,000 rows and 42 columns. It has 500 starting lots, six paths per lot, and 40 readings per path. The 2030 dates and all readings are fictional. No real AeroSense workbook was available; the only workbook was the simulator summary.

Duplicate audit: there are **0 exact duplicate rows** and 0 repeated trajectory/time keys. There are 100,000 repeated lot/age keys because each starting lot branches into six paths at the same 40 ages. These are separate simulated trajectories sharing one simulated starting lot. The independent grouping unit is therefore 500 simulated lots, not 120,000 rows or 3,000 independent lots. If “no replicas” means no shared starting lot or branched trajectories, this supplied dataset cannot be represented as an independent-lot experiment; grouped splitting only prevents train/test overlap.

The simulator assigned status using its hypothetical inspection-defect percentage: acceptable <7%, warning from 7% to <15%, and spoiled ≥15%. These are simulator assumptions, not accepted thresholds for all five crops. The real tomato table has only storage-scenario labels. The potato figure workbook shows some study-specific quality criteria (for example, rot-rate/firmness/sugar thresholds), but those are not linked to individual timestamped sensor rows and cannot be imported as five-crop status cutoffs.

| Crop | Rows | Lots | Paths | Age range (days) | Train events / censored | Test events / censored |
|---|---:|---:|---:|---:|---:|---:|
| Wheat | 24,000 | 100 | 600 | 0 to 273 | 258 / 222 | 65 / 55 |
| Maize | 24,000 | 100 | 600 | 0 to 273 | 326 / 154 | 78 / 42 |
| Table potato | 24,000 | 100 | 600 | 0 to 39 | 321 / 159 | 79 / 41 |
| Cured dry onion | 24,000 | 100 | 600 | 0 to 39 | 277 / 203 | 73 / 47 |
| Spinach | 24,000 | 100 | 600 | 0 to 9.75 | 425 / 55 | 113 / 7 |

Status totals are 37,884 acceptable, 44,199 warning, and 37,917 spoiled. Grain moisture is missing on 72,000 vegetable rows. Failure and remaining-day fields are blank for 985 paths that were still acceptable when monitoring ended. Times increase within every path.

The environment field names for temperature, dew point, and heat index did not match the CSV because of a degree-symbol encoding issue. The names were fixed. The original status results were checked against the saved models and matched. The fixed train/test lot split is 400/100, with 20 test lots per crop.

## Status models

The models use readings available at or before prediction time. They exclude status and inspection outcomes, failure targets, IDs, scenario names, fictional dates, and post-failure flags. History summaries include the current reading but no future readings. Missing values are handled inside the model pipeline.

All rows below are test readings from the same 100 held-out lots. The scores describe the simulator only.

| Features | Model | Grouped CV macro F1 | Test macro F1 | Spoiled recall | Log loss | Brier score |
|---|---|---:|---:|---:|---:|---:|
| Any | Majority baseline | -- | 0.1794 | 0.0000 | 1.0962 | 0.6650 |
| Environment | Random Forest | -- | 0.8226 | 0.8399 | 0.4077 | 0.2553 |
| Environment | XGBoost | -- | 0.8360 | 0.8445 | 0.3921 | 0.2382 |
| Nine MQ | Random Forest | -- | 0.9230 | 0.9526 | 0.1909 | 0.1138 |
| Nine MQ | XGBoost | -- | 0.9251 | 0.9526 | 0.1738 | 0.1084 |
| Environment + MQ | Random Forest | 0.9309 +/- 0.0030 | 0.9309 | 0.9587 | 0.1783 | 0.1055 |
| Environment + MQ | XGBoost | 0.9301 +/- 0.0036 | 0.9300 | 0.9562 | 0.1622 | 0.1004 |

Only the combined Random Forest and XGBoost were tuned with five-fold grouped cross-validation. All paths from a lot stayed together. Preprocessing was fitted separately inside each fold. The models use their own probabilities without an extra calibration step.

XGBoost was selected for the combined model because its probability scores were better on this simulator. The paired 95% confidence intervals for XGBoost minus Random Forest were:

| Metric | Difference | 95% whole-lot bootstrap interval |
|---|---:|---:|
| Macro F1 | -0.0009 | [-0.0034, 0.0014] |
| Spoiled recall | -0.0025 | [-0.0061, 0.0006] |
| Log loss | -0.0161 | [-0.0217, -0.0092] |
| Brier score | -0.0051 | [-0.0079, -0.0017] |

The intervals for macro F1 and spoiled recall include zero, so those differences are unclear. Log loss and Brier favor XGBoost here. Random Forest is still a similar benchmark. Neither result proves how the models work on real crops.

### Additional XGBoost vs LightGBM comparison

LightGBM was not rejected based on earlier test evidence; it had not been run. It is now compared with XGBoost using the same combined features and a nested, lot-grouped validation on the original 400 training lots. Five outer folds each validate on 80 whole lots; each outer training fold tunes its parameters in three inner grouped folds. The fixed 100-lot test set was not used for fitting, tuning, or scoring. These are pooled out-of-fold results, not a new final holdout score. Native class probabilities were evaluated without post-hoc calibration.

| Model | Pooled OOF macro F1 | Fold macro F1 mean ± SD | Spoiled recall | Log loss | Brier |
|---|---:|---:|---:|---:|---:|
| XGBoost | 0.9302 | 0.9302 ± 0.0036 | 0.9551 | 0.1646 | 0.1014 |
| LightGBM | 0.9300 | 0.9300 ± 0.0027 | 0.9555 | 0.1663 | 0.1022 |

| Crop | XGBoost macro F1 / spoiled recall | LightGBM macro F1 / spoiled recall |
|---|---:|---:|
| Maize | 0.9251 / 0.9458 | 0.9250 / 0.9484 |
| Cured dry onion | 0.9167 / 0.9336 | 0.9169 / 0.9329 |
| Table potato | 0.9366 / 0.9524 | 0.9367 / 0.9529 |
| Spinach | 0.9438 / 0.9758 | 0.9432 / 0.9752 |
| Wheat | 0.9233 / 0.9481 | 0.9227 / 0.9483 |

The scores are effectively tied on this simulator. XGBoost has slightly lower log loss and Brier; LightGBM has slightly higher spoiled recall. These small differences do not justify saying one is generally better. For the current demo, retain XGBoost because it is already integrated and the results are comparable. LightGBM remains a valid alternative to re-evaluate on independently collected, inspected lots. Both scores are simulator reconstruction, not crop accuracy.

The nested comparison used XGBoost `n_estimators=240`, learning rate 0.05, depth candidates 3 and 5, subsample 0.85, column subsample 0.85, and L2 regularization 2. LightGBM used 240 estimators, learning rate 0.05, leaf candidates 7, 15, and 31, subsample 0.85, column subsample 0.85, L2 regularization 2, and minimum child samples 20. Best depth was 5 in each XGBoost outer fold; LightGBM selected 7 leaves in the first three folds and 15 in the last two. Run `python -m crop_prototype.cli compare-boosting` to reproduce; detailed fold and per-crop metrics are saved in `artifacts/boosting_comparison.json` and `.csv`.

The selected XGBoost recalls were 0.9311 for acceptable, 0.9032 for warning, and 0.9562 for spoiled. Its confusion matrix (true rows; predicted columns in acceptable, warning, spoiled order) was:

```text
[[6768,  501,    0],
 [ 627, 7981,  228],
 [   0,  346, 7549]]
```

Per-crop macro F1 / spoiled recall:

| Crop | Environment XGBoost | MQ XGBoost | Combined RF | Combined XGBoost |
|---|---:|---:|---:|---:|
| Wheat | 0.8153 / 0.8053 | 0.9134 / 0.9481 | 0.9242 / 0.9509 | 0.9185 / 0.9536 |
| Maize | 0.8249 / 0.8441 | 0.9202 / 0.9372 | 0.9274 / 0.9457 | 0.9232 / 0.9394 |
| Potato | 0.8444 / 0.8448 | 0.9348 / 0.9522 | 0.9375 / 0.9600 | 0.9400 / 0.9621 |
| Onion | 0.8120 / 0.7934 | 0.9105 / 0.9376 | 0.9166 / 0.9482 | 0.9165 / 0.9391 |
| Spinach | 0.8689 / 0.8868 | 0.9428 / 0.9706 | 0.9452 / 0.9737 | 0.9506 / 0.9718 |

Full class scores and confusion matrices for all feature/model combinations are in `artifacts/advanced_status_metrics.json`.

### Starting inspection field

The same models were also run with the starting inspection value added. Results changed only slightly. The value would need to be measured in a real study.

| Model | Starting inspection used? | Macro F1 | Spoiled recall | Log loss | Brier |
|---|---|---:|---:|---:|---:|
| Random Forest | No | 0.9309 | 0.9587 | 0.1783 | 0.1055 |
| Random Forest | Yes | 0.9296 | 0.9574 | 0.1796 | 0.1060 |
| XGBoost | No | 0.9300 | 0.9562 | 0.1622 | 0.1004 |
| XGBoost | Yes | 0.9311 | 0.9540 | 0.1636 | 0.1010 |

## Survival models

A survival event is the first simulated spoiled inspection. Warning is not a failure. A failed path has a recorded interval between checks. A path that remains acceptable at the end is censored; it is not assigned a fake failure day.

The split is still 400 training and 100 test lots. The test set has 15,913 at-risk intervals and 408 event intervals. Models use readings from the start of each interval. Readings at or after the failure endpoint are left out.

| Model | Test interval Brier | Test interval AUC |
|---|---:|---:|
| Discrete logistic hazard | 0.05504 | 0.98297 |
| Discrete XGBoost hazard | 0.01545 | 0.98036 |

These scores measure prediction of failure by the next check. AUC is not an estimate of days remaining.

For each crop, the calendar checkpoint was chosen from training data only: the 25th percentile of failure-check times, rounded up to the inspection schedule. The table compares the chance of failure at the next check from the listed starting time. AFT gives the chance of failure by the listed calendar day.

| Crop | Check day | Start of hazard interval | Test paths at start | Failures at next check | Hazard Brier: crop baseline / logistic / XGBoost | AFT Brier |
|---|---:|---:|---:|---:|---:|---:|
| Wheat | 105 | 98 | 106 | 2 | 0.01852 / 0.03577 / 0.00248 | 0.04545 |
| Maize | 105 | 98 | 99 | 2 | 0.01980 / 0.03295 / 0.00703 | 0.06901 |
| Potato | 18 | 17 | 95 | 6 | 0.05932 / 0.06303 / 0.03570 | 0.12454 |
| Cured dry onion | 16 | 15 | 101 | 4 | 0.03855 / 0.04336 / 0.02980 | 0.09007 |
| Spinach | 2.75 | 2.5 | 92 | 4 | 0.04197 / 0.12386 / 0.02551 | 0.11304 |

Calibration compares the model's average chance with what happened. Values below are predicted / observed. Hazard values refer to failure at the next check; AFT values refer to failure by the calendar check.

| Crop | XGBoost hazard | XGBoost AFT |
|---|---:|---:|
| Wheat | 0.0255 / 0.0189 | 0.1979 / 0.1333 |
| Maize | 0.0168 / 0.0202 | 0.2481 / 0.1917 |
| Potato | 0.0499 / 0.0632 | 0.2823 / 0.2583 |
| Cured dry onion | 0.0138 / 0.0396 | 0.2076 / 0.1917 |
| Spinach | 0.0530 / 0.0435 | 0.3100 / 0.2667 |

The AFT scores use censoring-aware Brier calculations. All paths were observed through these checkpoints in this simulator, so the known-outcome share and censoring survival were both 1.0. This may not be true for future data.

The AFT model uses the known failure interval for failed paths and the known monitoring end for censored paths. Its median distance from a predicted failure time to the observed failure interval was 7.81 days; the average was 37.65 days. These scores include only paths that failed. They are not exact-day errors.

The hazard predicts one inspection at a time. The project does not claim a failure time between inspections. Future-path results need future environment and MQ readings. They do not show that cooling causes more storage days.

## Current input interface check

The local web interface loads saved models without retraining. Manual prediction and uploaded-CSV batch scoring support combined, environment-only, and nine-MQ-only status models. A two-row combined CSV smoke check returned two predictions with no per-row errors; the saved example also returned status probabilities in all three modes. The combined mode only returns next-inspection risk when a positive interval is supplied. Environment-only and MQ-only return status only. Missing readings are reported; they are not fabricated. Files from different studies/devices are not automatically joined. Combined inputs must already refer to the same lot and matched time.

## Separate public real-data experiment: tomato scenario

Zenodo 15469472's 52-row random-sampling table contains 18 Tc, 16 Trt, and 18 Trtd samples. The paper describes these as separately sampled tomatoes; numeric `Sample ID` values are reused across storage scenarios, so the audit key is scenario plus sample ID. The continuous table contains repeated histories of nine additional tracked tomatoes. It was kept out of training; one day-3 record from each tomato was used as a small separate-cohort test (n=9). The target is **storage scenario**, not acceptable/warning/spoiled or failure time. The released CSV has 12 MQ-family channels and five weight/color measurements; it has no temperature/RH fields and no MQ7. “Paired” here means sensor + weight/color from the same tomato, not AeroSense + the exact nine-channel array.

No tuning was performed on this small cohort. Fixed majority, Random Forest, XGBoost, and SVC configurations were compared using (a) five-fold stratified sample-level CV, similar to the source study's validation style, and (b) leave-one-storage-day-out CV, where all rows from a day are held out together. The latter is a stricter check against day-specific patterns. Scores pool out-of-fold predictions across all 52 rows; the six day groups and one study run are not an external validation cohort.

| Inputs | Model | Validation | Macro F1 | Accuracy | Log loss | Multiclass Brier |
|---|---|---|---:|---:|---:|---:|
| 12 MQ | Majority | Leave one day out | 0.171 | 0.346 | 1.101 | 0.668 |
| 12 MQ | Random Forest | Leave one day out | 0.514 | 0.519 | 1.024 | 0.594 |
| 12 MQ | XGBoost | Leave one day out | 0.498 | 0.519 | 1.005 | 0.601 |
| 12 MQ | XGBoost | Stratified 5-fold | 0.547 | 0.558 | 0.987 | 0.579 |
| MQ + weight/color | Random Forest | Leave one day out | 0.472 | 0.481 | 1.032 | 0.618 |
| MQ + weight/color | XGBoost | Leave one day out | 0.546 | 0.558 | 1.037 | 0.629 |
| MQ + weight/color | XGBoost | Stratified 5-fold | 0.491 | 0.519 | 1.013 | 0.597 |
| Any | Majority | Stratified 5-fold | 0.227 | 0.327 | 1.101 | 0.669 |

The best strict day-held-out macro F1 was 0.546 for paired-input XGBoost; its scenario recalls were Tc 0.722, Trt 0.375, and Trtd 0.556. Ordinary stratified results did not show a consistent benefit from adding weight/color: XGBoost macro F1 was 0.547 with MQ alone and 0.491 with MQ plus weight/color. The protocols disagree about the best feature set, and this small dataset is too limited to select a real deployment model. This is a working real-tomato **scenario** demonstration only.

The additional held-out continuous cohort is the more important warning. Models trained on the 52 random tomatoes and tested on day 3 of the nine tracked tomatoes scored:

| Inputs | Model | Independent test n | Macro F1 | Accuracy | Log loss | Multiclass Brier |
|---|---|---:|---:|---:|---:|---:|
| 12 MQ | XGBoost | 9 tomatoes | 0.278 | 0.333 | 1.247 | 0.770 |
| 12 MQ | SVC | 9 tomatoes | 0.533 | 0.556 | 1.078 | 0.655 |
| MQ + weight/color | Random Forest | 9 tomatoes | 0.356 | 0.444 | 1.181 | 0.691 |
| MQ + weight/color | XGBoost | 9 tomatoes | 0.278 | 0.333 | 1.229 | 0.707 |
| MQ + weight/color | SVC | 9 tomatoes | 0.345 | 0.444 | 1.012 | 0.616 |

This small holdout does not support a robust winner; the XGBoost paired score is close to chance for three balanced classes. The 52-row model must not be advertised as a validated quality model. The test estimates transfer only to these nine tracked tomatoes within the same study, not to new harvests, devices, or other crops.

Full out-of-fold metrics are in `artifacts/public_tomato/metrics.json`, held-out-by-day predictions are in `oof_predictions.csv`, and one held-out example is in `heldout_tomato_example.json`. Full-data estimators are saved in the same folder for demonstrations; they were fitted on all 52 rows and are **not** the validation models used to calculate the scores.

The downloaded potato archive has 66,363 environment rows across 17 sensor nodes and 2024–2025, but no MQ array and no per-row quality targets. All timestamps parse; timestamp/node keys are unique. The workbook has 27,236 missing air-temperature entries, 27,311 missing RH entries, 50,077 missing tuber-core-temperature entries, and 55,002 missing CO2 entries. Its figure tables contain summaries and limited replicate values without a validated sample-to-sensor-time join. No potato quality model was trained because creating those joins or labels would fabricate evidence. The nine-MQ archive also lacks inspected spoilage labels. These datasets remain separate and cannot be merged into the five-crop AeroSense+MQ failure model.

## Example prediction

The saved example input predicted acceptable for a simulated maize reading at day 0:

- Acceptable: 0.99936
- Warning: 0.00059
- Spoiled: 0.00005
- Chance of a spoiled inspection by the next 7-day check: 0.000071

This is marked **SIMULATION ONLY**. The command loads saved models and does not retrain them. It does not output days remaining.

## Commands used

Run from the project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.cli inspect
.\.venv\Scripts\python.exe -m crop_prototype.cli train
.\.venv\Scripts\python.exe -m crop_prototype.cli validate
.\.venv\Scripts\python.exe -m crop_prototype.cli bootstrap
.\.venv\Scripts\python.exe -m crop_prototype.cli initial-inspection --out artifacts_with_initial
.\.venv\Scripts\python.exe -m crop_prototype.cli survival
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_prediction_input.json
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato-predict --input examples\public_tomato_mq_input.json --model mq_12__svc
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

All 20 focused checks passed in the project `.venv`. They check the data keys and order, group split, forbidden model inputs, past/current history, survival censoring, failure intervals, explicit future readings, missing prediction inputs, web API responses, CSV scoring, and rejection of target fields. Running the same command with system Python instead of `.venv` failed before tests loaded because that Python has an incompatible pandas/NumPy installation; use the documented virtual-environment command.

## What is still needed

There is no public dataset here with AeroSense, the requested exact nine MQ channels, and independent crop inspections from the same lots and times. A real AeroSense workbook was not present. The tomato scenario experiment is weak on its nine-tomato held-out cohort and does not predict quality or failure time. No potato spoilage model was trained because the downloaded histories and summary quality values have no verified lot/time linkage. A real paired crop study is still needed before claiming crop accuracy or shelf life.
