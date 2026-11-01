"""Download and arrange public crop-source files for Dataset Edition 2.

This script handles original source archives only. It does not join datasets,
add simulated values, make labels, or train models. Existing files under
data/real_sources are read-only inputs; this script copies them into the
edition folder and verifies downloads with SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent / "dataset_edition_2"
PROJECT = Path(__file__).resolve().parents[1]
RAW = PROJECT / "data" / "real_sources" / "raw"
EXTRACTED = PROJECT / "data" / "real_sources" / "extracted"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_prefix: bytes | None = None) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "CropResearchDataOrganizer/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        first = response.read(16)
        if expected_prefix and not first.startswith(expected_prefix):
            raise ValueError(f"Unexpected response content for {destination.name}: {first!r}")
        output.write(first)
        shutil.copyfileobj(response, output)
        content_type = response.headers.get("Content-Type", "")
    return {"path": str(destination.relative_to(ROOT)), "bytes": destination.stat().st_size,
            "sha256": sha256(destination), "content_type": content_type, "source_url": url}


def copy_source(source: Path, destination: Path, source_url: str, description: str) -> dict:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": str(destination.relative_to(ROOT)), "bytes": destination.stat().st_size,
            "sha256": sha256(destination), "source_url": source_url,
            "description": description, "copied_from_project_source": str(source.relative_to(PROJECT))}


def extract_zip(archive_path: Path, output_dir: Path, names: set[str] | None = None) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            pure = PurePosixPath(member.filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"Unsafe archive member path: {member.filename}")
            if names is not None and pure.name not in names:
                continue
            target = output_dir.joinpath(*pure.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            written.append(str(target.relative_to(ROOT)))
    return written


def main() -> None:
    inventory = []

    # Existing project copies: preserve the original files and their licenses.
    inventory.append(copy_source(
        RAW / "mendeley_potato_storage_environment.zip",
        ROOT / "potato" / "original" / "mendeley_potato_environment" / "source_archive.zip",
        "https://data.mendeley.com/datasets/sbwxmtpj47/1",
        "Potato storage environment archive; temperature/RH/core temperature/CO2 and separate quality summaries; not MQ-paired."))
    extract_zip(ROOT / inventory[-1]["path"], ROOT / "potato" / "original" / "mendeley_potato_environment" / "extracted")

    inventory.append(copy_source(
        RAW / "zenodo_15469472_tomato_sensor_lab.zip",
        ROOT / "tomato" / "original" / "zenodo_tomato_12_channel_enose" / "source_archive.zip",
        "https://zenodo.org/records/15469472",
        "Tomato measurements with 12 Rs/R0 channels, weight, color, storage day and scenario; released CSVs omit temperature/RH and lack inspected spoilage labels."))
    extract_zip(ROOT / inventory[-1]["path"], ROOT / "tomato" / "original" / "zenodo_tomato_12_channel_enose" / "extracted")

    inventory.append(copy_source(
        RAW / "zenodo_17285312_nine_mq_food_freshness.zip",
        ROOT / "shared_sources" / "zenodo_exact_nine_mq_food_freshness" / "source_archive.zip",
        "https://zenodo.org/records/17285312",
        "Exact nine-MQ short recordings across foods; no verified lot IDs, matched environment history or independent spoilage labels."))
    selected_tomato = {f"Tomato D{i}.csv" for i in range(1, 6)} | {f"tomato D{i}.csv" for i in range(1, 6)}
    inventory[-1]["tomato_recordings_extracted"] = extract_zip(
        ROOT / inventory[-1]["path"], ROOT / "tomato" / "original" / "zenodo_exact_nine_mq_tomato_recordings", selected_tomato)
    selected_banana = {f"Banana D{i}.csv" for i in range(1, 6)}
    inventory[-1]["banana_recordings_extracted"] = extract_zip(
        ROOT / inventory[-1]["path"], ROOT / "banana" / "original" / "zenodo_exact_nine_mq_banana_recordings", selected_banana)

    # Additional publicly downloadable crop sources found in the follow-up search.
    inventory.append(download(
        "https://data.mendeley.com/public-api/zip/53ckhtd8gj/download/3",
        ROOT / "wheat" / "original" / "mendeley_wheat_silo_insect_storage" / "source_archive_v3.zip",
        b"PK\x03\x04"))
    extract_zip(ROOT / inventory[-1]["path"], ROOT / "wheat" / "original" / "mendeley_wheat_silo_insect_storage" / "extracted")

    inventory.append(download(
        "https://data.cimmyt.org/api/access/datafile/20789",
        ROOT / "maize" / "original" / "cimmyt_maize_storage_quality" / "DAT-PostharvestLoss-SeedGermination-2022-07-26.xlsx",
        b"PK\x03\x04"))

    inventory.append(download(
        "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0210577.s003&type=supplementary",
        ROOT / "onion" / "original" / "plos_onion_microclimate_quality" / "S1_Dataset_all_microclimate_and_quality.xlsx",
        b"PK\x03\x04"))

    spinach_zip = download(
        "https://data.mendeley.com/public-api/zip/kphtgxn3ff/download/4",
        ROOT / "spinach" / "original" / "mendeley_realtime_shelf_life_model" / "source_archive_v4.zip",
        b"PK\x03\x04")
    inventory.append(spinach_zip)
    extract_zip(ROOT / spinach_zip["path"], ROOT / "spinach" / "original" / "mendeley_realtime_shelf_life_model" / "extracted")

    bath_root = ROOT / "banana" / "original" / "bath_multisensor_banana_ripeness"
    bath_files = [("ds_34.zip", "https://researchdata.bath.ac.uk/1459/1/ds_34.zip"),
                  ("Spect.zip", "https://researchdata.bath.ac.uk/1459/2/Spect.zip"),
                  ("TPHiS.zip", "https://researchdata.bath.ac.uk/1459/3/TPHiS.zip"),
                  ("VOC.zip", "https://researchdata.bath.ac.uk/1459/4/VOC.zip")]
    for filename, url in bath_files:
        item = download(url, bath_root / filename, b"PK\x03\x04")
        inventory.append(item)
    for filename, _ in bath_files:
        extract_zip(bath_root / filename, bath_root / "extracted" / Path(filename).stem)

    # Shared, already-downloaded reference tables are kept separate from crop-lot files.
    for filename, url, note in [
        ("github_environment_fruit_spoilage_Dataset.csv", "https://github.com/SdIshtiyaqAhmed/fruit-spoilage-prediction-iot-ml", "Environment-only fruit table; Good/Bad is not verified inspection spoilage."),
        ("github_intellistore_environment_Dataset.csv", "https://github.com/shivamsingha/aiot-food-storage", "Small sensor table with uncertain physical lot/time and target provenance."),
        ("github_intellistore_fruit_reference.csv", "https://github.com/shivamsingha/aiot-food-storage", "Reference table, not paired sensor/inspection records."),
    ]:
        inventory.append(copy_source(RAW / filename, ROOT / "shared_sources" / "github_reference_tables" / filename,
                                     url, note))

    # Explicitly preserve absence/size limits rather than making up local source data.
    unavailable = {
        "carrot": "TriModal Ripeness 6 contains carrot records with MQ-4 and images, but its roughly 20.4 GB archive was not downloaded: current C: free space is below the archive size, before extraction. See the source card.",
        "guava": "TriModal Ripeness 6 source is identified, but the roughly 20.4 GB archive was not downloaded for the same disk-space reason.",
        "indian_gooseberry": "TriModal Ripeness 6 source is identified, but the roughly 20.4 GB archive was not downloaded for the same disk-space reason.",
        "mango": "TriModal Ripeness 6 source is identified, but the roughly 20.4 GB archive was not downloaded for the same disk-space reason.",
        "orange": "An existing shared fruit-environment table contains orange rows but no verified lot IDs, timestamps or inspection-based spoilage labels. It is stored under shared_sources.",
        "pineapple": "An existing shared fruit-environment table contains pineapple rows but no verified lot IDs, timestamps or inspection-based spoilage labels. It is stored under shared_sources.",
    }
    for crop, note in unavailable.items():
        folder = ROOT / crop / "original"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SOURCE_STATUS.md").write_text(
            f"# {crop.replace('_', ' ').title()} original-source status\n\n{note}\n",
            encoding="utf-8")

    notes = {
        "potato": "Environmental storage histories and separate quality summaries only. Separate potato e-nose papers are catalogued in the root source index; their raw row-level measurements were not public downloads.",
        "tomato": "Two original studies are kept separate: the 12-channel tomato e-nose archive, and the five short tomato recordings extracted from the exact-nine-MQ archive. Neither supplies a same-lot paired T/RH + nine-MQ + independently inspected failure table.",
        "wheat": "Three-silo temperature/moisture/insect records support a narrow infestation/environment task; only three silos and no MQ spoilage measurements.",
        "maize": "CIMMYT workbook contains storage quality/insect/germination outcomes and environment context; no MQ array or repeated synchronized sensor histories.",
        "onion": "PLOS workbook contains microclimate and quality for six batches; no MQ channels and sparse quality inspection occasions.",
        "spinach": "The Mendeley bundle is a shelf-life model/data resource, not a paired MQ-spoilage table; see its original files and license.",
        "banana": "Bath data include environment and non-MQ VOC/spectral data; exact-nine-MQ short recordings are a different source and are not joined to Bath samples.",
    }
    for crop, note in notes.items():
        folder = ROOT / crop / "original"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SOURCE_NOTES.md").write_text(f"# {crop.replace('_', ' ').title()} sources\n\n{note}\n", encoding="utf-8")

    manifest = {"edition": "2 originals organization", "created_by": "data/fetch_edition_2_originals.py",
                "no_cross_study_join": True, "no_synthetic_values_added": True,
                "files": inventory}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = """# Dataset Edition 2 — original source files gathered by crop

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
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"edition_folder": str(ROOT), "files_copied_or_downloaded": len(inventory),
                      "manifest": str(ROOT / "source_manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
