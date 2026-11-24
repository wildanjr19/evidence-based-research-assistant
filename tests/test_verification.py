import json
import sqlite3
import sys
from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.config import load_config
from rag.evaluation.annotations import export_annotations, load_manual_labels
from rag.evaluation.citations import evaluate_citations
from rag.evaluation.metrics import citation_metrics, cohens_kappa
from rag.generation.client import Completion
from rag.generation.pipeline import generate_answer
from rag.indexing.embedding import text_hash
from rag.verification.judge import Judge, sample_claim_ids
from rag.verification.minicheck import CachedVerifier, MiniCheck
from rag.verification.pipeline import verify_answer
from test_generation import FIRST, SECOND, FakeLLM, completion
from test_generation import corpus as corpus


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import httpx2

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Verification tests cannot download models or call paid APIs")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)
    if find_spec("requests") is not None:
        monkeypatch.setattr("requests.sessions.Session.send", forbidden)


class FakeSupport:
    def __init__(self, values: list[float] | None = None) -> None:
        self.values = values if values is not None else [0.9]
        self.calls = 0

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls += 1
        return self.values


def test_verifier_cache_revision_threshold_and_namespace(corpus: tuple) -> None:
    config, _ = corpus
    backend = FakeSupport()
    first = CachedVerifier(config, backend)
    assert first.verify("A claim", "Evidence")["label"] == "supported"
    assert first.verify("A claim", "Evidence")["score"] == 0.9
    assert backend.calls == 1
    assert first.cache_hits == 1
    second = CachedVerifier(config, backend)
    assert second.verify("A claim", "Evidence")["label"] == "supported"
    assert second.cache_hits == 1
    changed = replace(config, verification=replace(config.verification, support_threshold=0.95))
    assert (
        CachedVerifier(changed, backend).verify("A claim", "Evidence")["label"] == "not_supported"
    )
    changed = replace(
        config, verification=replace(config.verification, minicheck_revision="a" * 40)
    )
    CachedVerifier(changed, backend).verify("A claim", "Evidence")
    assert backend.calls == 3


@pytest.mark.parametrize("values", [[float("nan")], [1.1], [-0.1], [True], [], [0.1, 0.2]])
def test_verifier_rejects_invalid_probabilities(corpus: tuple, values: list) -> None:
    config, _ = corpus
    with pytest.raises(ValueError):
        CachedVerifier(config, FakeSupport(values)).verify("Claim", "Evidence")


def test_corrupt_cache_never_recomputes(corpus: tuple) -> None:
    config, _ = corpus
    backend = FakeSupport()
    verifier = CachedVerifier(config, backend)
    verifier.verify("Claim", "Evidence")
    path = next((Path(config.paths.cache_dir) / "verification").glob("*.json"))
    cached = json.loads(path.read_text())
    cached["score"] = 0.1
    path.write_text(json.dumps(cached))
    with pytest.raises(ValueError, match="Invalid verifier cache"):
        verifier.verify("Claim", "Evidence")
    assert backend.calls == 1


def test_minicheck_adapter_uses_upstream_tokens_and_rejects_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import torch
    import transformers

    calls = []

    class Batch(dict):
        def to(self, device: str) -> "Batch":
            return self

    class Tokenizer:
        eos_token = "</s>"

        def __call__(self, texts: list[str], **kwargs: object) -> dict:
            calls.append((texts, kwargs))
            assert kwargs["truncation"] is False
            if kwargs.get("return_tensors"):
                return Batch(input_ids=torch.ones((len(texts), 10), dtype=torch.long))
            return {"input_ids": [[1] * (600 if "TOO_LONG" in text else 10) for text in texts]}

    class Model:
        config = SimpleNamespace(n_positions=512, decoder_start_token_id=0)

        def to(self, device: str) -> "Model":
            assert device == "cpu"
            return self

        def eval(self) -> None:
            pass

        def __call__(self, **kwargs: object) -> SimpleNamespace:
            assert not torch.is_grad_enabled()
            assert kwargs["decoder_input_ids"].tolist() == [[0]]
            logits = torch.zeros((1, 1, 32128))
            logits[0, 0, 209] = 2
            return SimpleNamespace(logits=logits)

    config = load_config()

    def load(cls: object, model: str, **kwargs: object) -> object:
        assert model == config.verification.minicheck_model
        assert kwargs["revision"] == config.verification.minicheck_revision
        assert kwargs["trust_remote_code"] is False
        return Tokenizer() if cls == "tokenizer" else Model()

    monkeypatch.setattr(
        transformers.AutoTokenizer, "from_pretrained", lambda *a, **k: load("tokenizer", *a, **k)
    )
    monkeypatch.setattr(
        transformers.AutoModelForSeq2SeqLM,
        "from_pretrained",
        lambda *a, **k: load("model", *a, **k),
    )
    model = MiniCheck(config)
    assert model.score([("Claim", "Evidence")])[0] == pytest.approx(0.880797, abs=1e-6)
    assert calls[0][0] == ["predict: Evidence</s>Claim"]
    with pytest.raises(ValueError, match="not truncated"):
        model.score([("Claim", "TOO_LONG")])
    other = MiniCheck(
        replace(config, verification=replace(config.verification, minicheck_model="other"))
    )
    with pytest.raises(ValueError, match="verified MiniCheck"):
        other.score([("Claim", "Evidence")])


def test_persist_exact_verification_schema_and_claim_validation(corpus: tuple) -> None:
    config, rows = corpus
    answer = generate_answer(
        "Question",
        rows[:1],
        config,
        FakeLLM(
            [
                completion(
                    [
                        {"text": "Claim", "citations": [FIRST]},
                        {"text": "Unsupported", "citations": []},
                    ]
                )
            ]
        ),
    )
    result = verify_answer(answer, config, CachedVerifier(config, FakeSupport()))
    assert len(result) == 1
    assert result[0]["label"] == "supported"
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT verifier, label FROM verification").fetchall() == [
            ("minicheck", "supported")
        ]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    answer["claims"][0]["text"] = "Tampered"
    with pytest.raises(ValueError, match="differs from persisted"):
        verify_answer(answer, config, CachedVerifier(config, FakeSupport()))


def test_verifier_failure_retains_answer_and_records_unknown(corpus: tuple) -> None:
    config, rows = corpus
    answer = generate_answer(
        "Question",
        rows[:1],
        config,
        FakeLLM(
            [
                completion(
                    [
                        {"text": "Claim", "citations": [FIRST]},
                    ]
                )
            ]
        ),
    )
    result = verify_answer(answer, config, CachedVerifier(config, FakeSupport([float("nan")])))
    assert result[0]["label"] is None
    assert "error" in result[0]
    assert answer["claims"][0]["text"] == "Claim"


def test_sampling_is_stable_and_independent_of_input_order() -> None:
    ids = [str(i) for i in range(20)]
    assert sample_claim_ids(ids, 0.25, 42) == sample_claim_ids(ids[::-1], 0.25, 42)
    assert len(sample_claim_ids(ids, 0.25, 42)) == 5
    assert sample_claim_ids(ids, 0, 42) == set()
    with pytest.raises(ValueError):
        sample_claim_ids(["a", "a"], 0.25, 42)


def test_judge_uses_only_pair_cache_and_independent_family(corpus: tuple) -> None:
    config, _ = corpus
    backend = FakeLLM(
        [Completion('{"label":"supported","rationale":"Explicit evidence"}', "gpt-fixture", 8, 4)]
    )
    judge = Judge(config, backend)
    assert judge.verify("Claim", "Evidence")["label"] == "supported"
    assert judge.verify("Claim", "Evidence")["label"] == "supported"
    user = json.loads(backend.calls[0][1]["content"])
    assert user == {"claim": "Claim", "evidence": "Evidence"}
    assert judge.client.calls == 1
    changed = replace(config, verification=replace(config.verification, judge_provider="deepseek"))
    with pytest.raises(ValueError, match="different model family"):
        Judge(changed)


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '{"label":"supported","rationale":""}',
        '{"label":"supported","label":"not_supported","rationale":"x"}',
        '{"label":[],"rationale":"x"}',
        "not json",
    ],
)
def test_judge_invalid_json_is_rejected(corpus: tuple, raw: str) -> None:
    config, _ = corpus
    judge = Judge(config, FakeLLM([Completion(raw, "gpt-fixture", 2, 2)]))
    with pytest.raises(ValueError):
        judge.verify("Claim", "Evidence")


def test_kappa_manual_calculation_and_degenerate_cases() -> None:
    assert cohens_kappa(["s", "s", "n", "n"], ["s", "n", "n", "n"]) == pytest.approx(0.5)
    assert cohens_kappa([], []) is None
    assert cohens_kappa(["s"], ["s"]) is None
    with pytest.raises(ValueError):
        cohens_kappa(["s"], [])


def record(qtype: str, claims: list[dict], verification: list[dict], status: str = "ok") -> dict:
    return {
        "qtype": qtype,
        "generation": {"claims": claims, "status": status, "rejected_citations": []},
        "verification": verification,
    }


def test_citation_metrics_unsupported_unanswerable_and_unknown() -> None:
    claims = [
        {"claim_id": "c1", "citations": [FIRST, SECOND], "unsupported": False},
        {"claim_id": "c2", "citations": [], "unsupported": True},
    ]
    pairs = [
        {"claim_id": "c1", "chunk_id": FIRST, "verifier": "minicheck", "label": "supported"},
        {"claim_id": "c1", "chunk_id": SECOND, "verifier": "minicheck", "label": "not_supported"},
    ]
    data = record("lookup", claims, pairs)
    data["generation"]["rejected_citations"] = [{"reason": "not_in_context"}]
    metrics = citation_metrics([data, record("unanswerable", [], [], "no_evidence")])
    assert metrics["citation_precision"] == 0.5
    assert metrics["citation_recall"] == 0.5
    assert metrics["faithfulness"] == 0.5
    assert metrics["hallucinated_citation_rate"] == pytest.approx(1 / 3)
    assert metrics["abstention_accuracy"] == 1
    assert citation_metrics([record("unanswerable", claims, pairs)])["faithfulness"] == 0
    assert citation_metrics([record("unanswerable", claims[1:], [])])["abstention_accuracy"] == 0
    assert citation_metrics([record("unanswerable", [], [], "failed")])["abstention_accuracy"] == 0
    pairs[0]["label"] = None
    assert citation_metrics([data])["faithfulness"] is None


def dataset(tmp_path: Path, config: object) -> object:
    questions = [
        {
            "qid": "q1",
            "question": "Alpha?",
            "qtype": "lookup",
            "gold_paper_ids": ["arxiv:2401.12345v1"],
            "gold_chunk_ids": [FIRST],
        },
        {
            "qid": "q2",
            "question": "Beta?",
            "qtype": "lookup",
            "gold_paper_ids": ["arxiv:2401.12345v1"],
            "gold_chunk_ids": [SECOND],
        },
        {
            "qid": "q3",
            "question": "Alpha unknown?",
            "qtype": "unanswerable",
            "gold_paper_ids": [],
            "gold_chunk_ids": [],
        },
    ]
    path = tmp_path / "questions.jsonl"
    path.write_text("\n".join(json.dumps(q) for q in questions), encoding="utf-8")
    return replace(
        config,
        evaluation=replace(
            config.evaluation,
            dataset_path=str(path),
            gold_labels_path=str(tmp_path / "gold.jsonl"),
            output_dir=str(tmp_path / "results"),
        ),
    )


def test_citation_evaluation_end_to_end_cache_and_reports(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    monkeypatch.chdir(tmp_path)
    backend = FakeLLM(
        [
            completion([{"text": "Alpha", "citations": [FIRST]}]),
            completion([{"text": "Beta", "citations": [SECOND]}]),
            completion([]),
        ]
    )
    support = FakeSupport()
    result = evaluate_citations(config, modes=("bm25",), backend=backend, support_backend=support)[
        0
    ]
    assert result["status"] == "ok"
    assert result["metrics"]["citation_precision"] == 1
    assert result["metrics"]["abstention_accuracy"] == 1
    assert result["metrics"]["verifier_agreement_kappa"] is None
    assert result["usage"]["generation"]["backend_calls"] == 3
    assert result["annotation_pair_count"] == 2
    annotation = Path(result["annotation_path"])
    assert annotation.exists()
    assert json.loads(annotation.read_text().splitlines()[0])["label"] is None
    reports = list((tmp_path / "results").glob("*/metrics.json"))
    assert len(reports) == 1
    repeat = evaluate_citations(config, modes=("bm25",), backend=backend, support_backend=support)[
        0
    ]
    assert repeat["run_id"] != result["run_id"]
    assert repeat["usage"]["generation"]["backend_calls"] == 0
    assert repeat["verifier_cache_hits"] == 2
    assert len(backend.calls) == 3


def test_batch_budget_includes_all_questions_and_modes(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    config = replace(config, generation=replace(config.generation, max_calls_per_run=1))
    monkeypatch.chdir(tmp_path)
    backend = FakeLLM([completion([{"text": "Alpha", "citations": [FIRST]}])])
    result = evaluate_citations(
        config, modes=("bm25",), backend=backend, support_backend=FakeSupport()
    )[0]
    assert len(backend.calls) == 1
    assert result["status"] == "incomplete"
    assert result["metrics"]["failed_question_count"] == 2
    assert result["metrics"]["faithfulness"] is None


def test_manual_annotations_bind_text_and_require_named_human(
    corpus: tuple, tmp_path: Path
) -> None:
    config, rows = corpus
    path = tmp_path / "labels.jsonl"
    item = {
        "claim": "Alpha",
        "chunk_id": FIRST,
        "text_sha256": text_hash(rows[0]["text"]),
        "label": "supported",
        "annotator": "fixture-human",
    }
    path.write_text(json.dumps(item))
    labels, digest = load_manual_labels(path, {r["chunk_id"]: r for r in rows})
    assert len(labels) == 1 and len(digest) == 64
    item["text_sha256"] = "a" * 64
    path.write_text(json.dumps(item))
    with pytest.raises(ValueError, match="Invalid manual"):
        load_manual_labels(path, {r["chunk_id"]: r for r in rows})
    with pytest.raises(ValueError, match="under data"):
        export_annotations([], {}, tmp_path / "outside.jsonl")


def test_cli_routes_citation_stage_without_enabling_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from rag.evaluation.__main__ import main

    calls = []

    def fake(*args: object, **kwargs: object) -> list[dict]:
        calls.append(kwargs)
        return [{"status": "ok"}]

    monkeypatch.setattr("rag.evaluation.citations.evaluate_citations", fake)
    monkeypatch.setattr(sys, "argv", ["eval", "--stage", "citations", "--mode", "bm25"])
    assert main() == 0
    assert calls == [{"allow_api": False, "with_judge": False}]


def test_agreement_evaluates_human_pairs_without_generation(
    corpus: tuple,
    tmp_path: Path,
) -> None:
    from rag.evaluation.agreement import evaluate_agreement

    config, rows = corpus
    path = tmp_path / "human.jsonl"
    items = [
        {
            "claim": text,
            "chunk_id": FIRST,
            "text_sha256": text_hash(rows[0]["text"]),
            "label": label,
            "annotator": "fixture-human",
        }
        for text, label in [("Alpha", "supported"), ("Contradiction", "not_supported")]
    ]
    path.write_bytes(("\r\n".join(json.dumps(item) for item in items) + "\r\n").encode())
    config = replace(
        config, evaluation=replace(config.evaluation, output_dir=str(tmp_path / "runs"))
    )

    class SupportByClaim:
        def score(self, pairs: list[tuple[str, str]]) -> list[float]:
            return [0.9 if claim == "Alpha" else 0.1 for claim, _ in pairs]

    result = evaluate_agreement(config, path, SupportByClaim())
    assert result["metrics"]["verifier_agreement_kappa"] == 1
    assert result["metrics"]["matched_pairs"] == 2
    assert result["paid_api_calls"] == 0
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT kind FROM run").fetchall() == [("eval",)]
    items[0]["label"] = None
    path.write_text(json.dumps(items[0]))
    with pytest.raises(ValueError, match="Invalid manual"):
        evaluate_agreement(config, path, SupportByClaim())


def test_evaluation_judge_sample_and_manual_kappa(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, rows = corpus
    config = dataset(tmp_path, config)
    manual = {
        "claim": "Alpha",
        "chunk_id": FIRST,
        "text_sha256": text_hash(rows[0]["text"]),
        "label": "supported",
        "annotator": "fixture-human",
    }
    Path(config.evaluation.gold_labels_path).write_text(json.dumps(manual))
    monkeypatch.chdir(tmp_path)
    backend = FakeLLM(
        [
            completion([{"text": "Alpha", "citations": [FIRST]}]),
            completion([{"text": "Beta", "citations": [SECOND]}]),
            completion([]),
        ]
    )
    judge_backend = FakeLLM(
        [Completion('{"label":"supported","rationale":"Fixture"}', "gpt-fixture", 10, 3)]
    )
    result = evaluate_citations(
        config,
        modes=("bm25",),
        backend=backend,
        support_backend=FakeSupport(),
        judge_backend=judge_backend,
        with_judge=True,
    )[0]
    assert len(result["judge_sample_keys"]) == 1
    assert result["metrics"]["manual_matched_pairs"] == 1
    assert result["metrics"]["judge_matched_pairs"] == 1
    assert result["usage"]["judge"]["backend_calls"] == 1
    public = next((tmp_path / "results").glob("*/per_question.jsonl")).read_text()
    assert rows[0]["text"] not in public
    assert '"markdown"' not in public
    assert '"quote"' not in public
    with sqlite3.connect(config.paths.db_path) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM verification WHERE verifier='llm_judge'"
            ).fetchone()[0]
            == 1
        )


def test_cache_miss_without_api_flag_is_failed_question(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    monkeypatch.chdir(tmp_path)
    result = evaluate_citations(config, modes=("bm25",), support_backend=FakeSupport())[0]
    assert result["status"] == "incomplete"
    assert result["metrics"]["failed_question_count"] == 3
    assert result["usage"]["generation"]["backend_calls"] == 0
    assert result["metrics"]["abstention_accuracy"] == 0


def test_run_collision_preserves_report(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("rag.evaluation.citations.make_run_id", lambda: "fixed")
    evaluate_citations(config, modes=("bm25",), support_backend=FakeSupport())
    report_path = tmp_path / "results" / "fixed" / "metrics.json"
    original = report_path.read_bytes()
    with pytest.raises(FileExistsError):
        evaluate_citations(config, modes=("bm25",), support_backend=FakeSupport())
    assert report_path.read_bytes() == original


def test_verification_schema_conflict_is_not_replaced(corpus: tuple) -> None:
    config, rows = corpus
    answer = generate_answer("Question", rows[:1], config, FakeLLM([completion([])]))
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("CREATE TABLE verification (different TEXT)")
    with pytest.raises(ValueError, match="differs from ARCHITECTURE"):
        verify_answer(answer, config, CachedVerifier(config, FakeSupport()))


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("verification", "minicheck_revision", "main"),
        ("verification", "device", "gpu"),
        ("verification", "max_tokens", 0),
        ("verification", "batch_size", 0),
        ("verification", "support_threshold", 0),
        ("verification", "support_threshold", 1),
        ("verification", "judge_max_calls_per_run", 0),
        ("verification", "judge_provider", "unknown"),
    ],
)
def test_verification_config_validates_new_fields(
    tmp_path: Path,
    section: str,
    key: str,
    value: object,
) -> None:
    import yaml

    from rag.config import ConfigError

    data = yaml.safe_load(Path("configs/config.yaml").read_text())
    data[section][key] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match=rf"{section}\.{key}"):
        load_config(path)


def test_agreement_persistence_failure_still_writes_failed_report(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag.evaluation import agreement

    config, rows = corpus
    path = tmp_path / "human.jsonl"
    path.write_text(
        json.dumps(
            {
                "claim": "Alpha",
                "chunk_id": FIRST,
                "text_sha256": text_hash(rows[0]["text"]),
                "label": "supported",
                "annotator": "fixture-human",
            }
        )
    )
    config = replace(
        config, evaluation=replace(config.evaluation, output_dir=str(tmp_path / "runs"))
    )
    original = agreement.connect_corpus
    calls = 0

    def fail_finish(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("fixture write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(agreement, "connect_corpus", fail_finish)
    with pytest.raises(sqlite3.OperationalError):
        agreement.evaluate_agreement(config, path, FakeSupport())
    report = json.loads(next((tmp_path / "runs").glob("*/metrics.json")).read_text())
    assert report["status"] == "failed"
    assert "persistence failed" in report["error"]


def test_annotation_export_failure_marks_evaluation_failed(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    monkeypatch.chdir(tmp_path)
    backend = FakeLLM([completion([]), completion([]), completion([])])

    def fail_export(*args: object, **kwargs: object) -> None:
        raise OSError("fixture disk failure")

    monkeypatch.setattr("rag.evaluation.citations.export_annotations", fail_export)
    with pytest.raises(OSError):
        evaluate_citations(config, modes=("bm25",), backend=backend, support_backend=FakeSupport())
    report = json.loads(next((tmp_path / "results").glob("*/metrics.json")).read_text())
    assert report["status"] == "failed"
    with sqlite3.connect(config.paths.db_path) as connection:
        notes = connection.execute("SELECT notes FROM run WHERE kind='eval'").fetchone()[0]
        assert json.loads(notes)["status"] == "failed"
