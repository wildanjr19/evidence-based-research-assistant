"""Opt-in three-document Docling pilot: extract in isolation, build in main environment."""

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import pymupdf
import yaml

from rag.chunking.docling import chunk_adapted
from rag.chunking.pipeline import CHUNK_SCHEMA, save_chunks
from rag.config import load_config
from rag.ids import make_run_id, paper_file_stem
from rag.indexing.embedding import Embedder
from rag.ingestion.store import PAPER_SCHEMA
from rag.parsing.docling_adapter import QualityPolicy, adapt_document
from rag.parsing.docling_backend import native_regions

logger = logging.getLogger(__name__)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def readonly(path: str) -> sqlite3.Connection:
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def extract(
    source_config: Path,
    backend_config: Path,
    samples_path: Path,
    output_root: Path,
    policy: QualityPolicy,
) -> Path:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch

    from rag.parsing.docling_backend import make_converter

    config = load_config(source_config)
    backend = yaml.safe_load(backend_config.read_text(encoding="utf-8"))
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    if not 1 <= len(samples) <= 3:
        raise ValueError("one to three existing pilot documents only")
    output = output_root / make_run_id().replace(":", "-")
    if not output.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("full text artifacts must stay under data/")
    protected = [config.paths.parsed_dir, config.paths.index_dir, config.paths.raw_dir]
    if any(output.resolve().is_relative_to(Path(p).resolve()) for p in protected):
        raise ValueError("output must be separate from source corpus")
    selected = []
    with closing(readonly(config.paths.db_path)) as connection:
        connection.row_factory = sqlite3.Row
        for sample in samples:
            path = Path(sample["pdf"])
            sha = digest(path)
            rows = connection.execute("SELECT * FROM paper WHERE pdf_sha256 = ?", (sha,)).fetchall()
            if sha != sample["pdf_sha256"] or len(rows) != 1:
                raise ValueError("source PDF identity differs or is ambiguous")
            paper = dict(rows[0])
            if paper["license"] not in config.ingestion.allowed_licenses:
                raise ValueError("source license not allowed")
            with pymupdf.open(path) as pdf:
                count = len(pdf)
            selected.append(dict(pdf=str(path), paper=paper, page_count=count, key=sample["key"]))
    if len({s["paper"]["paper_id"] for s in selected}) != len(selected):
        raise ValueError("duplicate pilot document")
    output.mkdir(parents=True, exist_ok=False)
    effective = asdict(config)
    effective["paths"].update(
        parsed_dir=str(output / "parsed"),
        index_dir=str(output / "index"),
        db_path=str(output / "index" / "corpus.db"),
    )
    effective["evaluation"].update(
        output_dir=str(output / "evaluation"),
        dataset_path=str(output / "evaluation" / "questions.jsonl"),
        gold_labels_path=str(output / "evaluation" / "gold-labels.jsonl"),
    )
    config_path = output / "pipeline-config.yaml"
    config_path.write_text(yaml.safe_dump(effective, sort_keys=False), encoding="utf-8")
    converter, options = make_converter(backend)
    manifest = dict(
        adapter_version=1,
        source_config=str(source_config),
        source_config_sha256=digest(source_config),
        policy=asdict(policy),
        backend=backend,
        options=options,
        seed=backend["seed"],
        config_sha256=digest(config_path),
        samples_sha256=digest(samples_path),
        versions={n: version(n) for n in ("docling", "docling-core", "torch", "easyocr")},
        code_sha256={
            p.name: digest(p)
            for folder in (Path(__file__).parent, Path(__file__).parents[1] / "chunking")
            for p in folder.glob("docling*.py")
        },
        model_sha256={
            str(p.relative_to(Path(backend["models_dir"]))): digest(p)
            for p in Path(backend["models_dir"]).rglob("*")
            if p.is_file() and ".cache" not in p.parts
        },
        documents=[],
    )
    write_json(output / "inputs.json", selected)
    for sample in selected:
        start = time.perf_counter()
        name = paper_file_stem(sample["paper"]["paper_id"])
        record = dict(sample, status="failed")
        try:
            torch.cuda.reset_peak_memory_stats()
            result = converter.convert(Path(sample["pdf"]), raises_on_error=False)
            if result.status.value != "success":
                raise ValueError(f"full conversion failed: {result.status.value}")
            raw = result.document.export_to_dict()
            if {int(p) for p in raw.get("pages", {})} != set(range(1, sample["page_count"] + 1)):
                raise ValueError("converted pages differ from complete original PDF")
            regions, pages = native_regions(raw, Path(sample["pdf"]))
            adapted = adapt_document(
                raw, sample["paper"]["paper_id"], sample["page_count"], regions, policy
            )
            write_json(output / f"{name}.docling.json", raw)
            write_json(output / f"{name}.native.json", dict(regions=regions, pages=pages))
            result.document.save_as_markdown(output / f"{name}.md")
            for i, table in enumerate(result.document.tables):
                (output / f"{name}.table-{i}.html").write_text(
                    table.export_to_html(doc=result.document), encoding="utf-8"
                )
            record.update(
                status="ok",
                artifact=f"{name}.docling.json",
                artifact_sha256=digest(output / f"{name}.docling.json"),
                native_sha256=digest(output / f"{name}.native.json"),
                quality=adapted.decisions,
                pages=pages,
                missing_body_pages=sorted(
                    set(range(1, sample["page_count"] + 1))
                    - {d.get("page") for d in adapted.decisions}
                ),
            )
        except Exception as exc:
            record["error"] = str(exc)
            logger.exception("Docling failed: %s", sample["key"])
        record.update(
            elapsed_seconds=time.perf_counter() - start,
            torch_peak_allocated=torch.cuda.max_memory_allocated(),
            torch_peak_reserved=torch.cuda.max_memory_reserved(),
        )
        manifest["documents"].append(record)
        logger.info("%s: %s, %.2fs", sample["key"], record["status"], record["elapsed_seconds"])
    write_json(output / "extraction.json", manifest)
    logger.info("Extraction: %s", output)
    return output


def _build(run: Path, embedder: Embedder | None = None) -> dict:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from rag.indexing.embedding import SentenceEmbedder

    manifest = json.loads((run / "extraction.json").read_text(encoding="utf-8"))
    if not manifest.get("documents") or any(r["status"] != "ok" for r in manifest["documents"]):
        raise ValueError(
            "extraction incomplete; failed documents must not count as a successful build"
        )
    if digest(run / "pipeline-config.yaml") != manifest["config_sha256"]:
        raise ValueError("pipeline config changed")
    config = load_config(run / "pipeline-config.yaml")
    if Path(config.paths.db_path).resolve() != (run / "index" / "corpus.db").resolve():
        raise ValueError("target database must belong to new run")
    source_path = Path(manifest["source_config"])
    if digest(source_path) != manifest["source_config_sha256"]:
        raise ValueError("source config changed")
    source = load_config(source_path)
    if Path(source.paths.db_path).resolve() == Path(config.paths.db_path).resolve():
        raise ValueError("source database is protected")
    encoder = embedder if embedder is not None else SentenceEmbedder(config)
    policy = QualityPolicy(**manifest["policy"])
    outcomes = []
    Path(config.paths.db_path).parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(readonly(source.paths.db_path)) as original,
        closing(sqlite3.connect(config.paths.db_path)) as connection,
    ):
        original.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(PAPER_SCHEMA + CHUNK_SCHEMA)
        for record in manifest["documents"]:
            paper = record["paper"]
            row = original.execute(
                "SELECT * FROM paper WHERE paper_id = ?", (paper["paper_id"],)
            ).fetchone()
            if (
                row is None
                or dict(row) != paper
                or digest(Path(record["pdf"])) != paper["pdf_sha256"]
            ):
                raise ValueError("source metadata or PDF changed")
            artifact = run / record["artifact"]
            if (
                artifact.parent.resolve() != run.resolve()
                or digest(artifact) != record["artifact_sha256"]
            ):
                raise ValueError("Docling artifact changed or outside run")
            raw = json.loads(artifact.read_text(encoding="utf-8"))
            regions, _ = native_regions(raw, Path(record["pdf"]))
            adapted = adapt_document(raw, paper["paper_id"], record["page_count"], regions, policy)
            chunks, events = chunk_adapted(
                adapted, config.chunking, lambda t: encoder.token_counts([t])[0], encoder.max_tokens
            )
            collection = manifest.get("admission_policy") == "user_local_collection"
            if not chunks and not collection:
                raise ValueError("no searchable chunks passed quality gates")
            values = dict(paper, parse_status="ok" if chunks else "held")
            existing = connection.execute(
                "SELECT * FROM paper WHERE paper_id = ?", (paper["paper_id"],)
            ).fetchone()
            if existing and existing != tuple(values.values()):
                raise ValueError("existing target paper differs")
            with connection:
                connection.execute(
                    "INSERT OR IGNORE INTO paper ("
                    + ",".join(values)
                    + ") VALUES ("
                    + ",".join("?" for _ in values)
                    + ")",
                    tuple(values.values()),
                )
            save_chunks(connection, paper["paper_id"], chunks)
            outcomes.append(
                dict(
                    key=record["key"],
                    status="ok" if chunks else "held",
                    chunks=len(chunks),
                    decisions=adapted.decisions,
                    chunk_events=events,
                )
            )
    report = dict(
        papers=outcomes,
        extraction_sha256=digest(run / "extraction.json"),
        policy=asdict(policy),
        config=asdict(config),
        paid_api_calls=0,
        code_sha256={
            p.name: digest(p)
            for folder in (Path(__file__).parent, Path(__file__).parents[1] / "chunking")
            for p in folder.glob("docling*.py")
        },
    )
    return report


def build(run: Path, embedder: Embedder | None = None) -> dict:
    """Reserve a fresh report, including failures, and leave previous corpus bytes intact."""
    report = dict(status="failed")
    start = time.perf_counter()
    with (run / f"build-{make_run_id().replace(':', '-')}.json").open(
        "x", encoding="utf-8"
    ) as stream:
        try:
            report.update(_build(run, embedder), status="ok")
            return report
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            report["elapsed_seconds"] = time.perf_counter() - start
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("--source-config", type=Path, required=True)
    extract_parser.add_argument("--docling-config", type=Path, required=True)
    extract_parser.add_argument("--samples", type=Path, required=True)
    extract_parser.add_argument(
        "--output-root", type=Path, default=Path("data/skripsi/docling-full")
    )
    extract_parser.add_argument("--native-word-coverage", type=float, default=0.8)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.command == "extract":
        output = extract(
            args.source_config,
            args.docling_config,
            args.samples,
            args.output_root,
            QualityPolicy(args.native_word_coverage),
        )
        report = json.loads((output / "extraction.json").read_text(encoding="utf-8"))
        if any(r["status"] != "ok" for r in report["documents"]):
            raise SystemExit(1)
    else:
        build(args.run)


if __name__ == "__main__":
    main()
