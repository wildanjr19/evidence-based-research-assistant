import hashlib
import json
import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from rag.config import Config
from rag.ingestion.arxiv import ArxivClient, Paper, atomic_write
from rag.ingestion.store import PAPER_SCHEMA, save_paper

logger = logging.getLogger(__name__)


def discover(config: Config, client: ArxivClient) -> list[Paper]:
    papers = client.discover()
    records = [
        json.dumps(
            {"paper_id": paper.paper_id, "landing_url": paper.landing_url, **asdict(paper)},
            ensure_ascii=False,
        )
        for paper in papers
    ]
    path = Path(config.paths.raw_dir) / "candidates.jsonl"
    atomic_write(path, ("\n".join(records) + ("\n" if records else "")).encode("utf-8"))
    logger.info("Saved %d candidates to %s", len(papers), path)
    return papers


def load_candidates(path: Path, limit: int) -> list[Paper]:
    papers = []
    seen = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number > limit:
                break
            try:
                raw = json.loads(line)
                paper_id = raw.pop("paper_id")
                landing_url = raw.pop("landing_url")
                paper = Paper(**raw)
                if paper_id != paper.paper_id or landing_url != paper.landing_url:
                    raise ValueError("candidate ID or landing URL does not match source_id")
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError(f"{path}: invalid candidate at line {line_number}: {exc}") from exc
            if paper.paper_id not in seen:
                seen.add(paper.paper_id)
                papers.append(paper)
    return papers


def fetch(config: Config, client: ArxivClient) -> int:
    """Only admit metadata after a licensed PDF and its real hash are available."""
    papers = load_candidates(
        Path(config.paths.raw_dir) / "candidates.jsonl", config.ingestion.max_papers
    )
    db_path = Path(config.paths.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    stored = 0
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(PAPER_SCHEMA)
        for paper in papers:
            if paper.license not in config.ingestion.allowed_licenses:
                logger.warning(
                    "Rejected %s: license %s is not allowed by config",
                    paper.paper_id,
                    paper.license,
                )
                continue
            path = Path(config.paths.raw_dir) / "pdf" / paper.filename
            if path.exists():
                if path.stat().st_size > config.ingestion.max_pdf_bytes:
                    raise ValueError(
                        f"{paper.paper_id}: cached PDF exceeds ingestion.max_pdf_bytes"
                    )
                content = path.read_bytes()
                if not content.startswith(b"%PDF-"):
                    raise ValueError(f"{paper.paper_id}: cached file is not a PDF")
            else:
                content = client.download_pdf(paper)
            digest = hashlib.sha256(content).hexdigest()
            existing = connection.execute(
                "SELECT pdf_sha256 FROM paper WHERE paper_id = ?", (paper.paper_id,)
            ).fetchone()
            if existing is not None and existing[0] != digest:
                raise ValueError(f"{paper.paper_id}: PDF hash differs from the stored version")
            if not path.exists():
                atomic_write(path, content)
            fetched_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            save_paper(connection, paper, digest, fetched_at)
            stored += 1
            logger.info("Available %s (license=%s)", paper.paper_id, paper.license)
    logger.info("%d papers available in %s", stored, db_path)
    return stored
