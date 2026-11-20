"""Compare isolated Docling page/table extraction with saved pilot parser output."""

import argparse
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import threading
import time
from importlib.metadata import version
from pathlib import Path

import yaml

from rag.evaluation.resources import process_resources
from rag.ids import make_run_id

logger = logging.getLogger(__name__)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", value.casefold())


def check_table_cells(grids: list[list[list[str]]], checks: list[dict]) -> list[dict]:
    """Check a row/column/value together, so an unrelated matching number cannot pass."""
    results = []
    for check in checks:
        row_label, column, expected = (normalized(check[k]) for k in ("row", "column", "value"))
        matches = []
        table_index = check.get("table_index", 0)
        for grid in grids[table_index : table_index + 1]:
            columns = {
                i for row in grid for i, text in enumerate(row) if normalized(text) == column
            }
            for row in grid:
                if any(row_label in normalized(cell) for cell in row):
                    matches.extend(row[i] for i in columns if i < len(row))
        results.append(
            dict(
                check,
                extracted=matches,
                passed=any(normalized(value) == expected for value in matches),
            )
        )
    return results


def rasterize_page(source: Path, page: int, destination: Path, dpi: int) -> None:
    import pymupdf

    with pymupdf.open(source) as original, pymupdf.open() as scan:
        selected = original[page - 1]
        pixmap = selected.get_pixmap(dpi=dpi)
        output = scan.new_page(width=selected.rect.width, height=selected.rect.height)
        output.insert_image(output.rect, stream=pixmap.tobytes("png"))
        scan.save(destination)


def run(config_path: Path, *, offline: bool = False) -> Path:
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import pymupdf
    import torch
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        EasyOcrOptions,
        LayoutObjectDetectionOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.datamodel.stage_model_specs import ObjectDetectionModelSpec
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from huggingface_hub import snapshot_download

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    samples_path = Path(config["samples_path"])
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    if not 1 <= len(samples) <= 3:
        raise ValueError("Pilot must contain one to three page samples")
    for sample in samples:
        if file_hash(Path(sample["pdf"])) != sample["pdf_sha256"]:
            raise ValueError("Source PDF changed")
        if file_hash(Path(sample["baseline"])) != sample["baseline_sha256"]:
            raise ValueError("Saved parser output changed")
        with pymupdf.open(sample["pdf"]) as pdf:
            if type(sample["page"]) is not int or not 1 <= sample["page"] <= len(pdf):
                raise ValueError("Source page outside PDF")
    if config["device"] != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("This GPU pilot requires CUDA; CPU fallback would hide a failed test")
    if config["batch_size"] != 1:
        raise ValueError("Pilot uses batch size one")
    random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    torch.set_num_threads(config["threads"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    models = Path(config["models_dir"])
    for repo, revision, patterns in (
        (
            "docling-project/docling-layout-heron",
            config["layout_revision"],
            ["*.json", "*.safetensors", "README.md", "LICENSE*"],
        ),
        (
            "docling-project/docling-models",
            config["table_revision"],
            ["model_artifacts/tableformer/accurate/*", "README.md", "LICENSE*"],
        ),
    ):
        destination = models / repo.replace("/", "--")
        if not offline:
            snapshot_download(
                repo, revision=revision, local_dir=destination, allow_patterns=patterns
            )
        if not destination.is_dir():
            raise ValueError("Pinned model artifacts missing")
    options = PdfPipelineOptions(
        artifacts_path=models,
        accelerator_options=AcceleratorOptions(device="cuda", num_threads=config["threads"]),
        layout_options=LayoutObjectDetectionOptions(
            model_spec=ObjectDetectionModelSpec(
                name="docling_layout_heron",
                repo_id="docling-project/docling-layout-heron",
                revision=config["layout_revision"],
            )
        ),
        do_ocr=True,
        ocr_options=EasyOcrOptions(
            lang=config["ocr_languages"],
            use_gpu=True,
            download_enabled=not offline,
            model_storage_directory=str(models / "easyocr"),
        ),
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=True,
        ),
        ocr_batch_size=1,
        layout_batch_size=1,
        table_batch_size=1,
        do_picture_description=False,
        do_picture_classification=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        enable_remote_services=False,
    )
    output = Path(config["output_dir"]) / make_run_id().replace(":", "-")
    if not output.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Document evidence must remain under data/")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.json", dict(config=config, options=options.model_dump(mode="json")))
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=options,
            )
        }
    )
    gpu_samples = []
    stop = threading.Event()

    def monitor() -> None:
        while not stop.is_set():
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                gpu_samples.append(int(result.stdout.splitlines()[0]))
            except (ValueError, OSError, subprocess.SubprocessError):
                pass
            stop.wait(0.5)

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    records = []
    started = time.perf_counter()
    try:
        for sample in samples:
            baseline = json.loads(Path(sample["baseline"]).read_text(encoding="utf-8"))
            old_text = "\n".join(
                b["text"] for b in baseline["document"]["blocks"] if b["page"] == sample["page"]
            )
            (output / (sample["key"] + "-baseline.txt")).write_text(old_text, encoding="utf-8")
            for variant in ("native", "scan"):
                name = sample["key"] + "-" + variant
                source, page = Path(sample["pdf"]), sample["page"]
                if variant == "scan":
                    source = output / (name + ".pdf")
                    rasterize_page(Path(sample["pdf"]), page, source, config["raster_dpi"])
                    with pymupdf.open(source) as scan:
                        if scan[0].get_text().strip():
                            raise ValueError("Raster OCR control unexpectedly contains native text")
                    page = 1
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                clock = time.perf_counter()
                result = converter.convert(source, page_range=(page, page), raises_on_error=False)
                torch.cuda.synchronize()
                tables = result.document.tables
                grids = [
                    [[cell.text for cell in row] for row in table.data.grid] for table in tables
                ]
                record = dict(
                    key=sample["key"],
                    variant=variant,
                    source_pdf_sha256=sample["pdf_sha256"],
                    original_pdf_page=sample["page"],
                    converted_pdf_page=page,
                    input_sha256=file_hash(source),
                    status=result.status.value,
                    elapsed_seconds=time.perf_counter() - clock,
                    table_count=len(tables),
                    table_grids=grids,
                    spot_checks=check_table_cells(grids, sample["checks"]),
                    check_provenance="AI visual spot checks; not human gold or parser accuracy",
                    baseline_has_expected_values=[c["value"] in old_text for c in sample["checks"]],
                    resources=process_resources(),
                )
                result.document.save_as_json(output / (name + ".json"))
                result.document.save_as_markdown(output / (name + ".md"))
                for ordinal, table in enumerate(tables, 1):
                    (output / f"{name}-table-{ordinal}.html").write_text(
                        table.export_to_html(doc=result.document),
                        encoding="utf-8",
                    )
                records.append(record)
                write_json(output / (name + "-report.json"), record)
                logger.info(
                    "%s: %s, tables=%d, cell checks=%d/%d, VRAM=%.1f MiB",
                    name,
                    record["status"],
                    len(tables),
                    sum(c["passed"] for c in record["spot_checks"]),
                    len(sample["checks"]),
                    torch.cuda.max_memory_allocated() / 2**20,
                )
    finally:
        stop.set()
        watcher.join(timeout=6)
        model_hashes = {
            str(p.relative_to(models)): file_hash(p)
            for p in models.rglob("*")
            if p.is_file() and ".cache" not in p.parts
        }
        write_json(
            output / "report.json",
            dict(
                config_sha256=file_hash(config_path),
                samples_sha256=file_hash(samples_path),
                config=config,
                offline=offline,
                records=records,
                model_sha256=model_hashes,
                versions={
                    n: version(n)
                    for n in (
                        "docling",
                        "docling-core",
                        "docling-ibm-models",
                        "docling-parse",
                        "easyocr",
                        "torch",
                        "torchvision",
                    )
                },
                source_sha256=file_hash(Path(__file__)),
                gpu=torch.cuda.get_device_name(0),
                gpu_total_bytes=torch.cuda.get_device_properties(0).total_memory,
                sampled_gpu_used_mib=gpu_samples,
                sampled_gpu_peak_mib=max(gpu_samples) if gpu_samples else None,
                gpu_sample_scope=(
                    "Whole GPU including other apps; 0.5s polling may miss short peaks"
                ),
                elapsed_seconds=time.perf_counter() - started,
                resources=process_resources(),
                paid_api_calls=0,
                corpus_write_operations=0,
            ),
        )
    logger.info("Docling pilot report: %s", output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/docling-pilot.yaml"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run(args.config, offline=args.offline)


if __name__ == "__main__":
    main()
