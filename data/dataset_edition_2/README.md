# Dataset Edition 2 — original source files gathered by crop

This folder is an organized copy of downloaded public source datasets and records. Original project copies under `data/real_sources/` remain unchanged. Files from different studies are not merged, and no simulated rows, MQ values, crop-lot IDs, or inspection labels have been added here.

## Folder map

- `potato/original/`: public potato environmental history; separate quality workbook is not verified at row/lot level.
- `tomato/original/`: public tomato 12-channel e-nose data plus separate short exact-nine-MQ tomato recordings.
- `wheat/original/`: public three-silo environment/moisture/insect files.
- `maize/original/`: public CIMMYT storage damage, weight-loss and seed-quality workbook.
- `onion/original/`: public onion microclimate and quality workbook.
- `spinach/original/`: shelf-life model/data archive; not a paired MQ-spoilage dataset.
- `banana/original/`: Bath environment + TGS/SGP40 VOC + spectral study files, and separate nine-MQ short recordings.
- `shared_sources/`: mixed-fruit and IntelliStore reference tables that lack verified crop-lot/time joins.
- Other crop folders contain a source-status note where the candidate file was too large or only a weak/partial lead was found.

The 20.4 GB TriModal Ripeness 6 archive was not downloaded because the system drive has less free space than the compressed archive size, before extraction. No login was needed for the downloaded public files. See `source_manifest.json` for source URLs, file sizes and SHA-256 hashes.

**This is a source-organizing step only.** Some datasets are useful for narrower environmental, storage-scenario, or ripeness tasks. None is a complete paired dataset with the same crop lot/time, temperature/RH, all nine MQ channels, and independent inspections through failure. Do not concatenate them as if they were one measured experiment.

No Edition 2 simulations or new model runs have been created in this step. Those should be planned after reviewing these originals and their schemas.
