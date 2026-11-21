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
def test_parent_uses_isolated_worker_and_binds_result(sample, tmp_path, monkeypatch, allow_api):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    calls = []

    def worker(command, **kwargs):
        calls.append(command)
        directory = Path(command[command.index("--directory") + 1])
        quality._write(
            directory / "result.json",
            dict(
                answer_id=answer["answer_id"],
                input_sha256=quality._file_hash(directory / "input.json"),
                status="evaluated",
                scores=dict(faithfulness=1.0, response_relevancy=0.8),
            ),
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(quality.subprocess, "run", worker)
    report = quality.evaluate_answer_quality(config, answer, allow_api=allow_api)
    assert report["status"] == "evaluated" and len(calls) == 1
    assert calls[0][0] == str(python)
    assert ("--allow-api" in calls[0]) is allow_api


def test_displayed_answer_tampering_never_starts_worker(sample, tmp_path, monkeypatch):
    config, _, answer = sample
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    python = quality._python(tmp_path / "data/skripsi/s5-ragas/.venv")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    answer["claims"][0]["text"] = "Changed display"
    with pytest.raises(ValueError, match="Displayed answer"):
        quality.evaluate_answer_quality(config, answer)


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
