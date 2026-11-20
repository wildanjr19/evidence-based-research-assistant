import json
from dataclasses import replace
from pathlib import Path

import pytest

from rag.evaluation.ragas import _validate_answer, prepare_ragas, score_ragas
from rag.indexing.embedding import text_hash
from test_generation import FIRST, FakeLLM, completion
from test_generation import corpus as corpus


@pytest.fixture
def prepared(corpus: tuple, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    config, rows = corpus
    monkeypatch.chdir(tmp_path)
    config = replace(
        config,
        evaluation=replace(config.evaluation, output_dir=str(tmp_path / "data" / "results")),
    )
    dataset = tmp_path / "questions.jsonl"
    questions = [
        dict(
            qid="one",
            question="What does Alpha support?",
            qtype="lookup",
            gold_chunk_ids=[FIRST],
            gold_paper_ids=[rows[0]["paper_id"]],
            reference="Alpha evidence supports the first result.",
            reference_status="ai_draft_unreviewed",
            reference_text_sha256={FIRST: text_hash(rows[0]["text"])},
        ),
        dict(
            qid="outside",
            question="What is tomorrow's weather?",
            qtype="unanswerable",
            gold_chunk_ids=[],
            gold_paper_ids=[],
            reference="No evidence.",
            reference_status="ai_draft_unreviewed",
            reference_text_sha256={},
        ),
    ]
    dataset.write_text("\n".join(json.dumps(q) for q in questions), encoding="utf-8")

    class FixedRetriever:
        def retrieve(self, question: str, mode: str) -> list:
            return rows[:1]

    backend = FakeLLM([completion([dict(text=rows[0]["text"], citations=[FIRST])]), completion([])])
    before = Path(config.paths.db_path).read_bytes()
    output = prepare_ragas(
        config, dataset, mode="bm25", max_calls=2, backend=backend, retriever=FixedRetriever()
    )
    assert Path(config.paths.db_path).read_bytes() == before
    return config, dataset, output, FixedRetriever(), before


def test_prepare_separates_snapshot_audit_and_unreviewed_references(prepared: tuple) -> None:
    config, _, directory, _, _ = prepared
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["generation_calls"] == 2
    assert manifest["human_accuracy"] is None
    assert manifest["reference_status"] == "ai_draft_unreviewed"
    samples = json.loads((directory / "samples.json").read_text())
    assert [r["generation"]["status"] for r in samples] == ["ok", "no_evidence"]
    assert (directory / "corpus.db").resolve() != Path(config.paths.db_path).resolve()
    audit = [
        json.loads(line) for line in (directory / "reference-audit.jsonl").read_text().splitlines()
    ]
    assert len(audit) == 2
    assert all(r["reference_correct"] is None and r["reviewer"] is None for r in audit)
    assert all("generation" not in r and "scores" not in r for r in audit)


def test_prepare_cache_miss_never_calls_provider(
    prepared: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, dataset, _, retriever, _ = prepared

    def forbidden(*args: object) -> None:
        raise AssertionError("No paid requests")

    monkeypatch.setattr("rag.generation.client.OpenAIBackend.complete", forbidden)
    directory = prepare_ragas(config, dataset, mode="bm25", retriever=retriever)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["generation_calls"] == 0
    assert all(
        r["generation"]["status"] == "failed"
        for r in json.loads((directory / "samples.json").read_text())
    )


def test_prepare_refuses_stale_ai_references(prepared: tuple) -> None:
    config, dataset, _, retriever, _ = prepared
    records = [json.loads(line) for line in dataset.read_text().splitlines()]
    records[0]["reference_text_sha256"][FIRST] = "wrong"
    dataset.write_text("\n".join(json.dumps(r) for r in records))
    with pytest.raises(ValueError, match="stale chunks"):
        prepare_ragas(config, dataset, retriever=retriever)


def test_prepare_offset_skips_pilot_without_changing_dataset(prepared: tuple) -> None:
    config, dataset, _, retriever, _ = prepared
    original = dataset.read_bytes()
    backend = FakeLLM([completion([])])
    directory = prepare_ragas(
        config, dataset, offset=1, limit=1, mode="bm25", backend=backend, retriever=retriever
    )
    manifest = json.loads((directory / "manifest.json").read_text())
    samples = json.loads((directory / "samples.json").read_text())
    assert manifest["offset"] == 1
    assert manifest["selected_qids"] == ["outside"]
    assert manifest["generation_calls"] == 0
    assert backend.calls == []
    assert [record["question"]["qid"] for record in samples] == ["outside"]
    assert dataset.read_bytes() == original


@pytest.mark.parametrize("offset", [-1, True, 1.5, 2])
def test_prepare_rejects_invalid_offset_before_creating_run(prepared: tuple, offset: int) -> None:
    config, dataset, _, retriever, _ = prepared
    before = set(Path(config.evaluation.output_dir).iterdir())
    with pytest.raises(ValueError, match="offset|Offset"):
        prepare_ragas(config, dataset, offset=offset, retriever=retriever)
    assert set(Path(config.evaluation.output_dir).iterdir()) == before


@pytest.mark.parametrize("name", ["samples.json", "config.yaml"])
def test_score_rejects_modified_prepared_inputs_before_models(prepared: tuple, name: str) -> None:
    path = prepared[2] / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="inputs differ"):
        score_ragas(prepared[2])


def test_score_rejects_changed_dataset(prepared: tuple) -> None:
    prepared[1].write_bytes(prepared[1].read_bytes() + b" ")
    with pytest.raises(ValueError, match="dataset differs"):
        score_ragas(prepared[2])


def test_generation_binding_rejects_claim_tampering(prepared: tuple) -> None:
    from rag.config import load_config

    config = load_config(prepared[2] / "config.yaml")
    sample = json.loads((prepared[2] / "samples.json").read_text())[0]
    _validate_answer(config, sample["generation"], sample["question"]["question"])
    sample["generation"]["claims"][0]["text"] = "Invented output"
    with pytest.raises(ValueError, match="persisted generation"):
        _validate_answer(config, sample["generation"], sample["question"]["question"])
