# Demo run guide

## What you can show

This repository has two separate demonstrations:

1. The five-crop browser app loads saved models and predicts acceptable/warning/spoiled probabilities plus next-inspection risk from explicit inputs. Every output says **SIMULATION ONLY**. These results were learned from fictional sensor readings and labels.
2. A command-line example loads a saved model for the public tomato study and predicts its recorded storage scenario (`Tc`, `Trt`, or `Trtd`). It does not predict tomato spoilage or time left.
3. Edition 2 V3 is a separate CLI demonstration for simulated tomato, potato, and banana inputs. It loads crop-specific saved models to return acceptable/warning/high-risk probabilities. Its readings and labels are synthetic; it does not alter or join the five-crop app or the public tomato study.

Do not combine records from the two studies. The public tomato data has 12 MQ-family channels and weight/color measurements, but not the exact requested nine-channel array and AeroSense environment. It also lacks the inspected unacceptable-quality target required for the five-crop goal.

## Start the browser demo (PowerShell)

From `C:\Users\Lunar Panda\3-Main\urop_crop`:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.web
```

Keep that terminal open. Then open <http://127.0.0.1:8765>. The app reads the saved files in `artifacts/`; launching it does not train models. Use the built-in example first, then try manual combined, environment-only, or MQ-only inputs. The CSV page supports row-by-row scoring and completeness checks.

The combined model needs a real set of fields for **one crop lot at one matched time**: crop, storage age in days, AeroSense environment fields, all nine MQ response indices, and the required past/current environmental summaries. It also needs the positive number of days to the next inspection to report next-inspection risk. Grain moisture and lot mass can be null because the saved pipeline imputes them. The app reports missing required values; do not fill them with guesses. Environment-only and MQ-only modes need their respective model inputs. MQ values are sensor response indices, not gas concentrations.

This is a local browser UI, not a live sensor connection. It does not read a serial port or pair two uploaded files automatically. Only submit a joined row when you have verified that its environment and MQ measurements belong to the same lot and compatible timestamps.

## Run the saved simulated example from the terminal

This command loads the already-saved models and writes a result to `artifacts/prediction.json`; it does not retrain:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.cli predict --input examples\simulated_prediction_input.json
```

Saved example output:

| Output | Value |
|---|---:|
| Label | **SIMULATION ONLY** |
| Crop / age | maize / day 0 |
| Predicted class | acceptable |
| Acceptable probability | 0.99936 |
| Warning probability | 0.00059 |
| Spoiled probability | 0.00005 |
| Simulated chance of first spoiled inspection by next 7-day check | 0.000071 |
| Estimated days remaining | Not returned |

This is a single synthetic input example. It does not show what a real maize lot would do.

## Run the separate three-crop V3 example

The V3 input uses only a held-out simulated example row and contains no target label. It loads the saved XGBoost combined-input tomato model without retraining:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.edition2_simulation_v3 --predict examples\edition2_v3_prediction_input.json
```

Output returns `acceptable`, `warning`, and `high_risk` probabilities and is marked **SIMULATION ONLY**. The generation assumptions and all held-out results are in `data/dataset_edition_2/SIMULATION_V3_README.md` and `artifacts/edition2_simulation_v3/metrics.json`.

## Run the separate public-tomato scenario example

The standalone estimator files are in `artifacts/public_tomato/`. Run:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato-predict --input examples\public_tomato_mq_input.json --model mq_12__svc
```

The saved example predicts `Trtd` with probabilities Tc 0.275, Trt 0.269, and Trtd 0.455. The command's input file contains only sensor inputs. The saved model was fit to the 52-row tomato training table. The model input features are the 12 listed Rs/R0 readings; this example does not establish a measured quality outcome. The output is a storage scenario, not a quality grade or shelf-life estimate.

If `.review_data\tomato_sensor_laboratory.zip` is absent, download the published archive, then rerun the study command:

```powershell
New-Item -ItemType Directory -Force .review_data | Out-Null
Invoke-WebRequest -Uri "https://zenodo.org/records/15469472/files/Sensor%20and%20Laboratory%20Data.zip?download=1" -OutFile ".review_data\tomato_sensor_laboratory.zip"
.\.venv\Scripts\python.exe -m crop_prototype.cli public-tomato
```

The output is saved under `artifacts/public_tomato/`. The repository's current results report only 9 independent tomatoes in the continuous-cohort check; performance there is weak and is not crop-quality validation.

## Reproduce the main evaluation

Use the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m crop_prototype.cli inspect
.\.venv\Scripts\python.exe -m crop_prototype.cli train
.\.venv\Scripts\python.exe -m crop_prototype.cli validate
.\.venv\Scripts\python.exe -m crop_prototype.cli bootstrap
.\.venv\Scripts\python.exe -m crop_prototype.cli survival
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The commands write models and metrics to `artifacts/`. The saved fixed test split groups on `sim_lot_id`: all paths and times from a starting lot remain together. Use `RESULTS.md` for metric definitions and detailed results. A run does not make the simulator data empirical.

## Future-path page

A future path must contain one explicit row per future inspection period with the future environment fields, past/current history fields available at each period, and all nine future MQ readings. The app does not copy today's MQ values forward or predict future sensor values. Output is a conditional simulator projection under those entered values, not evidence that cooling or another intervention causes a specific shelf-life gain.

## Five-minute faculty walkthrough

1. Show `README.md`'s simulation warning and the count calculation: 5 crops × 100 starting lots per crop × 6 storage paths per lot × 40 readings per path = 120,000 rows. The report table lists 24,000 rows per crop; its TOTAL row is 120,000 rows, 500 starting lots, and 3,000 paths. These are repeated simulator observations, not 120,000 independent lots.
2. Start the browser app and select its built-in simulated example. Point out the three probabilities, next-inspection hazard, and explicit simulation label.
3. Try removing a required input and show that the app reports the missing field. Do not substitute a value from a different lot or study.
4. Show `RESULTS.md`'s grouped split and held-out scores, and state they measure reconstruction of this simulator.
5. If useful, run the separate tomato scenario command and explain that its target is treatment/storage scenario. Its small independent cohort is not a spoilage label.
6. Close with the real-data milestone: collect paired AeroSense plus nine-MQ readings and blinded inspections on independent lots, with a defined unacceptable endpoint and censoring follow-up.

## Common fixes

- If Python cannot find `crop_prototype`, run the command from the repository root.
- If a dependency is missing, install once with `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- If the browser page does not load, confirm the server terminal still runs and that port 8765 is free.
- The real AeroSense workbook is optional and was not present in the reviewed workspace. The AeroSense reader reports workbook quality only; it does not create crop labels, lot identity, or MQ pairs.
