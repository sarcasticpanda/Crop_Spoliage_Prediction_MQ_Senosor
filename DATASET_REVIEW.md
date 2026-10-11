# Input and public dataset review

## Supplied simulator

Read the ZIP, `READ_ME_FIRST.md`, `summary.json`, and CSV before implementation. The CSV has 120,000 rows × 42 columns. Each crop has 24,000 rows, 100 `sim_lot_id` values, and 600 `sim_trajectory_id` values. Across crops there are 500 starting lots and 3,000 trajectories (six paths × 40 records per lot). Status totals are acceptable 37,884, warning 44,199, spoiled 37,917. All rows have `data_origin=SIMULATED_ALL`; timestamps span fictional crop-specific storage ages (wheat/maize 0–273 days, potato/onion 0–39, spinach 0–9.75). Every trajectory has strictly increasing age.

An exact audit found **0 byte/value-identical duplicate rows** and **0 duplicate (`sim_trajectory_id`, `storage_age_days`) keys**. It found 100,000 repeated (`sim_lot_id`, `storage_age_days`) keys because each starting lot is copied into six simulated storage paths, each with the same 40 inspection ages. Those are different simulated path outcomes, not accidental duplicate rows, but they reuse one simulated starting lot. Therefore the dataset has 500 simulated starting lots, not 120,000 independent samples or 3,000 independent biological replicates. If the faculty rule means every experimental record must be an independently collected lot with no branched/reused starting lot, this simulator cannot meet that requirement; do not describe its paths or rows as independent replicates. Grouping all paths by `sim_lot_id` prevents train/test leakage but does not make the simulation real or create biological replication.

Missing values: `grain_moisture_pct_SIM` is blank in 72,000 vegetable rows. Failure interval start/end and remaining days are blank in 39,400 rows, representing 985 right-censored trajectories × 40 rows. Those blank targets are expected. `summary.json` agrees on crop row totals, overall event counts (2,015), and status totals.

The 42-column schema, in source order:

```text
data_origin, crop, crop_group, sim_lot_id, sim_trajectory_id, scenario_SIM,
sim_timestamp_utc, storage_age_days, Date, Time, Temperature(°C), Humidity(%),
Pressure(hPa), AQI, Gas (kOhms), Altitude(m), DewPoint(°C), HeatIndex(°C),
grain_moisture_pct_SIM, lot_mass_kg_SIM, initial_inspection_defect_pct_SIM,
past_mean_temp_C_SIM, past_mean_rh_pct_SIM, past_hot_degree_days_SIM,
MQ2_response_index_SIM, MQ3_response_index_SIM, MQ4_response_index_SIM,
MQ5_response_index_SIM, MQ6_response_index_SIM, MQ7_response_index_SIM,
MQ8_response_index_SIM, MQ9_response_index_SIM, MQ135_response_index_SIM,
inspection_defect_type_SIM, inspection_defect_pct_SIM, status_SIM,
failure_interval_start_days_SIM, failure_interval_end_days_SIM,
event_observed_SIM, observed_followup_days_SIM,
remaining_days_to_first_failed_check_SIM, post_failure_SIM
```

## Public tomato paired data: Zenodo 15469472

Downloaded and inspected the 15,443-byte `Sensor and Laboratory Data.zip` separately. Its README and CSVs show semicolon-delimited data with columns `Sample ID`, `Storage Scenario`, `Storage Day`, two weights, three CIELAB color values, and 12 Rs/R0 channels: MQ2, MQ3_1, MQ3_10, MQ4, MQ5, MQ6, MQ8, MQ9, MQ135, MQ136, MQ137, MQ138. Thus it does not include MQ7 and is not the same nine-channel device schema.

`Dataframe_ML_complete.csv` has 52 rows and 18 reused numeric sample labels across storage days 3, 5, 7, 10, 12, and 14, with scenarios Tc, Trt, and Trtd. The released table has 12 MQ-family Rs/R0 channels, initial/current weights, and three color values (17 candidate predictors); it has no temperature/RH columns and no MQ7. Each scenario/sample key occurs once in this random-sampling table. The paper says sampled tomatoes were discarded after measurement. `Dataframe_continous.csv` has 90 repeated measurements of three tomatoes in each of the three scenarios (9 physical tomato series), measured on days 3–14. It is excluded from training and used only for a small separate-cohort test: one day-3 record per tracked tomato, so test n=9 independent tomatoes rather than 90 independent rows. The available actual target is storage scenario (Tc cooled, Trt room, Trtd room plus mechanical damage). The other published target is storage day. Neither table has an independently inspected acceptable/warning/spoiled endpoint or first-failure interval. Storage day is not remaining time to spoilage. The random-sample table supports only a separate tomato scenario/day experiment, not a five-crop spoilage or survival model.

The separate tomato exploratory experiment has now been run. It compares 12 MQ features with MQ plus the five released weight/color fields, using majority, Random Forest, XGBoost and SVC. It reports 5-fold stratified sample-level CV, leave-one-storage-day-out CV, and an external test on one earliest-day row for each of nine tracked tomatoes. The external test is small and within the same study, but it prevents repeated day readings from being counted as independent people/lots. Outputs and full-data demonstration estimators are under `artifacts/public_tomato/`. These model files are not loaded by the five-crop simulator interface.

## Public nine-MQ archive: Zenodo 17285312

Downloaded and inspected the 10.3 MB archive listing and sample CSVs separately. The files have a `Ticks` timestamp and exactly the nine columns MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, MQ135. It contains distinct files named Tomato D1–D4 and tomato D5 (plus other fruit/food combinations), with raw frequent samples grouped by food/day file. Its record describes approximately three-minute recordings repeated daily near room temperature. File/day identity permits a separate preprocessing or day-group exploratory study; no inspection-based unacceptable-quality label or varied-temperature intervention is established. D5 is not assumed to mean spoiled.

## Public potato storage history: Mendeley sbwxmtpj47/1

The downloaded public ZIP is 4,511,437 bytes and contains three files: a pre-merged workbook, a processing script, and a figures-data workbook. The pre-merged `Data` sheet has 66,363 rows and 14 columns, including timestamp, campaign/year, storage mode, node name, air temperature, relative humidity, tuber-core temperature, CO2, and derived VPD/wet-bulb fields. It contains no MQ readings and no per-reading quality label. Although the record description mentions 17 raw IoT workbooks, those raw workbooks are not present in the ZIP that was downloaded; the supplied script expects them as inputs. The figures workbook contains aggregate tables and a small 2025 set of five quality replicates per storage mode, but no validated join from those quality samples to specific environment sensor nodes/timestamps. Thus it can support a separate descriptive storage-environment analysis, but it cannot train or validate our spoilage label without inventing matches. No nine-MQ sensors are listed. This experiment stays separate from both Zenodo studies and the simulator.

The pre-merged table has 17 node names and only 2024–2025 records. Storage-mode counts are H=34,385, 7°C=12,398, outdoor=11,810, and traditional=7,770. All timestamps parse, and timestamp/node keys are unique. Missing counts are air temperature 27,236, relative humidity 27,311, tuber-core temperature 50,077, and CO2 55,002. These readings describe storage environments; predicting the known storage-mode field would identify the treatment setup, not potato quality.

None of the already reviewed open sources supplies verified paired AeroSense plus the requested nine MQ channels plus inspected failure intervals for all five target crops.

## Crop-only research leads found in follow-up search

### Potato rot e-nose study (best matching target, data not public)

The most relevant lead for the requested crop is the 2024 study *Early Identification of Rotten Potatoes Using an Electronic Nose Based on Feature Discretization and Ensemble Convolutional Neural Network*. It reports normal, slightly rotten, and totally rotten potato samples, with readings collected in both a laboratory and a storage facility. The sensor records are 12 channels × 180 time points per sample, and the study reports 300 lab plus 300 storage sample records. Its raw data availability statement says the data are available from the corresponding author on request. The paper does not expose a downloadable sample-level table in the sources checked. Its sensor array is not the project's exact nine MQ channels, and the paper's facility temperature/RH settings do not establish that matched per-sample AeroSense measurements are included. A real reanalysis would need physical sample IDs and the separate storage-box/run IDs to make grouped validation possible. Do not use the paper's published random/test split scores as evidence of new-lot generalization without verifying its split unit. [Sensors article](https://www.mdpi.com/1424-8220/24/10/3105).

Another potato rot study reports normal, slight rot, and severe rot using an electronic nose, but it also says the sample-level data are available from authors on reasonable request. It uses 12 × 180 signals and has a related environmental monitoring module; the article does not provide a public paired table with explicit sample-level environment fields and stable independent-lot IDs. This is a data-access lead, not data that can be trained locally today. [Chemosensors article](https://www.mdpi.com/2227-9040/12/12/275).

### Paired crop + MQ + environment paper (banana, outside target crop list)

A 2026 banana ripeness paper reports 953 labeled observations with eight MQ channels (MQ2, MQ3, MQ4, MQ5, MQ6, MQ8, MQ9, MQ135) plus temperature and humidity, for unripe/ripe/rotten classes. It omits MQ7, uses bananas rather than the five target crops, and reports a stratified random row split. The raw data are available from the corresponding author on request, not as a public downloadable file. It cannot train the potato or five-crop model, and its reported score is not a leakage-safe independent-fruit result. It is a useful example of the minimum combined measurement pattern, not a source to merge into this project. [Electronics article](https://www.mdpi.com/2079-9292/15/12/2502).

### Potato e-nose with chemical quality measurements

Two published potato studies are more directly relevant than the tomato scenario table for a crop-quality task:

- The 2022 study measured one potato cultivar with e-nose, Vis/NIR, soluble solids content (SSC), and pH at four time periods with 15 replications. Its e-nose had nine MOS sensors, but only MQ3, MQ4, MQ8, and MQ9 plus MQ135 overlap the target device; it also used MQ136 and several TGS sensors. Storage conditions were fixed, so it does not test changing AeroSense temperature/RH paths. The paper says underlying sample data are available from the corresponding author on reasonable request; they are not an open downloadable table at the paper page. Its endpoints are SSC and pH, not acceptable/warning/spoiled or time to failure. [Foods article](https://pmc.ncbi.nlm.nih.gov/articles/PMC9778509/).
- A 2023 PLOS ONE study measured three potato cultivars over six 15-day periods, with 15 replications, using a nine-sensor e-nose and chemical quality measures. Its reported 90%+ classification mostly targets storage period, not independently defined spoilage. The paper states relevant data are within the manuscript; its reported 270 records and high scores need re-analysis with grouped, leakage-safe validation before reuse. The sensor set includes MQ3, MQ4, MQ8, MQ9, MQ135, MQ136, and TGS devices, so it is not the requested nine MQ sensors. [PLOS ONE article](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0284612).

**Best crop-only training lead:** request sample-level potato rot records from the 2024 potato e-nose study authors. Before training, require raw signal rows, sensor names/units, physical sample ID, source lot, storage box/run ID, label rubric, collection time, and matched temperature/RH (if available). Use sample- or lot-grouped validation, and a separate environment-only / MQ-only / combined comparison only where the modalities are genuinely paired. If no matched environmental fields are supplied, report an MQ-only potato rot experiment and keep AeroSense out of that model. This would be a real potato rot-stage experiment, not remaining-life prediction. Do not reconstruct raw measurements from aggregate plots or tables.

### Spinach e-nose plus freshness grades

A 2019 spinach study reports four freshness grades assigned by 10 trained panelists, with e-nose, machine vision, and fused models. The abstract reports 81.25% e-nose accuracy and 93.75% fused accuracy. The raw study files were not located in the sources checked, and the available article summary does not establish the exact sensor array or independent-lot split. It is a good crop-specific contact/data-access lead, but not data we can presently train on or treat as a reproducible benchmark. [Journal of Food Safety article](https://onlinelibrary.wiley.com/doi/10.1111/jfs.12708).

### Newly found open spoilage dataset: TriModal Ripeness 6 (tomato is one crop)

The 2026 *Data in Brief* article links to an openly downloadable Figshare record, [TriModal Ripeness 6](https://doi.org/10.6084/m9.figshare.30783827). It contains six produce types, including tomato; a binary `Spoiled` / `Not_spoiled` classification tree; daily gas readings from an MQ-4; and paired RGB and thermal images. The article describes fruit being monitored from purchase until visible spoilage, with collection three times daily. Figshare lists one ZIP at about 20.4 GB. This is the strongest no-author-contact route found for a real **single-MQ tomato visible-spoilage** experiment, if it passes a file-level audit.

It is not a drop-in dataset for this project's requested model: it has MQ-4 only (not the nine-channel array), no continuously logged temperature/RH or AeroSense fields, no crop-storage lot histories across the five target crops, and no explicit warning grade or independently defined failure interval. The article also says ambient temperature/RH were not continuously recorded. Before modeling, inspect archive paths and metadata for unique fruit IDs, whether the gas files map to the same fruit/day as the labels/images, and how many independent fruits exist. Split all images and readings by physical fruit ID; if IDs cannot be recovered, do not report a generalization score. A valid result would be a narrow real-tomato binary experiment, not evidence that the simulated combined model works on real crops. [Dataset article](https://pmc.ncbi.nlm.nih.gov/articles/PMC12925515/); [Figshare download record](https://figshare.com/articles/dataset/TriModal_Ripeness_6/30783827).

### Public Dryad tomato storage-quality data (environment is not row-matched)

Dryad provides spreadsheets for tomato decay, marketability, weight loss, and other quality measurements on days 4 through 36. Its description reports a room-level temperature and RH range over the study. It uses destructively sampled fruit from three treatment replications at each time point, rather than repeated sensor-and-inspection rows for identified fruit lots, and it has no MQ sensor data. It may support a treatment/day-to-quality analysis after spreadsheet ID and replicate review; it cannot currently validate the AeroSense + MQ model or time-to-failure from matched sensor histories. The page exposes the files, although the attempted anonymous file/API download from this environment returned an anti-bot/authorization response. [Dryad record](https://datadryad.org/dataset/doi:10.5061/dryad.5mkkwh772).

The potato environment archive, the exact nine-MQ archive, the Zenodo tomato scenario dataset, and TriModal Ripeness 6 remain separate studies with different samples and targets. No verified lot/time join exists among them, so they must not be merged to fabricate data. The simulator remains the only runnable combined crop + AeroSense-like environment + nine-MQ model in the repository, and all its scores remain simulation-only.
