import hashlib
import json
import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from rag.config import Config
from rag.ids import make_chunk_id, make_run_id
from rag.indexing.embedding import Embedder, SentenceEmbedder, embed_chunks, embedding_identity
from rag.indexing.store import FTS_TOKENIZER, VectorStore, index_keywords

logger = logging.getLogger(__name__)


def load_chunks(connection: sqlite3.Connection) -> list[dict]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT chunk.*, paper.parse_status FROM chunk
           LEFT JOIN paper USING (paper_id) ORDER BY chunk_id"""
    ).fetchall()
    chunks = []
    for row in rows:
        chunk = dict(row)
        expected_id = make_chunk_id(chunk["paper_id"], chunk["page_start"], chunk["chunk_order"])
        if (
            chunk["chunk_id"] != expected_id
            or chunk["parse_status"] != "ok"
            or chunk["page_end"] < chunk["page_start"]
            or not chunk["text"].strip()
        ):
            raise ValueError(f"Invalid or unparsed corpus chunk: {chunk['chunk_id']}")
        chunks.append(chunk)
    if not chunks:
        raise ValueError("No chunks available; run parsing and chunking first")
    connection.row_factory = None
    return chunks


def index_corpus(config: Config, embedder: Embedder | None = None) -> dict:
    if not Path(config.paths.db_path).is_file():
        raise ValueError("Corpus database is missing; run ingestion, parsing and chunking first")
    started = time.perf_counter()
    run_id = make_run_id()
    effective_config = asdict(config)
    report = {
        "run_id": run_id,
        "stage": "index",
        "status": "failed",
        "config": effective_config,
        "config_hash": hashlib.sha256(
            json.dumps(effective_config, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "seed": config.verification.seed,
        "versions": {
            name: version(name)
            for name in ("torch", "sentence-transformers", "transformers", "lancedb")
        },
        "fts_tokenizer": FTS_TOKENIZER,
    }
    report_path = (
        Path(config.paths.index_dir) / "reports" / f"index-{run_id.replace(':', '-')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the report name before indexing so a run ID collision cannot overwrite history.
    with report_path.open("x", encoding="utf-8") as stream:
        try:
            with closing(sqlite3.connect(config.paths.db_path)) as connection:
                chunks = load_chunks(connection)
                report["chunks"] = len(chunks)
                encoder = embedder if embedder is not None else SentenceEmbedder(config)
                identity = embedding_identity(config, encoder)
                report["embedding"] = identity
                vectors, statistics = embed_chunks(chunks, config, encoder)
                report.update(statistics)
                store = VectorStore(Path(config.paths.index_dir) / "vectors.lance", identity)
                report["vector_count"] = store.append(chunks, vectors)
                report["fts_count"] = index_keywords(connection, chunks)
                if report["fts_count"] != len(chunks):
                    raise ValueError("Keyword row count does not match corpus chunk count")
                report["status"] = "ok"
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            report["elapsed_seconds"] = time.perf_counter() - started
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            logger.info("Indexing %s; report=%s", report["status"], report_path)
    logger.info(
        "Indexed %d chunks in %.2fs: %d embeddings computed, %d cached",
        report["chunks"],
        report["elapsed_seconds"],
        report["computed_embeddings"],
        report["cache_hits"],
    )
    return report
