"""Reference-free answer evaluation, with Ragas kept in its isolated environment."""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

import yaml

from rag.config import Config, load_config
from rag.evaluation.ragas import _corpus, _file_hash, _validate_answer, _write
from rag.evaluation.retrieval import _code_version
from rag.generation.client import LLMBackend
from rag.generation.store import connect_corpus, load_context
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash

ROOT = Path(__file__).resolve().parents[3]
MAX_CALLS = 5
MAX_OUTPUT_TOKENS = 1024
MAX_PROMPT_BYTES = 65536


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prepare_quality(config: Config, answer_id: str, database: str | None = None) -> Path:
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
        question=stored[0],
        response="\n\n".join(claim["text"] for claim in generation["claims"]),
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
    item, config = _inputs(directory)
    report = dict(
        answer_id=item["answer_id"],
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
        protocol="answer-quality-v1",
        embedding=asdict(config.embedding),
        response_relevancy_strictness=3,
        interpretation="AI estimates; all retrieved context; not citation accuracy or human truth",
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
            start = len(traces)
            try:
                report["scores"][name] = metric_value(
                    metrics[name].score(**arguments),
                    minimum=-1.0 if name == "response_relevancy" else 0.0,
                )
            except (ValueError, RuntimeError, OSError) as exc:
                report["errors"][name] = type(exc).__name__
            report["traces"][name] = traces[start:]
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
    _write(directory / "result.json", report)
    return report


def evaluate_answer_quality(config: Config, answer: dict, *, allow_api: bool = False) -> dict:
    python = _python(ROOT / "data/skripsi/s5-ragas/.venv")
    if not python.is_file():
        raise ValueError("Environment RAGAS terpisah belum tersedia.")
    directory = prepare_quality(config, answer["answer_id"], answer.get("database_path"))
    item = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    if item["question"] != answer["question"] or item["response"] != "\n\n".join(
        claim["text"] for claim in answer["claims"]
    ):
        raise ValueError("Displayed answer differs from persisted generation")
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
    if report["answer_id"] != answer["answer_id"] or report["input_sha256"] != _file_hash(
        directory / "input.json"
    ):
        raise ValueError("Evaluation result does not match the selected answer")
    report["directory"] = str(directory)
    return report


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
    parser.add_argument("command", choices=["score", "embed"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    if args.command == "score" and args.directory:
        score_quality(args.directory, allow_api=args.allow_api)
    elif args.command == "embed" and args.config:
        _embed(args.config)
    else:
        parser.error("score requires --directory; embed requires --config")


if __name__ == "__main__":
    main()
