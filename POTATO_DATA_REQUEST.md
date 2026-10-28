# Potato study data request draft

Subject: Request for sample-level potato electronic-nose data for grouped reanalysis

Corresponding-author email listed in the article: `weizhb@zju.edu.cn`.

Dear Dr. Wei and co-authors,

I am developing a crop-quality research project on sensor-based potato storage monitoring. I read your paper, “Early Identification of Rotten Potatoes Using an Electronic Nose Based on Feature Discretization and Ensemble Convolutional Neural Network” (Sensors, 2024; DOI: 10.3390/s24103105). Your normal, slightly rotten, and totally rotten potato measurements are highly relevant to our potato-only work.

Would you be willing to share the sample-level data and metadata needed to reproduce a leakage-safe analysis? Ideally, this would include:

- the 12-channel × 180-time-point raw response for each sample, with channel names, units, and preprocessing details;
- stable physical sample/tuber ID, source lot, storage box or chamber ID, and acquisition run/date;
- the label for each sample and the exact visual/rot-ratio rubric used to assign it;
- whether any tubers or mixtures appear in more than one sample or split;
- measured temperature and relative humidity matched to each sample or storage box, if collected;
- the original train/validation/test assignment and the grouping unit used for it;
- the permitted research use and citation/licensing conditions.

We will keep this study separate from other crops and will not infer AeroSense, MQ, lot, or quality values that were not measured. If the environmental measurements are not paired at sample or box level, we will analyze the e-nose data as MQ-only and will not claim a combined MQ + environment model.

Thank you for considering the request.

Best regards,
\[Name / institution / advisor contact\]

**Status:** prepared for you/advisor to send. No email has been sent from this workspace.

## Acceptance checks before modeling

1. Confirm that every row maps to one independently defined sample and preserve source-lot and chamber/run identifiers.
2. Determine whether the reported 300 laboratory and 300 storage records are independent potatoes, repeat readings, or pooled mixtures.
3. Group all records from a potato, lot, and storage run together during validation; keep a final group untouched.
4. Compare MQ-only, environment-only, and combined features only if the environmental fields are actually matched to the same potato sample or storage box at that time.
5. Treat the three labels as the paper's rot stages. Do not rename them acceptable/warning/spoiled until an advisor defines and justifies that mapping.
6. Treat this as current rot-stage classification. The described experiment does not by itself provide time-to-failure or censored shelf-life targets.
