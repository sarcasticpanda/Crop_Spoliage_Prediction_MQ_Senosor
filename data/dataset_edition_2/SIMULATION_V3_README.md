# Edition 2 source-informed three-crop simulation

**SIMULATION ONLY.** The V3 tables are generated examples. No generated row is
a measured tomato, potato, or banana sample, and no V3 label is an independent
inspection. No percentage of closeness to reality is claimed.

## What was created

There are three separate CSVs: tomato, table potato, and banana. Each contains
100 simulated sample trajectories and eight observations per trajectory, for
800 rows per crop and 2,400 rows total. A row is one simulated sample at one
storage age. Keys are unique by `(sim_sample_id, storage_age_days_SIM)`.

```text
data/dataset_edition_2/tomato/simulated_v3/tomato_source_informed_3state_SIMULATED.csv
data/dataset_edition_2/potato/simulated_v3/potato_source_informed_3state_SIMULATED.csv
data/dataset_edition_2/banana/simulated_v3/banana_source_informed_3state_SIMULATED.csv
```

Existing Edition 2 V2 and five-crop simulations were not overwritten. V3 uses
the same nine response channels for each crop so the feature interface stays
consistent; this does **not** establish that all nine channels are necessary.

## Data and assumptions

- Tomato and banana environmental scenario centers were informed by UC Davis
  postharvest guidance. The simulation assumes mature-green fruit. Potato is
  table potato. Guidance sets scenario centers, not spoilage cutoffs.
- For tomato and banana, source session medians from the five day-coded
  recordings in Zenodo record 17285312 are used only to anchor response scale
  and between-session variation. They are not joined to environmental data,
  sample identity, or labels. They are not used as independent physical lots.
- No potato MQ recordings were available in the project. Its V3 MQ values use
  a generic scale prior from the separate tomato/banana session summaries and
  synthetic noise. They are not potato sensor observations.
- Temperature/RH paths are generated with small correlated variation around
  one of five scenario offsets. MQ responses change with a generated hidden
  degradation variable, sensor-specific synthetic sensitivities, and noise.
  They are response-like indices, not ppm or calibrated gas concentrations.
- The three labels are created by simulator thresholds on that hidden
  variable: acceptable below 0.32, warning from 0.32 to below 0.58, and
  high-risk at or above 0.58. These thresholds are demonstration assumptions,
  not values learned from crop inspections.
- Operationally, future real inspections should define acceptable as sound
  and marketable with no active decay; warning as early deterioration or
  limited defects requiring recheck; and high risk as severe/active decay or
  nonmarketable condition. Assessors must document crop-specific signs and
  agree on the protocol before collecting labels. Banana ripeness alone is
  not spoilage. High-risk is not a food-safety certification.

## Schema

Identifiers and audit fields include `sim_sample_id`,
`sim_observation_id`, `crop`, `crop_stage_SIM`, `storage_scenario_SIM`,
`data_origin`, `label_origin`, `label_rule_version_SIM`, and
`mq_source_basis_SIM`. Predictors used for training are only:

- Environment only: storage age, temperature, and relative humidity.
- MQ only: nine `MQ*_response_SIM` values.
- Combined: age, temperature, relative humidity, and all nine MQ responses.

Labels, identifiers, scenario, stage, and provenance are excluded from all
predictors. No absolute dates, invented failure times, inspection measurements,
or survival claims are included in V3.

## Training and held-out-lot results

Random Forest and XGBoost were fitted separately per crop and feature set.
Each crop uses a fixed 80/20 split by entire `sim_sample_id` trajectories,
stratified by terminal simulated class: 80 training and 20 held-out samples,
with all eight times per sample retained together. This is a test of the
simulator only; it is not external crop validation. The high-risk recall below
is especially relevant because missing a severe simulated state matters for
the demo. The results remain sensitive to the generator assumptions.

All-crop simulated label counts:

| Crop | Acceptable | Warning | High risk |
|---|---:|---:|---:|
| Tomato | 393 | 271 | 136 |
| Table potato | 380 | 286 | 134 |
| Banana | 368 | 287 | 145 |

Combined-input held-out metrics (20 held-out trajectories, 160 observations
per crop):

| Crop | Model | Macro F1 | High-risk recall | Log loss | Multiclass Brier |
|---|---|---:|---:|---:|---:|
| Tomato | Random Forest | 0.787 | 0.630 | 0.546 | 0.318 |
| Tomato | XGBoost | 0.746 | 0.667 | 0.468 | 0.292 |
| Table potato | Random Forest | 0.614 | 0.400 | 0.684 | 0.420 |
| Table potato | XGBoost | 0.580 | 0.320 | 0.712 | 0.445 |
| Banana | Random Forest | 0.687 | 0.633 | 0.614 | 0.371 |
| Banana | XGBoost | 0.745 | 0.733 | 0.578 | 0.365 |

There is no model winner across all three synthetic crops. The test scores and
channel rankings only reflect this generator. V3 is useful for schema, grouped
validation, and a three-state CLI demonstration; it does not show that values
or labels will match physical crops.

## Commands

Run from the repository root in PowerShell:

```powershell
# Regenerate V3 and fit RF/XGBoost feature-set comparisons
.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation_v3

# Predict from a saved model; no retraining
.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation_v3 --predict examples\edition2_v3_prediction_input.json

# Focused project checks
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Artifacts and metrics are in `artifacts/edition2_simulation_v3/`. The example
input has no answer label; output is always marked `SIMULATION ONLY`. The
existing five-crop web demo is separate and uses its own saved models.

## What is needed for real transfer

For each sample, collect crop and stage, stable lot/sample ID, storage age,
timestamp, AeroSense temperature/RH, all nine MQ responses at a matched time,
device/calibration/warm-up metadata, and independent crop-specific inspection
time, assessor, method, and defect evidence. Record the last acceptable and
first unacceptable inspections, or monitoring end for censored samples. Keep
all readings from a lot in one split. Train on inspected real lots and evaluate
on untouched real lots. Compare real-only with real-plus-simulation training;
retain simulated examples only if they improve the real held-out result.
