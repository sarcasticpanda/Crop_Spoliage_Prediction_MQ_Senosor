# Next 48 hours: paper and demo work plan

## Research decision

The honest paper available from the current evidence is a **simulation pipeline audit plus a separate exploratory tomato storage-scenario study**. It cannot be a validated five-crop spoilage or remaining-life paper: the five-crop labels are simulated, and the real sources cannot be linked into one labeled set of matching crop lots and times.

The current five-crop simulator already includes some random sensor variation, lot effects, drift, and MQ cross-sensitivity. Making another simulation more complicated will not make it real or prove transfer. A new v2 is justified only as a clearly labeled robustness study with pre-specified device shifts, missing channels, and storage paths. Keep v1 and its scores unchanged; never tune v2 assumptions to improve headline performance.

The strongest newly found no-email dataset is the public TriModal Ripeness 6 archive: tomato is included with MQ-4 readings and visible-spoilage binary labels, but it has no AeroSense fields or full nine-MQ array and its ZIP is about 20 GB. It can support a separate, crop-specific real tomato gas-sensor experiment if file-level inspection confirms that readings and labels match by fruit and there are enough identifiable independent fruits for a grouped holdout. Treat it as a binary visual-spoilage task, not as the five-crop combined model or remaining-life model. The potato rot papers remain the closer match to a target crop and three rot grades, but their raw sample data are author-request only. Nothing found provides openly downloadable, verified same-lot/same-time AeroSense + all nine MQ channels + independent quality/failure labels for the target crops. Do not merge unrelated archives. Details and links are in `DATASET_REVIEW.md`.

## Work sequence

### Today: freeze and verify the evidence

1. Preserve the supplied CSV/ZIP and v1 result artifacts. Record a code revision or copy the run outputs before editing result-generating code.
2. Run the saved-data audit, current status/survival evaluations, and focused checks from `DEMO_GUIDE.md` in the project virtual environment.
3. Keep the fixed 100-lot simulator test set untouched during any changes. Label every score simulator-only.
4. Run the local browser app and demonstrate saved-model inference, missing-input feedback, CSV validation, and the result label. Do not present a predicted probability as a real crop probability.
5. Give the advisor `PAPER_DRAFT.md`, `RESULTS.md`, and this decision memo for rapid scope feedback. Ask the advisor to confirm author list, target venue, endpoint definition, and whether a simulation/software paper is in scope.

### Tomorrow: make the manuscript reviewable

1. Fill in author/affiliation, advisor-approved venue, citation style, and ethics/data availability statements.
2. Re-run the exact manuscript commands and replace any table if the regenerated outputs differ. Save logs and environment/package versions.
3. Have a second person check all numbers against the JSON artifacts and ensure tables do not call the 3,000 trajectories independent lots.
4. Review wording for claims that suggest real-world predictive accuracy, days gained from cooling, or equivalence among the separately collected public datasets.
5. Demo the browser app from a clean PowerShell session and capture screenshots only after verifying no errors.
6. If disk, time, and download capacity allow, fetch TriModal Ripeness 6 from its direct Figshare record (about 20 GB), inventory only the tomato gas/label paths first, and confirm fruit IDs, label provenance, and per-fruit match coverage before any fitting. Then run an MQ-4-only binary spoilage experiment with all days/images from each fruit grouped together. If the archive structure does not support independent-fruit splitting, stop before scoring. A potato author data request is an optional parallel route, not a dependency for this no-email experiment.

### Day after tomorrow: submit or present the defensible version

1. Send the advisor the complete manuscript draft and a short limitations statement with the demo link/local instructions.
2. Submit only if the advisor agrees that the selected venue accepts a simulation/software audit and the real tomato experiment is correctly described as a separate scenario task. Otherwise present it as a research-in-progress paper/demo and revise scope before journal submission.
3. Start the real pilot planning sheet: crop, cultivar/variety, independent lot count, sensor calibration, matched sample IDs, inspection schedule, operational unacceptable threshold, and duration/censor rules.

## Minimum paired real-data schema

| Record | Required fields |
|---|---|
| Study and lot | `study_id`, stable `lot_id`, crop, variety/cultivar, harvest/source, independent biological replicate definition |
| Storage path | `storage_unit_id`, treatment, start time, setpoint and actual conditions, packaging/handling, path assignment |
| Sensor sample | UTC timestamp, storage age, AeroSense device ID/firmware/calibration, original supplied AQI and environmental fields with units, all nine MQ channel values and units/response definition, MQ device/calibration/baseline, sample/headspace protocol |
| Quality inspection | lot ID, inspection timestamp, blinded assessor ID, predefined method, measured defects/weight/firmness/etc., class, explicit acceptable threshold and its crop-specific source/justification |
| Failure/censoring | last acceptable inspection time, first unacceptable inspection time, or last follow-up time for lots still acceptable; event indicator; reason for withdrawal/missing follow-up |
| Join audit | exact match key, tolerance rule, matched/unmatched status, sensor lag and exclusions |

Split by independent `lot_id`; if several lots share one storage chamber or treatment run, assess a second split grouped by chamber/run to measure transfer beyond one device/path. Fit imputation, scaling, feature selection, tuning, and probability calibration using training folds only. Keep a final untouched group of lots (preferably from a later harvest/run/device) for the final result. Pre-register the primary target and metrics before opening that final group.

## What counts as success now

- The local saved-model demo runs and visibly labels the simulator results.
- The paper accurately says what each dataset measures and does not combine unrelated rows.
- Grouped metrics can be recreated from versioned code/artifacts.
- The advisor can judge a concrete scope before submission.

## What does not count as established

- High simulator scores do not show real-crop accuracy.
- A storage-day or storage-scenario classifier is not a spoilage classifier.
- Sensor similarity across separate studies does not create matched lot/time pairs.
- A future temperature/RH scenario with assumed future MQ readings is not a causal estimate of shelf-life gain.
- Peer-reviewed journal publication cannot be promised within two days; editorial and review timelines are outside this project. The deliverable by then can be a complete, reviewable draft and working demo.

## Sources checked

- Tomato sensor/laboratory data record and article: [Zenodo 15469472](https://zenodo.org/records/15469472), [Chemosensors article](https://www.mdpi.com/2227-9040/13/7/255).
- Nine-channel e-nose archive: [Zenodo 17285312](https://zenodo.org/records/17285312).
- Potato storage environment and quality figures: [Mendeley Data](https://data.mendeley.com/datasets/sbwxmtpj47/1).
- Grouped validation rationale: [scikit-learn GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html).
