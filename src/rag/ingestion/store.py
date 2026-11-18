import json
import re
import sqlite3

from rag.ingestion.arxiv import Paper

PAPER_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper (
    paper_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    license TEXT NOT NULL,
    license_url TEXT,
    landing_url TEXT NOT NULL,
    pdf_sha256 TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    parse_status TEXT NOT NULL DEFAULT 'pending'
);
"""


def save_paper(connection: sqlite3.Connection, paper: Paper, sha256: str, fetched_at: str) -> None:
    """Preserve existing parse status and refuse changed bytes under a versioned paper ID."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("pdf_sha256 must be a SHA-256 digest")
    existing = connection.execute(
        "SELECT pdf_sha256 FROM paper WHERE paper_id = ?", (paper.paper_id,)
    ).fetchone()
    if existing is not None and existing[0] != sha256:
        raise ValueError(f"{paper.paper_id}: PDF hash differs from the stored version")
    with connection:
        connection.execute(
            """INSERT INTO paper (
                paper_id, source, source_id, title, authors, year, venue, doi,
                license, license_url, landing_url, pdf_sha256, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO NOTHING""",
            (
                paper.paper_id,
                "arxiv",
                paper.source_id,
                paper.title,
                json.dumps(paper.authors, ensure_ascii=False),
                paper.year,
                paper.venue,
                paper.doi,
                paper.license,
                paper.license_url,
                paper.landing_url,
                sha256,
                fetched_at,
            ),
        )
