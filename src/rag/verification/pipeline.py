import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from rag.config import Config
from rag.generation.store import connect_corpus
from rag.verification.judge import ClaimJudge
from rag.verification.minicheck import CachedVerifier

VERIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS verification (
    claim_id TEXT NOT NULL REFERENCES claim(claim_id),
    chunk_id TEXT NOT NULL REFERENCES chunk(chunk_id),
    verifier TEXT NOT NULL,
    model TEXT,
    label TEXT NOT NULL,
    score REAL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (claim_id, chunk_id, verifier)
)
"""


def verify_answer(
    answer: dict,
    config: Config,
    verifier: CachedVerifier,
    judge: ClaimJudge | None = None,
    sampled_claim_ids: set[str] | None = None,
) -> list[dict]:
    results = []
    with closing(connect_corpus(config, writable=True)) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(verification)")]
        expected = [
            "claim_id",
            "chunk_id",
            "verifier",
            "model",
            "label",
            "score",
            "rationale",
            "created_at",
        ]
        if columns and columns != expected:
            raise ValueError("Existing verification table differs from ARCHITECTURE.md")
        with connection:
            connection.execute(VERIFICATION_SCHEMA)
        connection.row_factory = sqlite3.Row
        for claim in answer["claims"]:
            stored = connection.execute(
                "SELECT text, citations, unsupported FROM claim WHERE claim_id = ?",
                (claim["claim_id"],),
            ).fetchone()
            if stored is None or (
                stored["text"] != claim["text"]
                or json.loads(stored["citations"]) != claim["citations"]
                or bool(stored["unsupported"]) != claim["unsupported"]
            ):
                raise ValueError("Verification claim differs from persisted generation")
            for chunk_id in claim["citations"]:
                evidence = connection.execute(
                    "SELECT text FROM chunk WHERE chunk_id = ?", (chunk_id,)
                ).fetchone()
                if evidence is None:
                    raise ValueError("Cited chunk is missing")
                backends = [verifier]
                if judge is not None and claim["claim_id"] in (sampled_claim_ids or set()):
                    backends.append(judge)
                for backend in backends:
                    record = {"claim_id": claim["claim_id"], "chunk_id": chunk_id}
                    try:
                        record.update(backend.verify(claim["text"], evidence["text"]))
                        with connection:
                            connection.execute(
                                """INSERT INTO verification VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                tuple(record[key] for key in expected[:-1])
                                + (datetime.now(UTC).isoformat(),),
                            )
                    except (ValueError, RuntimeError, OSError, ImportError) as exc:
                        record.update(
                            verifier="llm_judge" if backend is judge else "minicheck",
                            label=None,
                            score=None,
                            error=f"Verification failed ({type(exc).__name__})",
                        )
                    results.append(record)
    return results
