# Edition 2 crop sensor demo (simulated)

This small demo has separate tomato, table-potato, and banana CSVs under each
crop's `simulated_v2` folder. Each has 600 one-time cases with storage age,
temperature, relative humidity, nine MQ response channels, and a `good`/`bad`
`status_SIM` label. It is intentionally not a lot/trajectory dataset.

## What the labels mean

`status_SIM` is generated from a hand-written latent deterioration-pressure
rule using storage age, distance from the assumed storage setpoint, and random
case variation. MQ readings are generated/resampled to correlate with that
latent value. This demonstrates a simple sensor-to-classifier pipeline. It is
not an independent inspection, measured crop spoilage, or validated
remaining-life target. Scores in `artifacts/edition2_simulation/metrics.json`
measure how well Random Forest reproduces this simulator on held-out synthetic
rows only.

All rows carry `data_origin=SIMULATED_RULE_BASED` and
`label_origin=SIMULATED_LATENT_RULE_NOT_INSPECTION`. For tomato and banana,
the nine-MQ values start from resampled raw readings in the separate short
Zenodo recordings, then receive synthetic perturbations. They are not joined
to those samples' environment, identity, or label. Potato has no public raw
MQ readings in the local source bundle, so its nine MQ values are fully
simulated. All crops receive simulated temperature/RH and labels. MQ values
are ADC-like response units, never ppm or exact gas concentrations.

## Assumed conditions and sources

The profiles are illustrative operating points, not universal crop limits:

| Crop assumption | Temperature center | RH center | Reference |
|---|---:|---:|---|
| Mature-green tomato | 13.75 °C | 92.5% | [UC Davis tomato guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/tomato) |
| Table potato | 7.0 °C | 96.5% | [UC Davis potato guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/potato) |
| Storage banana | 13.5 °C | 92.5% | [UC Davis banana guidance](https://postharvest.ucdavis.edu/es/produce-facts-sheets/banano-platano) |

Each setpoint is based on a published postharvest recommendation, but the
simulation's deviation limits, MQ channel sensitivities, latent rule, label
threshold, and random variability are engineering assumptions. The tomato
setpoint assumes mature-green fruit. Potato recommendations vary by intended
use and cultivar. Banana ripening-stage recommendations differ from storage.

## Generate and train

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation
```

This writes the three CSV files and crop-specific Random Forest models. The
split is a stratified row split because the rows are independent synthetic
cases; it does not demonstrate generalization to unseen real lots. Do not
compare its scores directly with measured studies or the five-crop simulator.

## Proposed improvements before any real-data claim

1. Replace simulated labels with independent repeated quality inspections.
2. Record stable physical lot/sample IDs and timestamps so whole samples can
   be held out during validation.
3. Record actual chamber/storage temperature and RH beside the same crop
   sample and MQ array, with device calibration and baseline readings.
4. Define good/bad operationally with a documented inspection rubric and
   include borderline cases.
5. Keep the synthetic files separate from original downloaded files; never
   describe the synthetic records as paired measurements.
