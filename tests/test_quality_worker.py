import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event

import pytest

from rag.config import load_config
from rag.evaluation import quality_worker as workers


@pytest.fixture
def processes(monkeypatch):
    original = subprocess.Popen
    launched = []
    script = """
import json, sys, time
for line in sys.stdin:
    request = json.loads(line)
    if request['directory'].endswith('fail'):
        sys.exit(1)
    if request['directory'].endswith('hang'):
        time.sleep(30)
    print(json.dumps(dict(type='embed', texts=['Question?'])), flush=True)
    answer = json.loads(sys.stdin.readline())
    print(json.dumps(dict(type='done' if 'vectors' in answer else 'error')), flush=True)
"""

    def launch(command, **kwargs):
        assert command[-1] == "worker" and "s5-ragas" in command[0]
        process = original([sys.executable, "-u", "-c", script], **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(workers.subprocess, "Popen", launch)
    monkeypatch.setattr(workers.LocalEmbeddings, "embed", lambda *args: [[1.0, 0.0]])
    yield launched
    for process in launched:
        if process.poll() is None:
            process.kill()
        process.wait()


def test_two_isolated_workers_reused_and_closed(processes, tmp_path, monkeypatch):
    pool = workers.QualityPool()
    barrier = Barrier(2)

    def embed(*args):
        barrier.wait(timeout=5)
        return [[1.0, 0.0]]

    monkeypatch.setattr(workers.LocalEmbeddings, "embed", embed)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for _ in range(2):
                futures = [executor.submit(pool.score, tmp_path, False) for _ in range(2)]
                for future in futures:
                    future.result(timeout=10)
        assert len(processes) == 2
    finally:
        pool.close()
    assert all(process.poll() is not None for process in processes)


@pytest.mark.parametrize("name", ["fail", "hang"])
def test_worker_failure_is_not_retried_and_later_request_can_start_fresh(
    processes, tmp_path, monkeypatch, name
):
    monkeypatch.setattr(workers, "WORKER_TIMEOUT", 0.5)
    pool = workers.QualityPool()
    try:
        with pytest.raises(RuntimeError):
            pool.score(tmp_path / name, False)
        assert len(processes) == 1
        assert processes[0].poll() is not None
        pool.score(tmp_path / "next", False)
        assert len(processes) == 2
    finally:
        pool.close()


def test_cancelled_request_never_starts_a_process(processes, tmp_path):
    cancelled = Event()
    cancelled.set()
    worker = workers.ScoreWorker(workers.LocalEmbeddings())
    with pytest.raises(RuntimeError, match="before startup"):
        worker.exchange(tmp_path, True, cancelled)
    assert processes == []


def test_timeout_does_not_reuse_lane_while_local_embedding_is_still_running(
    processes, tmp_path, monkeypatch
):
    monkeypatch.setattr(workers, "WORKER_TIMEOUT", 0.5)
    entered, release = Event(), Event()

    def embed(*args):
        entered.set()
        assert release.wait(timeout=5)
        return [[1.0, 0.0]]

    monkeypatch.setattr(workers.LocalEmbeddings, "embed", embed)
    pool = workers.QualityPool()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pool.score, tmp_path, False)
            try:
                assert entered.wait(timeout=3)
                with pytest.raises(RuntimeError, match="timeout"):
                    future.result(timeout=3)
                assert pool.available.qsize() == 1
                assert len(processes) == 1 and processes[0].poll() is not None
            finally:
                release.set()
            first = pool.available.get(timeout=3)
            second = pool.available.get(timeout=3)
            pool.available.put(first)
            pool.available.put(second)
    finally:
        release.set()
        pool.close()


def test_embedding_model_reused_but_config_change_loads_matching_model(tmp_path, monkeypatch):
    from rag.indexing import embedding

    config = load_config()
    config = replace(config, paths=replace(config.paths, cache_dir=str(tmp_path)))
    selected = [config]
    monkeypatch.setattr(workers, "load_config", lambda _: selected[0])
    loaded = []

    class Model:
        dimension = 2
        max_tokens = 512

        def __init__(self, config):
            loaded.append(config.embedding.revision)

        def token_counts(self, texts):
            return [2 for _ in texts]

        def encode(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(embedding, "SentenceEmbedder", Model)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    bridge = workers.LocalEmbeddings()
    for text in ["First?", "Second?"]:
        assert bridge.embed(tmp_path, [text]) == [[1.0, 0.0]]
    assert len(loaded) == 1
    selected[0] = replace(config, embedding=replace(config.embedding, revision="other"))
    bridge.embed(tmp_path, ["Third?"])
    assert loaded == [config.embedding.revision, "other"]


def test_worker_protocol_keeps_stdout_clean_and_binds_embedding_reply(tmp_path, monkeypatch):
    import io

    from rag.evaluation import answer_quality as quality

    request = dict(directory=str(tmp_path), allow_api=False)
    wire = io.StringIO()
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps(request) + "\n" + json.dumps(dict(vectors=[[1.0, 0.0]])) + "\n"),
    )
    monkeypatch.setattr(sys, "stdout", wire)

    def score(directory, *, allow_api, embed_texts):
        assert directory == tmp_path and allow_api is False
        print("Library output must not corrupt the protocol")
        assert embed_texts(["Question?"]) == [[1.0, 0.0]]

    monkeypatch.setattr(quality, "score_quality", score)
    quality._worker()
    messages = [json.loads(line) for line in wire.getvalue().splitlines()]
    assert messages == [dict(type="embed", texts=["Question?"]), dict(type="done")]
