import json
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

from rag.config import Config
from rag.generation.client import LLMError
from rag.verification.judge import Judge, create_judge
from test_generation import corpus as corpus


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, corpus: tuple) -> None:
    monkeypatch.chdir(tmp_path)
    for variable in ("GPT_MODEL_ID", "SURPLUS_API_URL", "SURPLUS_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    (tmp_path / ".env").write_text(
        "GPT_MODEL_ID=gpt-4o-mini\n"
        "SURPLUS_API_URL=https://api.surplusintelligence.ai/v1\n"
        "SURPLUS_API_KEY=fixture-surplus-key\n",
        encoding="utf-8",
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Surplus chat tests cannot make network requests")

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", forbidden)


def chat_config(config: Config) -> Config:
    return replace(
        config,
        verification=replace(
            config.verification, judge_provider="surplus-chat", judge_max_calls_per_run=1
        ),
    )


@pytest.mark.parametrize("status", [200, 500])
def test_chat_transport_surplus_key_usage_cache_and_no_retry(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    import openai

    config, _ = corpus
    config = chat_config(config)
    requests = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert str(request.url) == "https://api.surplusintelligence.ai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture-surplus-key"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-4o-mini"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_tokens"] == config.generation.max_output_tokens
        assert "thinking" not in payload
        assert json.loads(payload["messages"][1]["content"]) == {
            "claim": "Claim",
            "evidence": "Evidence",
        }
        return httpx2.Response(
            status,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"label":"supported","rationale":"Explicit evidence"}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    original = openai.OpenAI

    def factory(**kwargs: object) -> object:
        assert kwargs["max_retries"] == 0
        return original(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))

    monkeypatch.setattr(openai, "OpenAI", factory)
    judge = create_judge(config, allow_api=True)
    assert isinstance(judge, Judge)
    assert judge.config.verification.judge_model == "gpt-4o-mini"
    assert judge.config.verification.judge_base_url == "https://api.surplusintelligence.ai/v1"
    if status != 200:
        with pytest.raises(LLMError, match="LLM request failed") as error:
            judge.verify("Claim", "Evidence")
        assert "fixture-surplus-key" not in str(error.value)
    else:
        result = judge.verify("Claim", "Evidence")
        assert result["rationale"] == "Explicit evidence"
        assert result["model"] == "gpt-4o-mini-2024-07-18"
        assert judge.client.attempts[0]["billed_input_tokens"] == 100
        assert judge.client.attempts[0]["billed_output_tokens"] == 20
        cached = create_judge(config)
        assert cached.verify("Claim", "Evidence") == result
        assert cached.client.calls == 0 and cached.client.attempts[0]["cache_hit"]
        with pytest.raises(LLMError, match="exhausted"):
            judge.verify("Different claim", "Evidence")
        for path in Path(config.paths.cache_dir).rglob("*.json"):
            assert "fixture-surplus-key" not in path.read_text()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.surplusintelligence.ai/v1",
        "https://example.com/v1",
        "https://secret@api.surplusintelligence.ai/v1",
        "https://api.surplusintelligence.ai/v1?secret=value",
        "https://api.surplusintelligence.ai/v1#secret",
        "https://api.surplusintelligence.ai:invalid/v1",
        "https://api.surplusintelligence.ai/v1/decisions",
    ],
)
def test_chat_rejects_untrusted_endpoint(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    config, _ = corpus
    monkeypatch.setenv("SURPLUS_API_URL", endpoint)
    with pytest.raises(ValueError, match="Surplus HTTPS /v1") as error:
        create_judge(chat_config(config))
    assert "secret" not in str(error.value)


def test_chat_rejects_same_family_and_model_substitution(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag.generation.client import Completion
    from test_generation import FakeLLM

    config, _ = corpus
    config = chat_config(config)
    openai_generator = replace(
        config, generation=replace(config.generation, provider="openai", model="gpt-4o-mini")
    )
    with pytest.raises(ValueError, match="different model family"):
        create_judge(openai_generator)
    backend = FakeLLM(
        [Completion('{"label":"supported","rationale":"Evidence"}', "deepseek-flash", 2, 2)]
    )
    with pytest.raises(ValueError, match="differs from GPT_MODEL_ID"):
        create_judge(config, backend).verify("Claim", "Evidence")
    monkeypatch.setenv("GPT_MODEL_ID", "deepseek-flash")
    with pytest.raises(ValueError, match="independent"):
        create_judge(config)


def test_citation_runner_records_effective_surplus_judge_and_replays(
    corpus: tuple, tmp_path: Path
) -> None:
    from rag.evaluation.citations import evaluate_citations
    from rag.generation.client import Completion
    from test_generation import FIRST, SECOND, FakeLLM, completion
    from test_verification import FakeSupport, dataset

    config, _ = corpus
    config = dataset(tmp_path, chat_config(config))
    generator = FakeLLM(
        [
            completion([{"text": "Alpha", "citations": [FIRST]}]),
            completion([{"text": "Beta", "citations": [SECOND]}]),
            completion([]),
        ]
    )
    judge = FakeLLM(
        [Completion('{"label":"supported","rationale":"Explicit evidence"}', "gpt-4o-mini", 8, 4)]
    )
    reports = []
    for _ in range(2):
        reports.append(
            evaluate_citations(
                config,
                modes=("bm25",),
                with_judge=True,
                backend=generator,
                judge_backend=judge,
                support_backend=FakeSupport(),
            )[0]
        )
    assert all(report["status"] == "ok" for report in reports)
    assert reports[0]["config"]["verification"]["judge_provider"] == "surplus-chat"
    assert reports[0]["config"]["verification"]["judge_model"] == "gpt-4o-mini"
    assert reports[0]["config"]["verification"]["judge_base_url"].endswith("/v1")
    assert reports[0]["judge_sample_keys"] == reports[1]["judge_sample_keys"]
    assert len(generator.calls) == 3 and len(judge.calls) == 1
    assert reports[1]["usage"]["judge"]["backend_calls"] == 0
    assert reports[1]["usage"]["generation"]["backend_calls"] == 0
