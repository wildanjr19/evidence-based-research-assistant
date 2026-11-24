import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.evaluation import answer_quality as quality
from rag.generation.pipeline import generate_answer
from rag.ui.service import load_answer
from test_generation import FIRST, SECOND, FakeLLM, completion
from test_generation import corpus as corpus


@pytest.fixture
def sample(corpus, tmp_path, monkeypatch):
    config, rows = corpus
    monkeypatch.chdir(tmp_path)
    config = replace(config, paths=replace(config.paths, cache_dir=str(tmp_path / "data/cache")))
    generation = generate_answer(
        "What does Alpha support?",
        rows[:2],
        config,
        FakeLLM([completion([dict(text="Alpha supports the result.", citations=[FIRST])])]),
    )
    return config, generation, load_answer(config, generation["answer_id"])


def test_prepare_uses_all_generation_context_and_keeps_source_readonly(sample):
    config, generation, _ = sample
    before = Path(config.paths.db_path).read_bytes()
    directory = quality.prepare_quality(config, generation["answer_id"])
    payload, _ = quality._inputs(directory)
    assert [c["chunk_id"] for c in payload["context"]] == [FIRST, SECOND]
    assert payload["response"] == "Alpha supports the result."
    assert payload["context_sha256"] == generation["context_sha256"]
    assert Path(config.paths.db_path).read_bytes() == before


def test_claim_evaluation_uses_only_selected_response_and_all_context(sample):
    config, _, _ = sample
    chunks, _ = quality._corpus(config)
    generation = generate_answer(
        "Compare Alpha and Beta",
        [chunks[FIRST], chunks[SECOND]],
        config,
        FakeLLM(
            [
                completion(
                    [
                        dict(text="Alpha result.", citations=[FIRST]),
                        dict(text="Beta result.", citations=[SECOND]),
                    ]
                )
            ]
        ),
    )
    before = Path(config.paths.db_path).read_bytes()
    for claim in generation["claims"]:
        directory = quality.prepare_quality(
            config, generation["answer_id"], claim_id=claim["claim_id"]
        )
        payload, _ = quality._inputs(directory)
        assert payload["claim_id"] == claim["claim_id"]
        assert payload["response"] == claim["text"]
        assert len(payload["context"]) == len(generation["context_chunk_ids"])
        assert payload["context_sha256"] == generation["context_sha256"]
    assert Path(config.paths.db_path).read_bytes() == before


def test_foreign_claim_is_rejected_before_artifacts_are_created(sample):
    config, generation, _ = sample
    with pytest.raises(ValueError, match="does not belong"):
        quality.prepare_quality(config, generation["answer_id"], claim_id="foreign")
    assert not list(Path(config.paths.cache_dir).rglob("input.json"))


def test_claim_scope_cannot_be_reassigned_even_with_refrozen_input(sample):
    config, generation, _ = sample
    directory = quality.prepare_quality(
        config, generation["answer_id"], claim_id=generation["claims"][0]["claim_id"]
    )
    payload = json.loads((directory / "input.json").read_text())
    payload["response"] = "A different card"
    (directory / "input.json").write_text(json.dumps(payload))
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["input_sha256"] = quality._file_hash(directory / "input.json")
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="scope differs"):
        quality._inputs(directory)


@pytest.mark.parametrize("target", ["input.json", "config.yaml"])
def test_changed_prepared_input_is_rejected(sample, target):
    config, generation, _ = sample
    directory = quality.prepare_quality(config, generation["answer_id"])
    path = directory / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="frozen manifest"):
        quality._inputs(directory)


def test_changed_source_report_is_rejected(sample):
    config, generation, _ = sample
    directory = quality.prepare_quality(config, generation["answer_id"])
    path = Path(generation["report_path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source changed"):
        quality._inputs(directory)


def test_no_claims_has_no_quality_score(sample):
    config, _, _ = sample
    answer = generate_answer("No evidence", [], config, FakeLLM([]))
    with pytest.raises(ValueError, match="nonempty"):
        quality.prepare_quality(config, answer["answer_id"])


@pytest.mark.parametrize("allow_api", [False, True])
@pytest.mark.parametrize("per_claim", [False, True])
def test_parent_uses_isolated_worker_and_binds_result(
    sample, tmp_path, monkeypatch, allow_api, per_claim
):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    calls = []
    claim_id = answer["claims"][0]["claim_id"] if per_claim else None

    def worker(command, **kwargs):
        calls.append(command)
        directory = Path(command[command.index("--directory") + 1])
        quality._write(
            directory / "result.json",
            dict(
                answer_id=answer["answer_id"],
                claim_id=claim_id,
                input_sha256=quality._file_hash(directory / "input.json"),
                status="evaluated",
                scores=dict(faithfulness=1.0, response_relevancy=0.8),
            ),
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quality.subprocess, "run", worker)
    report = quality.evaluate_answer_quality(config, answer, allow_api=allow_api, claim_id=claim_id)
    assert report["status"] == "evaluated" and len(calls) == 1
    assert calls[0][0] == str(python)
    assert ("--allow-api" in calls[0]) is allow_api
    payload = json.loads((Path(report["directory"]) / "input.json").read_text())
    assert payload["claim_id"] == claim_id


def test_displayed_answer_tampering_never_starts_worker(sample, tmp_path, monkeypatch):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    answer["claims"][0]["text"] = "Changed display"
    with pytest.raises(ValueError, match="Displayed answer"):
        quality.evaluate_answer_quality(config, answer)


def test_worker_result_for_another_card_is_rejected(sample, tmp_path, monkeypatch):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")

    def worker(command, **kwargs):
        directory = Path(command[command.index("--directory") + 1])
        quality._write(
            directory / "result.json",
            dict(
                answer_id=answer["answer_id"],
                claim_id="another-card",
                input_sha256=quality._file_hash(directory / "input.json"),
            ),
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quality.subprocess, "run", worker)
    with pytest.raises(ValueError, match="does not match"):
        quality.evaluate_answer_quality(config, answer, claim_id=answer["claims"][0]["claim_id"])


def test_embedding_bridge_has_no_paid_api_flag(tmp_path, monkeypatch):
    calls = []

    def embed(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="[[1.0, 0.0]]")

    monkeypatch.setattr(quality.subprocess, "run", embed)
    assert quality._local_embeddings(tmp_path / "config.yaml", ["Question?"]) == [[1.0, 0.0]]
    command, kwargs = calls[0]
    assert "embed" in command and "--allow-api" not in command
    assert json.loads(kwargs["input"]) == ["Question?"]


def test_evaluation_timeout_does_not_modify_answer(sample, tmp_path, monkeypatch):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    before = json.dumps(answer, sort_keys=True)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 600)

    monkeypatch.setattr(quality.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timeout"):
        quality.evaluate_answer_quality(config, answer)
    assert json.dumps(answer, sort_keys=True) == before


@pytest.fixture
def cached_evaluator(sample, tmp_path, monkeypatch):
    config, generation, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    calls = []

    def runner(directory, allow_api):
        item, _ = quality._inputs(directory)
        calls.append((directory, allow_api))
        quality._write(
            directory / "result.json",
            dict(
                answer_id=item["answer_id"],
                claim_id=item.get("claim_id"),
                input_sha256=quality._file_hash(directory / "input.json"),
                context_sha256=item["context_sha256"],
                status="evaluated",
                errors={},
                scores=dict(faithfulness=1.0, response_relevancy=-0.1),
                usage=dict(
                    backend_calls=3,
                    input_tokens=200,
                    output_tokens=30,
                    cache_hits=2,
                    unknown_usage_attempts=0,
                ),
                attempts=[dict(cache_hit=False)],
            ),
        )

    return config, generation, answer, runner, calls


def test_full_score_cache_skips_worker_and_does_not_rebill_historical_usage(cached_evaluator):
    config, _, answer, runner, calls = cached_evaluator
    claim_id = answer["claims"][0]["claim_id"]
    first = quality.evaluate_answer_quality(config, answer, claim_id=claim_id, runner=runner)
    repeated = quality.evaluate_answer_quality(config, answer, claim_id=claim_id, runner=runner)
    assert len(calls) == 1 and calls[0][1] is False
    assert repeated["score_cache_hit"] and repeated["scores"] == first["scores"]
    assert repeated["cached_result"] == str((Path(first["directory"]) / "result.json").resolve())
    assert repeated["directory"] != first["directory"]
    assert repeated["attempts"] == []
    assert all(value == 0 for value in repeated["usage"].values())


def test_score_cache_can_rebind_identical_content_to_new_claim_ids(cached_evaluator):
    config, generation, answer, runner, calls = cached_evaluator
    first = quality.evaluate_answer_quality(
        config,
        answer,
        claim_id=answer["claims"][0]["claim_id"],
        runner=runner,
    )
    chunks, _ = quality._corpus(config)
    regenerated = generate_answer(
        answer["question"],
        [chunks[FIRST], chunks[SECOND]],
        config,
        FakeLLM([completion([dict(text=answer["claims"][0]["text"], citations=[FIRST])])]),
    )
    assert regenerated["answer_id"] != generation["answer_id"]
    other = load_answer(config, regenerated["answer_id"])
    repeated = quality.evaluate_answer_quality(
        config,
        other,
        claim_id=other["claims"][0]["claim_id"],
        runner=runner,
    )
    assert len(calls) == 1
    assert repeated["answer_id"] == other["answer_id"]
    assert repeated["claim_id"] == other["claims"][0]["claim_id"]
    assert repeated["scores"] == first["scores"]


@pytest.mark.parametrize("field", ["question", "response", "context_sha256", "claim_id"])
def test_score_cache_key_binds_evaluation_scope(sample, field):
    config, generation, _ = sample
    directory = quality.prepare_quality(config, generation["answer_id"])
    item, selected = quality._inputs(directory)
    original = quality._quality_key(item, selected)
    changed = dict(item, **{field: "different"})
    assert quality._quality_key(changed, selected) != original


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("verification", "judge_model", "gpt-4o"),
        ("verification", "seed", 12),
        ("embedding", "revision", "different-revision"),
    ],
)
def test_score_cache_key_binds_model_and_protocol_config(sample, section, field, value):
    config, generation, _ = sample
    directory = quality.prepare_quality(config, generation["answer_id"])
    item, selected = quality._inputs(directory)
    changed = replace(selected, **{section: replace(getattr(selected, section), **{field: value})})
    assert quality._quality_key(item, changed) != quality._quality_key(item, selected)


def test_corrupt_score_cache_does_not_start_new_api_work(cached_evaluator):
    config, _, answer, runner, calls = cached_evaluator
    first = quality.evaluate_answer_quality(config, answer, runner=runner)
    result = Path(first["directory"]) / "result.json"
    result.write_bytes(result.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Cache skor tidak valid"):
        quality.evaluate_answer_quality(config, answer, runner=runner, allow_api=True)
    assert len(calls) == 1


def test_partial_score_is_not_promoted_to_complete_cache(cached_evaluator):
    config, _, answer, _, calls = cached_evaluator

    def runner(directory, allow_api):
        item, _ = quality._inputs(directory)
        calls.append(directory)
        quality._write(
            directory / "result.json",
            dict(
                answer_id=item["answer_id"],
                claim_id=None,
                input_sha256=quality._file_hash(directory / "input.json"),
                status="partial",
                errors=dict(response_relevancy="RuntimeError"),
                scores=dict(faithfulness=1, response_relevancy=None),
            ),
        )

    quality.evaluate_answer_quality(config, answer, runner=runner)
    assert not list((Path(config.paths.cache_dir) / "answer-quality-cache").glob("*.json"))


def test_duplicate_score_requests_across_sessions_only_start_one_worker(cached_evaluator):
    from concurrent.futures import ThreadPoolExecutor

    config, _, answer, runner, calls = cached_evaluator
    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(
            executor.map(
                lambda _: quality.evaluate_answer_quality(config, answer, runner=runner),
                range(2),
            )
        )
    assert len(calls) == 1
    assert sum(report.get("score_cache_hit", False) for report in reports) == 1
