# Sensor and Laboratory Data – Weight, Color, Sensor Data

## Overview

This folder contains two CSV datasets used to study the shelf life of tomatoes under different storage scenarios. The datasets include weight measurement, color data and sensor recordings, either for machine learning model development (Dataframe_ML_complete.csv) or for time-based trend analysis using continuous sampling (Dataframe_continous.csv).

## Purpose

- **Dataframe_ML_complete.csv:** Contains samples collected using **random sampling** across multiple storage days. This dataset was used to train and validate machine learning models for shelf life and freshness prediction.
- **Dataframe_continous.csv** Contains **continuous sampling** data of individual tomatoes over time. This was used to analyze trends in weight loss, color change, and sensor response, helping to understand their relation to shelf life.

## Files

- `Dataframe_ML_complete.csv` — Randomly sampled data for machine learning
- `Dataframe_continous.csv` — Continuously sampled data for trend analysis

## Column Descriptions

| Column Name       | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `Sample ID`       | Unique identifier for each tomato (used as label)                           |
| `Storage Scenario`| Storage condition: `Tc` (cooled), `Trt` (room temperature), `Trtd` (room temperature + damaged) |
| `Storage Day`     | Day of storage when data was collected                                      |
| `minitial`        | Initial weight (g) of the tomato on day of purchase                         |
| `mcurrent`        | Weight (g) of the tomato on the current storage day                         |
| `L`, `a`, `b`     | Mean CIELAB color values (lightness (L*), red/green (a*), yellow/blue (b*)) averaged over 3 sides |
| `MQ2` to `MQ138`  | Sensor readings from 12 gas sensors (expressed as Rs/R₀ resistance ratios)  |

### Sensor Details

Sensor values represent **Rs/R₀** (sensor resistance over baseline resistance), indicating volatile compound presence. Sensors included:
- `MQ2`, `MQ3_1`, `MQ3_10`, `MQ4`, `MQ5`, `MQ6`, `MQ8`, `MQ9`, `MQ135`, `MQ136`, `MQ137`, `MQ138`


## Citation

If you use this dataset in your research or publication, please cite:
Senge, J.M.; Kaltenecker, F.; Krupitzer, C. Integrating Sensor Data, Laboratory Analysis, and Computer Vision in Machine Learning-Driven E-Nose Systems for Predicting Tomato Shelf Life. Chemosensors 2025, 13, 255. https://doi.org/10.3390/chemosensors13070255