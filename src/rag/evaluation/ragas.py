"""Prepare immutable thesis runs, then score them in an isolated Ragas environment."""

import argparse
import hashlib
import json
import logging
import random
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

import yaml

from rag.config import Config, load_config
from rag.evaluation.retrieval import _code_version, load_questions
from rag.generation.client import CachedLLM, LLMBackend
from rag.generation.pipeline import generate_answer
from rag.generation.store import connect_corpus, load_context
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash
from rag.indexing.pipeline import load_chunks
from rag.verification.judge import Judge

logger = logging.getLogger(__name__)


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corpus(config: Config) -> tuple[dict, str]:
    with closing(connect_corpus(config)) as connection:
        chunks = {c["chunk_id"]: c for c in load_chunks(connection)}
    return chunks, text_hash(json.dumps(chunks, sort_keys=True, ensure_ascii=False))


def _directory(config: Config, prefix: str) -> Path:
    directory = Path(config.evaluation.output_dir) / (prefix + make_run_id().replace(":", "-"))
    if not directory.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Ragas artifacts containing evidence must remain under data/")
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _validate_answer(config: Config, generation: dict, question: str) -> None:
    with closing(connect_corpus(config)) as connection:
        stored = connection.execute(
            """SELECT answer.question, run.notes FROM answer JOIN run USING (run_id)
               WHERE answer_id = ?""",
            (generation["answer_id"],),
        ).fetchone()
        rows = connection.execute(
            "SELECT claim_id,text,citations,unsupported FROM claim "
            "WHERE answer_id=? ORDER BY claim_order",
            (generation["answer_id"],),
        ).fetchall()
    expected = [
        (c["claim_id"], c["text"], c["citations"], c["unsupported"]) for c in generation["claims"]
    ]
    actual = [(row[0], row[1], json.loads(row[2]), bool(row[3])) for row in rows]
    if (
        stored is None
        or stored[0] != question
        or json.loads(stored[1])["status"] != generation["status"]
        or actual != expected
    ):
        raise ValueError("Ragas answer differs from the persisted generation")


def prepare_ragas(
    config: Config,
    dataset: Path,
    *,
    limit: int = 20,
    offset: int = 0,
    mode: str = "hybrid+rerank",
    allow_api: bool = False,
    max_calls: int = 8,
    backend: LLMBackend | None = None,
    retriever: object | None = None,
) -> Path:
    if (
        type(limit) is not int
        or not 1 <= limit <= 20
        or type(offset) is not int
        or offset < 0
        or type(max_calls) is not int
        or max_calls < 1
    ):
        raise ValueError("Expected limit 1..20, nonnegative offset and positive request budget")
    chunks, corpus_hash = _corpus(config)
    questions, dataset_hash = load_questions(dataset, chunks)
    if offset >= len(questions):
        raise ValueError("Offset selects no questions")
    for item in questions:
        if (
            item.get("reference_status") != "ai_draft_unreviewed"
            or not isinstance(item.get("reference"), str)
            or not item["reference"].strip()
            or item.get("reference_text_sha256")
            != {key: text_hash(chunks[key]["text"]) for key in item["gold_chunk_ids"]}
        ):
            raise ValueError("Ragas draft reference is missing, reviewed, or bound to stale chunks")
    directory = _directory(config, "ragas-inputs-")
    selected = replace(
        config,
        paths=replace(config.paths, db_path=str(directory / "corpus.db"), index_dir=str(directory)),
        generation=replace(config.generation, max_calls_per_run=max_calls),
    )
    with (
        closing(connect_corpus(config)) as source,
        closing(sqlite3.connect(selected.paths.db_path)) as target,
    ):
        source.backup(target)
    config_text = yaml.safe_dump(asdict(selected), sort_keys=False)
    (directory / "config.yaml").write_text(config_text, encoding="utf-8")
    if retriever is None:
        from rag.retrieval.pipeline import Retriever

        retriever = Retriever(config)
    client = CachedLLM(selected, backend, allow_api)
    records = []
    for item in questions[offset : offset + limit]:
        hits = retriever.retrieve(item["question"], mode)
        generation = generate_answer(item["question"], hits, selected, mode=mode, client=client)
        records.append(dict(question=item, generation=generation))
        logger.info("Ragas input %s: %s", item["qid"], generation["status"])
    _write(directory / "samples.json", records)
    audit = random.Random(config.verification.seed).sample(records, min(10, len(records)))
    audit_lines = [
        "# Audit kecil referensi skripsi",
        "",
        "Draf dibuat AI dan belum menjadi gold manusia. Prediksi judge tidak ditampilkan.",
        "Tinjau jawaban acuan, baca kutipan, dan tulis koreksi. Audit ini dibantu draf AI, "
        "bukan penilaian buta. Untuk kasus tanpa bukti, periksa apakah jawaban "
        "memang tidak tersedia.",
    ]
    with (directory / "reference-audit.jsonl").open("x", encoding="utf-8") as stream:
        for ordinal, record in enumerate(audit, 1):
            item = record["question"]
            evidence, _ = load_context([chunks[key] for key in item["gold_chunk_ids"]], config)
            audit_lines.extend(
                [
                    "",
                    f"## {ordinal}. {item['qid']}",
                    "",
                    item["question"],
                    "",
                    "Jawaban acuan AI: " + item["reference"],
                    "",
                    "Penilaian Anda: [ ] sesuai [ ] perlu koreksi [ ] bukti belum cukup",
                    "",
                    "Koreksi/catatan: ...",
                    "",
                ]
            )
            for chunk in evidence:
                audit_lines.extend(
                    [
                        f"Sumber: {chunk['title']}, halaman PDF "
                        f"{chunk['page_start']}–{chunk['page_end']}",
                        f"ID: `{chunk['chunk_id']}`",
                        "",
                        *["> " + line for line in chunk["text"].splitlines()],
                        "",
                    ]
                )
            stream.write(
                json.dumps(
                    dict(
                        qid=item["qid"],
                        question=item["question"],
                        reference=item["reference"],
                        reference_status=item["reference_status"],
                        evidence=evidence,
                        reference_correct=None,
                        reviewer=None,
                        notes="",
                        review_condition="AI draft visible; judge predictions omitted",
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    with (directory / "reference-audit.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(audit_lines) + "\n")
    _write(
        directory / "manifest.json",
        dict(
            dataset_path=str(dataset.resolve()),
            dataset_sha256=dataset_hash,
            corpus_sha256=corpus_hash,
            config_sha256=_file_hash(directory / "config.yaml"),
            samples_sha256=_file_hash(directory / "samples.json"),
            reference_status="ai_draft_unreviewed",
            human_accuracy=None,
            code_version=_code_version(),
            seed=config.verification.seed,
            mode=mode,
            limit=limit,
            offset=offset,
            selected_qids=[record["question"]["qid"] for record in records],
            generation_backend=client.backend_name,
            generation_attempts=client.attempts,
            generation_calls=client.calls,
        ),
    )
    return directory


def score_ragas(
    directory: Path,
    *,
    allow_api: bool = False,
    max_calls: int = 12,
    max_prompt_bytes: int = 65536,
    backend: LLMBackend | None = None,
) -> Path:
    started = time.perf_counter()
    if type(max_calls) is not int or max_calls < 1 or max_prompt_bytes < 1:
        raise ValueError("Expected positive judge request and prompt byte budgets")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in (
        ("config.yaml", manifest["config_sha256"]),
        ("samples.json", manifest["samples_sha256"]),
    ):
        if _file_hash(directory / name) != expected:
            raise ValueError("Ragas inputs differ from their manifest")
    if _file_hash(Path(manifest["dataset_path"])) != manifest["dataset_sha256"]:
        raise ValueError("Ragas dataset differs from its manifest")
    config = load_config(directory / "config.yaml")
    chunks, digest = _corpus(config)
    if digest != manifest["corpus_sha256"]:
        raise ValueError("Ragas corpus differs from the prepared snapshot")
    config = replace(
        config,
        verification=replace(config.verification, judge_max_calls_per_run=max_calls),
    )
    judge = Judge(config, backend, allow_api)
    from rag.evaluation.ragas_adapter import create_metrics, metric_value

    metrics, traces = create_metrics(judge.client, max_prompt_bytes)
    output = _directory(config, "ragas-scores-")
    results = []
    for record in json.loads((directory / "samples.json").read_text(encoding="utf-8")):
        item, generation = record["question"], record["generation"]
        _validate_answer(config, generation, item["question"])
        result = dict(qid=item["qid"], qtype=item["qtype"], status=generation["status"], scores={})
        if generation["status"] == "failed":
            result["skip_reason"] = "generation_failed"
        elif not generation["claims"]:
            result.update(abstained=True, skip_reason="no_claims; faithfulness undefined")
        else:
            identifiers = generation["context_chunk_ids"]
            context, _ = load_context([chunks[key] for key in identifiers], config)
            if (
                text_hash(json.dumps(context, sort_keys=True, ensure_ascii=False))
                != generation["context_sha256"]
            ):
                raise ValueError("Ragas context differs from the canonical generation context")
            if any(key not in identifiers for c in generation["claims"] for key in c["citations"]):
                raise ValueError("Ragas claim cites outside retrieved context")
            response = "\n".join(c["text"] for c in generation["claims"])
            requests = dict(
                faithfulness=dict(
                    user_input=item["question"],
                    response=response,
                    retrieved_contexts=[c["text"] for c in context],
                ),
            )
            if item["qtype"] != "unanswerable":
                requests["context_recall"] = dict(
                    user_input=item["question"],
                    reference=item["reference"],
                    retrieved_contexts=[c["text"] for c in context],
                )
            for name, arguments in requests.items():
                start = len(traces)
                metric_started = time.perf_counter()
                try:
                    result["scores"][name] = metric_value(metrics[name].score(**arguments))
                except (ValueError, RuntimeError, OSError) as exc:
                    result["scores"][name] = None
                    result.setdefault("errors", {})[name] = type(exc).__name__
                result.setdefault("traces", {})[name] = traces[start:]
                result.setdefault("elapsed_seconds", {})[name] = (
                    time.perf_counter() - metric_started
                )
            result["abstained"] = False
        results.append(result)
        logger.info("Ragas scores %s: %s", item["qid"], result["scores"])
    _write(output / "per_question.json", results)
    aggregates = {}
    for name in metrics:
        eligible = [
            r
            for r in results
            if r["status"] == "ok" and (name != "context_recall" or r["qtype"] != "unanswerable")
        ]
        values = [r["scores"].get(name) for r in eligible]
        known = [value for value in values if value is not None]
        aggregates[name] = dict(
            eligible=len(eligible),
            scored=len(known),
            mean=sum(known) / len(known) if known and len(known) == len(eligible) else None,
            mean_on_scored=sum(known) / len(known) if known else None,
            complete=bool(eligible) and len(known) == len(eligible),
        )
    _write(
        output / "report.json",
        dict(
            input_directory=str(directory),
            input_manifest=manifest,
            config=asdict(judge.config),
            ragas_version=version("ragas"),
            code_version=_code_version(),
            max_prompt_bytes=max_prompt_bytes,
            judge_calls=judge.client.calls,
            judge_backend=judge.client.backend_name,
            judge_attempts=judge.client.attempts,
            usage=dict(
                backend_calls=judge.client.calls,
                cache_hits=sum(a["cache_hit"] for a in judge.client.attempts),
                input_tokens=sum(a.get("billed_input_tokens") or 0 for a in judge.client.attempts),
                output_tokens=sum(
                    a.get("billed_output_tokens") or 0 for a in judge.client.attempts
                ),
                unknown_usage_attempts=sum(
                    not a["cache_hit"] and a.get("billed_input_tokens") is None
                    for a in judge.client.attempts
                ),
            ),
            elapsed_seconds=time.perf_counter() - started,
            versions={name: version(name) for name in ("ragas", "openai", "pydantic")},
            metrics=aggregates,
            human_accuracy=None,
            interpretation=(
                "Automated scores; AI draft references; not human accuracy. "
                "Faithfulness uses all retrieved contexts, not citation-specific support. "
                "Failed generation is excluded from metric eligibility and reported separately."
            ),
            generation_failed=sum(r["status"] == "failed" for r in results),
            unanswerable_questions=sum(r["qtype"] == "unanswerable" for r in results),
            unanswerable_abstained=sum(
                r["qtype"] == "unanswerable" and r.get("abstained", False) for r in results
            ),
            unanswerable_claimed=sum(
                r["qtype"] == "unanswerable" and r.get("abstained") is False for r in results
            ),
            cost_usd=None,
        ),
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--config", required=True)
    prepare.add_argument("--dataset", type=Path, required=True)
    prepare.add_argument("--limit", type=int, default=20)
    prepare.add_argument("--offset", type=int, default=0)
    prepare.add_argument(
        "--mode", choices=["bm25", "dense", "hybrid", "hybrid+rerank"], default="hybrid+rerank"
    )
    prepare.add_argument("--max-generation-calls", type=int, default=8)
    score = commands.add_parser("score")
    score.add_argument("--inputs", type=Path, required=True)
    score.add_argument("--max-judge-calls", type=int, default=12)
    score.add_argument("--max-prompt-bytes", type=int, default=65536)
    for command in (prepare, score):
        command.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.command == "prepare":
        output = prepare_ragas(
            load_config(args.config),
            args.dataset,
            limit=args.limit,
            offset=args.offset,
            mode=args.mode,
            allow_api=args.allow_api,
            max_calls=args.max_generation_calls,
        )
    else:
        output = score_ragas(
            args.inputs,
            allow_api=args.allow_api,
            max_calls=args.max_judge_calls,
            max_prompt_bytes=args.max_prompt_bytes,
        )
    logger.info("Ragas artifacts: %s", output)


if __name__ == "__main__":
    main()
