# Real-data source audit and safe experiment plan

**Status: source audit; no cross-study joins and no synthetic labels have been added to the real files.** The raw downloads and extracted copies are in `data/real_sources/`. Re-run the inventory with:

```powershell
.\.venv\Scripts\python.exe data\real_sources\audit_sources.py
```

The audit output is `data/real_sources/source_audit.json`. The three original archives already in `.review_data/` were copied unchanged; two additional public CSVs were downloaded from their cited GitHub repositories.

## What the downloaded files actually contain

| Source | What is measured | What the released target means | Safe use now |
|---|---|---|---|
| [Zenodo tomato e-nose study](https://zenodo.org/records/15469472) | 52 random tomato samples and 90 records from 9 continuously tracked tomatoes; 12 Rs/R0 sensor channels, weight, colour, storage day and scenario | `Tc`, `Trt`, `Trtd` are storage scenarios. They are not inspected acceptable/warning/spoiled labels or event times. | A small, separate real-tomato storage-scenario task. The repository already reports this experiment. Do not claim shelf-life prediction. |
| [Zenodo nine-MQ food freshness](https://zenodo.org/records/17285312) | 59 short raw recordings, 838,502 points, all exact nine MQ columns. The tomato subset is five D1–D5 recordings with 63,885 raw points; each spans about 110–233 seconds. | Day is encoded in filenames; there is no released independent lot ID or inspected spoilage target. The source describes room-temperature recordings. | Aggregate each recording for descriptive sensor trends. Do not treat each high-frequency row as a fruit or train/test sample. Five tomato recordings cannot support a new-lot spoilage claim. |
| [Mendeley potato storage archive](https://data.mendeley.com/datasets/sbwxmtpj47/1) | 66,363 timestamped rows from 17 nodes across campaigns and storage modes; temperature, RH, tuber-core temperature and CO2. Invalid timestamps: 0. | `Mode_Stockage` is a storage treatment. Quality values are supplied separately in figure/campaign/mode summaries, without a verified join to individual IoT rows or potato lots. | Real potato environmental history and storage-mode descriptions. It is not an MQ + inspection training table. |
| [Mendeley fruit environment-condition dataset](https://data.mendeley.com/datasets/czz68d9fwj/1) mirrored from the public record | 10,995 rows for tomato, orange, pineapple and banana; temperature, humidity, light and CO2. There are 2,880 exact duplicate rows and no timestamp or lot/sample key. | Record description defines `Good`/`Bad` as optimal/suboptimal storage conditions, not whether a fruit was independently inspected and spoiled. | At most an environmental-condition classification exercise after separate source review. Not spoilage ground truth. |
| [IntelliStore public CSV](https://github.com/shivamsingha/aiot-food-storage/tree/main/datasets) | 250 rows for 10 produce names with temperature, humidity, CO2, days and `Spoiled`; 21–25 rows per produce type. No timestamps or stable sample/lot IDs. Some fruit names have whitespace variants. | The CSV has a binary spoiled field, but its released rows do not show the inspection protocol or which repeated readings belong to one physical sample. | A small exploratory table only. It cannot support a valid grouped repeated-lot evaluation from the released file alone. |
| [TriModal Ripeness 6](https://doi.org/10.6084/m9.figshare.30783827) | Six produce types including tomato; images and MQ-4 measurements; the article describes repeated observation until visible spoilage. | Visible spoiled/not-spoiled organization, not three-grade inspected quality. Ambient temperature/RH were not continuously recorded. | Strong candidate for a narrow real one-MQ visible-spoilage pilot **if** archive IDs connect gas files, fruit IDs, days and labels. Its one ZIP is about 20.4 GB, so it has not been downloaded or file-audited yet. |
| Potato e-nose storage paper | Three potato cultivars; repeated storage periods; an e-nose with some MQ plus TGS channels, and pH/soluble-solids measurements. | Storage-stage/quality-trait prediction, not the requested exact nine channels plus environmental path and inspected failure target. | Useful methods and crop evidence. The paper says the underlying data are available on request; the table is not a ready raw public download. |
| Recent potato MQ spoilage paper | A potato spoilage study reports MQ-3/MQ-135 response and microbiological measurements over time. | Microbiology/visual evidence is closer to spoilage than a storage-day label. | Potential future potato pilot; article says underlying data are available on request, so raw row-level data are not downloaded. |
| [IntelliStore paper](https://doi.org/10.1002/itl2.402) | Temperature, humidity and CO2 monitoring across 10 fruits/vegetables, with public repository CSVs. | The released `Spoiled` table lacks sample and time keys needed to verify a grouped evaluation. | Inspect as a research lead, not as validated lot-level performance. |

## Main conclusion

There is no public source found in this pass that simultaneously provides the same crop lot and timestamps with AeroSense-like temperature/RH, the exact nine MQ channels, and independent, time-stamped inspections through failure. The current project still targets **five crop types** (wheat, maize, table potato, cured dry onion, spinach). It does not contain ten real crops or ten varieties. A variety/cultivar is a subgroup within a crop species; the current synthetic lot IDs are not cultivars.

Tomato is the most practical **single-crop** candidate because multiple public studies provide real tomato sensor records. The small Zenodo dataset supports storage-scenario classification; the exact-nine-MQ archive supports a limited sensor-trend description; neither supports verified tomato spoilage prediction. TriModal Ripeness 6 has the strongest visible-spoilage label, but only MQ-4 and images, no continuous temperature/RH, and a 20.4 GB archive that still requires ID/alignment auditing.

## How to create the requested source-informed simulator without faking a join

1. Keep each downloaded source immutable. Preserve its DOI/URL, file hash, raw units, and source-specific row/sample key.
2. Build one experiment per crop and per observed target. Example: measured tomato MQ + measured tomato weight/colour predicts *storage scenario*; potato environment predicts *storage mode or measured environmental summaries*. These remain separate tasks.
3. If we generate the missing modality, write it to a **new simulation-only table**, with fields such as `source_anchor`, `generated_environment_SIM`, `generated_MQ_SIM`, `simulated_inspection_SIM`, and `assumption_set`. Never fill the raw measured table as if those fields were observed.
4. Generate a shared latent deterioration process first. Storage exposure can affect that state; the state can affect simulated VOC signals and simulated inspection labels. Keep crop-specific parameter ranges and cite the source of each range. Vary uncertain parameters and report sensitivity, rather than selecting one setting to maximize scores.
5. Keep every generated lot together during train/validation/test. Test the model against the simulator's rules only. A strong score would show that the model learned those rules; it would **not** show closeness to real spoilage prediction.
6. Compare MQ channel subsets only within a crop and target that has enough independent measured lots and labels. On generated labels, “best five sensors” would only mean best under the chosen simulator assumptions.

For a defensible paper by the immediate deadline, present the five-crop work as a simulator pipeline, the small real tomato scenario experiment as a separate real-data task, and this source audit as the justification for a future paired-lot pilot. Do not present generated environment/MQ values as measurements or call simulator performance “close to real” without an external real-lot validation set.

## Additional online leads reviewed

- [Mendeley wheat-silo insect dataset](https://data.mendeley.com/datasets/53ckhtd8gj/1): three wheat silos with temperature/moisture and insect infestation observations. This is useful for a narrow grain-infestation-risk task, not MQ spoilage; only three silos also constrain independent generalization.
- [Potato MQ e-nose and quality-trait paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9778509/): potato storage periods, MQ/TGS array and pH/SSC measurements; data availability is “within the manuscript” rather than a clean row-level download.
- [Potato MQ/microbiology spoilage paper](https://www.sciencedirect.com/science/article/pii/S0023643825016111): relevant target and sensors, but its data statement is “available on request.”
- [Spinach package-gas sensor study](https://pubs.acs.org/doi/full/10.1021/acssensors.4c02510): real spinach spoilage and microbial evidence, but uses a different sensor technology rather than the project’s MQ array.
- Onion storage sensor papers describe temperature/RH and MQ hardware, but the recent study found in this pass says raw data are not yet publicly archived.
