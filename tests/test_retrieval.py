import hashlib
import json
import math
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.chunking.core import Chunk
from rag.chunking.pipeline import CHUNK_SCHEMA, save_chunks
from rag.config import Config, load_config
from rag.evaluation.__main__ import main as evaluation_main
from rag.evaluation.metrics import retrieval_metrics
from rag.evaluation.retrieval import evaluate_retrieval, load_questions
from rag.ids import make_chunk_id
from rag.indexing.pipeline import index_corpus
from rag.ingestion.arxiv import Paper
from rag.ingestion.store import PAPER_SCHEMA, save_paper
from rag.retrieval.__main__ import main as retrieval_main
from rag.retrieval.fusion import reciprocal_rank_fusion
from rag.retrieval.pipeline import MODES, Retriever
from rag.retrieval.rerank import BGEReranker

PAPER_ID = "arxiv:2401.12345v1"
DATASET = Path(__file__).parent / "fixtures" / "retrieval_questions.jsonl"


class FakeEmbedder:
    dimension = 3
    max_tokens = 512

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def token_counts(self, texts: list[str]) -> list[int]:
        return [len(text.split()) + 2 for text in texts]

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        vectors = []
        for text in texts:
            text = text.lower()
            if "alpha" in text and "beta" in text:
                vectors.append([math.sqrt(0.5), math.sqrt(0.5), 0.0])
            elif "alpha" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "beta" in text:
                vectors.append([0.0, 1.0, 0.0])
            elif "gamma" in text:
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([-1.0, 0.0, 0.0])
        return vectors


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, str]]] = []

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(pairs)
        return [float(len(set(q.lower().split()) & set(text.lower().split()))) for q, text in pairs]


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import requests

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Retrieval tests must not use the network or download models")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "send", forbidden)
    monkeypatch.setattr("rag.retrieval.pipeline.SentenceEmbedder", forbidden)
    monkeypatch.setattr("rag.retrieval.rerank.BGEReranker", forbidden)


@pytest.fixture
def indexed(tmp_path: Path) -> tuple[Config, FakeEmbedder, FakeReranker]:
    base = load_config()
    config = replace(
        base,
        paths=replace(
            base.paths,
            db_path=str(tmp_path / "corpus.db"),
            index_dir=str(tmp_path / "index"),
            cache_dir=str(tmp_path / "cache"),
        ),
        evaluation=replace(base.evaluation, output_dir=str(tmp_path / "results")),
    )
    paper = Paper(
        "2401.12345v1",
        "Synthetic retrieval fixture",
        ["Fixture"],
        2024,
        None,
        None,
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    )
    texts = [
        "Cafe alpha evidence",
        "Caf\u00e9 alpha evidence",
        "Beta evidence experiment",
        "Gamma retrieval fusion",
        "Alpha beta comparison",
        "Caf\u00e9 alpha evidence",
    ]
    texts += [f"Control filler study {i}" for i in range(24)]
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.executescript(PAPER_SCHEMA + CHUNK_SCHEMA)
        save_paper(connection, paper, "a" * 64, "2026-11-18T04:00:00Z")
        connection.execute("UPDATE paper SET parse_status = 'ok'")
        connection.commit()
        chunks = [
            Chunk(
                make_chunk_id(PAPER_ID, 1, n),
                PAPER_ID,
                1,
                1,
                None,
                None,
                n,
                text,
                len(text.split()),
                "low_quality" if n == 1 else "ok",
            )
            for n, text in enumerate(texts, 1)
        ]
        save_chunks(connection, PAPER_ID, chunks)
    embedder = FakeEmbedder()
    index_corpus(config, embedder)
    embedder.calls.clear()
    return config, embedder, FakeReranker()


def test_rrf_matches_manual_fractions_and_deduplicates() -> None:
    hits = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "a"]], 60)
    assert [key for key, _ in hits] == ["b", "a", "c"]
    assert dict(hits) == pytest.approx(
        {"a": 1 / 61 + 1 / 63, "b": 1 / 62 + 1 / 61, "c": 1 / 63 + 1 / 62}
    )
    assert reciprocal_rank_fusion([["a", "a", "b"], ["b"]], 0) == [("b", 1.5), ("a", 1.0)]
    assert reciprocal_rank_fusion([["z"], ["a"]], 60)[0][0] == "a"
    assert reciprocal_rank_fusion([[], []], 60) == []
    with pytest.raises(ValueError, match="non-negative"):
        reciprocal_rank_fusion([], -1)


def test_metrics_match_hand_calculation_and_keep_unanswerable_undefined() -> None:
    metrics = retrieval_metrics(["x", "a", "y", "b"], ["a", "b", "c"], [1, 3, 5])
    assert metrics == {"recall@1": 0.0, "recall@3": 1 / 3, "recall@5": 2 / 3, "mrr": 0.5}
    assert retrieval_metrics([], ["a"], [5]) == {"recall@5": 0.0, "mrr": 0.0}
    assert retrieval_metrics(["a"], [], [5]) == {"recall@5": None, "mrr": None}
    with pytest.raises(ValueError, match="unique"):
        retrieval_metrics(["a", "a"], ["a"], [5])


@pytest.mark.parametrize("mode", MODES)
def test_four_modes_filter_quality_before_cutoff_and_return_canonical_chunks(
    indexed: tuple, mode: str
) -> None:
    config, embedder, reranker = indexed
    config = replace(config, retrieval=replace(config.retrieval, dense_top_k=1, bm25_top_k=1))
    retriever = Retriever(config, embedder, reranker)
    before = Path(config.paths.db_path).read_bytes()
    hits = retriever.retrieve("Cafe alpha evidence", mode)
    assert hits[0]["chunk_id"] == make_chunk_id(PAPER_ID, 1, 2)
    assert all(hit["quality_flag"] != "low_quality" for hit in hits)
    for hit in hits:
        canonical = retriever.store.chunks[hit["chunk_id"]]
        assert hit["text"] == canonical["text"]
        assert hit["paper_id"] == canonical["paper_id"]
    assert before == Path(config.paths.db_path).read_bytes()
    if mode != "bm25":
        assert embedder.calls == [[config.retrieval.query_prefix + "Cafe alpha evidence"]]
    else:
        assert not embedder.calls
    assert bool(reranker.calls) == (mode == "hybrid+rerank")


def test_bm25_is_lazy_and_treats_fts_syntax_as_text(indexed: tuple) -> None:
    config, _, _ = indexed
    retriever = Retriever(config)
    hits = retriever.retrieve('cafe" OR chunk_id:* - (:)', "bm25")
    assert hits and hits[0]["chunk_id"] == make_chunk_id(PAPER_ID, 1, 2)
    assert retriever.retrieve("!?* :", "bm25") == []
    assert retriever.embedder is None and retriever.reranker is None


def test_query_and_pair_caches_prevent_recomputation(indexed: tuple) -> None:
    config, embedder, reranker = indexed
    retriever = Retriever(config, embedder, reranker)
    first = retriever.retrieve("alpha evidence", "hybrid+rerank")
    calls = len(reranker.calls)
    second = retriever.retrieve("alpha evidence", "hybrid+rerank")
    assert first == second
    assert len(embedder.calls) == 1 and len(reranker.calls) == calls
    assert retriever.statistics["computed_embeddings"] == 0
    assert retriever.statistics["computed_pairs"] == 0
    assert retriever.statistics["reranker_cache_hits"] > 0
    retriever.reranker = None
    assert retriever.retrieve("alpha evidence", "hybrid+rerank") == first


def test_reranking_reorders_only_the_fused_candidate_pool_and_default_honors_config(
    indexed: tuple,
) -> None:
    config, embedder, _ = indexed
    config = replace(
        config,
        retrieval=replace(config.retrieval, rerank_candidates=3, final_top_k=2, use_reranker=False),
    )
    model = SimpleNamespace(
        score=lambda pairs: [100.0 if "beta" in text.lower() else 0.0 for _, text in pairs]
    )
    retriever = Retriever(config, embedder, model)
    fused = retriever.retrieve("alpha", "hybrid", top_k=3)
    assert retriever.retrieve("alpha") == fused[:2]
    hits = retriever.retrieve("alpha", "hybrid+rerank", top_k=3)
    assert hits[0]["chunk_id"] == make_chunk_id(PAPER_ID, 1, 5) != fused[0]["chunk_id"]
    assert {h["chunk_id"] for h in hits} == {h["chunk_id"] for h in fused}
    assert [h["score"] for h in hits] == [100.0, 0.0, 0.0]


def test_changed_prefix_and_reranker_revision_use_new_cache_entries(indexed: tuple) -> None:
    config, embedder, reranker = indexed
    Retriever(config, embedder, reranker).retrieve("alpha", "hybrid+rerank")
    first_calls = len(reranker.calls)
    config = replace(
        config, retrieval=replace(config.retrieval, query_prefix="", reranker_revision="c" * 40)
    )
    retriever = Retriever(config, embedder, reranker)
    retriever.retrieve("alpha", "hybrid+rerank")
    assert embedder.calls[-1] == ["alpha"]
    assert len(reranker.calls) > first_calls
    assert retriever.statistics["computed_embeddings"] == 1
    assert retriever.statistics["computed_pairs"] > 0


def test_query_limit_includes_prefix_without_truncation(indexed: tuple) -> None:
    config, embedder, reranker = indexed
    with pytest.raises(ValueError, match="exceed model limit"):
        Retriever(config, embedder, reranker).retrieve("alpha " * 512, "dense")
    assert not embedder.calls


def test_empty_and_invalid_requests_and_all_low_quality(indexed: tuple) -> None:
    config, embedder, reranker = indexed
    retriever = Retriever(config, embedder, reranker)
    for question, mode, limit in [(" ", "dense", 8), ("alpha", "wrong", 8), ("alpha", "dense", 0)]:
        with pytest.raises(ValueError):
            retriever.retrieve(question, mode, limit)
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("UPDATE chunk SET quality_flag = 'low_quality'")
    retriever = Retriever(config)
    assert retriever.retrieve("alpha", "hybrid+rerank") == []
    assert retriever.embedder is None


def test_missing_database_does_not_create_one(tmp_path: Path) -> None:
    base = load_config()
    config = replace(base, paths=replace(base.paths, db_path=str(tmp_path / "absent.db")))
    with pytest.raises(ValueError, match="missing"):
        Retriever(config)
    assert not (tmp_path / "absent.db").exists()


@pytest.mark.parametrize("corruption", ["fts", "vector", "manifest"])
def test_stale_or_partial_indexes_are_rejected(indexed: tuple, corruption: str) -> None:
    config, embedder, reranker = indexed
    if corruption == "manifest":
        config = replace(config, embedding=replace(config.embedding, revision="b" * 40))
    elif corruption == "fts":
        with sqlite3.connect(config.paths.db_path) as connection:
            connection.execute(
                "DELETE FROM chunk_fts WHERE chunk_id = ?", (make_chunk_id(PAPER_ID, 1, 2),)
            )
    else:
        with sqlite3.connect(config.paths.db_path) as connection:
            connection.execute("UPDATE chunk SET text = 'changed' WHERE chunk_order = 2")
    with pytest.raises(ValueError, match="differs|manifest|incomplete"):
        Retriever(config, embedder, reranker).retrieve(
            "alpha", "bm25" if corruption == "fts" else "dense"
        )


def test_reranker_bad_scores_and_corrupt_cache_are_rejected(indexed: tuple) -> None:
    config, embedder, reranker = indexed
    bad = SimpleNamespace(score=lambda pairs: [float("nan")] * len(pairs))
    with pytest.raises(ValueError, match="invalid scores"):
        Retriever(config, embedder, bad).retrieve("alpha", "hybrid+rerank")
    retriever = Retriever(config, embedder, reranker)
    retriever.retrieve("alpha", "hybrid+rerank")
    cached = next((Path(config.paths.cache_dir) / "reranking").glob("*.json"))
    cached.write_text('{"score": 1, "provenance": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid reranker cache"):
        retriever.retrieve("alpha", "hybrid+rerank")


def test_evaluation_all_modes_persists_provenance_and_retrieves_beyond_prompt_top_k(
    indexed: tuple,
) -> None:
    config, embedder, reranker = indexed
    dataset_before = DATASET.read_bytes()
    db_before = Path(config.paths.db_path).read_bytes()
    reports = evaluate_retrieval(config, DATASET, embedder=embedder, reranker=reranker)
    assert [r["mode"] for r in reports] == list(MODES)
    assert len({r["run_id"] for r in reports}) == 4
    for report in reports:
        assert report["status"] == "ok" and report["ranking_depth"] == 20
        assert report["answerable_count"] == 4 and report["question_count"] == 5
        assert report["dataset_sha256"] == hashlib.sha256(dataset_before).hexdigest()
        assert report["config_hash"] and report["versions"] and report["corpus_sha256"]
        directory = Path(config.evaluation.output_dir) / report["run_id"].replace(":", "-")
        assert json.loads((directory / "metrics.json").read_text()) == report
        rows = [
            json.loads(line) for line in (directory / "per_question.jsonl").read_text().splitlines()
        ]
        assert all(value is None for value in rows[-1]["metrics"].values())
        assert "MRR depth: 20" in (directory / "report.md").read_text()
        if report["mode"] != "bm25":
            assert len(rows[0]["ranking"]) == 20 > config.retrieval.final_top_k
        assert report["metrics"]["recall@5"] == 1.0
    assert DATASET.read_bytes() == dataset_before
    assert Path(config.paths.db_path).read_bytes() == db_before


def test_evaluation_failures_and_run_collision_preserve_history(
    indexed: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, embedder, reranker = indexed
    reports = evaluate_retrieval(config, DATASET, ("bm25",), embedder, reranker)
    run_id = reports[0]["run_id"]
    path = Path(config.evaluation.output_dir) / run_id.replace(":", "-") / "metrics.json"
    original = path.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr("rag.evaluation.retrieval.make_run_id", lambda: run_id)
        with pytest.raises(FileExistsError):
            evaluate_retrieval(config, DATASET, ("bm25",), embedder, reranker)
    assert path.read_bytes() == original

    def fail(pairs: list) -> list:
        raise RuntimeError("fixture inference failure")

    with pytest.raises(RuntimeError, match="fixture inference failure"):
        evaluate_retrieval(
            config, DATASET, ("hybrid+rerank",), embedder, SimpleNamespace(score=fail)
        )
    persisted = [
        json.loads(p.read_text()) for p in Path(config.evaluation.output_dir).glob("*/metrics.json")
    ]
    assert any(
        r["status"] == "failed" and r["error"] == "fixture inference failure" for r in persisted
    )


@pytest.mark.parametrize("change", ["duplicate", "missing", "invalid", "wrong-paper", "empty"])
def test_dataset_validation_rejects_bad_gold_without_rewriting_it(
    indexed: tuple, tmp_path: Path, change: str
) -> None:
    config, _, _ = indexed
    questions = [json.loads(line) for line in DATASET.read_text().splitlines()]
    if change == "duplicate":
        questions.append(questions[0])
    elif change == "missing":
        questions[0]["gold_chunk_ids"] = [make_chunk_id(PAPER_ID, 1, 999)]
    elif change == "invalid":
        questions[0]["gold_chunk_ids"] = ["invented"]
    elif change == "wrong-paper":
        questions[0]["gold_paper_ids"] = []
    else:
        questions = []
    path = tmp_path / "questions.jsonl"
    path.write_text("\n".join(json.dumps(q) for q in questions), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid validation question|dataset is empty"):
        load_questions(path, Retriever(config).store.chunks)
    assert path.read_bytes() == before


def test_bge_reranker_pins_revision_batches_pairs_and_limits_document_only(
    indexed: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    config, _, _ = indexed
    calls = {}

    class Encoding(dict):
        def to(self, device: str) -> dict:
            calls["device"] = device
            return self

    class Tokenizer:
        model_max_length = 512

        def encode(self, text: str, **kwargs: object) -> list:
            return text.split()

        def num_special_tokens_to_add(self, pair: bool) -> int:
            return 4

        def __call__(self, questions: list, texts: list, **kwargs: object) -> Encoding:
            calls["tokenize"] = kwargs
            calls["pairs"] = list(zip(questions, texts, strict=True))
            return Encoding(input_ids=torch.tensor([[1], [2]]))

    class Model:
        def to(self, device: str) -> "Model":
            return self

        def eval(self) -> None:
            calls["eval"] = True

        def __call__(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(logits=torch.tensor([[2.0], [-3.0]]))

    def tokenizer_factory(name: str, **kwargs: object) -> Tokenizer:
        calls["model_name"] = name
        calls["options"] = kwargs
        return Tokenizer()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_factory),
            AutoModelForSequenceClassification=SimpleNamespace(
                from_pretrained=lambda *a, **k: Model()
            ),
        ),
    )
    model = BGEReranker(config)
    assert model.score([("question", "passage"), ("question", "another passage")]) == [2.0, -3.0]
    assert calls["tokenize"]["truncation"] == "only_second"
    assert calls["tokenize"]["max_length"] == 512
    assert calls["options"]["revision"] == config.retrieval.reranker_revision
    assert calls["options"]["trust_remote_code"] is False
    assert calls["eval"] and calls["device"] == "cpu"
    with pytest.raises(ValueError, match="Question exceeds"):
        model.score([("word " * 509, "passage")])


@pytest.mark.parametrize("fail", [False, True])
def test_retrieval_cli_dispatch_and_errors(monkeypatch: pytest.MonkeyPatch, fail: bool) -> None:
    calls = []

    def run(question: str, config: Config, mode: str) -> list:
        calls.append((question, mode))
        if fail:
            raise ValueError("fixture retrieval error")
        return []

    monkeypatch.setattr(sys, "argv", ["rag.retrieval", "--question", "alpha", "--mode", "bm25"])
    monkeypatch.setattr("rag.retrieval.__main__.retrieve", run)
    assert retrieval_main() == (1 if fail else 0)
    assert calls == [("alpha", "bm25")]


@pytest.mark.parametrize("fail", [False, True])
def test_evaluation_cli_dispatch_and_errors(monkeypatch: pytest.MonkeyPatch, fail: bool) -> None:
    calls = []

    def run(config: Config, dataset: str | None, modes: tuple) -> list:
        calls.append((dataset, modes))
        if fail:
            raise ValueError("fixture evaluation error")
        return []

    monkeypatch.setattr(sys, "argv", ["rag.evaluation", "--dataset", str(DATASET)])
    monkeypatch.setattr("rag.evaluation.__main__.evaluate_retrieval", run)
    assert evaluation_main() == (1 if fail else 0)
    assert calls == [(str(DATASET), MODES)]
