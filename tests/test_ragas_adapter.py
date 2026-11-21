import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

os.environ["RAGAS_DO_NOT_TRACK"] = "true"
pytest.importorskip("ragas", reason="Ragas integration runs in its separate locked environment")

from rag.config import load_config
from rag.evaluation.ragas_adapter import create_metrics, metric_value
from rag.generation.client import CachedLLM, Completion
from test_ragas import corpus as corpus
from test_ragas import prepared as prepared


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import httpx2
    import requests

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Ragas integration tests must never access the network")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "send", forbidden)


class StructuredBackend:
    def __init__(self, verdict: int = 1, omit: bool = False, malformed: bool = False) -> None:
        self.calls = 0
        self.verdict = verdict
        self.omit = omit
        self.malformed = malformed

    def complete(self, messages: list, config: object) -> Completion:
        self.calls += 1
        system = messages[0]["content"]
        if "StatementGeneratorOutput" in system:
            data = dict(statements=["Alpha supports the result."])
        elif "NLIStatementOutput" in system:
            data = dict(
                statements=[]
                if self.omit
                else [
                    dict(
                        statement="Alpha supports the result.",
                        reason="Fixture evidence.",
                        verdict=self.verdict,
                    )
                ]
            )
        elif "AnswerRelevanceOutput" in system:
            data = dict(question="What does Alpha support?", noncommittal=0)
        else:
            data = dict(
                classifications=[
                    dict(
                        statement="Alpha supports the result.",
                        reason="Fixture evidence.",
                        attributed=1,
                    )
                ]
            )
        return Completion(
            "not JSON" if self.malformed else json.dumps(data), "gpt-4o-mini-fixture", 100, 30
        )


def client_for(tmp_path: object, backend: object, max_calls: int = 3) -> CachedLLM:
    base = load_config()
    config = replace(
        base,
        paths=replace(base.paths, cache_dir=str(tmp_path)),
        generation=replace(
            base.generation, provider="openai", model="gpt-4o-mini", max_calls_per_run=max_calls
        ),
    )
    return CachedLLM(config, backend)


@pytest.mark.parametrize("verdict,expected", [(0, 0.0), (1, 1.0)])
def test_real_ragas_faithfulness_recall_and_offline_replay(
    tmp_path: object, verdict: int, expected: float
) -> None:
    backend = StructuredBackend(verdict)
    client = client_for(tmp_path, backend)
    metrics, traces = create_metrics(client, 65536)
    arguments = dict(
        user_input="What does Alpha support?",
        response="Alpha supports the result.",
        retrieved_contexts=["Alpha supports the result."],
    )
    assert metric_value(metrics["faithfulness"].score(**arguments)) == expected
    assert (
        metric_value(
            metrics["context_recall"].score(
                user_input=arguments["user_input"],
                retrieved_contexts=arguments["retrieved_contexts"],
                reference=arguments["response"],
            )
        )
        == 1
    )
    assert backend.calls == client.calls == 3
    assert len(traces) == 3
    replay, _ = create_metrics(client, 65536)
    assert metric_value(replay["faithfulness"].score(**arguments)) == expected
    assert backend.calls == 3


@pytest.mark.parametrize("options", [dict(verdict=2), dict(omit=True), dict(malformed=True)])
def test_invalid_judge_output_is_not_a_supported_score(tmp_path: object, options: dict) -> None:
    metrics, _ = create_metrics(client_for(tmp_path, StructuredBackend(**options)), 65536)
    with pytest.raises(ValueError):
        metrics["faithfulness"].score(
            user_input="Question",
            response="Alpha supports the result.",
            retrieved_contexts=["Evidence"],
        )


def test_prompt_limit_and_request_budget_are_hard(tmp_path: object) -> None:
    backend = StructuredBackend()
    client = client_for(tmp_path, backend, max_calls=1)
    metrics, _ = create_metrics(client, 1)
    with pytest.raises(ValueError, match="byte limit"):
        metrics["faithfulness"].score(
            user_input="Question", response="Answer", retrieved_contexts=["Evidence"]
        )
    assert backend.calls == 0
    metrics, _ = create_metrics(client, 65536)
    with pytest.raises(ValueError, match="exhausted"):
        metrics["faithfulness"].score(
            user_input="Question", response="Answer", retrieved_contexts=["Evidence"]
        )
    assert backend.calls == 1


def test_undefined_metric_is_not_serialized_as_a_good_score() -> None:
    with pytest.raises(ValueError, match="undefined"):
        metric_value(SimpleNamespace(value=float("nan")))


def test_score_pipeline_replays_without_provider_calls(prepared: tuple) -> None:
    from rag.evaluation.ragas import score_ragas

    directory = prepared[2]
    first = score_ragas(directory, backend=StructuredBackend(), max_calls=3)
    replay = score_ragas(directory, backend=StructuredBackend(), max_calls=3)
    report = json.loads((first / "report.json").read_text())
    repeated = json.loads((replay / "report.json").read_text())
    assert report["judge_calls"] == 3
    assert repeated["judge_calls"] == 0
    assert report["metrics"] == repeated["metrics"]
    assert report["metrics"]["faithfulness"]["mean"] == 1
    assert report["unanswerable_abstained"] == 1
    assert report["human_accuracy"] is None
    assert report["cost_usd"] is None


def test_incomplete_judge_budget_has_unknown_aggregate(prepared: tuple) -> None:
    from rag.evaluation.ragas import score_ragas

    output = score_ragas(prepared[2], backend=StructuredBackend(), max_calls=1)
    report = json.loads((output / "report.json").read_text())
    assert report["judge_calls"] == 1
    assert report["metrics"]["faithfulness"]["mean"] is None
    assert report["metrics"]["faithfulness"]["scored"] == 0


@pytest.mark.parametrize("opposite,expected", [(False, 1.0), (True, -1.0)])
def test_real_relevancy_uses_local_vectors_and_preserves_cosine_range(tmp_path, opposite, expected):
    backend = StructuredBackend()
    client = client_for(tmp_path, backend, max_calls=5)

    def vectors(texts):
        return [
            [-1.0, 0.0] if opposite and text != "Original question" else [1.0, 0.0]
            for text in texts
        ]

    metrics, traces = create_metrics(client, 65536, embed_texts=vectors)
    score = metrics["response_relevancy"].score(
        user_input="Original question", response="Alpha supports the result."
    )
    assert metric_value(score, minimum=-1.0) == expected
    assert len(traces) == 3 and backend.calls == 1


def test_single_answer_quality_scores_and_cache_replay(prepared, monkeypatch):
    from rag.evaluation.answer_quality import prepare_quality, score_quality

    directory = prepared[2]
    config = load_config(directory / "config.yaml")
    config = replace(
        config, paths=replace(config.paths, cache_dir=str(directory / "quality-cache"))
    )
    sample = json.loads((directory / "samples.json").read_text())[0]["generation"]
    backend = StructuredBackend()

    def vectors(texts):
        return [[1.0, 0.0] for _ in texts]

    first = score_quality(
        prepare_quality(config, sample["answer_id"]), backend=backend, embed_texts=vectors
    )
    assert first["status"] == "evaluated"
    assert first["scores"] == dict(faithfulness=1.0, response_relevancy=1.0)
    calls = backend.calls
    replay = score_quality(
        prepare_quality(config, sample["answer_id"]), backend=backend, embed_texts=vectors
    )
    assert replay["scores"] == first["scores"]
    assert replay["usage"]["backend_calls"] == 0 and backend.calls == calls
    assert first["human_accuracy"] is None


def test_single_answer_cache_miss_remains_unknown_without_api(prepared):
    from rag.evaluation.answer_quality import prepare_quality, score_quality

    directory = prepared[2]
    config = load_config(directory / "config.yaml")
    config = replace(
        config, paths=replace(config.paths, cache_dir=str(directory / "quality-cache"))
    )
    sample = json.loads((directory / "samples.json").read_text())[0]["generation"]
    report = score_quality(prepare_quality(config, sample["answer_id"]))
    assert report["status"] == "failed"
    assert all(value is None for value in report["scores"].values())
    assert report["usage"]["backend_calls"] == 0
