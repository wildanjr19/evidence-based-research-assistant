"""Reference-free answer evaluation, with Ragas kept in its isolated environment."""

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import closing, redirect_stdout
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from threading import Lock

import yaml

from rag.config import Config, load_config
from rag.evaluation.ragas import _corpus, _file_hash, _validate_answer, _write
from rag.evaluation.retrieval import _code_version
from rag.files import atomic_write
from rag.generation.client import LLMBackend
from rag.generation.store import connect_corpus, load_context
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash

ROOT = Path(__file__).resolve().parents[3]
MAX_CALLS = 5
MAX_OUTPUT_TOKENS = 1024
MAX_PROMPT_BYTES = 65536
CACHE_LOCKS = [Lock() for _ in range(32)]


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _response(generation: dict, claim_id: str | None) -> str:
    if claim_id is None:
        return "\n\n".join(claim["text"] for claim in generation["claims"])
    claims = [claim for claim in generation["claims"] if claim["claim_id"] == claim_id]
    if len(claims) != 1:
        raise ValueError("Selected claim does not belong to the answer")
    return claims[0]["text"]


def prepare_quality(
    config: Config,
    answer_id: str,
    database: str | None = None,
    *,
    claim_id: str | None = None,
) -> Path:
    selected = replace(
        config, paths=replace(config.paths, db_path=database or config.paths.db_path)
    )
    with closing(connect_corpus(selected)) as connection:
        stored = connection.execute(
            "SELECT answer.question, run.notes FROM answer JOIN run USING (run_id) "
            "WHERE answer_id=?",
            (answer_id,),
        ).fetchone()
    if stored is None:
        raise ValueError("Answer is missing from its source database")
    source_report = Path(json.loads(stored[1])["report_path"])
    generation = json.loads(source_report.read_text(encoding="utf-8"))
    if generation["answer_id"] != answer_id:
        raise ValueError("Generation report refers to another answer")
    _validate_answer(selected, generation, stored[0])
    if generation["status"] != "ok" or not generation["claims"]:
        raise ValueError("Quality scores require a completed, nonempty answer")
    response = _response(generation, claim_id)
    chunks, _ = _corpus(selected)
    context, _ = load_context([chunks[key] for key in generation["context_chunk_ids"]], selected)
    if (
        text_hash(json.dumps(context, sort_keys=True, ensure_ascii=False))
        != generation["context_sha256"]
    ):
        raise ValueError("Generation context differs from canonical source")
    if any(
        key not in generation["context_chunk_ids"]
        for claim in generation["claims"]
        for key in claim["citations"]
    ):
        raise ValueError("Answer cites outside its generation context")
    directory = Path(config.paths.cache_dir) / "answer-quality" / make_run_id().replace(":", "-")
    if not directory.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Answer evidence must stay under data/")
    directory.mkdir(parents=True, exist_ok=False)
    selected = replace(
        selected,
        generation=replace(selected.generation, max_output_tokens=MAX_OUTPUT_TOKENS),
        verification=replace(selected.verification, judge_max_calls_per_run=MAX_CALLS),
    )
    with (directory / "config.yaml").open("x", encoding="utf-8") as stream:
        yaml.safe_dump(asdict(selected), stream, sort_keys=False)
    payload = dict(
        answer_id=answer_id,
        claim_id=claim_id,
        question=stored[0],
        response=response,
        generation=generation,
        context=context,
        context_sha256=generation["context_sha256"],
        source_report=str(source_report.resolve()),
        source_report_sha256=_file_hash(source_report),
        source_db_sha256=_file_hash(Path(selected.paths.db_path)),
    )
    _write(directory / "input.json", payload)
    _write(
        directory / "manifest.json",
        dict(
            input_sha256=_file_hash(directory / "input.json"),
            config_sha256=_file_hash(directory / "config.yaml"),
            seed=selected.verification.seed,
            max_calls=MAX_CALLS,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_prompt_bytes=MAX_PROMPT_BYTES,
            metrics=["faithfulness", "response_relevancy"],
        ),
    )
    return directory


def _inputs(directory: Path) -> tuple[dict, Config]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for filename, key in (("input.json", "input_sha256"), ("config.yaml", "config_sha256")):
        if _file_hash(directory / filename) != manifest[key]:
            raise ValueError("Quality input differs from frozen manifest")
    item = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    config = load_config(directory / "config.yaml")
    if (
        _file_hash(Path(config.paths.db_path)) != item["source_db_sha256"]
        or _file_hash(Path(item["source_report"])) != item["source_report_sha256"]
    ):
        raise ValueError("Quality source changed after preparation")
    _validate_answer(config, item["generation"], item["question"])
    if (
        item["answer_id"] != item["generation"]["answer_id"]
        or item["response"] != _response(item["generation"], item.get("claim_id"))
        or item["context_sha256"] != item["generation"]["context_sha256"]
    ):
        raise ValueError("Evaluation scope differs from persisted generation")
    context, _ = load_context(item["context"], config)
    if (
        context != item["context"]
        or text_hash(json.dumps(context, sort_keys=True, ensure_ascii=False))
        != item["context_sha256"]
    ):
        raise ValueError("Quality context changed")
    return item, config


def _local_embeddings(config_file: Path, texts: list[str]) -> list[list[float]]:
    result = subprocess.run(
        [
            str(_python(ROOT / ".venv")),
            "-m",
            "rag.evaluation.answer_quality",
            "embed",
            "--config",
            str(config_file.resolve()),
        ],
        input=json.dumps(texts),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=ROOT,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError("Local embedding process failed")
    vectors = json.loads(result.stdout)
    if len(vectors) != len(texts):
        raise ValueError("Embedding count differs from question count")
    return vectors


def score_quality(
    directory: Path,
    *,
    allow_api: bool = False,
    backend: LLMBackend | None = None,
    embed_texts: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict:
    started = time.perf_counter()
    item, config = _inputs(directory)
    report = dict(
        answer_id=item["answer_id"],
        claim_id=item.get("claim_id"),
        input_sha256=_file_hash(directory / "input.json"),
        context_sha256=item["context_sha256"],
        status="failed",
        scores=dict(faithfulness=None, response_relevancy=None),
        errors={},
        traces={},
        allow_api=allow_api,
        seed=config.verification.seed,
        human_accuracy=None,
        code_version=_code_version(),
        protocol="claim-quality-v1" if item.get("claim_id") else "answer-quality-v1",
        embedding=asdict(config.embedding),
        response_relevancy_strictness=3,
        interpretation="AI estimates; all retrieved context; not citation accuracy or human truth",
        timings=dict(validation_seconds=time.perf_counter() - started),
    )
    judge = None
    try:
        from rag.evaluation.ragas_adapter import create_metrics, metric_value
        from rag.verification.judge import Judge

        judge = Judge(config, backend, allow_api)
        report["judge"] = asdict(judge.config.verification)
        report["judge_backend"] = judge.client.backend_name
        report["ragas_version"] = version("ragas")
        metrics, traces = create_metrics(
            judge.client,
            MAX_PROMPT_BYTES,
            embed_texts=embed_texts
            or (lambda texts: _local_embeddings(directory / "config.yaml", texts)),
        )
        requests = dict(
            faithfulness=dict(
                user_input=item["question"],
                response=item["response"],
                retrieved_contexts=[chunk["text"] for chunk in item["context"]],
            ),
            response_relevancy=dict(user_input=item["question"], response=item["response"]),
        )
        for name, arguments in requests.items():
            metric_started = time.perf_counter()
            start = len(traces)
            try:
                report["scores"][name] = metric_value(
                    metrics[name].score(**arguments),
                    minimum=-1.0 if name == "response_relevancy" else 0.0,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                report["errors"][name] = type(exc).__name__
            report["traces"][name] = traces[start:]
            report["timings"][name + "_seconds"] = time.perf_counter() - metric_started
        known = sum(value is not None for value in report["scores"].values())
        report["status"] = "evaluated" if known == 2 else "partial" if known else "failed"
    except (ValueError, RuntimeError, OSError, ImportError) as exc:
        report["errors"]["evaluator"] = type(exc).__name__
    attempts = judge.client.attempts if judge else []
    report["attempts"] = attempts
    report["usage"] = dict(
        backend_calls=judge.client.calls if judge else 0,
        cache_hits=sum(a["cache_hit"] for a in attempts),
        input_tokens=sum(a.get("billed_input_tokens") or 0 for a in attempts),
        output_tokens=sum(a.get("billed_output_tokens") or 0 for a in attempts),
        unknown_usage_attempts=sum(
            not a["cache_hit"]
            and (a.get("billed_input_tokens") is None or a.get("billed_output_tokens") is None)
            for a in attempts
        ),
    )
    report["timings"]["total_seconds"] = time.perf_counter() - started
    _write(directory / "result.json", report)
    return report


def _quality_key(item: dict, config: Config) -> str:
    from rag.verification.judge import Judge

    judge = Judge(config, allow_api=False)
    code = Path(__file__).resolve().parent
    identity = dict(
        question=item["question"],
        response=item["response"],
        context_sha256=item["context_sha256"],
        protocol="claim-quality-v1" if item.get("claim_id") else "answer-quality-v1",
        generation=asdict(judge.client.config.generation),
        verification=asdict(judge.config.verification),
        embedding=asdict(config.embedding),
        limits=[MAX_CALLS, MAX_OUTPUT_TOKENS, MAX_PROMPT_BYTES, 3],
        implementation={
            name: _file_hash(code / name)
            for name in (
                "answer_quality.py",
                "quality_worker.py",
                "ragas_adapter.py",
                "../verification/judge.py",
                "../generation/client.py",
                "../indexing/embedding.py",
            )
        },
        ragas_lock=_file_hash(code.parents[2] / "eval/ragas-requirements.lock"),
    )
    return text_hash(json.dumps(identity, sort_keys=True, ensure_ascii=False))


def _cached_score(
    directory: Path,
    config: Config,
    item: dict,
    runner: Callable[[Path, bool], None],
    allow_api: bool,
) -> None:
    key = _quality_key(item, config)
    cache = Path(config.paths.cache_dir) / "answer-quality-cache" / (key + ".json")
    with CACHE_LOCKS[int(key[:8], 16) % len(CACHE_LOCKS)]:
        if cache.is_file():
            try:
                pointer = json.loads(cache.read_text(encoding="utf-8"))
                source = Path(pointer["result"])
                if not source.resolve().is_relative_to(Path(config.paths.cache_dir).resolve()):
                    raise ValueError("Quality cache path differs")
                previous = json.loads(source.read_text(encoding="utf-8"))
                if pointer["key"] != key or _file_hash(source) != pointer["sha256"]:
                    raise ValueError("Quality cache hash differs")
                if previous["status"] != "evaluated" or previous.get("errors"):
                    raise ValueError("Quality cache is incomplete")
                from types import SimpleNamespace

                from rag.evaluation.ragas_adapter import metric_value

                for name, minimum in (("faithfulness", 0.0), ("response_relevancy", -1.0)):
                    metric_value(SimpleNamespace(value=previous["scores"][name]), minimum=minimum)
            except (OSError, ValueError, TypeError, KeyError):
                raise ValueError(
                    "Cache skor tidak valid; periksa artefak sebelum evaluasi."
                ) from None
            previous.update(
                answer_id=item["answer_id"],
                claim_id=item.get("claim_id"),
                input_sha256=_file_hash(directory / "input.json"),
                allow_api=allow_api,
                score_cache_hit=True,
                cached_result=str(source),
                attempts=[],
                usage=dict(
                    backend_calls=0,
                    cache_hits=0,
                    input_tokens=0,
                    output_tokens=0,
                    unknown_usage_attempts=0,
                ),
                timings={},
            )
            _write(directory / "result.json", previous)
            return
        runner(directory, allow_api)
        result = directory / "result.json"
        report = json.loads(result.read_text(encoding="utf-8"))
        if (
            report["answer_id"] != item["answer_id"]
            or report.get("claim_id") != item.get("claim_id")
            or report["input_sha256"] != _file_hash(directory / "input.json")
        ):
            raise ValueError("Evaluation result does not match the selected answer")
        if report["status"] == "evaluated" and not report.get("errors"):
            atomic_write(
                cache,
                json.dumps(
                    dict(key=key, result=str(result.resolve()), sha256=_file_hash(result))
                ).encode("utf-8"),
            )


def evaluate_answer_quality(
    config: Config,
    answer: dict,
    *,
    allow_api: bool = False,
    claim_id: str | None = None,
    runner: Callable[[Path, bool], None] | None = None,
) -> dict:
    started = time.perf_counter()
    python = _python(ROOT / "data/skripsi/s5-ragas/.venv")
    if not python.is_file():
        raise ValueError("Environment RAGAS terpisah belum tersedia.")
    directory = prepare_quality(
        config, answer["answer_id"], answer.get("database_path"), claim_id=claim_id
    )
    item = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    if (
        item["question"] != answer["question"]
        or _response(item["generation"], None) != _response(answer, None)
        or item["response"] != _response(answer, claim_id)
    ):
        raise ValueError("Displayed answer differs from persisted generation")
    prepared_seconds = time.perf_counter() - started
    if runner is not None:
        _cached_score(directory, load_config(directory / "config.yaml"), item, runner, allow_api)
        report = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        report["directory"] = str(directory)
        report.setdefault("timings", {}).update(
            preparation_seconds=prepared_seconds,
            parent_total_seconds=time.perf_counter() - started,
        )
        return report
    command = [
        str(python),
        "-m",
        "rag.evaluation.answer_quality",
        "score",
        "--directory",
        str(directory.resolve()),
    ]
    if allow_api:
        command.append("--allow-api")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Evaluasi timeout; jawaban tetap tersedia. Periksa artefak sebelum mengulang."
        ) from None
    if result.returncode:
        raise RuntimeError("Evaluasi gagal; jawaban tetap tersedia.")
    report = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    if (
        report["answer_id"] != answer["answer_id"]
        or report.get("claim_id") != claim_id
        or report["input_sha256"] != _file_hash(directory / "input.json")
    ):
        raise ValueError("Evaluation result does not match the selected answer")
    report["directory"] = str(directory)
    report.setdefault("timings", {}).update(
        preparation_seconds=prepared_seconds, parent_total_seconds=time.perf_counter() - started
    )
    return report


def _worker() -> None:
    wire = sys.stdout

    def send(message: dict) -> None:
        wire.write(json.dumps(message, allow_nan=False) + "\n")
        wire.flush()

    for line in sys.stdin:
        try:
            request = json.loads(line)
            directory = Path(request["directory"])
            if type(request["allow_api"]) is not bool:
                raise ValueError("Invalid API permission")

            def embed(texts: list[str]) -> list[list[float]]:
                send(dict(type="embed", texts=texts))
                response = json.loads(sys.stdin.readline())
                if "error" in response or len(response["vectors"]) != len(texts):
                    raise ValueError("Local embedding failed")
                return response["vectors"]

            with redirect_stdout(sys.stderr):
                score_quality(directory, allow_api=request["allow_api"], embed_texts=embed)
            send(dict(type="done"))
        except Exception as exc:
            send(dict(type="error", error=type(exc).__name__))


def _embed(config_path: Path) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from rag.indexing.embedding import SentenceEmbedder, embed_chunks

    config = load_config(config_path)
    texts = json.loads(sys.stdin.read())
    if (
        not isinstance(texts, list)
        or not 1 <= len(texts) <= 3
        or any(not isinstance(text, str) or not text.strip() for text in texts)
    ):
        raise ValueError("Expected one to three nonempty questions")
    vectors, _ = embed_chunks(
        [dict(chunk_id=str(i), text=text) for i, text in enumerate(texts)],
        config,
        SentenceEmbedder(config),
    )
    sys.stdout.write(json.dumps(vectors, allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["score", "embed", "worker"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    if args.command == "worker":
        _worker()
    elif args.command == "score" and args.directory:
        score_quality(args.directory, allow_api=args.allow_api)
    elif args.command == "embed" and args.config:
        _embed(args.config)
    else:
        parser.error("score requires --directory; embed requires --config")


if __name__ == "__main__":
    main()
