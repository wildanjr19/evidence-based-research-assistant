import json
import logging
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from rag.chunking.core import Chunk
from rag.chunking.pipeline import CHUNK_SCHEMA, save_chunks
from rag.config import Config, load_config
from rag.generation.__main__ import main
from rag.generation.citations import ResponseFormatError, parse_claims
from rag.generation.client import Completion, LLMError, OpenAIBackend, _api_key
from rag.generation.pipeline import answer_question, generate_answer
from rag.generation.prompt import build_messages
from rag.generation.render import render_answer
from rag.generation.store import load_context
from rag.ids import make_chunk_id
from rag.indexing.store import index_keywords
from rag.ingestion.arxiv import Paper
from rag.ingestion.store import PAPER_SCHEMA, save_paper

PAPER_ID = "arxiv:2401.12345v1"
FIRST = make_chunk_id(PAPER_ID, 1, 1)
SECOND = make_chunk_id(PAPER_ID, 2, 2)
OUTSIDE = make_chunk_id(PAPER_ID, 3, 3)
UNKNOWN = make_chunk_id(PAPER_ID, 9, 99)


class FakeLLM:
    def __init__(self, responses: list[Completion | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], config: Config) -> Completion:
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def completion(claims: list[dict], **kwargs: object) -> Completion:
    return Completion(json.dumps({"claims": claims}), "fixture-model-v1", 100, 20, **kwargs)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import httpx2

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Generation tests must not use the network or paid APIs")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", forbidden)


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Config, list[dict]]:
    base = load_config()
    config = replace(
        base,
        paths=replace(
            base.paths,
            db_path=str(tmp_path / "corpus.db"),
            index_dir=str(tmp_path / "index"),
            cache_dir=str(tmp_path / "cache"),
        ),
    )
    paper = Paper(
        "2401.12345v1",
        "Fixture paper",
        ["Fixture"],
        2024,
        None,
        None,
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    )
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.executescript(PAPER_SCHEMA + CHUNK_SCHEMA)
        save_paper(connection, paper, "a" * 64, "2026-11-18T00:00:00Z")
        connection.execute("UPDATE paper SET parse_status = 'ok'")
        connection.commit()
        chunks = [
            Chunk(
                make_chunk_id(PAPER_ID, n, n),
                PAPER_ID,
                n,
                n,
                "Methods",
                1,
                n,
                text,
                len(text.split()),
                "low_quality" if n == 4 else "ok",
            )
            for n, text in enumerate(
                [
                    "Alpha evidence supports the first result.",
                    "Beta evidence supports the second result.",
                    "HIDDEN_CORPUS_TEXT outside context.",
                    "Damaged evidence.",
                ],
                1,
            )
        ]
        save_chunks(connection, PAPER_ID, chunks)
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute("SELECT * FROM chunk ORDER BY chunk_order")]
        index_keywords(connection, rows)
    return config, rows


def test_prompt_contains_only_selected_canonical_evidence_and_generic_instructions(
    corpus: tuple,
) -> None:
    config, rows = corpus
    context, _ = load_context(rows[:2], config)
    messages = build_messages("Compare the evidence.", context)
    user = json.loads(messages[1]["content"])
    assert user["question"] == "Compare the evidence."
    assert [c["chunk_id"] for c in user["chunks"]] == [FIRST, SECOND]
    assert user["chunks"][0]["text"] == rows[0]["text"]
    assert "HIDDEN_CORPUS_TEXT" not in json.dumps(messages)
    assert OUTSIDE not in json.dumps(messages)
    assert all(
        set(c) == {"chunk_id", "paper_id", "title", "page_start", "page_end", "section", "text"}
        for c in user["chunks"]
    )
    assert "outside knowledge" in messages[0]["content"]
    assert "untrusted data" in messages[0]["content"]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "```json\n{}\n```",
        "null",
        "[]",
        '{"claims":{}}',
        '{"claims":[],"extra":1}',
        '{"claims":[],"claims":[]}',
        '{"claims":NaN}',
        '{"claims":[{"text":"","citations":[]}]}',
        '{"claims":[{"text":"x","citations":[1]}]}',
        '{"claims":[{"text":"x","citations":[],"unsupported":"false"}]}',
        '{"claims":[{"text":"x","citations":[],"page":1}]}',
    ],
)
def test_response_schema_rejects_malformed_json_and_claims(raw: str) -> None:
    with pytest.raises(ResponseFormatError):
        parse_claims(raw, {FIRST}, {FIRST})


def test_citation_validation_filters_invented_and_out_of_context_ids_preserves_claims() -> None:
    raw = json.dumps(
        {
            "claims": [
                {"text": "First claim", "citations": [FIRST, FIRST, "invented", UNKNOWN, OUTSIDE]},
                {"text": "Unproven claim", "citations": [UNKNOWN], "unsupported": False},
                {"text": "Self-declared unsupported", "citations": [FIRST], "unsupported": True},
            ]
        }
    )
    claims, rejected = parse_claims(raw, {FIRST, OUTSIDE}, {FIRST})
    assert claims == [
        {"text": "First claim", "citations": [FIRST], "unsupported": False},
        {"text": "Unproven claim", "citations": [], "unsupported": True},
        {"text": "Self-declared unsupported", "citations": [FIRST], "unsupported": True},
    ]
    assert [event["reason"] for event in rejected] == [
        "invalid_id",
        "not_in_corpus",
        "not_in_context",
        "not_in_corpus",
    ]


def test_generate_persists_fixed_schema_and_renders_only_canonical_metadata(corpus: tuple) -> None:
    config, rows = corpus
    supplied = [dict(rows[0], title="Forged title"), rows[1]]
    backend = FakeLLM(
        [
            completion(
                [
                    {"text": "Alpha result", "citations": [FIRST, FIRST, UNKNOWN, OUTSIDE]},
                    {"text": "Unproven claim", "citations": []},
                ]
            )
        ]
    )
    with sqlite3.connect(config.paths.db_path) as connection:
        before = connection.execute("SELECT * FROM chunk").fetchall()
        fts_before = connection.execute("SELECT * FROM chunk_fts").fetchall()
    result = generate_answer("What is supported?", supplied, config, backend)
    assert result["status"] == "ok" and len(result["claims"]) == 2
    assert result["claims"][1]["unsupported"] is True
    assert result["references"][0]["title"] == "Fixture paper"
    assert result["references"][0]["quote"] == rows[0]["text"]
    assert "tidak ada bukti" in result["markdown"] and "belum diverifikasi" in result["markdown"]
    assert "Forged title" not in json.dumps(backend.calls)
    assert result["input_tokens"] == 100 and result["output_tokens"] == 20
    assert result["verification_status"] == "not_run"
    assert result["hallucinated_citation_count"] == 1
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT * FROM chunk").fetchall() == before
        assert connection.execute("SELECT * FROM chunk_fts").fetchall() == fts_before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT raw_response FROM answer").fetchone()[0]
            == result["attempts"][0]["content"]
        )
        persisted = connection.execute(
            "SELECT citations, unsupported FROM claim ORDER BY claim_order"
        ).fetchall()
        assert persisted == [(json.dumps([FIRST]), 0), ("[]", 1)]
        notes = json.loads(connection.execute("SELECT notes FROM run").fetchone()[0])
        assert notes["status"] == "ok" and notes["input_tokens"] == 100
    assert json.loads(Path(result["report_path"]).read_text(encoding="utf-8")) == result


def test_one_format_retry_counts_all_tokens_without_adding_previous_answer_to_prompt(
    corpus: tuple,
) -> None:
    config, rows = corpus
    bad = Completion("EXTERNAL_ASSERTION_WITHOUT_EVIDENCE", "fixture-v1", 12, 3)
    backend = FakeLLM([bad, completion([{"text": "Alpha", "citations": [FIRST]}])])
    result = generate_answer("Alpha?", rows[:1], config, backend)
    assert result["status"] == "ok" and result["backend_calls"] == 2
    assert result["input_tokens"] == 112 and result["output_tokens"] == 23
    assert len(result["format_failures"]) == 1
    assert "EXTERNAL_ASSERTION_WITHOUT_EVIDENCE" not in json.dumps(backend.calls[1])
    assert json.loads(backend.calls[0][1]["content"]) == json.loads(backend.calls[1][1]["content"])
    repeat = generate_answer("Alpha?", rows[:1], config, FakeLLM([]))
    assert repeat["claims"][0]["text"] == "Alpha"
    assert repeat["backend_calls"] == 0 and repeat["cache_hits"] == 2
    assert repeat["input_tokens"] == repeat["output_tokens"] == 0
    assert repeat["attempts"][0]["input_tokens"] == 12
    assert repeat["run_id"] != result["run_id"]


@pytest.mark.parametrize("limit", [1, 200])
def test_invalid_json_failure_is_bounded_persisted_and_does_not_crash(
    corpus: tuple, limit: int
) -> None:
    config, rows = corpus
    config = replace(config, generation=replace(config.generation, max_calls_per_run=limit))
    bad = Completion("broken", "fixture-v1", 5, 2)
    backend = FakeLLM([bad, bad, bad])
    result = generate_answer("Question", rows[:1], config, backend)
    assert result["status"] == "failed" and result["claims"] == []
    assert result["backend_calls"] == min(limit, 2)
    assert len(backend.calls) == min(limit, 2)
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT raw_response FROM answer").fetchone()[0] == "broken"
        assert connection.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 0
        assert (
            json.loads(connection.execute("SELECT notes FROM run").fetchone()[0])["status"]
            == "failed"
        )


def test_length_finish_reason_retries_even_if_partial_response_is_parseable(corpus: tuple) -> None:
    config, rows = corpus
    backend = FakeLLM([completion([], finish_reason="length"), completion([])])
    result = generate_answer("Question", rows[:1], config, backend)
    assert result["status"] == "no_evidence" and result["backend_calls"] == 2


def test_empty_context_never_calls_llm_and_cache_miss_requires_explicit_api(corpus: tuple) -> None:
    config, rows = corpus
    unused = FakeLLM([])
    empty = generate_answer("Question", [], config, unused)
    assert empty["status"] == "no_evidence" and empty["backend_calls"] == 0
    assert empty["input_tokens"] == 0 and not unused.calls
    blocked = generate_answer("Question", rows[:1], config)
    assert blocked["status"] == "failed" and "--allow-api" in blocked["error"]
    assert blocked["backend_calls"] == 0


def test_unknown_usage_and_provider_errors_are_recorded_without_leaking_secrets(
    corpus: tuple, caplog: pytest.LogCaptureFixture
) -> None:
    config, rows = corpus
    caplog.set_level(logging.INFO)
    missing = FakeLLM([Completion('{"claims": []}', "fixture", None, 10)])
    result = generate_answer("Missing usage", rows[:1], config, missing)
    assert result["status"] == "failed" and result["unknown_usage_attempts"] == 1
    secret = "secret-fixture-key-never-log"
    backend = FakeLLM([RuntimeError(secret)])
    failure = generate_answer("API failure", rows[:1], config, backend)
    assert failure["status"] == "failed"
    assert (
        secret not in json.dumps(failure) + caplog.text + Path(failure["report_path"]).read_text()
    )


def test_corrupt_cache_is_preserved_and_does_not_trigger_a_new_call(corpus: tuple) -> None:
    config, rows = corpus
    generate_answer("Question", rows[:1], config, FakeLLM([completion([])]))
    path = next((Path(config.paths.cache_dir) / "llm").glob("*.json"))
    path.write_text('{"corrupted":true}', encoding="utf-8")
    result = generate_answer("Question", rows[:1], config, FakeLLM([]))
    assert result["status"] == "failed" and result["backend_calls"] == 0
    assert path.read_text() == '{"corrupted":true}'


@pytest.mark.parametrize("problem", ["text", "duplicate", "low-quality", "missing"])
def test_context_validation_rejects_stale_unretrieved_or_invalid_chunks(
    corpus: tuple, problem: str
) -> None:
    config, rows = corpus
    provided = [dict(rows[0])]
    if problem == "text":
        provided[0]["text"] = "Injected outside knowledge"
    elif problem == "duplicate":
        provided *= 2
    elif problem == "low-quality":
        provided = [rows[3]]
    else:
        provided[0]["chunk_id"] = UNKNOWN
    with pytest.raises(ValueError):
        generate_answer("Question", provided, config, FakeLLM([]))


def test_run_collision_never_overwrites_history(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows = corpus
    first = generate_answer("Question", rows[:1], config, FakeLLM([completion([])]))
    path = Path(first["report_path"])
    before = path.read_bytes()
    monkeypatch.setattr("rag.generation.pipeline.make_run_id", lambda: first["run_id"])
    with pytest.raises(FileExistsError):
        generate_answer("Question", rows[:1], config, FakeLLM([]))
    assert path.read_bytes() == before
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run").fetchone()[0] == 1


def test_bm25_to_generation_integration_uses_real_fts_and_mock_llm(corpus: tuple) -> None:
    config, _ = corpus
    backend = FakeLLM([completion([{"text": "Alpha evidence", "citations": [FIRST]}])])
    result = answer_question("Alpha", config, "bm25", backend)
    assert result["status"] == "ok" and FIRST in result["context_chunk_ids"]
    assert "HIDDEN_CORPUS_TEXT" not in json.dumps(backend.calls)
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT model_embed, model_rerank FROM run").fetchone() == (
            None,
            None,
        )


@pytest.mark.parametrize("provider", ["deepseek", "openai"])
@pytest.mark.parametrize("key_source", ["environment", "dotenv"])
@pytest.mark.parametrize("thinking", [False, True])
def test_actual_sdk_with_mock_http_transport_records_usage_and_disables_retries(
    corpus: tuple,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    key_source: str,
    thinking: bool,
) -> None:
    import httpx2
    import openai

    config, rows = corpus
    config = replace(
        config, generation=replace(config.generation, provider=provider, thinking=thinking)
    )
    variable = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
    monkeypatch.chdir(tmp_path)
    if key_source == "environment":
        monkeypatch.setenv(variable, "test-secret-key")
    else:
        monkeypatch.delenv(variable, raising=False)
        (tmp_path / ".env").write_text(f'{variable}="test-secret-key"\n', encoding="utf-8")
    original = openai.OpenAI
    observed = []
    options = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        observed.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-secret-key"
        return httpx2.Response(
            200,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture-server-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"claims": []}'},
                    }
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 25, "total_tokens": 175},
            },
        )

    def factory(**kwargs: object) -> object:
        options.append(kwargs)
        return original(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))

    monkeypatch.setattr(openai, "OpenAI", factory)
    result = generate_answer("SDK transport test", rows[:1], config, OpenAIBackend())
    assert result["status"] == "no_evidence"
    assert result["input_tokens"] == 150 and result["output_tokens"] == 25
    assert result["attempts"][0]["model"] == "fixture-server-model"
    assert observed[0]["response_format"] == {"type": "json_object"}
    parameter = "max_tokens" if provider == "deepseek" else "max_completion_tokens"
    assert observed[0][parameter] == config.generation.max_output_tokens
    if provider == "deepseek":
        assert observed[0]["thinking"] == {"type": "enabled" if thinking else "disabled"}
    else:
        assert "thinking" not in observed[0]
    assert options[0]["max_retries"] == 0 and options[0]["timeout"] == 60.0
    assert "test-secret-key" not in json.dumps(result)


def test_thinking_mode_separates_response_caches(corpus: tuple) -> None:
    config, rows = corpus
    backend = FakeLLM([completion([]), completion([])])
    first = generate_answer("Thinking cache", rows[:1], config, backend)
    thinking = replace(config, generation=replace(config.generation, thinking=True))
    second = generate_answer("Thinking cache", rows[:1], thinking, backend)
    repeat = generate_answer("Thinking cache", rows[:1], thinking, backend)
    assert first["backend_calls"] == second["backend_calls"] == 1
    assert repeat["backend_calls"] == 0 and repeat["cache_hits"] == 1


@pytest.mark.parametrize(
    "assignment",
    [
        "DEEPSEEK_API_KEY=fixture-key",
        "export DEEPSEEK_API_KEY = 'fixture-key' # local key",
        'DEEPSEEK_API_KEY="fixture-key"',
        "DEEPSEEK_API_KEY=fixture-key # local key",
    ],
)
def test_dotenv_reads_only_provider_key_without_changing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, assignment: str
) -> None:
    import os

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text(f"# local settings\nUNRELATED_KEY=ignore\n{assignment}\n", encoding="utf-8-sig")
    before = dict(os.environ)
    assert _api_key("DEEPSEEK_API_KEY") == "fixture-key"
    assert dict(os.environ) == before


@pytest.mark.parametrize("environment_key", ["environment-fixture", "", "   "])
def test_environment_key_takes_precedence_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment_key: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", environment_key)
    (tmp_path / ".env").write_bytes(b"\xff")
    if environment_key.strip():
        assert _api_key("DEEPSEEK_API_KEY") == environment_key
    else:
        with pytest.raises(LLMError, match="Missing DEEPSEEK_API_KEY"):
            _api_key("DEEPSEEK_API_KEY")


@pytest.mark.parametrize(
    "contents",
    [
        None,
        b"DEEPSEEK_API_KEY=\n",
        b"OPENAI_API_KEY=other-secret\n",
        b'DEEPSEEK_API_KEY="secret-never-print\n',
        b"DEEPSEEK_API_KEY='secret-never-print' trailing\n",
        b"DEEPSEEK_API_KEY=\xff\n",
    ],
)
def test_dotenv_errors_never_expose_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: bytes | None
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    if contents is not None:
        (tmp_path / ".env").write_bytes(contents)
    with pytest.raises(LLMError) as error:
        _api_key("DEEPSEEK_API_KEY")
    assert "secret" not in str(error.value)


def test_sdk_transport_error_makes_one_request_without_exposing_response_body(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx2
    import openai

    config, rows = corpus
    monkeypatch.setenv("DEEPSEEK_API_KEY", "transport-secret-fixture")
    original = openai.OpenAI
    requests = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(500, json={"error": {"message": "transport-secret-fixture"}})

    def factory(**kwargs: object) -> object:
        return original(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))

    monkeypatch.setattr(openai, "OpenAI", factory)
    result = generate_answer("HTTP failure", rows[:1], config, OpenAIBackend())
    assert result["status"] == "failed" and len(requests) == 1
    assert result["unknown_usage_attempts"] == 1
    assert "transport-secret-fixture" not in json.dumps(result)


def test_sqlite_failure_is_reported_as_failure(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows = corpus

    def fail(*args: object) -> None:
        raise sqlite3.OperationalError("fixture storage failure")

    monkeypatch.setattr("rag.generation.pipeline.finish_run", fail)
    with pytest.raises(sqlite3.OperationalError):
        generate_answer("Storage failure", rows[:1], config, FakeLLM([completion([])]))
    path = next((Path(config.paths.index_dir) / "reports").glob("generation-*.json"))
    report = json.loads(path.read_text())
    assert (
        report["status"] == "failed" and report["error"] == "Persistence failed (OperationalError)"
    )


def test_conflicting_existing_schema_is_not_replaced(corpus: tuple) -> None:
    config, rows = corpus
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("CREATE TABLE run (run_id TEXT, preserve_me TEXT)")
        connection.execute("INSERT INTO run VALUES ('old', 'history')")
    with pytest.raises(ValueError, match="differs from ARCHITECTURE"):
        generate_answer("Schema conflict", rows[:1], config, FakeLLM([]))
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT * FROM run").fetchall() == [("old", "history")]
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('answer','claim')"
            ).fetchall()
            == []
        )


@pytest.mark.parametrize("invalid", [float("nan"), True, -1, "100"])
def test_invalid_usage_is_reported_as_unknown_without_breaking_report_json(
    corpus: tuple, invalid: object
) -> None:
    config, rows = corpus
    backend = FakeLLM([Completion('{"claims": []}', "fixture", invalid, 20)])
    result = generate_answer("Invalid usage", rows[:1], config, backend)
    assert result["status"] == "failed" and result["unknown_usage_attempts"] == 1
    assert result["attempts"][0]["input_tokens"] is None
    assert json.loads(Path(result["report_path"]).read_text()) == result


def test_invalid_unicode_claim_gets_a_bounded_format_retry(corpus: tuple) -> None:
    config, rows = corpus
    backend = FakeLLM(
        [
            Completion('{"claims":[{"text":"\\ud800","citations":[]}]}', "fixture", 10, 5),
            completion([]),
        ]
    )
    result = generate_answer("Bad Unicode", rows[:1], config, backend)
    assert result["status"] == "no_evidence" and len(result["format_failures"]) == 1


def test_render_escapes_untrusted_markdown_and_reuses_reference_numbers(corpus: tuple) -> None:
    config, rows = corpus
    context, _ = load_context(rows[:1], config)
    claim = {
        "text": "<script>x</script> [click](https://example.invalid)",
        "citations": [FIRST],
        "unsupported": False,
    }
    result = render_answer([claim, claim], context)
    assert len(result["references"]) == 1
    assert "<script>" not in result["markdown"]
    assert "[click](https://example.invalid)" not in result["markdown"]


@pytest.mark.parametrize("failed", [False, True])
def test_cli_dispatch_and_failure_exit_code(monkeypatch: pytest.MonkeyPatch, failed: bool) -> None:
    calls = []

    def run(question: str, config: Config, mode: str, **kwargs: object) -> dict:
        calls.append((question, mode, kwargs))
        return {"status": "failed" if failed else "ok", "markdown": "fixture"}

    monkeypatch.setattr(sys, "argv", ["rag.generation", "--question", "Question", "--mode", "bm25"])
    monkeypatch.setattr("rag.generation.__main__.answer_question", run)
    assert main() == int(failed)
    assert calls == [("Question", "bm25", {"allow_api": False})]
