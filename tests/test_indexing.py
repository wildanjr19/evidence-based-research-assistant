import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.chunking.core import Chunk
from rag.chunking.pipeline import CHUNK_SCHEMA, save_chunks
from rag.config import Config, load_config
from rag.ids import make_chunk_id
from rag.indexing.__main__ import main
from rag.indexing.embedding import SentenceEmbedder, embed_chunks, embedding_identity
from rag.indexing.pipeline import index_corpus
from rag.indexing.store import VectorStore, index_keywords
from rag.ingestion.arxiv import Paper
from rag.ingestion.store import PAPER_SCHEMA, save_paper

PAPER_ID = "arxiv:2401.12345v1"


class FakeEmbedder:
    dimension = 3
    max_tokens = 512

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def token_counts(self, texts: list[str]) -> list[int]:
        return [len(text.split()) + 2 for text in texts]

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0, 0.0, 0.0] for text in texts]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    base = load_config()
    return replace(
        base,
        embedding=replace(base.embedding, batch_size=2),
        paths=replace(
            base.paths,
            db_path=str(tmp_path / "corpus.db"),
            cache_dir=str(tmp_path / "cache"),
            index_dir=str(tmp_path / "index"),
        ),
    )


def add_chunks(config: Config, texts: list[str] | None = None) -> list[dict]:
    paper = Paper(
        "2401.12345v1",
        "Synthetic",
        ["Fixture"],
        2024,
        None,
        None,
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    )
    texts = (
        texts
        if texts is not None
        else ["Caf\u00e9 alpha evidence", "Beta evidence", "Beta evidence"]
    )
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.executescript(PAPER_SCHEMA + CHUNK_SCHEMA)
        save_paper(connection, paper, "a" * 64, "2026-11-18T04:00:00Z")
        connection.execute("UPDATE paper SET parse_status = 'ok'")
        connection.commit()
        chunks = [
            Chunk(
                make_chunk_id(PAPER_ID, 1, number),
                PAPER_ID,
                1,
                1,
                None,
                None,
                number,
                text,
                len(text.split()),
                "low_quality" if number == 2 else "ok",
            )
            for number, text in enumerate(texts, 1)
        ]
        save_chunks(connection, PAPER_ID, chunks)
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("SELECT * FROM chunk ORDER BY chunk_order")]


def test_real_lancedb_and_fts_indexing_repeats_without_embedding_or_duplicate_rows(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests must not access network")

    monkeypatch.setattr(httpx.Client, "send", network_forbidden)
    chunks = add_chunks(config)
    encoder = FakeEmbedder()
    first = index_corpus(config, encoder)
    assert first["chunks"] == first["vector_count"] == first["fts_count"] == 3
    assert first["computed_embeddings"] == 2
    assert first["cache_hits"] == 0
    assert first["model_tokens"] == 13
    assert first["computed_tokens"] == 9
    assert len(encoder.calls) == 1
    store = VectorStore(Path(config.paths.index_dir) / "vectors.lance", first["embedding"])
    rows = store.records()
    assert {row["chunk_id"] for row in rows} == {chunk["chunk_id"] for chunk in chunks}
    assert rows[1]["quality_flag"] == "low_quality"
    assert store.connection.open_table("chunks").schema.field("vector").type.list_size == 3
    hits = store.connection.open_table("chunks").search([1.0, 0.0, 0.0]).limit(3).to_list()
    assert len(hits) == 3
    with sqlite3.connect(config.paths.db_path) as connection:
        matched = connection.execute(
            "SELECT chunk_id, bm25(chunk_fts) FROM chunk_fts WHERE chunk_fts MATCH 'cafe'"
        ).fetchall()
        assert matched[0][0] == chunks[0]["chunk_id"]
        assert matched[0][1] < 0
        original = connection.execute("SELECT * FROM chunk").fetchall()
    second = index_corpus(config, encoder)
    assert second["computed_embeddings"] == second["computed_tokens"] == 0
    assert second["cache_hits"] == 2
    assert second["vector_count"] == second["fts_count"] == 3
    assert len(encoder.calls) == 1
    assert store.records() == rows
    assert second["run_id"] != first["run_id"]
    reports = list((Path(config.paths.index_dir) / "reports").glob("*.json"))
    assert len(reports) == 2
    assert {json.loads(path.read_text())["status"] for path in reports} == {"ok"}
    assert first["elapsed_seconds"] > 0
    assert first["config"]["embedding"]["revision"] == config.embedding.revision
    assert len(first["config_hash"]) == 64
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT * FROM chunk").fetchall() == original


def test_embedding_cache_batches_deduplicates_and_separates_model_revisions(config: Config) -> None:
    chunks = [{"chunk_id": str(n), "text": str(n)} for n in range(5)]
    encoder = FakeEmbedder()
    vectors, stats = embed_chunks(chunks + chunks[:1], config, encoder)
    assert len(vectors) == 6
    assert stats["unique_texts"] == 5
    assert list(map(len, encoder.calls)) == [2, 2, 1]
    changed = replace(config, embedding=replace(config.embedding, revision="b" * 40))
    _, stats = embed_chunks(chunks, changed, encoder)
    assert stats["computed_embeddings"] == 5
    assert len(list((Path(config.paths.cache_dir) / "embeddings").glob("*.json"))) == 10


def test_oversized_chunks_fail_before_encoding_or_creating_indexes(config: Config) -> None:
    chunks = add_chunks(config, ["word " * 511])
    encoder = FakeEmbedder()
    with pytest.raises(ValueError, match="exceed model limit 512"):
        index_corpus(config, encoder)
    assert encoder.calls == []
    assert not (Path(config.paths.cache_dir) / "embeddings").exists()
    assert not (Path(config.paths.index_dir) / "vectors.lance").exists()
    report = json.loads(next((Path(config.paths.index_dir) / "reports").glob("*.json")).read_text())
    assert report["status"] == "failed"
    assert chunks[0]["chunk_id"] in report["error"]
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT text FROM chunk").fetchone()[0] == chunks[0]["text"]


def test_corrupt_embedding_cache_is_preserved_and_rejected(config: Config) -> None:
    chunks = add_chunks(config)
    encoder = FakeEmbedder()
    embed_chunks(chunks, config, encoder)
    path = next((Path(config.paths.cache_dir) / "embeddings").glob("*.json"))
    path.write_text('{"vector": [0]}', encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid embedding cache"):
        embed_chunks(chunks, config, encoder)
    assert path.read_bytes() == original
    assert len(encoder.calls) == 1


@pytest.mark.parametrize("bad", [[[float("nan"), 0, 0]], [[0, 0, 0]], [[1, 0]], []])
def test_bad_vectors_are_not_cached(
    config: Config, bad: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoder = FakeEmbedder()
    monkeypatch.setattr(encoder, "encode", lambda texts: bad)
    with pytest.raises(ValueError, match="embedding|number of vectors"):
        embed_chunks([{"chunk_id": "fixture", "text": "evidence"}], config, encoder)
    assert not (Path(config.paths.cache_dir) / "embeddings").exists()


def test_partial_vector_and_fts_indexes_accept_missing_chunks_only(config: Config) -> None:
    chunks = add_chunks(config)
    encoder = FakeEmbedder()
    identity = embedding_identity(config, encoder)
    store = VectorStore(Path(config.paths.index_dir) / "vectors.lance", identity)
    store.append(chunks[:1], encoder.encode([chunks[0]["text"]]))
    with sqlite3.connect(config.paths.db_path) as connection:
        index_keywords(connection, chunks[:1])
    report = index_corpus(config, encoder)
    assert report["fts_count"] == report["vector_count"] == 3
    assert len(store.records()) == 3


def test_changed_chunks_or_model_cannot_replace_existing_indexes(config: Config) -> None:
    add_chunks(config)
    encoder = FakeEmbedder()
    first = index_corpus(config, encoder)
    path = Path(config.paths.index_dir) / "vectors.lance"
    store = VectorStore(path, first["embedding"])
    original = store.records()
    changed_identity = {**first["embedding"], "revision": "b" * 40}
    with pytest.raises(ValueError, match="manifest differs"):
        VectorStore(path, changed_identity)
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("UPDATE chunk SET text = 'Changed evidence' WHERE chunk_order = 1")
    with pytest.raises(ValueError, match="metadata differs"):
        index_corpus(config, encoder)
    assert store.records() == original
    with sqlite3.connect(config.paths.db_path) as connection:
        assert (
            connection.execute("SELECT text FROM chunk_fts LIMIT 1").fetchone()[0]
            != "Changed evidence"
        )


def test_duplicate_or_changed_keyword_rows_are_rejected(config: Config) -> None:
    chunks = add_chunks(config)
    with sqlite3.connect(config.paths.db_path) as connection:
        index_keywords(connection, chunks)
        connection.execute("INSERT INTO chunk_fts SELECT * FROM chunk_fts LIMIT 1")
        connection.commit()
        with pytest.raises(ValueError, match="keyword index differs"):
            index_keywords(connection, chunks)
        assert connection.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0] == 4


def test_missing_database_and_unparsed_chunks_fail_clearly(config: Config) -> None:
    with pytest.raises(ValueError, match="database is missing"):
        index_corpus(config, FakeEmbedder())
    assert not Path(config.paths.db_path).exists()
    add_chunks(config)
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("UPDATE paper SET parse_status = 'failed'")
    with pytest.raises(ValueError, match="unparsed corpus chunk"):
        index_corpus(config, FakeEmbedder())


def test_report_collision_is_detected_before_any_index_change(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_chunks(config)
    monkeypatch.setattr("rag.indexing.pipeline.make_run_id", lambda: "2026-11-18T04:00:00Z_123456")
    index_corpus(config, FakeEmbedder())
    report = next((Path(config.paths.index_dir) / "reports").glob("*.json"))
    original = report.read_bytes()
    encoder = FakeEmbedder()
    with pytest.raises(FileExistsError):
        index_corpus(config, encoder)
    assert report.read_bytes() == original
    assert encoder.calls == []


def test_cli_injects_model_and_reports_failure(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_chunks(config)
    monkeypatch.setattr("rag.indexing.__main__.load_config", lambda path: config)
    monkeypatch.setattr("rag.indexing.pipeline.SentenceEmbedder", lambda config: FakeEmbedder())
    monkeypatch.setattr(sys, "argv", ["rag.indexing", "--config", "fixture.yaml"])
    assert main() == 0
    missing = replace(config, paths=replace(config.paths, db_path="missing-corpus.db"))
    monkeypatch.setattr("rag.indexing.__main__.load_config", lambda path: missing)
    assert main() == 1


def test_sentence_adapter_pins_model_counts_special_tokens_and_disables_truncation(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {}

    class Model:
        max_seq_length = 512

        def __init__(self, name: str, **kwargs: object) -> None:
            calls["load"] = (name, kwargs)

        def get_embedding_dimension(self) -> int:
            return 3

        def tokenizer(self, texts: list[str], **kwargs: object) -> dict:
            calls["tokenize"] = kwargs
            return {"input_ids": [[101, 17, 102] for text in texts]}

        def encode(self, texts: list[str], **kwargs: object) -> object:
            calls["encode"] = kwargs
            return SimpleNamespace(tolist=lambda: [[1.0, 0.0, 0.0]])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    encoder = SentenceEmbedder(config)
    assert encoder.token_counts(["evidence"]) == [3]
    assert encoder.encode(["evidence"]) == [[1.0, 0.0, 0.0]]
    assert calls["load"][1]["revision"] == config.embedding.revision
    assert calls["load"][1]["trust_remote_code"] is False
    assert calls["tokenize"] == {"add_special_tokens": True, "truncation": False, "padding": False}
    assert calls["encode"]["normalize_embeddings"] is True
    assert calls["encode"]["prompt"] == ""
    assert calls["encode"]["precision"] == "float32"


def test_requested_cuda_is_not_silently_replaced_by_cpu(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    )
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=object)
    )
    config = replace(config, embedding=replace(config.embedding, device="cuda"))
    with pytest.raises(ValueError, match="CUDA is unavailable"):
        SentenceEmbedder(config)


@pytest.mark.gpu
def test_cuda_tensor_round_trip() -> None:
    import torch

    if not torch.cuda.is_available():
        pytest.skip("CUDA build/device is unavailable")
    values = torch.tensor([1.0, 2.0, 3.0], device="cuda")
    assert values.square().sum().cpu().item() == 14.0
