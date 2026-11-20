"""Offline-only Docling backend, imported inside the isolated environment."""

from pathlib import Path

import pymupdf


def native_regions(raw: dict, pdf: Path) -> tuple[dict[str, str], list[dict]]:
    regions, pages = {}, []
    with pymupdf.open(pdf) as document:
        if document.needs_pass or not document.is_pdf:
            raise ValueError("expected an unencrypted PDF")

        def read(page_number: int, box: dict) -> str:
            if type(page_number) is not int or not 1 <= page_number <= len(document):
                return ""
            page = document[page_number - 1]
            if box.get("coord_origin") == "BOTTOMLEFT":
                rect = pymupdf.Rect(
                    box["l"], page.rect.height - box["t"], box["r"], page.rect.height - box["b"]
                )
            elif box.get("coord_origin") == "TOPLEFT":
                rect = pymupdf.Rect(box["l"], box["t"], box["r"], box["b"])
            else:
                return ""
            if rect.is_empty or rect.is_infinite or not page.rect.contains(rect):
                return ""
            # Word centres avoid losing glyphs when model boxes clip ascenders/descenders.
            return " ".join(
                w[4]
                for w in page.get_text("words")
                if rect.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
            )

        for name in ("texts", "tables"):
            for item in raw.get(name, []):
                provenance = item.get("prov", [])
                if len(provenance) != 1:
                    continue
                p = provenance[0]
                try:
                    regions[item["self_ref"]] = read(p["page_no"], p["bbox"])
                    if name == "tables":
                        for i, cell in enumerate(item["data"]["table_cells"]):
                            regions[f"{item['self_ref']}/cell/{i}"] = read(
                                p["page_no"], cell["bbox"]
                            )
                except (KeyError, TypeError, ValueError):
                    continue
        for i, page in enumerate(document, 1):
            pages.append(
                dict(
                    page=i,
                    native_characters=len(page.get_text().strip()),
                    images=len(page.get_images()),
                )
            )
    return regions, pages


def make_converter(config: dict) -> tuple[object, dict]:
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

    if config["device"] != "cuda" or not torch.cuda.is_available() or config["batch_size"] != 1:
        raise ValueError("Docling requires CUDA and batch size one; no fallback")
    cell_matching = config.get("do_cell_matching", True)
    if type(cell_matching) is not bool:
        raise ValueError("do_cell_matching must be a boolean")
    torch.manual_seed(config["seed"])
    torch.set_num_threads(config["threads"])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    models = Path(config["models_dir"])
    if not models.is_dir():
        raise ValueError("pinned local models missing")
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
            download_enabled=False,
            model_storage_directory=str(models / "easyocr"),
        ),
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE, do_cell_matching=cell_matching
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
    # Docling AUTO OCR selects bitmap regions; never force a native page to full-page OCR.
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    ), options.model_dump(mode="json", serialize_as_any=True)
