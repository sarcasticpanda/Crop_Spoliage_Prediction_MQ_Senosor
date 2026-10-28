# Draft paper for faculty review

> **Draft status:** This is a research manuscript draft, not evidence that the model is validated on real crop quality. The five-crop results below come from a synthetic simulator. The public tomato study is a separate, small storage-scenario experiment.

## Title

**A Leakage-Aware Multimodal Crop-Storage Modeling Pipeline: Simulation Audit and a Separate Public Tomato Scenario Study**

## Abstract

Predicting stored-crop quality from environmental and gas-sensor measurements requires observations from the same crop lot at matched times, plus independent quality inspections. Such paired records were not available for the five target crops in this project. We therefore audited a 120,000-row, fully simulated dataset and evaluated a grouped modeling pipeline as a software and analysis exercise. The data contain 500 simulated starting lots, each expanded into six storage paths with 40 repeated readings per path. All paths from a starting lot were held in the same partition. On 100 held-out simulated lots, a combined environment plus nine-channel metal-oxide (MQ) XGBoost classifier reached macro F1 0.9300 and spoiled-class recall 0.9562; the combined Random Forest reached 0.9309 and 0.9587. XGBoost had lower log loss (0.1622 versus 0.1783) and multiclass Brier score (0.1004 versus 0.1055). These are simulator reconstruction scores: the simulator generates sensor values and inspection outcomes from shared assumptions, so they do not estimate real crop accuracy. Separately, a public tomato dataset was used for its released storage-scenario target. Its best leave-one-storage-day-out macro F1 was 0.546, and a separate nine-tomato cohort produced weak and inconsistent results. Neither public table provides a verified unacceptable-quality endpoint or time-to-failure target for this project. The working software demonstrates grouped evaluation and saved-model inference, but real validation requires prospectively paired sensor readings and independent crop inspections.

**Keywords:** postharvest storage; electronic nose; metal-oxide sensors; grouped validation; simulated data; tomato; survival analysis; data leakage

## 1. Introduction

Temperature, humidity, and volatile-compound sensor responses may change during storage. A useful quality model needs these signals paired to the same physical lot and timestamp, with a quality assessment made independently of the model inputs. A remaining-life model additionally needs inspection times that bracket the first unacceptable inspection and follow-up times for lots that remain acceptable.

The project aims to combine AeroSense environmental fields with MQ2, MQ3, MQ4, MQ5, MQ6, MQ7, MQ8, MQ9, and MQ135 responses for wheat, maize, table potato, cured dry onion, and spinach. The available five-crop bundle is entirely simulated. The project also reviewed public tomato, nine-MQ, and potato-storage datasets, but those sources do not form one joinable five-crop dataset. Combining unrelated records would create false matched lots, so each source is analyzed separately.

This work asks:

1. Can a runnable pipeline audit and reconstruct labels in the supplied simulator while keeping starting lots separated across partitions?
2. How do environment-only, MQ-only, and combined models compare on the same held-out simulated lots?
3. What does a separate public tomato storage-scenario experiment show, and what target claims does it not support?
4. What measurements are needed before evaluating real crop quality or remaining storage life?

The study does **not** test whether simulator success predicts real-world success. Synthetic evaluation can test code paths, leakage controls, and behavior under explicit assumptions; it cannot establish a real sensor-to-quality relationship.

## 2. Data and provenance

### 2.1 Five-crop simulator

The supplied ZIP and `READ_ME_FIRST.md` describe a CSV with 120,000 rows and 42 fields. It contains 24,000 rows per crop, 500 simulated starting lots (100 per crop), six trajectories per lot, and 40 readings per trajectory. The 2030 timestamps, sensor readings, defects, labels, failure intervals, and censoring records are simulated. The status rule is acceptable below 7% simulated defects, warning from 7% to below 15%, and spoiled at 15% or higher. These values are assumptions in this data bundle, not adopted quality standards for the five crops.

There are no byte/value-identical duplicate rows and no duplicate trajectory/time keys. However, 100,000 lot/age keys repeat because each starting lot is branched into six paths at the same reading ages. This gives 500 simulator starting units, not 120,000 independent samples. The six paths share the simulated starting lot and should not be reported as independent biological replicates. Status counts are 37,884 acceptable, 44,199 warning, and 37,917 spoiled. Grain moisture is absent from all 72,000 vegetable rows. There are 985 right-censored trajectories, represented by 39,400 rows with blank failure and remaining-life fields.

The simulator encodes lot susceptibility, sensor baselines/gains, cross-sensitive MQ responses, random reading variation, and a small drift term. Its sensor patterns and labels are both generated from simulator assumptions and shared latent damage. This shared construction is a major reason the task can be easier than real-world prediction; it is not independent evidence that the nine channels measure crop deterioration.

### 2.2 Separate public tomato experiment

Zenodo record 15469472 provides tomato sensor/laboratory tables and images. The released random-sampling ML table has 52 observations and a `Storage Scenario` label (Tc, Trt, or Trtd), six storage days, 12 Rs/R0 channels, weight, and color features. It does not have the project's exact nine-channel schema: it lacks MQ7 and includes MQ136, MQ137, and MQ138. It also has no AeroSense temperature/RH columns. The associated article describes storage condition and storage-day prediction; the dataset target used here is the recorded scenario, not independently inspected acceptable/warning/spoiled status or time to first failure. The article notes visual spoilage in one continuously monitored tomato late in the experiment, which is not a cohort-wide inspected failure target. [Dataset record](https://zenodo.org/records/15469472) · [associated article](https://www.mdpi.com/2227-9040/13/7/255)

The 52-row table was evaluated with sample-level stratified folds and leave-one-storage-day-out folds. A separate continuous table was reserved as a small cohort check: one day-3 reading from each of nine tracked tomatoes. That cohort estimates performance only for those nine tomatoes in that study. It was not merged with the five-crop simulator.

### 2.3 Other public studies reviewed

Zenodo 17285312 lists the exact requested nine MQ channel names and daily recordings made at room temperature, but its file/day labels do not provide independent inspected failure intervals for the target crops. Day labels are not treated as spoilage labels. [Dataset record](https://zenodo.org/records/17285312)

The Mendeley potato record describes environmental history (temperature, relative humidity, tuber-core temperature, and CO2) and quality/weight-loss analyses. The downloaded archive includes a merged environment workbook and figure data, but no nine-MQ data and no verified row-level link between timestamped sensors and individual quality measurements. It remains a separate descriptive environment study. [Dataset record](https://data.mendeley.com/datasets/sbwxmtpj47/1)

## 3. Methods

### 3.1 Predictors and leakage controls

Three predictor sets were evaluated: (i) environment, (ii) nine MQ response indices, and (iii) environment plus nine MQ responses. A separate comparison adds the starting inspection field, which would have to be independently collected at deployment. The feature builder omits current status, inspection defect outcomes, event/failure/follow-up/remaining-life targets, post-failure flags, lot and trajectory IDs, scenario, and fictional absolute date/time. Current and past summaries use readings no later than the prediction row. Missing values are imputed within each training pipeline.

### 3.2 Split and status models

The saved outer split contains 400 training and 100 test starting lots, with 20 test lots per crop. All six paths and all 40 readings from a starting lot remain together. Model selection and preprocessing use training lots only; the fixed outer test lots are not used to choose model settings. Grouped cross-validation keeps each group entirely on one side of each fold, as required when repeated observations from a physical unit are dependent ([scikit-learn GroupKFold documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html)).

The status comparison includes a majority-class DummyClassifier, Random Forest, and XGBoost. The combined Random Forest configuration uses 220 trees, minimum leaf size 2, balanced subsampling, and a fixed seed. Combined XGBoost uses 300 trees, maximum depth 6, learning rate 0.06, row and column subsampling of 0.85, L2 regularization 2, multiclass soft probabilities, histogram tree method, and early stopping based on grouped validation. The same outer held-out lots are used for the environment-only, MQ-only, and combined comparisons.

Metrics are macro F1, spoiled recall, log loss, and multiclass Brier score. Macro F1 weights each quality class equally. Log loss and Brier score assess probability quality, with lower values better. Paired bootstrap intervals resample complete held-out starting lots, retaining their paths and time rows.

### 3.3 Time-to-first-unacceptable analysis

The simulator's operational event is its first `spoiled` inspection. The source provides a last-known acceptable / first-failed inspection interval; event time is interval-censored. Trajectories that remain acceptable at the end are right-censored. Discrete-time logistic and XGBoost hazards use features at the start of each inspection interval and predict failure at its next inspection. Readings at or after a failure endpoint are excluded. A crop-specific baseline and an XGBoost AFT interval-censored comparator are also reported. This evaluation supports risk by a future inspection or a defined calendar horizon only where observed follow-up supports it; it does not interpolate an exact failure day between inspections.

### 3.4 Software demonstration

The local interface loads saved artifacts and supports manual and CSV status scoring in combined, environment-only, and MQ-only modes. Combined current status and next-inspection risk require readings already matched to the same lot/time, the required current/past fields, and a positive inspection interval. The application labels simulator predictions explicitly. Future-path projections require explicit future environment and all nine future MQ values for each interval; they are conditional simulator outputs and do not estimate the causal benefit of cooling.

## 4. Results

### 4.1 Five-crop simulator status reconstruction

**All values in this subsection are simulator performance, not validated crop accuracy.** The selected fixed test set consists of 100 simulated starting lots, with all their trajectories and rows held out together.

| Features | Model | Test macro F1 | Spoiled recall | Log loss | Multiclass Brier |
|---|---|---:|---:|---:|---:|
| Any | Majority baseline | 0.1794 | 0.0000 | 1.0962 | 0.6650 |
| Environment | Random Forest | 0.8226 | 0.8399 | 0.4077 | 0.2553 |
| Environment | XGBoost | 0.8360 | 0.8445 | 0.3921 | 0.2382 |
| Nine MQ | Random Forest | 0.9230 | 0.9526 | 0.1909 | 0.1138 |
| Nine MQ | XGBoost | 0.9251 | 0.9526 | 0.1738 | 0.1084 |
| Environment + nine MQ | Random Forest | 0.9309 | 0.9587 | 0.1783 | 0.1055 |
| Environment + nine MQ | XGBoost | 0.9300 | 0.9562 | 0.1622 | 0.1004 |

Environment plus MQ XGBoost had better log loss and Brier score than combined Random Forest in this run, while Random Forest's macro F1 and spoiled recall were marginally higher. Paired whole-lot 95% bootstrap differences (XGBoost minus Random Forest) were macro F1 -0.0009 [-0.0034, 0.0014], spoiled recall -0.0025 [-0.0061, 0.0006], log loss -0.0161 [-0.0217, -0.0092], and Brier -0.0051 [-0.0079, -0.0017]. On this simulator, the probability metrics favor XGBoost; the point metrics are effectively tied. Neither should be considered a real-crop winner.

Combined XGBoost per-crop macro F1 / spoiled recall were wheat 0.9185 / 0.9536, maize 0.9232 / 0.9394, potato 0.9400 / 0.9621, cured dry onion 0.9165 / 0.9391, and spinach 0.9506 / 0.9718. Its pooled acceptable, warning, and spoiled recalls were 0.9311, 0.9032, and 0.9562. Full per-class metrics and confusion matrices are in `RESULTS.md` and `artifacts/advanced_status_metrics.json`.

Including the starting inspection value barely changed results: combined XGBoost macro F1 moved from 0.9300 to 0.9311, while spoiled recall moved from 0.9562 to 0.9540. This field adds no consistent benefit in this simulator and requires an inspection at deployment.

### 4.2 Simulator next-inspection risk

On held-out at-risk inspection intervals, discrete logistic had Brier 0.05504 and AUC 0.98297; discrete XGBoost had Brier 0.01545 and AUC 0.98036. AUC measures ranking for the next inspection outcome; it is not days-left accuracy. The calendar-horizon and calibration results, including crop-specific baselines and XGBoost AFT, are recorded in `RESULTS.md` and `artifacts/survival_metrics.json`. Their support is limited to the simulator's inspection schedule and follow-up. No exact-day claim is made.

### 4.3 Separate public tomato scenario experiment

On the 52-row random-sampling table, leave-one-storage-day-out macro F1 was 0.514 for Random Forest with 12 MQ channels and 0.546 for XGBoost with the 12 MQ plus weight/color features. On ordinary five-fold sample stratification, MQ-only XGBoost macro F1 was 0.547, compared with 0.491 after adding weight/color; the feature-set comparison is inconsistent across protocols. The independent nine-tomato check produced macro F1 0.278 for MQ-only XGBoost and 0.533 for MQ-only SVC, with only three tomatoes per scenario. The model's example prediction misclassified a day-3 Tc tomato as Trt. This is exploratory scenario classification, not spoilage prediction; n=9 is too small to establish a reliable winner.

## 5. Discussion

The software can demonstrate data auditing, grouped splitting, separate feature modes, saved-model inference, and censor-aware target handling. The high five-crop simulator scores mainly establish that the code can reconstruct outcomes under the generator's assumptions. Because the generator supplies both sensor responses and status from shared synthetic latent structure, the holdout is another sample from the same simulator and does not test transfer to real crops, devices, farms, varieties, or handling histories.

The public tomato experiment offers limited real sensor data but answers a different question. Its storage-scenario labels describe treatment groups, not independently assessed quality classes or days until unacceptability. The nine-MQ and potato records have complementary sensor/environment coverage but lack verified pairing and the needed supervised target. There is no statistically defensible way to merge them into a labeled multimodal lot table. A model trained on one source and “fine-tuned” with another would not solve absent labels or sample identity; it would risk confusing sensor/source differences with crop condition.

The next high-value experiment is a small prospective paired study, not a larger synthetic row count: choose one crop and a clear operational endpoint; enroll independent lots; collect calibrated, timestamped AeroSense and nine-MQ readings from the same headspace/lot; log storage conditions and sensor metadata; have blinded assessors record predefined quality measures on a schedule; and follow each lot until first unacceptable assessment or administrative censoring. Hold out whole lots and, if possible, a later harvest or device. Before using “remaining shelf life,” agree on the unacceptable threshold with the domain expert and record both last acceptable and first unacceptable inspection times.

A new simulator version may be useful as a **robustness test** if its assumptions are explicit and independently varied (for example, device baseline/gain shifts, missing channels, and changed storage paths). It must not be used to claim expected real-world accuracy. The current v1 already includes some noise, drift, lot variation, and cross-sensitivity, so merely adding rows or noise would not create empirical realism. A v2 should be reported as stress scenarios with specified parameter ranges and versioned separately; do not tune assumptions to improve headline scores.

## 6. Limitations

1. The five-crop labels, sensor values, inspections, dates, and outcomes are all simulated.
2. Six trajectories branch from each simulated starting lot; they are not six independent biological replicates.
3. Synthetic sensors and outcomes share generator assumptions, potentially making classification easier than a real deployment.
4. The 7% and 15% defect cutoffs are illustrative simulator rules, not universal crop standards.
5. The public tomato scenario table is small, lacks the requested exact sensor schema, and does not provide a cohort-wide inspected failure label.
6. Public nine-MQ and potato environment datasets lack verified multimodal lot/time/inspection links.
7. Survival estimates are bounded by inspection intervals and observed follow-up; they do not imply exact failure times or causal effects of changing storage temperature.
8. Model probability calibration and performance under sensor/device shift need prospective evaluation on independent real lots.

## 7. Conclusion

This project provides a runnable, leakage-aware modeling and demonstration pipeline and a documented audit of the available datasets. Its five-crop metrics are simulator reconstruction results. The separate public tomato results concern storage-scenario classification and are weak on a nine-tomato cohort. Neither establishes validated crop-quality classification or remaining shelf life. A paired, independently inspected real-lot dataset is required for those claims. The appropriate next use of the software is as a data-collection and analysis scaffold, with a prospective pilot determining whether the proposed sensor combination carries useful information.

## Data and code availability

The project code and synthetic inputs are in this repository. The supplied five-crop bundle is labeled simulated. Public source records are linked in Section 2; locally downloaded source archives are stored separately and excluded from version control. Saved artifacts and full evaluation tables are under the git-ignored `artifacts/` folder and can be recreated using commands in `DEMO_GUIDE.md` and `README.md`.

## References

1. Kaltenecker F, Krupitzer C, Senge J. *Integrating Sensor Data, Laboratory Analysis, and Computer Vision in Machine Learning-Driven E-Nose Systems for Predicting Tomato Shelf Life*. Chemosensors. 2025;13(7):255. [Article](https://www.mdpi.com/2227-9040/13/7/255). [Dataset](https://zenodo.org/records/15469472).
2. Mahdian M. *Food Freshness Electronic Nose Dataset*. Zenodo. 2025. [https://zenodo.org/records/17285312](https://zenodo.org/records/17285312).
3. Ouni A, Chtourou W, Kharroubi H, Elmoueddeb K. *Active evaporative cooling, refrigeration and traditional storage of potato ...* Mendeley Data. 2026. [https://data.mendeley.com/datasets/sbwxmtpj47/1](https://data.mendeley.com/datasets/sbwxmtpj47/1).
4. scikit-learn developers. *GroupKFold*. [Documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html).

## Before submitting

- Confirm the final title, author list, affiliation, supervisor, and journal scope with the faculty advisor.
- Replace this draft's saved-result tables only after rerunning the documented commands on the intended code revision.
- Add crop-specific endpoint definitions and citations from authoritative postharvest standards if the manuscript proposes a real crop-quality outcome.
- Do not state that simulator results predict real-world success. Any claim about real accuracy requires the prospective paired validation described above.
