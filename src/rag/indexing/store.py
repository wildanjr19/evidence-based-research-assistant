import json
import sqlite3
from pathlib import Path

from rag.files import atomic_write
from rag.indexing.embedding import text_hash, validate_vector

FTS_TOKENIZER = "unicode61 remove_diacritics 2"
FTS_SCHEMA = f"""CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts
    USING fts5(chunk_id UNINDEXED, text, tokenize='{FTS_TOKENIZER}')"""


def index_keywords(connection: sqlite3.Connection, chunks: list[dict]) -> int:
    with connection:
        connection.execute(FTS_SCHEMA)
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'chunk_fts'"
        ).fetchone()[0]
        if "USING fts5" not in definition or f"tokenize='{FTS_TOKENIZER}'" not in definition:
            raise ValueError("Existing keyword index has a different definition; use a separate DB")
        rows = connection.execute("SELECT chunk_id, text FROM chunk_fts").fetchall()
        existing = dict(rows)
        expected = {chunk["chunk_id"]: chunk["text"] for chunk in chunks}
        if len(existing) != len(rows) or any(
            identifier not in expected or text != expected[identifier]
            for identifier, text in existing.items()
        ):
            raise ValueError("Existing keyword index differs from chunks; refusing to replace it")
        connection.executemany(
            "INSERT INTO chunk_fts (chunk_id, text) VALUES (?, ?)",
            [(key, text) for key, text in expected.items() if key not in existing],
        )
        return connection.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0]


class VectorStore:
    def __init__(self, path: Path, identity: dict) -> None:
        import lancedb

        self.path = path
        self.identity = identity
        manifest = path / "manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8")) != identity:
                raise ValueError("Vector model manifest differs; use a separate index_dir")
        else:
            if path.exists() and any(path.iterdir()):
                raise ValueError("Vector store has no model manifest; refusing to reuse it")
            atomic_write(manifest, json.dumps(identity, sort_keys=True).encode("utf-8"))
        self.connection = lancedb.connect(str(path))

    def records(self) -> list[dict]:
        if "chunks" not in self.connection.list_tables().tables:
            return []
        return self.connection.open_table("chunks").to_arrow().to_pylist()

    def append(self, chunks: list[dict], vectors: list[list[float]]) -> int:
        records = [
            {
                "chunk_id": chunk["chunk_id"],
                "paper_id": chunk["paper_id"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "section": chunk["section"],
                "quality_flag": chunk["quality_flag"],
                "text_sha256": text_hash(chunk["text"]),
                "vector": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        existing = self.records()
        by_id = {row["chunk_id"]: row for row in existing}
        expected = {row["chunk_id"]: row for row in records}
        if len(by_id) != len(existing):
            raise ValueError("Duplicate vector IDs; refusing to replace existing vectors")
        for identifier, row in by_id.items():
            validate_vector(row["vector"], self.identity["dimension"])
            if identifier not in expected or any(
                value != expected[identifier][key] for key, value in row.items() if key != "vector"
            ):
                raise ValueError(
                    "Existing vector metadata differs from chunks; use a separate index"
                )
        pending = [row for row in records if row["chunk_id"] not in by_id]
        if pending:
            import pyarrow as pa

            schema = pa.schema(
                [
                    pa.field("chunk_id", pa.string(), nullable=False),
                    pa.field("paper_id", pa.string(), nullable=False),
                    pa.field("page_start", pa.int64(), nullable=False),
                    pa.field("page_end", pa.int64(), nullable=False),
                    pa.field("section", pa.string()),
                    pa.field("quality_flag", pa.string()),
                    pa.field("text_sha256", pa.string(), nullable=False),
                    pa.field("vector", pa.list_(pa.float32(), self.identity["dimension"])),
                ]
            )
            data = pa.Table.from_pylist(pending, schema=schema)
            if "chunks" in self.connection.list_tables().tables:
                self.connection.open_table("chunks").add(data)
            else:
                self.connection.create_table("chunks", data=data)
        count = self.connection.open_table("chunks").count_rows() if records else 0
        if count != len(chunks):
            raise ValueError("Vector row count does not match the corpus chunk count")
        return count
