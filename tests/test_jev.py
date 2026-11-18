import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from rag.config import load_config
from rag.evaluation.citations import evaluate_citations
from rag.evaluation.decisions import compare_decisions
from rag.generation.client import Completion, LLMError
from rag.indexing.embedding import text_hash
from rag.verification.jev import JevJudge, decision_endpoint
from rag.verification.judge import create_judge
from test_generation import FIRST, SECOND, FakeLLM, completion
from test_generation import corpus as corpus
from test_verification import FakeSupport, dataset


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SURPLUS_API_KEY", "fixture-surplus-secret")
    monkeypatch.setenv("SURPLUS_API_URL", "https://api.surplusintelligence.ai/v1")
    monkeypatch.setenv("JEV_MODEL_ID", "jev-1.14")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Jev tests cannot make real network requests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)


def decision(label: str = "supported", **updates: object) -> Completion:
    data = {
        "model": "typesafe/jev-1.14-20261014",
        "answers": {
            "support": {
                "type": "choice",
                "choice": label,
                "probabilities": {
                    key: 0.8 if key == label else 0.1
                    for key in ("supported", "partially_supported", "not_supported")
                },
                "confidence": 0.7,
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 4},
    }
    data.update(updates)
    return Completion(json.dumps(data), data["model"], 100, 4)


@pytest.mark.parametrize("path", ["/v1", "/v1/", "/v1/decisions", "/v1/decisions/"])
def test_endpoint_normalization(path: str) -> None:
    assert decision_endpoint("https://api.surplusintelligence.ai" + path) == (
        "https://api.surplusintelligence.ai/v1/decisions"
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://api.surplusintelligence.ai/v1",
        "https://example.com/v1",
        "https://secret@api.surplusintelligence.ai/v1",
        "https://api.surplusintelligence.ai/v1?key=secret",
        "https://api.surplusintelligence.ai/v1#secret",
        "https://api.surplusintelligence.ai:invalid/v1",
        "https://api.surplusintelligence.ai/v1/chat/completions",
    ],
)
def test_endpoint_rejects_credentials_other_hosts_and_wrong_protocol(value: str) -> None:
    with pytest.raises(ValueError, match="SURPLUS_API_URL") as error:
        decision_endpoint(value)
    assert "secret" not in str(error.value)


def test_jev_uses_selected_env_model_and_preserves_distribution(corpus: tuple) -> None:
    config, _ = corpus
    backend = FakeLLM([decision("partially_supported")])
    judge = JevJudge(config, backend)
    result = judge.verify("A claim", "Evidence")
    assert result["label"] == "partially_supported"
    assert result["rationale"] is None
    assert result["score"] == 0.1
    assert result["confidence"] == 0.7
    assert judge.config.verification.judge_model == "jev-1.14"
    assert judge.config.verification.judge_provider == "surplus"
    assert judge.client.config.generation.provider == "surplus"
    payload = json.loads(backend.calls[0][0]["content"])
    assert payload["state"] == {"claim": "A claim", "evidence": "Evidence"}
    assert set(payload["questions"]["support"]["criteria"]) == {
        "supported",
        "partially_supported",
        "not_supported",
    }
    assert judge.verify("A claim", "Evidence") == result
    assert len(backend.calls) == 1


def test_real_backend_cache_miss_requires_explicit_api_flag(corpus: tuple) -> None:
    config, _ = corpus
    judge = JevJudge(config)
    with pytest.raises(LLMError, match="--allow-api"):
        judge.verify("Claim", "Evidence")
    assert judge.client.calls == 0


def test_http_transport_native_request_token_usage_and_offline_repeat(
    corpus: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://api.surplusintelligence.ai/v1/decisions"
        assert request.headers["Authorization"] == "Bearer fixture-surplus-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "jev-1.14"
        assert payload["state"] == {"claim": "Claim", "evidence": "Evidence"}
        assert "messages" not in payload
        return httpx.Response(200, json=json.loads(decision().content))

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    judge = JevJudge(config, allow_api=True)
    assert judge.verify("Claim", "Evidence")["label"] == "supported"
    assert judge.client.attempts[0]["billed_input_tokens"] == 100
    assert judge.client.attempts[0]["billed_output_tokens"] == 4
    cached = JevJudge(config, allow_api=False)
    assert cached.verify("Claim", "Evidence")["label"] == "supported"
    assert cached.client.calls == 0
    assert len(requests) == 1
    for path in Path(config.paths.cache_dir).rglob("*.json"):
        assert "fixture-surplus-secret" not in path.read_text()


@pytest.mark.parametrize("status", [302, 401, 402, 403, 429, 500])
def test_http_error_has_no_retry_and_does_not_leak_response_or_key(
    corpus: tuple,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    config, _ = corpus
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, text="fixture-surplus-secret", headers={"location": "https://example.com/steal"}
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    judge = JevJudge(config, allow_api=True)
    with pytest.raises(LLMError, match=str(status)) as error:
        judge.verify("Claim", "Evidence")
    assert len(requests) == 1
    assert "secret" not in str(error.value)
    assert judge.client.calls == 1


@pytest.mark.parametrize(
    "change",
    [
        "wrong_model",
        "wrong_type",
        "missing_choice",
        "missing_probability",
        "nan",
        "sum",
        "negative",
        "bad_confidence",
        "wrong_winner",
        "refusal",
        "wrong_question",
    ],
)
def test_invalid_decision_is_not_accepted(corpus: tuple, change: str) -> None:
    config, _ = corpus
    data = json.loads(decision().content)
    answer = data["answers"]["support"]
    if change == "wrong_model":
        data["model"] = "typesafe/jev-1.13-20260917"
    elif change == "wrong_type":
        answer["type"] = "score"
    elif change == "missing_choice":
        answer.pop("choice")
    elif change == "missing_probability":
        answer["probabilities"].pop("supported")
    elif change == "nan":
        answer["probabilities"]["supported"] = float("nan")
    elif change == "sum":
        answer["probabilities"]["supported"] = 0.5
    elif change == "negative":
        answer["probabilities"]["supported"] = -0.1
    elif change == "bad_confidence":
        answer["confidence"] = True
    elif change == "wrong_winner":
        answer["choice"] = "not_supported"
    elif change == "refusal":
        data["answers"]["support"] = {"type": "refusal"}
    elif change == "wrong_question":
        data["answers"] = {"other": answer}
    response = Completion(json.dumps(data), data["model"], 100, 4)
    judge = JevJudge(config, FakeLLM([response]))
    with pytest.raises(LLMError):
        judge.verify("Claim", "Evidence")


def test_budget_is_shared_across_pairs(corpus: tuple) -> None:
    config, _ = corpus
    config = replace(config, verification=replace(config.verification, judge_max_calls_per_run=1))
    backend = FakeLLM([decision()])
    judge = JevJudge(config, backend)
    judge.verify("One", "Evidence")
    with pytest.raises(LLMError, match="exhausted"):
        judge.verify("Two", "Evidence")
    assert len(backend.calls) == 1


@pytest.mark.parametrize("model", ["jev-latest", "gpt-4o-mini", "jev-preview"])
def test_rolling_or_non_jev_model_is_rejected(
    corpus: tuple,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
) -> None:
    config, _ = corpus
    monkeypatch.setenv("JEV_MODEL_ID", model)
    with pytest.raises(ValueError, match="explicit Jev version"):
        JevJudge(config)


def test_jev_integrates_with_evaluation_and_existing_sqlite_schema(
    corpus: tuple,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = corpus
    config = dataset(tmp_path, config)
    config = replace(config, verification=replace(config.verification, judge_provider="surplus"))
    assert isinstance(create_judge(config, FakeLLM([])), JevJudge)
    monkeypatch.chdir(tmp_path)
    generation = FakeLLM(
        [
            completion([{"text": "Alpha", "citations": [FIRST]}]),
            completion([{"text": "Beta", "citations": [SECOND]}]),
            completion([]),
        ]
    )
    result = evaluate_citations(
        config,
        modes=("bm25",),
        backend=generation,
        with_judge=True,
        judge_backend=FakeLLM([decision()]),
        support_backend=FakeSupport(),
    )[0]
    assert result["status"] == "ok"
    assert result["config"]["verification"]["judge_model"] == "jev-1.14"
    assert result["models"]["reported_judge_models"] == ["typesafe/jev-1.14-20261014"]
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute(
            "SELECT label, score, rationale FROM verification WHERE verifier='llm_judge'"
        ).fetchall() == [("supported", 0.8, None)]


def test_repository_config_still_uses_original_generator() -> None:
    config = load_config()
    assert config.generation.provider == "deepseek"
    assert config.generation.model == "deepseek-flash"


def pair_file(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "pairs.jsonl"
    pairs = [
        {
            "claim": f"Claim {number}",
            "chunk_id": rows[0]["chunk_id"],
            "text_sha256": text_hash(rows[0]["text"]),
            "label": None,
        }
        for number in range(4)
    ]
    path.write_text("\n".join(json.dumps(p) for p in pairs), encoding="utf-8")
    return path


def test_comparison_is_reproducible_cached_and_has_no_human_accuracy(
    corpus: tuple,
    tmp_path: Path,
) -> None:
    config, rows = corpus
    config = replace(
        config, evaluation=replace(config.evaluation, output_dir=str(tmp_path / "results"))
    )
    path = pair_file(tmp_path, rows)
    before = path.read_bytes()
    backend = FakeLLM([decision(), decision("not_supported"), decision()])
    first = compare_decisions(config, path, 3, backend=backend, support_backend=FakeSupport())
    assert first["status"] == "ok"
    assert first["metrics"]["comparable_pairs"] == 3
    assert first["metrics"]["inter_model_agreement"] == pytest.approx(2 / 3)
    assert first["metrics"]["accuracy_against_human_gold"] is None
    assert first["metrics"]["human_gold_pair_count"] == 0
    assert first["usage"]["backend_calls"] == 3
    repeat = compare_decisions(config, path, 3, backend=backend, support_backend=FakeSupport())
    assert repeat["run_id"] != first["run_id"]
    assert repeat["selected_input_rows"] == first["selected_input_rows"]
    assert repeat["metrics"] == first["metrics"]
    assert repeat["usage"]["backend_calls"] == 0
    assert repeat["usage"]["cache_hits"] == 3
    assert repeat["new_request_median_http_seconds"] is None
    assert path.read_bytes() == before
    public = "".join(p.read_text() for p in (tmp_path / "results").glob("*/*.json*"))
    assert rows[0]["text"] not in public
    assert "fixture-surplus-secret" not in public


def test_comparison_stops_at_first_provider_failure(corpus: tuple, tmp_path: Path) -> None:
    config, rows = corpus
    config = replace(
        config, evaluation=replace(config.evaluation, output_dir=str(tmp_path / "results"))
    )
    backend = FakeLLM([LLMError("Surplus decision HTTP 403; no automatic retry")])
    result = compare_decisions(
        config, pair_file(tmp_path, rows), 3, backend=backend, support_backend=FakeSupport()
    )
    assert result["status"] == "failed"
    assert result["metrics"]["jev_completed_pairs"] == 0
    assert len(backend.calls) == 1
    assert "403" in result["error"]
    assert len(list((tmp_path / "results").glob("*/metrics.json"))) == 1


def test_comparison_preserves_local_model_failure_as_missing(corpus: tuple, tmp_path: Path) -> None:
    config, rows = corpus
    config = replace(
        config, evaluation=replace(config.evaluation, output_dir=str(tmp_path / "results"))
    )

    class TooLong:
        def score(self, pairs: list[tuple[str, str]]) -> list[float]:
            raise ValueError("MiniCheck input exceeds token limit")

    result = compare_decisions(
        config,
        pair_file(tmp_path, rows),
        2,
        backend=FakeLLM([decision(), decision()]),
        support_backend=TooLong(),
    )
    assert result["status"] == "incomplete"
    assert result["metrics"]["minicheck_unverified_pairs"] == 2
    assert result["metrics"]["inter_model_agreement"] is None


def test_changed_evidence_is_rejected_before_paid_request(corpus: tuple, tmp_path: Path) -> None:
    config, rows = corpus
    path = pair_file(tmp_path, rows)
    items = [json.loads(line) for line in path.read_text().splitlines()]
    items[0]["text_sha256"] = "a" * 64
    path.write_text("\n".join(json.dumps(item) for item in items))
    backend = FakeLLM([])
    with pytest.raises(ValueError, match="Invalid decision comparison pair"):
        compare_decisions(config, path, backend=backend)
    assert backend.calls == []
