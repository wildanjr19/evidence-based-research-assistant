import hashlib
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pymupdf

from rag.config import Config
from rag.files import atomic_write
from rag.ids import make_run_id, paper_file_stem
from rag.parsing.pdf import ParsedPaper, TextBlock, parse_pdf

logger = logging.getLogger(__name__)


def parser_manifest(config: Config, pdf_sha256: str) -> dict:
    return {
        "pdf_sha256": pdf_sha256,
        "pymupdf_version": pymupdf.VersionBind,
        "normalization_version": 2,
        "parsing_config": asdict(config.parsing),
    }


def _document_hash(document: dict) -> str:
    content = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def load_parsed(path: Path, paper_id: str, expected_manifest: dict) -> ParsedPaper:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if artifact["manifest"] != expected_manifest:
            raise ValueError("parser manifest changed; use a separate parsed_dir and database")
        raw = artifact["document"]
        if artifact["document_hash"] != _document_hash(raw) or raw["paper_id"] != paper_id:
            raise ValueError("parsed document hash or paper ID does not match")
        document = ParsedPaper(
            raw["paper_id"],
            raw["page_count"],
            [TextBlock(**block) for block in raw["blocks"]],
            raw["removed_margin_lines"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"Invalid parsed artifact {path}: {exc}") from exc
    return document


def write_report(config: Config, stage: str, papers: list[dict]) -> dict:
    run_id = make_run_id()
    report = {
        "run_id": run_id,
        "stage": stage,
        "config": asdict(config),
        "papers": papers,
        "ok": sum(paper["status"] == "ok" for paper in papers),
        "failed": sum(paper["status"] == "failed" for paper in papers),
    }
    path = Path(config.paths.parsed_dir) / "reports" / f"{stage}-{run_id.replace(':', '-')}.json"
    if path.exists():
        raise FileExistsError(f"Report already exists; refusing to overwrite {path}")
    atomic_write(path, json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    logger.info("%s: %d ok, %d failed; report=%s", stage, report["ok"], report["failed"], path)
    return report


def parse_corpus(config: Config, paper_id: str | None = None) -> dict:
    if not Path(config.paths.db_path).is_file():
        raise ValueError("Corpus database is missing; run ingestion fetch first")
    outcomes = []
    with closing(sqlite3.connect(config.paths.db_path)) as connection:
        query = "SELECT paper_id, pdf_sha256 FROM paper"
        rows = connection.execute(
            query + (" WHERE paper_id = ?" if paper_id else "") + " ORDER BY paper_id",
            (paper_id,) if paper_id else (),
        ).fetchall()
        if not rows:
            raise ValueError("No matching papers in corpus database")
        for identifier, expected_hash in rows:
            try:
                stem = paper_file_stem(identifier)
                pdf_path = Path(config.paths.raw_dir) / "pdf" / f"{stem}.pdf"
                if pdf_path.stat().st_size > config.ingestion.max_pdf_bytes:
                    raise ValueError("PDF exceeds ingestion.max_pdf_bytes")
                if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError("PDF hash differs from ingested paper version")
                manifest = parser_manifest(config, expected_hash)
                output = Path(config.paths.parsed_dir) / f"{stem}.json"
                cached = output.exists()
                if cached:
                    document = load_parsed(output, identifier, manifest)
                else:
                    document = parse_pdf(pdf_path, identifier, config.parsing)
                    raw = asdict(document)
                    artifact = {
                        "manifest": manifest,
                        "document": raw,
                        "document_hash": _document_hash(raw),
                    }
                    atomic_write(
                        output, json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")
                    )
                with connection:
                    connection.execute(
                        "UPDATE paper SET parse_status = 'ok' WHERE paper_id = ?", (identifier,)
                    )
                outcomes.append(
                    {
                        "paper_id": identifier,
                        "status": "ok",
                        "cached": cached,
                        "pages": document.page_count,
                        "removed_margin_lines": document.removed_margin_lines,
                    }
                )
                logger.info(
                    "Parsed %s: %d pages (cached=%s)", identifier, document.page_count, cached
                )
            except (OSError, ValueError, RuntimeError) as exc:
                with connection:
                    connection.execute(
                        "UPDATE paper SET parse_status = 'failed' WHERE paper_id = ?", (identifier,)
                    )
                outcomes.append({"paper_id": identifier, "status": "failed", "error": str(exc)})
                logger.error("Parse failed %s: %s", identifier, exc)
    return write_report(config, "parse", outcomes)
