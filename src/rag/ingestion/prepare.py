"""Admit validated local download snapshots to the existing corpus schema."""

import hashlib
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rag.config import Config
from rag.files import atomic_write
from rag.ids import make_paper_id, make_run_id, paper_file_stem
from rag.ingestion.arxiv import license_from_url
from rag.ingestion.bibliography import normalize_doi
from rag.ingestion.download_http import DownloadSettings
from rag.ingestion.downloads import validate_pdf
from rag.ingestion.store import PAPER_SCHEMA

logger = logging.getLogger(__name__)


def prepare_downloads(config: Config, download_report: Path) -> dict:
    """Validate every admitted snapshot before writing PDFs or metadata; never replace a version."""
    report = json.loads(download_report.read_text(encoding="utf-8"))
    settings = DownloadSettings(**report["config"])
    bibliography = Path(settings.bibliography_run)
    for name, expected_hash in report["input_sha256"].items():
        if name not in {"entries.jsonl", "references.jsonl"}:
            raise ValueError("Unexpected bibliography input path")
        if hashlib.sha256((bibliography / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Bibliography differs from the download report")
    if set(report["input_sha256"]) != {"entries.jsonl", "references.jsonl"}:
        raise ValueError("Download report lacks bibliography hashes")
    entries = {
        e["reference_id"]: e
        for e in (
            json.loads(line)
            for line in (bibliography / "entries.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    ready = [r for r in report["references"] if r["status"] == "pdf_ready"]
    if not ready or len(ready) > config.ingestion.max_papers:
        raise ValueError("Expected 1..ingestion.max_papers ready PDF snapshots")
    prepared = []
    seen = set()
    for record in ready:
        entry = entries[record["reference_id"]]
        doi = normalize_doi(entry["metadata"]["doi"])
        if doi is None or doi != entry["doi"]:
            raise ValueError("Missing or inconsistent bibliography DOI")
        if (
            record["license"] not in config.ingestion.allowed_licenses
            or license_from_url(record["license_url"]) != record["license"]
        ):
            raise ValueError("Snapshot license is invalid or not allowed by corpus config")
        source_pdf = Path(record["pdf_path"])
        source_pdf.resolve().relative_to((download_report.parent.parent / "pdf").resolve())
        if source_pdf.stat().st_size > config.ingestion.max_pdf_bytes:
            raise ValueError("PDF exceeds ingestion.max_pdf_bytes")
        content = source_pdf.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != record["pdf_sha256"] or record["snapshot_version"] != "sha256:" + digest:
            raise ValueError("Downloaded PDF hash or snapshot version differs")
        validation = validate_pdf(content, "application/pdf", entry, record, settings)
        if validation["pages"] != record["pages"]:
            raise ValueError("Downloaded PDF page count differs")
        source_id = f"{doi}_sha256_{digest}"
        paper_id = make_paper_id("crossref", source_id)
        stem = paper_file_stem(paper_id)
        if stem in seen:
            raise ValueError("Duplicate PDF snapshot or filename in download report")
        seen.add(stem)
        if datetime.fromisoformat(record["fetched_at"]).tzinfo is None:
            raise ValueError("Snapshot fetched_at requires a timezone")
        authors = [a.strip() for a in entry["metadata"]["author"].split(" and ")]
        values = (
            paper_id,
            "crossref",
            source_id,
            record["publisher_title"],
            json.dumps(authors, ensure_ascii=False),
            int(entry["metadata"]["year"]),
            None,
            doi,
            record["license"],
            record["license_url"],
            record["landing_url"],
            digest,
            record["fetched_at"],
        )
        path = Path(config.paths.raw_dir) / "pdf" / f"{stem}.pdf"
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Existing corpus PDF differs; refusing to overwrite")
        prepared.append(
            (
                values,
                path,
                content,
                {
                    "paper_id": paper_id,
                    "reference_id": record["reference_id"],
                    "citation_keys": record["citation_keys"],
                    "pdf_sha256": digest,
                    "snapshot_version": record["snapshot_version"],
                    "content_version": record["content_version"],
                    "doi": doi,
                    "pdf_path": str(path),
                    "original_pdf_path": str(source_pdf),
                    "pdf_url": record["pdf_url"],
                    "pages": record["pages"],
                },
            )
        )
    db = Path(config.paths.db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db)) as connection:
        connection.executescript(PAPER_SCHEMA)
        for values, _, _, _ in prepared:
            existing = connection.execute(
                """SELECT paper_id, source, source_id, title, authors, year, venue, doi,
                   license, license_url, landing_url, pdf_sha256, fetched_at
                   FROM paper WHERE paper_id = ?""",
                (values[0],),
            ).fetchone()
            if existing is not None and existing != values:
                raise ValueError("Existing snapshot metadata differs; refusing to overwrite")
        with connection:
            for values, path, content, _ in prepared:
                if not path.exists():
                    atomic_write(path, content)
                connection.execute(
                    """INSERT INTO paper (paper_id, source, source_id, title, authors, year,
                       venue, doi, license, license_url, landing_url, pdf_sha256, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(paper_id) DO NOTHING""",
                    values,
                )
    result = {
        "run_id": make_run_id(),
        "config": asdict(config),
        "download_report": str(download_report),
        "download_report_sha256": hashlib.sha256(download_report.read_bytes()).hexdigest(),
        "papers": [p[3] for p in prepared],
    }
    destination = (
        Path(config.paths.index_dir)
        / "reports"
        / ("prepare-" + result["run_id"].replace(":", "-") + ".json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    logger.info("Prepared %d local snapshots; report: %s", len(prepared), destination)
    return result
