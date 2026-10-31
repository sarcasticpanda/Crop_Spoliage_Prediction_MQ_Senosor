# Synthetic paired sensor dataset v2

> **SIMULATION ONLY.** These are fabricated records. The dataset does not contain measured AeroSense, MQ, or crop-inspection data and cannot establish real-crop accuracy or real storage life.

## What changed from v1

V2 contains 20,000 rows: 100 synthetic lots per crop × 40 observations per lot across wheat, maize, table potato, cured dry onion, and spinach. Each unique synthetic lot has exactly one storage trajectory. There are no repeated starting lots copied into multiple counterfactual paths. Six illustrative storage-condition patterns are assigned across separate simulated lots.

Each row contains simulated environment fields and all nine MQ response indices from the same generated lot and inspection time, plus synthetic inspection and survival fields. This creates a paired-schema example for exercising the pipeline. It does **not** make those values measured or biologically independent.

## Generation assumptions

- Seed: `20261031`; change `--seed` to generate another reproducible dataset.
- Inspection ages: wheat/maize every 7 days to day 273; potato/onion every 2 days to day 78; spinach every 6 hours to day 9.75.
- Storage conditions vary by scenario and by autocorrelated temperature/RH fluctuations. Lot susceptibility, reading noise, and initial condition vary between generated lots.
- Deterioration increases with a synthetic crop-specific rate, temperature stress, and moisture stress. These coefficients are code assumptions, not estimates fitted to real crop outcomes.
- The inspection-defect value is a simulated monotone quality-decline signal with noise. `status_SIM` uses the inherited assumed thresholds: acceptable below 7%, warning from 7% to below 15%, spoiled at or above 15%. These are not accepted crop standards.
- MQ channels are dimensionless simulated response indices. They include synthetic per-lot offsets, cross-channel sensitivity, temperature/RH response, drift, and noise. They are not ppm, measured Rs/R0, or validated outputs from a physical nine-MQ device.
- AeroSense-named fields are illustrative synthetic values. This generator does not reproduce the AeroSense firmware's AQI or other calculations.
- Survival event intervals come from the first synthetic spoiled inspection. Still-acceptable lots are right-censored at the final inspection; post-failure rows are excluded by the existing survival pipeline.
- Timestamps use a fictional 2031 clock for schema compatibility and are excluded from predictor inputs.

The generator links inspection outcome and sensor response through a shared simulated deterioration state. Therefore even grouped test scores measure recovery of these assumptions, not independent confirmation that real sensors predict real quality.

## Generate and train

From PowerShell in the repository folder:

```powershell
# Regenerate the separate v2 data and summary
.\.venv\Scripts\python.exe -m crop_prototype.cli generate-v2 --output data\simulated_paired_v2.csv --lots-per-crop 100 --seed 20261031

# Inspect it
.\.venv\Scripts\python.exe -m crop_prototype.cli inspect --data data\simulated_paired_v2.csv

# Train majority, Random Forest, and XGBoost status models
.\.venv\Scripts\python.exe -m crop_prototype.cli train --data data\simulated_paired_v2.csv --out artifacts_v2

# Train discrete-time logistic/XGBoost hazards and the XGBoost AFT comparator
.\.venv\Scripts\python.exe -m crop_prototype.cli survival --data data\simulated_paired_v2.csv --out artifacts_v2

# Make a saved-model prediction from the held-out v2 example
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_v2_prediction_input.json --out artifacts_v2

# Optional: open the local input interface with the v2 saved models
.\.venv\Scripts\python.exe -m crop_prototype.web --artifacts artifacts_v2
```

V1's CSV and `artifacts/` are left intact. V2 data are saved to `data/simulated_paired_v2.csv`; generation counts and assumptions are in `data/summary_v2.json`. Status models and metrics are in `artifacts_v2/`; survival models and metrics are in the same folder.

## Actual v2 run

The generated data had 20,000 rows, 500 synthetic lot IDs and 500 trajectories. The seeded grouped holdout placed 400 whole lots (16,000 rows) in training and 100 whole lots (4,000 rows) in testing. All six scenario types appear across independent generated lots; they are not six replicated paths per lot.

### Held-out status results

All results below are **simulation-only**. The majority baseline predicts the overall most frequent class and has low macro F1.

| Features | Model | Macro F1 | Spoiled recall | Log loss | Multiclass Brier |
|---|---|---:|---:|---:|---:|
| Any | Majority | 0.2063 | 1.0000 | 1.0641 | 0.6438 |
| Environment | Random Forest | 0.8131 | 0.8270 | 0.4374 | 0.2627 |
| Environment | XGBoost | 0.8202 | 0.8449 | 0.4335 | 0.2586 |
| Nine MQ | Random Forest | 0.7861 | 0.8103 | 0.5014 | 0.3007 |
| Nine MQ | XGBoost | 0.8031 | 0.8376 | 0.4414 | 0.2707 |
| Combined | Random Forest | 0.8292 | 0.8677 | 0.4238 | 0.2503 |
| Combined | XGBoost | **0.8342** | **0.8800** | **0.3863** | **0.2318** |

Combined XGBoost is the best of these six models on all four listed metrics in this run. This is a simulator-only choice; the difference depends on the synthetic generator and is not a real deployment model-selection result.

The majority baseline gets 1.00 spoiled recall only because `spoiled` is the largest class and the baseline predicts it for every row; its macro F1 is 0.2063 and it misses every acceptable and warning reading.

The Random Forest uses 220 trees, minimum leaf size 2, and balanced subsampling. XGBoost uses depth 6, learning rate 0.06, row/column subsampling 0.85, and L2 regularization 2; grouped training validation selected 69, 136, and 106 boosting rounds for environment-only, MQ-only, and combined respectively. The outer 100-lot test set was held out from that selection.

Combined Random Forest / XGBoost per-crop macro F1:

| Crop | Random Forest | XGBoost |
|---|---:|---:|
| Wheat | 0.758 | 0.760 |
| Maize | 0.768 | 0.805 |
| Potato | 0.829 | 0.829 |
| Cured dry onion | 0.863 | 0.868 |
| Spinach | 0.833 | 0.819 |

### Held-out survival results

The 100 test lots contained 89 generated failures and 11 right-censored lots. The test hazard table had 2,197 observed at-risk intervals and 89 event intervals. Discrete XGBoost had interval Brier **0.0353** and AUC **0.8910**; discrete logistic had Brier **0.1436** and AUC **0.8719**. These are next-inspection simulator metrics, not days-left accuracy. Test event/censor counts were maize 14/6, onion 19/1, potato 20/0, spinach 20/0, and wheat 16/4. The XGBoost AFT comparator's median distance to the recorded failure interval was 6.11 days and mean absolute distance was 55.67 days among observed failures only; those pooled days span very different crop inspection calendars and are not a reliable shelf-life claim.

The saved-model example is a held-out synthetic maize lot at day 140. It predicts acceptable 0.7226, warning 0.2524, and spoiled 0.0249, with simulated probability 0.0023 of a first spoiled inspection by the next 7-day check. The example input omits all target labels. This demonstrates loading the saved model; it is not evidence of real predictive performance.

Some per-crop horizon test groups had zero failures at the selected checkpoint. Their Brier score can look deceptively favorable. Use the full `artifacts_v2/survival_metrics.json` to see support, calibration, censoring, and horizon details; do not present a per-crop metric without its event count.

## Saved files

- `data/simulated_paired_v2.csv` — fabricated paired-schema rows.
- `data/summary_v2.json` — generation metadata and counts.
- `examples/simulated_v2_prediction_input.json` — held-out synthetic input with no answer label.
- `artifacts_v2/status_metrics.json`, `model_comparison.csv` — grouped status split and scores.
- `artifacts_v2/*__*.joblib` — fitted status models.
- `artifacts_v2/survival_metrics.json` — hazard and AFT evaluation.
- `artifacts_v2/discrete_hazard_*.joblib`, `xgboost_aft.joblib` — fitted survival models.

Do not concatenate this dataset with v1 or with the separate real AeroSense, tomato, potato, or MQ archives as though they were observed paired measurements. V2 is an engineering simulation for testing code and demonstrating end-to-end mechanics only.
