# Public real-data sources

`raw/` holds downloaded source files; `extracted/` contains the original files extracted from those archives. Treat these as read-only inputs. No source rows have been joined across studies or filled with generated values.

Run the audit from the project root:

```powershell
.\.venv\Scripts\python.exe data\real_sources\audit_sources.py
```

The command writes `source_audit.json` with source-file SHA-256 hashes, schemas, row counts, missingness, duplicate counts, timestamp checks, and target/ID cautions. See the project-root `REAL_DATA_AUDIT.md` for what each source can and cannot support.

## Downloaded files

- `raw/zenodo_15469472_tomato_sensor_lab.zip` — tomato gas sensor, weight, colour and storage-scenario tables; DOI 10.5281/zenodo.15469472.
- `raw/zenodo_17285312_nine_mq_food_freshness.zip` — raw files from all nine exact MQ channels across food recordings; DOI 10.5281/zenodo.17285312.
- `raw/mendeley_potato_storage_environment.zip` — potato environment histories and separate quality-summary workbook; DOI 10.17632/sbwxmtpj47.1.
- `raw/github_environment_fruit_spoilage_Dataset.csv` — public mirror associated with Mendeley DOI 10.17632/czz68d9fwj.1. Its `Good`/`Bad` class is described as environmental condition quality, not inspected fruit spoilage.
- `raw/github_intellistore_environment_Dataset.csv` and `raw/github_intellistore_fruit_reference.csv` — public IntelliStore repository tables. The measurement table has no timestamps or stable physical-sample IDs.

The large TriModal Ripeness 6 Figshare archive (about 20.4 GB) has **not** been downloaded. Its article and repository metadata are listed in `REAL_DATA_AUDIT.md`; download it only if we proceed with the narrow tomato visible-spoilage task and have enough storage for the archive and extracted files.
