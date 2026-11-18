import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from rag.config import Config
from rag.indexing.embedding import text_hash, validate_vector
from rag.indexing.pipeline import load_chunks
from rag.indexing.store import FTS_TOKENIZER


class RetrievalStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        path = Path(config.paths.db_path).resolve()
        if not path.is_file():
            raise ValueError("Corpus database is missing; run M1 to M3 first")
        self.uri = path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(self.uri, uri=True)) as connection:
            self.chunks = {row["chunk_id"]: row for row in load_chunks(connection)}
        self.fts_checked = False
        self.table = None
        self.identity: dict | None = None

    def bm25(self, question: str, limit: int) -> list[tuple[str, float]]:
        # Quote lexical terms so user input cannot become FTS operators or column selectors.
        terms = list(dict.fromkeys(re.findall(r"\w+", question, re.UNICODE)))
        if not terms:
            return []
        expression = " OR ".join('"' + term + '"' for term in terms)
        with closing(sqlite3.connect(self.uri, uri=True)) as connection:
            if not self.fts_checked:
                definition = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name = 'chunk_fts'"
                ).fetchone()
                if not definition or f"tokenize='{FTS_TOKENIZER}'" not in definition[0]:
                    raise ValueError("Keyword index is missing or incompatible; run indexing first")
                rows = connection.execute("SELECT chunk_id, text FROM chunk_fts").fetchall()
                if len(rows) != len(self.chunks) or dict(rows) != {
                    key: chunk["text"] for key, chunk in self.chunks.items()
                }:
                    raise ValueError("Keyword index differs from corpus; use a complete M3 index")
                self.fts_checked = True
            rows = connection.execute(
                """SELECT chunk_fts.chunk_id, bm25(chunk_fts) AS score FROM chunk_fts
                   JOIN chunk USING (chunk_id) WHERE chunk_fts MATCH ?
                   AND (chunk.quality_flag IS NULL OR chunk.quality_flag != 'low_quality')
                   ORDER BY score ASC, chunk_fts.chunk_id ASC LIMIT ?""",
                (expression, limit),
            ).fetchall()
        return [(identifier, float(score)) for identifier, score in rows]

    def open_vectors(self, identity: dict) -> None:
        if self.table is not None:
            if self.identity != identity:
                raise ValueError("Query model identity changed during retrieval")
            return
        import lancedb

        path = Path(self.config.paths.index_dir) / "vectors.lance"
        manifest = path / "manifest.json"
        if not manifest.is_file():
            raise ValueError("Vector manifest is missing; run indexing first")
        if json.loads(manifest.read_text(encoding="utf-8")) != identity:
            raise ValueError("Query embedding model differs from the M3 vector manifest")
        connection = lancedb.connect(str(path))
        if "chunks" not in connection.list_tables().tables:
            raise ValueError("Vector table is missing; run indexing first")
        table = connection.open_table("chunks")
        if table.schema.field("vector").type.list_size != identity["dimension"]:
            raise ValueError("Vector dimension differs from manifest")
        metadata = table.to_arrow().drop(["vector"]).to_pylist()
        if len(metadata) != len(self.chunks) or len({r["chunk_id"] for r in metadata}) != len(
            metadata
        ):
            raise ValueError("Vector index IDs differ from corpus; indexing may be incomplete")
        for row in metadata:
            chunk = self.chunks.get(row["chunk_id"])
            if chunk is None or any(
                value != (text_hash(chunk["text"]) if key == "text_sha256" else chunk[key])
                for key, value in row.items()
            ):
                raise ValueError("Vector metadata differs from corpus; use a complete M3 index")
        self.table = table
        self.identity = identity

    def dense(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        if self.table is None or self.identity is None:
            raise ValueError("Vector index has not been opened")
        validate_vector(vector, self.identity["dimension"])
        rows = (
            self.table.search(vector)
            .distance_type("cosine")
            .bypass_vector_index()
            .where("quality_flag IS NULL OR quality_flag != 'low_quality'", prefilter=True)
            .select(["chunk_id", "_distance"])
            # Scan all distances so ties at the top-k boundary are deterministic too.
            .limit(len(self.chunks))
            .to_list()
        )
        if any(not math.isfinite(row["_distance"]) for row in rows):
            raise ValueError("Vector index returned a non-finite distance")
        ordered = sorted(rows, key=lambda row: (row["_distance"], row["chunk_id"]))
        return [(row["chunk_id"], 1.0 - float(row["_distance"])) for row in ordered[:limit]]
