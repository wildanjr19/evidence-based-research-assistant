import logging
import sqlite3
from contextlib import closing
from dataclasses import astuple
from pathlib import Path

from rag.chunking.core import Chunk, chunk_document
from rag.config import Config
from rag.ids import paper_file_stem
from rag.parsing.pipeline import load_parsed, parser_manifest, write_report

logger = logging.getLogger(__name__)

CHUNK_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk (
    chunk_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper(paper_id),
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section TEXT,
    section_order INTEGER,
    chunk_order INTEGER NOT NULL,
    text TEXT NOT NULL,
    n_tokens INTEGER NOT NULL,
    quality_flag TEXT
);
"""


def save_chunks(connection: sqlite3.Connection, paper_id: str, chunks: list[Chunk]) -> None:
    values = [astuple(chunk) for chunk in chunks]
    existing = connection.execute(
        """SELECT chunk_id, paper_id, page_start, page_end, section, section_order,
                  chunk_order, text, n_tokens, quality_flag
           FROM chunk WHERE paper_id = ? ORDER BY chunk_order""",
        (paper_id,),
    ).fetchall()
    if existing:
        if existing != values:
            raise ValueError("existing chunks differ; use a separate database for new chunking")
        return
    if any(chunk.paper_id != paper_id for chunk in chunks):
        raise ValueError("chunk paper ID does not match requested paper")
    with connection:
        connection.executemany(
            """INSERT INTO chunk (chunk_id, paper_id, page_start, page_end, section,
                section_order, chunk_order, text, n_tokens, quality_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )


def chunk_corpus(config: Config, paper_id: str | None = None) -> dict:
    if not Path(config.paths.db_path).is_file():
        raise ValueError("Corpus database is missing; run ingestion fetch first")
    outcomes = []
    with closing(sqlite3.connect(config.paths.db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(CHUNK_SCHEMA)
        query = "SELECT paper_id, pdf_sha256, parse_status FROM paper"
        rows = connection.execute(
            query + (" WHERE paper_id = ?" if paper_id else "") + " ORDER BY paper_id",
            (paper_id,) if paper_id else (),
        ).fetchall()
        if not rows:
            raise ValueError("No matching papers in corpus database")
        for identifier, expected_hash, parse_status in rows:
            try:
                if parse_status != "ok":
                    raise ValueError("parse_status is not ok; run parsing first")
                path = Path(config.paths.parsed_dir) / f"{paper_file_stem(identifier)}.json"
                document = load_parsed(path, identifier, parser_manifest(config, expected_hash))
                result = chunk_document(document, config.chunking)
                save_chunks(connection, identifier, result.chunks)
                outcomes.append(
                    {
                        "paper_id": identifier,
                        "status": "ok",
                        "chunks": len(result.chunks),
                        "dropped_tokens": result.dropped_tokens,
                        "low_quality_chunks": sum(
                            chunk.quality_flag == "low_quality" for chunk in result.chunks
                        ),
                    }
                )
                logger.info(
                    "Chunked %s: %d chunks, %d lexical tokens dropped",
                    identifier,
                    len(result.chunks),
                    result.dropped_tokens,
                )
            except (OSError, ValueError) as exc:
                outcomes.append({"paper_id": identifier, "status": "failed", "error": str(exc)})
                logger.error("Chunking failed %s: %s", identifier, exc)
    return write_report(config, "chunk", outcomes)
