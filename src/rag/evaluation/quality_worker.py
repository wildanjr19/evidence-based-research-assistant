"""Reusable isolated Ragas workers; embedding stays in the main Python environment."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from queue import Queue
from threading import Event, Lock, RLock

from rag.config import load_config

QUALITY_WORKERS = 2
WORKER_TIMEOUT = 600


class LocalEmbeddings:
    def __init__(self) -> None:
        self.lock = Lock()
        self.identity: str | None = None
        self.model = None

    def embed(self, config_file: Path, texts: list[str]) -> list[list[float]]:
        from rag.indexing.embedding import SentenceEmbedder, embed_chunks

        config = load_config(config_file)
        if (
            not isinstance(texts, list)
            or not 1 <= len(texts) <= 3
            or any(not isinstance(text, str) or not text.strip() for text in texts)
        ):
            raise ValueError("Expected one to three nonempty questions")
        identity = json.dumps(
            [asdict(config.embedding), config.paths.cache_dir, config.verification.seed],
            sort_keys=True,
        )
        with self.lock:
            if self.identity != identity:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                self.model = SentenceEmbedder(config)
                self.identity = identity
            vectors, _ = embed_chunks(
                [dict(chunk_id=str(i), text=text) for i, text in enumerate(texts)],
                config,
                self.model,
            )
            return vectors


class ScoreWorker:
    def __init__(self, embeddings: LocalEmbeddings) -> None:
        self.embeddings = embeddings
        self.process: subprocess.Popen | None = None
        self.process_lock = RLock()

    def close(self) -> None:
        with self.process_lock:
            if self.process is None:
                return
            process, self.process = self.process, None
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def exchange(self, directory: Path, allow_api: bool, cancelled: Event) -> None:
        from rag.evaluation.answer_quality import ROOT, _python

        with self.process_lock:
            if cancelled.is_set():
                raise RuntimeError("Quality request timed out before startup")
            if self.process is None or self.process.poll() is not None:
                self.close()
                self.process = subprocess.Popen(
                    [
                        str(_python(ROOT / "data/skripsi/s5-ragas/.venv")),
                        "-m",
                        "rag.evaluation.answer_quality",
                        "worker",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    cwd=ROOT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            process = self.process

        def send(message: dict) -> None:
            process.stdin.write(json.dumps(message, allow_nan=False) + "\n")
            process.stdin.flush()

        send(dict(directory=str(directory.resolve()), allow_api=allow_api))
        while True:
            if cancelled.is_set():
                raise RuntimeError("Quality request timed out")
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Quality worker stopped; inspect receipts before retrying")
            message = json.loads(line)
            if message.get("type") == "done":
                return
            if message.get("type") != "embed":
                raise RuntimeError("Quality worker failed; inspect receipts before retrying")
            try:
                vectors = self.embeddings.embed(directory / "config.yaml", message["texts"])
                send(dict(vectors=vectors))
            except (ValueError, RuntimeError, OSError, KeyError):
                send(dict(error="Local embedding failed"))


class QualityPool:
    def __init__(self) -> None:
        embeddings = LocalEmbeddings()
        self.workers = [ScoreWorker(embeddings) for _ in range(QUALITY_WORKERS)]
        self.available: Queue = Queue()
        for worker in self.workers:
            self.available.put(worker)
        self.executor = ThreadPoolExecutor(max_workers=QUALITY_WORKERS)

    def score(self, directory: Path, allow_api: bool) -> None:
        worker = self.available.get()
        recycle = True
        cancelled = Event()
        try:
            future = self.executor.submit(worker.exchange, directory, allow_api, cancelled)
            try:
                future.result(timeout=WORKER_TIMEOUT)
            except TimeoutError:
                cancelled.set()
                future.cancel()
                worker.close()
                # A timed-out embedding may still finish locally; do not reuse its lane yet.
                recycle = False
                future.add_done_callback(lambda _: self.available.put(worker))
                raise RuntimeError(
                    "Evaluasi timeout; periksa artefak sebelum mencoba kembali."
                ) from None
            except Exception:
                worker.close()
                raise
        finally:
            if recycle:
                self.available.put(worker)

    def close(self) -> None:
        for worker in self.workers:
            with suppress(OSError):
                worker.close()
        self.executor.shutdown(wait=True)
