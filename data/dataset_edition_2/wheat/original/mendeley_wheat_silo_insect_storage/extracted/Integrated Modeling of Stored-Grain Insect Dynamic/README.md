# Stored-Grain Insect Dynamics and Infestation Risk

## Overview

This code accompanies the manuscript *Integrated Modeling of Stored-Grain Insect Dynamics and Infestation Risk in Wheat Silos* by Natalia Papadimitriou, Paraskevi Agrafioti, Christos Nakas and Christos G. Athanassiou.

The workflow analyses insect-monitoring observations from three wheat silos, five beetle species, three sampling categories and 15 sampling occasions. It includes count modelling, temporal trajectories, threshold-exceedance classification, grain-trier density models and environmental nomograms.

The Gompertz section uses a previously fitted model supplied as an RDS file. It reproduces summaries and plots from that object; the current script does not refit the Gompertz model from raw data.

## Required files

Keep the following files together in one working folder:

| File | Purpose |
| --- | --- |
| `Integrated Modeling of Stored-Grain Insect Dynamics and Infestation Risk in Wheat Silos_CODE.R` | Main analysis script. |
| Excel workbook named `Integrated Modeling of Stored-Grain Insect Dynamics and Infestation Risk in Wheat Silos` | Input observations. Retain the workbook's actual Excel extension. |
| `fit_gompertz_final.rds` | Saved final derivative-Gompertz model. |
| `README.md` | Execution instructions. |

If a downloaded copy of the model has a suffix such as `(1)`, rename it to `fit_gompertz_final.rds`, as required by the script. Select the input Excel workbook interactively when prompted; its filename is not hard-coded.

## Software requirements

Run the analysis in R. RStudio is convenient for interactive execution but is not required.

Required R packages are `readxl`, `dplyr`, `ggplot2`, `glmmTMB`, `DHARMa`, `brms`, `bayesplot`, `patchwork`, `lubridate`, `tidyr` and `cmdstanr`. The `splines` and `grid` packages are supplied with R. Package dependencies must also be installed.

The Bayesian hierarchical abundance model uses the `cmdstanr` backend. This requires a working CmdStan installation and a compatible C++ toolchain in addition to the R package. Follow the [official CmdStanR installation instructions](https://mc-stan.org/cmdstanr/articles/cmdstanr.html). Confirm the installation with `cmdstanr::cmdstan_version()` before running the Bayesian section.

The abundance model is configured for four chains and four cores. Runtime and memory requirements depend on the computer and software versions; no benchmark runtime is specified. Bayesian sampling and simulation-based diagnostics are the main computationally intensive steps.

## Running the analysis

1. Place the script, Excel workbook and Gompertz RDS file in the same folder.
2. Start a fresh R session without restoring a previous workspace.
3. Open the script. Set R's working directory to the folder containing these files. In RStudio, use **Session > Set Working Directory > To Source File Location**. Check the directory with `getwd()`.
4. Install any missing dependencies and confirm that CmdStan is available.
5. Execute the script in order from the beginning. When `file.choose()` opens a selection window, select the Excel workbook named **Integrated Modeling of Stored-Grain Insect Dynamics and Infestation Risk in Wheat Silos**.
6. Allow model fitting and diagnostics to finish. Later sections use objects created earlier, so they should not be run independently unless their prerequisite objects have already been created.
7. Review console messages, model summaries and warnings alongside the exported results.

Choosing the Excel file does not change the working directory. The Gompertz file must remain accessible from that directory even if the selected Excel file is elsewhere.

Results are written to the current working directory using the filenames specified in the script. Re-running the analysis can overwrite existing outputs with the same names; use a separate working copy of the folder to preserve earlier runs.

## Input data conventions

The script reads the first worksheet by default. Column names and categorical labels are case-sensitive. The following fields are used by the workflow:

| Column | Meaning |
| --- | --- |
| `Count` | Observed insect count for the corresponding species and sampling unit. |
| `Species` | Full species name. |
| `Silo` | Silo identifier: `1`, `2` or `3`. |
| `Zone` | `CENTER`, `MIDDLE` or `EDGE`. |
| `Trap_type` | `Trap_2m`, `Trap_top` or `Trier`. |
| `Time_Index` | Sampling occasion, from 1 to 15. |
| `Date` | Sampling date, stored in a format that `readxl` imports as a date or date-time. |
| `Temperature` | Grain temperature in degrees Celsius. |
| `Humidity` | Grain moisture content (%), not air relative humidity. |

Species labels are `Cryptolestes ferrugineus`, `Oryzaephilus surinamensis`, `Rhyzopertha dominica`, `Sitophilus oryzae` and `Tribolium castaneum`.

The script constructs `Date_fixed`, assigning occasions 1–13 to 1997 and occasions 14–15 to 1998 while retaining the recorded month and day. Standardized environmental and temporal variables are derived within the script. For cross-validation, standardization is calculated within each training set.

Trier density calculations assume a 0.75-kg sample per location and aggregate sampled masses of 1.50, 3.75 and 5.25 kg for CENTER, MIDDLE and EDGE, respectively. These assumptions belong to this study design and must be reviewed before adapting the code to other datasets.

## Analysis structure

| Script sections | Content |
| --- | --- |
| 1–3 | Data preparation, descriptive summaries and exploratory figures. |
| 4–5 | Frequentist count models, model comparison and residual diagnostics. The added checks examine zero-inflation sensitivity and a BFGS refit initialized from the original coefficients. |
| 6–10 | Bayesian hierarchical negative-binomial abundance model, diagnostics and posterior summaries. |
| 11 | Species-specific spline trajectories and sensitivity analyses. |
| 12 | Loading the fitted Gompertz model, posterior peak timing and comparison with spline estimates. |
| 13 | Grain-trier-defined threshold exceedance, leave-one-sampling-date-out validation, operating cutoffs and calibration. |
| 14 | Mass-offset grain-trier density models and diagnostics. |
| 15 | Overall and species-specific environmental infestation nomograms. |

The original additive ZINB object, `m_zinb_add`, is retained separately from the sensitivity fits. Some zero-inflation coefficients have very large standard errors; consult the manuscript's discussion of this limitation rather than treating optimizer convergence alone as evidence that every coefficient is reliably estimated.

## Outputs

The workflow exports CSV summaries, graphical files and the fitted Bayesian abundance model `m_bayes_final.rds`. Other results are printed to the Console or retained as R objects.

Representative outputs include:

- `frequentist_model_comparison.csv` and `final_ZINB_effect_sizes.csv`.
- `spline_model_comparison.csv` and spline peak-sensitivity summaries.
- `gompertz_species_peak_timing.csv` and `gompertz_vs_primary_spline_df4.csv`.
- `time_adjusted_detection_crossvalidated_predictions.csv` and `time_adjusted_detection_crossvalidated_performance.csv`.
- `final_time_detection_calibration.csv`, including calibration estimates and model-based standard errors.
- `trier_density_model_comparison.csv` and `trier_density_diagnostic_summary.csv`.
- `species_nomogram_predictions.csv` and `overall_nomogram_predictions.csv`.
- Descriptive, diagnostic, temporal and nomogram figures in the formats specified in each export command.

The script also produces exploratory figures. Output filenames are computational labels and do not necessarily match the final manuscript figure numbering.

The final computational-environment block writes `sessionInfo.txt` and `cmdstan_version.txt`. Retain these with the results of the completed run. They describe the environment used for that execution; they are not a dependency lockfile. Random seeds are specified at selected fitting and simulation steps, but numerical or Monte Carlo differences may occur across software versions and platforms.

## Interpretation and reuse

The threshold of 2 live insects per kilogram is a literature-based management reference, not a locally validated regulatory limit. Calibration standard errors are model-based estimates from regressions on pooled out-of-fold predictions and do not incorporate all uncertainty in the cross-validation procedure.

Nomograms represent expected insect density averaged across the observed sampling occasions within the observed joint temperature–moisture domain. They are not direct probabilities of exceeding the reference threshold. Application to new storage systems requires appropriate validation.

## Contact

Natalia Papadimitriou  
Laboratory of Biometry, University of Thessaly  
Email: napapadim@uth.gr
