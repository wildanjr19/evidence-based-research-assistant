import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rag.config import Config
from rag.ids import is_valid_chunk_id, make_chunk_id

GENERATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    code_version TEXT,
    seed INTEGER NOT NULL,
    model_gen TEXT,
    model_embed TEXT,
    model_rerank TEXT,
    model_verify TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS answer (
    answer_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    question TEXT NOT NULL,
    raw_response TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim (
    claim_id TEXT PRIMARY KEY,
    answer_id TEXT NOT NULL REFERENCES answer(answer_id),
    claim_order INTEGER NOT NULL,
    text TEXT NOT NULL,
    citations TEXT NOT NULL,
    unsupported INTEGER NOT NULL DEFAULT 0
);
"""


def connect_corpus(config: Config, writable: bool = False) -> sqlite3.Connection:
    path = Path(config.paths.db_path).resolve()
    if not path.is_file():
        raise ValueError("Corpus database is missing; run M1 to M3 first")
    mode = "rw" if writable else "ro"
    connection = sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def load_context(chunks: list[dict], config: Config) -> tuple[list[dict], set[str]]:
    if len(chunks) > config.retrieval.final_top_k:
        raise ValueError("Context exceeds retrieval.final_top_k")
    canonical, seen = [], set()
    with closing(connect_corpus(config)) as connection:
        corpus_ids = {row[0] for row in connection.execute("SELECT chunk_id FROM chunk")}
        connection.row_factory = sqlite3.Row
        for provided in chunks:
            identifier = provided.get("chunk_id")
            if not is_valid_chunk_id(identifier) or identifier in seen:
                raise ValueError("Context must contain unique valid chunk IDs")
            row = connection.execute(
                """SELECT chunk.*, paper.title, paper.parse_status FROM chunk
                   JOIN paper USING (paper_id) WHERE chunk_id = ?""",
                (identifier,),
            ).fetchone()
            if row is None:
                raise ValueError("Context chunk is missing from corpus")
            chunk = dict(row)
            if (
                identifier
                != make_chunk_id(chunk["paper_id"], chunk["page_start"], chunk["chunk_order"])
                or chunk["parse_status"] != "ok"
                or chunk["quality_flag"] == "low_quality"
                or chunk["page_end"] < chunk["page_start"]
                or not chunk["text"].strip()
                or any(
                    provided.get(key) != chunk[key]
                    for key in ("paper_id", "page_start", "page_end", "section", "text")
                )
            ):
                raise ValueError("Context differs from canonical parsed corpus chunks")
            seen.add(identifier)
            canonical.append(chunk)
    return canonical, corpus_ids


def start_run(connection: sqlite3.Connection, report: dict) -> None:
    expected = {
        "run": [
            "run_id",
            "kind",
            "config_hash",
            "config_json",
            "code_version",
            "seed",
            "model_gen",
            "model_embed",
            "model_rerank",
            "model_verify",
            "started_at",
            "finished_at",
            "notes",
        ],
        "answer": ["answer_id", "run_id", "question", "raw_response", "created_at"],
        "claim": ["claim_id", "answer_id", "claim_order", "text", "citations", "unsupported"],
    }
    with connection:
        for table, names in expected.items():
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            if columns and columns != names:
                raise ValueError(
                    f"Existing {table} table differs from ARCHITECTURE.md; refusing to modify it"
                )
        for statement in GENERATION_SCHEMA.split(";"):
            if statement.strip():
                connection.execute(statement)
        connection.execute(
            """INSERT INTO run (run_id, kind, config_hash, config_json, code_version, seed,
               model_gen, model_embed, model_rerank, model_verify, started_at, notes)
               VALUES (?, 'query', ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                report["run_id"],
                report["config_hash"],
                json.dumps(report["config"], sort_keys=True),
                report["code_version"],
                report["seed"],
                report["config"]["generation"]["model"],
                report["config"]["embedding"]["model"]
                if report["retrieval_mode"] != "bm25"
                else None,
                report["config"]["retrieval"]["reranker_model"]
                if report["retrieval_mode"] == "hybrid+rerank"
                else None,
                report["started_at"],
                json.dumps({"status": "running"}),
            ),
        )


def finish_run(connection: sqlite3.Connection, report: dict, raw_response: str | None) -> None:
    with connection:
        connection.execute(
            """INSERT INTO answer (answer_id, run_id, question, raw_response, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                report["answer_id"],
                report["run_id"],
                report["question"],
                raw_response,
                report["finished_at"],
            ),
        )
        connection.executemany(
            """INSERT INTO claim (claim_id, answer_id, claim_order, text, citations, unsupported)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    claim["claim_id"],
                    report["answer_id"],
                    claim["claim_order"],
                    claim["text"],
                    json.dumps(claim["citations"]),
                    int(claim["unsupported"]),
                )
                for claim in report["claims"]
            ],
        )
        notes = {
            key: report[key]
            for key in (
                "status",
                "backend_calls",
                "cache_hits",
                "input_tokens",
                "output_tokens",
                "unknown_usage_attempts",
                "format_failures",
                "rejected_citations",
                "report_path",
            )
        }
        if "error" in report:
            notes["error"] = report["error"]
        connection.execute(
            "UPDATE run SET finished_at = ?, notes = ? WHERE run_id = ?",
            (report["finished_at"], json.dumps(notes), report["run_id"]),
        )
