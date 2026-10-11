# Five-crop training prototype: 120,000 simulated readings

**Every value in the CSV is simulated.** No row is an AeroSense reading, an MQ-device reading, or an observed crop failure. `data_origin=SIMULATED_ALL` is repeated in every row. The 2030 timestamps are a fictional experimental clock. Keep the separate real AeroSense workbook unchanged; it has no matching crop/lot, MQ array or observed failure records.

## What this dataset contains

- Wheat, maize, table potato, cured dry onion, and spinach: 24,000 rows each.
- 100 independent *simulated* starting lots per crop; each is copied into six counterfactual storage paths with 40 observations: **5 × 100 × 6 × 40 = 120,000 rows**.
- 500 starting lots and 3,000 trajectories. The 120,000 readings are repeated measures, **not** 120,000 independent experiments.
- Observation interval: wheat/maize every 7 days through day 273; potato/onion daily through day 39; spinach every 6 hours through day 9.75.
- Nine shared, simulated MQ response-index channels: MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, MQ135. They are *dimensionless indices*, not gas concentrations, measured Rs/R0, or confirmed hardware voltage.
- Your ten AeroSense column names are included; their values in **this file** are simulated. The AQI and `Gas (kOhms)` fields are illustrative, with no asserted equivalence to the faculty device's firmware. Dew point and heat index follow a stated illustrative calculation, which may differ from that firmware.

## The six paths

Each simulated starting lot is followed at `cool_proper`, `ambient`, `warm`, `warm_humid`, `ambient_to_cool`, and `ambient_to_warm`. In the final two paths, temperature switches after 13 of 40 observations. Up to the switch, they share their ambient counterpart's entire **present and past** sensor history and inspection status. Later outcomes can differ and are stored in separate target columns. Conditions have crop-specific temperature and humidity settings:

| Crop | Cool proper | Ambient | Warm | Warm humid |
| --- | --- | --- | --- | --- |
| Wheat and maize | 15°C, 55% RH | 25°C, 65% | 32°C, 65% | 32°C, 85% |
| Table potato | 7°C, 95% | 18°C, 88% | 27°C, 88% | 27°C, 97% |
| Cured dry onion | 2°C, 68% | 20°C, 68% | 30°C, 68% | 30°C, 84% |
| Spinach | 2°C, 96% | 10°C, 88% | 20°C, 88% | 20°C, 99% |

These are **illustrative settings for model development**, not universal optimums or validated expected failure times. The numerical deterioration coefficients and MQ mixing coefficients are explicit assumptions in `build_large_simulation.mjs`. Sources support the *direction* of some storage effects, not these coefficients or the simulator's quantitative predictions: [UC Davis spinach](https://postharvest.ucdavis.edu/produce-facts-sheets/spinach), [dry onions](https://postharvest.ucdavis.edu/produce-facts-sheets/onions-dry), [potatoes](https://postharvest.ucdavis.edu/produce-facts-sheets/potato), and [FAO grain moisture and temperature](https://www.fao.org/4/s1250e/S1250E0u.htm). The [MQ food-freshness archive](https://zenodo.org/records/17285312) lists the nine channel types, but its recordings were **not** copied into this file.

## Column map

| Columns | Meaning and allowed use |
| --- | --- |
| `data_origin`, `sim_lot_id`, `sim_trajectory_id`, `scenario_SIM` | Provenance and grouping; IDs and scenario are for splitting/analysis, not predictive inputs. |
| `crop`, `crop_group`, `sim_timestamp_utc`, `storage_age_days`, `Date`, `Time` | Simulated identity and time. `storage_age_days` is elapsed time since the simulated lot entered storage, not harvest age. Avoid using absolute fictional date to predict failure. |
| Ten AeroSense named columns | Simulated current environment. The derived values may duplicate temperature/humidity information. The device's real firmware outputs require separate checking before deployment. |
| `grain_moisture_pct_SIM` | Simulated grain condition for wheat and maize; blank for the three vegetables. A real grain model requires a real moisture measurement. |
| `lot_mass_kg_SIM`, `initial_inspection_defect_pct_SIM` | Simulated lot context and initial observed condition. Use only if comparable real inputs will be collected. |
| `past_mean_temp_C_SIM`, `past_mean_rh_pct_SIM`, `past_hot_degree_days_SIM` | History through the current reading only. Hot degree days accumulate temperature above this crop's illustrative reference temperature. |
| Nine `MQ..._response_index_SIM` columns | Cross-sensitive response patterns with lot offsets, temperature/humidity response, noise, and drift. No channel is an exact chemical ppm measurement. |
| `inspection_defect_type_SIM`, `inspection_defect_pct_SIM` | Invented inspections. Defect fraction is rounded before status assignment and is **not** a sensor-derived ground truth in a real experiment. Exclude these as predictors when evaluating sensor-only classification. |
| `status_SIM` | Target: acceptable below 7% simulated inspected defects; warning from 7% to below 15%; spoiled at 15% or more. These thresholds are hypothetical and require crop-specific faculty decisions. |
| `failure_interval_start_days_SIM`, `failure_interval_end_days_SIM` | First observed crossing lies between the prior and current inspection; blank when no crossing occurs. |
| `event_observed_SIM`, `observed_followup_days_SIM`, `remaining_days_to_first_failed_check_SIM`, `post_failure_SIM` | Survival/target bookkeeping. For a still-good trajectory, failure is right-censored; remaining days are blank. Do not use these fields as predictors. Exclude post-failure rows from time-to-failure training. |

## Safe training demonstration

1. Split on **`sim_lot_id`**, keeping all six scenarios and readings of each starting lot together. Never randomly split individual rows. A grouped split can be implemented with `GroupKFold`.
2. Train a Random Forest baseline and a gradient-boosted classifier for `status_SIM`. Compare environment-only, MQ-only, and fused features. Use only information available at the prediction time: crop, storage age, current sensor readings, past history, and optionally initial condition.
3. For survival training, keep pre-failure observations. A failed trajectory gives an interval from `[failure_interval_start_days_SIM - storage_age_days, failure_interval_end_days_SIM - storage_age_days]`, with a positive lower bound as required by the chosen implementation. A still-good trajectory is right-censored after `observed_followup_days_SIM`. Check the survival implementation's interval/censoring conventions.
4. Report model scores as **simulation reconstruction**. No model trained here is validated for real wheat, maize, potato, onion, or spinach. Both MQ indices and inspection targets depend on the same hypothetical latent condition, so excellent scores can be circular evidence about the simulator.
5. When measured paired lots arrive, replace these inputs and outcomes with real time-aligned measurements and independent inspections. Test on entirely new lots and storage periods. Do not map an unrelated public MQ file onto an AeroSense timestamp as though the same crop was measured.

## Checks performed

The generator uses a fixed seed `20261012` and writes `summary.json`. Independent CSV validation checks the 120,000 × 42 shape, 500 lot IDs, 3,000 unique trajectories, 40 chronologically ordered readings per trajectory, no status reversal, non-empty failure targets only for observed crossings, and identical pre-switch current/past histories in paired paths. The summary workbook contains a short overview and example rows; the full dataset is the CSV.

**Quantitative limits:** temperature changes affect the simulated deterioration rate according to assumptions. They do not prove that lowering a real warehouse from 25°C to 20°C adds a certain number of days. The simulator does not resolve ventilation, local hot spots, microbial food safety, sensor calibration or real variety effects.
