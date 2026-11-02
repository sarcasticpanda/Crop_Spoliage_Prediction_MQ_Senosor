# Faculty walkthrough: 20-minute version

## One-sentence project description

This project builds and checks a crop-storage sensor modeling workflow using a simulated five-crop dataset, then separately audits small real public datasets whose targets and sensor coverage do not form one paired spoilage dataset.

Say **XGBoost** (often heard as “X-G-Boost”), not “HD-Boost.” Every score from generated data is simulation-only.

## Where each dataset is stored

| Dataset | Folder/file | What it really contains | Was it trained as a spoilage model? |
|---|---|---|---|
| Original five-crop simulator | `five_crop_120000_simulated_training_bundle/five_crop_120000_ALL_SIMULATED_9MQ.csv` | 120,000 generated rows: 5 crops × 100 simulated starting lots/crop × 6 paths/lot × 40 readings/path. Includes nine simulated MQ responses, environmental values, and simulator-made labels. | Yes. This is the main five-crop classification and survival demonstration. It is not real crop accuracy. |
| Paired-schema five-crop V2 simulator | `data/simulated_paired_v2.csv` | 20,000 generated rows: 500 generated lots, one path each, 40 readings per lot. Environment, MQ, and labels were generated together by assumptions. | Yes, as a separate simulator run. Results/models are in `artifacts_v2/`. |
| Edition 2 V2 crop examples | `data/dataset_edition_2/{tomato,potato,banana}/simulated_v2/` | 600 one-time generated cases per crop with generated good/bad labels. Tomato/banana MQ response scale was anchored to separate recordings; potato MQ, environment, and all labels were generated. | Yes, as separate small synthetic examples only. |
| Edition 2 V3 crop examples | `data/dataset_edition_2/{tomato,potato,banana}/simulated_v3/` | 800 generated observations per crop: 100 sample trajectories × 8 times, with generated acceptable/warning/high-risk states. | Yes, with whole trajectories held out. Still simulation-only. |
| Real tomato e-nose study | `data/dataset_edition_2/tomato/original/zenodo_tomato_12_channel_enose/extracted/Sensor and Laboratory Data/` | The 52-row table has 12 Rs/R0 channels, weight, colour, storage day, and `Storage Scenario`. That target is a scenario code, not a measured spoilage label. | Yes, only for the published storage-scenario target, as a separate exploratory experiment. |
| Real nine-MQ recordings | `data/dataset_edition_2/tomato/original/zenodo_exact_nine_mq_tomato_recordings/AllSmaples-Report/` and the corresponding banana folder | Short day-coded sensor sessions. They provide raw channel patterns, but no verified lot ID or independent spoilage inspection. | No spoilage model. Used only as descriptive/source-scale information for separate synthetic examples. |
| Real potato environment archive | `data/dataset_edition_2/potato/original/mendeley_potato_environment/extracted/` | Workbook `IoT_Data_Consolidee_17noeuds.xlsx`: temperature, relative humidity, tuber-core temperature, CO2 and related fields. Its quality summaries do not have a verified row-level lot/time join to these sensor rows. | No combined MQ/spoilage model. Use it for environmental history description only. |
| Other collected source files | `data/dataset_edition_2/{wheat,maize,onion,spinach,banana}/original/` and `data/real_sources/` | Separate public-source files with different targets, units, IDs, and sensors. See `REAL_DATA_AUDIT.md`; do not merge as if the records were the same lot. | Not as one combined spoilage model. |

The downloaded original archives are under `data/real_sources/raw/`; extracted copies are under `data/real_sources/extracted/`. Edition 2 organizes copies by crop. The originals and generated CSVs are kept in different `original/` and `simulated_v*` folders.

## What each notebook shows

Open them from the project’s `notebooks/` folder. The new graphical notebooks have been executed and their tables/plots are saved in the files.

1. `01_saved_results.ipynb` — saved v1 status and survival metrics.
2. `02_saved_model_prediction.ipynb` — one input with no answer label, loaded through saved models.
3. `03_public_tomato_study.ipynb` — real tomato **scenario** experiment, not spoilage.
4. `04_five_crop_graphical_evaluation.ipynb` — precision, recall, F1, log loss, Brier, confusion matrix, per-crop scores, and next-inspection hazard charts for the five-crop simulator.
5. `05_public_tomato_graphical_evaluation.ipynb` — day-held-out and nine-tomato cohort results for the real scenario target.
6. `06_edition2_v2_v3_simulation_evaluation.ipynb` — 20,000-row synthetic V2 plus the separate small crop V2 and V3 simulated results.
7. `07_real_source_dataset_tour.ipynb` — actual tomato table, nine-MQ session summaries, and potato environmental history; no cross-study join.

## A simple explanation of the models

- **Precision:** when the model predicts a class, how often it is right.
- **Recall:** among the real rows of a class, how many the model finds. Spoiled recall matters because missed spoiled examples are important.
- **F1:** balances precision and recall. Macro F1 gives each class equal weight, so a large class cannot hide poor performance on a smaller class.
- **Log loss and Brier score:** check the quality of predicted probabilities; lower is better.
- **Confusion matrix:** shows which true classes were predicted as which classes.
- **XGBoost:** a supervised boosted-tree method. It builds trees in sequence, each learning patterns left by the previous ones. It can represent nonlinear interactions in structured sensor tables. We compare it with Random Forest and a majority baseline; the simulator scores do not prove it is best for real crops.
- **K-means:** an unsupervised clustering method. It does not learn the provided acceptable/warning/spoiled labels, so it is not a direct replacement for a supervised classifier. It could be used to explore unlabeled sensor patterns.

On the original simulated holdout, combined XGBoost macro F1 is about **0.930** and combined Random Forest is about **0.931**; their spoiled recall is about **0.956** and **0.959** respectively. XGBoost has better log loss/Brier in the saved run. Explain this as a close simulator comparison—not real accuracy.

## 20-minute presentation order

| Time | Show / explain |
|---|---|
| 0–3 min | Project question and folder map. Explain the 120,000 count using the multiplication above; 120,000 is rows, not independent lots. |
| 3–6 min | Show `07_real_source_dataset_tour.ipynb`. Point out tomato scenario labels, nine-MQ recordings, and potato environment data are different studies. |
| 6–10 min | Show `04_five_crop_graphical_evaluation.ipynb`. Explain grouped split, class metrics, confusion matrix, and why macro F1/recall are shown. |
| 10–13 min | Explain XGBoost vs Random Forest and why K-means answers a different, unlabeled clustering question. |
| 13–16 min | Show `06_edition2_v2_v3_simulation_evaluation.ipynb`. State exactly which inputs/labels are generated in each edition. |
| 16–18 min | Run the saved-model web demo. Use a supplied simulated example; point to the “SIMULATION ONLY” label. |
| 18–20 min | Close with the evidence gap: real paired sensor records and independent inspections on the same identified lots are required before real-crop validation. |

## Commands to prepare the demo

Run these in PowerShell from `C:\Users\Lunar Panda\3-Main\urop_crop`:

```powershell
# Open the app using saved models; this does not retrain.
.\.venv\Scripts\python.exe -m crop_prototype.web

# Open the saved-model example in the terminal (also does not retrain).
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_prediction_input.json

# If running notebooks in VS Code, select the project .venv Python kernel.
# Notebook/plot dependencies, if missing:
.\.venv\Scripts\python.exe -m pip install -r requirements-notebooks.txt
```

## Important files to show

- `README.md` — project start page and commands.
- `DATASET_REVIEW.md` and `REAL_DATA_AUDIT.md` — what the source datasets do and do not contain.
- `RESULTS.md` — saved metrics and evaluation interpretation.
- `crop_prototype/cli.py`, `models.py`, `survival.py`, `inference.py`, and `web.py` — loading, grouped training, survival targets, prediction, and browser app.
- `artifacts/status_metrics.json`, `artifacts/advanced_status_metrics.json`, and `artifacts/survival_metrics.json` — machine-readable v1 evidence.
- `artifacts/public_tomato/metrics.json` — the separate real tomato scenario experiment.
- `artifacts_v2/` and `artifacts/edition2_simulation_v3/` — separate synthetic result/model folders.
- `notebooks/` — executed result notebooks listed above.

## Answers to likely questions

**Did we train on 120,000 real crop readings?** No. They are generated rows. The independent starting-lot count is 500, not 120,000.

**Did we combine tomato MQ with potato environment data?** No. Those are different studies with no verified shared sample or timestamp key.

**Does the tomato dataset tell us spoiled/not spoiled?** Its released model table target is storage scenario. It is not independent spoilage inspection.

**Are all nine MQ channels proven necessary?** No. The interface uses the same nine for a consistent experiment; channel necessity must be checked on enough real, grouped, inspected samples.

**Can this show the model works on actual crops?** Not yet. It demonstrates the pipeline and generated-label learning. Real paired measurements and held-out inspected lots are still needed.
