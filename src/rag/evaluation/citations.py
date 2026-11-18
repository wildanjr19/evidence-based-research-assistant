import json
import logging
import time
from collections import Counter
from contextlib import closing
from dataclasses import asdict, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from rag.config import Config
from rag.evaluation.annotations import export_annotations, load_manual_labels
from rag.evaluation.metrics import citation_metrics, cohens_kappa, retrieval_metrics
from rag.evaluation.resources import process_resources
from rag.evaluation.retrieval import _code_version, load_questions
from rag.generation.client import CachedLLM, LLMBackend
from rag.generation.pipeline import generate_answer
from rag.generation.store import connect_corpus, start_run
from rag.ids import make_run_id
from rag.indexing.embedding import Embedder, text_hash
from rag.retrieval.pipeline import MODES, Retriever
from rag.retrieval.rerank import Reranker
from rag.verification.judge import create_judge, sample_claim_ids
from rag.verification.minicheck import CachedVerifier, SupportBackend
from rag.verification.pipeline import verify_answer

logger = logging.getLogger(__name__)


def _write_results(directory: Path, report: dict, records: list[dict]) -> None:
    with (directory / "per_question.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            generation = {
                key: value
                for key, value in record["generation"].items()
                if key not in {"markdown", "references"}
            }
            stream.write(
                json.dumps(dict(record, generation=generation), ensure_ascii=True, allow_nan=False)
                + "\n"
            )
    with (directory / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2, allow_nan=False)
    lines = [
        f"# Citation evaluation: {report['mode']}",
        "",
        f"Run: `{report['run_id']}`. Status: {report['status']}.",
        "",
        f"Config SHA-256: `{report['config_hash']}`.",
        "",
        f"Dataset SHA-256: `{report['dataset_sha256']}`.",
        "",
        f"Seed: {report['seed']}. Questions: {report['question_count']}.",
        "",
        "Models and backends: `" + json.dumps(report["models"], sort_keys=True) + "`.",
        "",
        "Question types: `" + json.dumps(report["question_types"], sort_keys=True) + "`.",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key, value in report.get("metrics", {}).items():
        lines.append(f"| {key} | {value if value is not None else 'undefined'} |")
    lines += [
        "",
        "MiniCheck pair labels determine primary support metrics; judge results are separate.",
        "Claims on unanswerable questions fail faithfulness. Failed generation is not abstention.",
        "Unknown support and failed generation make aggregate support metrics undefined.",
        "Citation events count unique IDs per claim after M5 deduplication, including rejections.",
        "Manual agreement requires matching human annotations; no AI labels substitute.",
        "Resources: `" + json.dumps(report["resources"], sort_keys=True) + "`.",
        "LLM usage: `" + json.dumps(report["usage"], sort_keys=True) + "`.",
    ]
    if report.get("error"):
        lines += ["", report["error"]]
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def evaluate_citations(
    config: Config,
    dataset_path: str | Path | None = None,
    modes: tuple[str, ...] = ("hybrid+rerank",),
    *,
    allow_api: bool = False,
    with_judge: bool = False,
    backend: LLMBackend | None = None,
    judge_backend: LLMBackend | None = None,
    support_backend: SupportBackend | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> list[dict]:
    if not modes or len(set(modes)) != len(modes) or any(mode not in MODES for mode in modes):
        raise ValueError("Specify unique retrieval modes")
    retriever = Retriever(config, embedder, reranker)
    chunks = retriever.store.chunks
    dataset = Path(dataset_path or config.evaluation.dataset_path)
    questions, digest = load_questions(dataset, chunks)
    manual, manual_digest = load_manual_labels(Path(config.evaluation.gold_labels_path), chunks)
    judge = create_judge(config, judge_backend, allow_api) if with_judge else None
    if judge is not None:
        config = judge.config
    client = CachedLLM(config, backend, allow_api)
    verifier = CachedVerifier(config, support_backend)
    reports = []
    for mode in modes:
        started = time.perf_counter()
        run_id = make_run_id()
        directory = Path(config.evaluation.output_dir) / run_id.replace(":", "-")
        directory.mkdir(parents=True, exist_ok=False)
        effective = asdict(
            replace(
                config,
                retrieval=replace(config.retrieval, use_reranker=mode == "hybrid+rerank"),
                evaluation=replace(config.evaluation, dataset_path=str(dataset)),
            )
        )
        calls_before, hits_before = verifier.computed_pairs, verifier.cache_hits
        attempts_before = len(client.attempts)
        judge_before = len(judge.client.attempts) if judge else 0
        report = {
            "run_id": run_id,
            "stage": "citation_evaluation",
            "status": "failed",
            "mode": mode,
            "retrieval_mode": mode,
            "started_at": datetime.now(UTC).isoformat(),
            "report_path": str(directory / "metrics.json"),
            "config": effective,
            "config_hash": text_hash(json.dumps(effective, sort_keys=True)),
            "seed": config.verification.seed,
            "code_version": _code_version(),
            "dataset_sha256": digest,
            "dataset_path": str(dataset),
            "corpus_sha256": text_hash(json.dumps(chunks, sort_keys=True, ensure_ascii=False)),
            "manual_labels_sha256": manual_digest,
            "manual_label_count": len(manual),
            "question_count": len(questions),
            "question_types": dict(Counter(q["qtype"] for q in questions)),
            "ranking_depth": max(config.evaluation.ks),
            "judge_requested": with_judge,
            "allow_api": allow_api,
            "models": {
                "generator": config.generation.model,
                "generator_backend": client.backend_name,
                "verifier": verifier.identity,
                "judge": config.verification.judge_model if judge else None,
                "judge_backend": judge.client.backend_name if judge else None,
                "judge_identity": getattr(judge, "identity", None),
                "embedding": {
                    "model": config.embedding.model,
                    "revision": config.embedding.revision,
                }
                if mode != "bm25"
                else None,
                "reranker": {
                    "model": config.retrieval.reranker_model,
                    "revision": config.retrieval.reranker_revision,
                }
                if mode == "hybrid+rerank"
                else None,
            },
            "versions": {name: version(name) for name in ("torch", "transformers", "openai")},
        }
        records = []
        run_started = False
        try:
            with closing(connect_corpus(config, writable=True)) as connection:
                start_run(connection, report)
                run_started = True
                with connection:
                    connection.execute(
                        "UPDATE run SET kind='eval', model_verify=? WHERE run_id=?",
                        (config.verification.minicheck_model, run_id),
                    )
            for question in questions:
                hits = retriever.retrieve(
                    question["question"],
                    mode,
                    top_k=max(max(config.evaluation.ks), config.retrieval.final_top_k),
                )
                generation = generate_answer(
                    question["question"],
                    hits[: config.retrieval.final_top_k],
                    config,
                    mode=mode,
                    client=client,
                )
                records.append(
                    {
                        "qid": question["qid"],
                        "qtype": question["qtype"],
                        "question": question["question"],
                        "gold_chunk_ids": question["gold_chunk_ids"],
                        "ranking": [hit["chunk_id"] for hit in hits],
                        "retrieval_metrics": retrieval_metrics(
                            [hit["chunk_id"] for hit in hits],
                            question["gold_chunk_ids"],
                            config.evaluation.ks,
                        ),
                        "generation": generation,
                        "verification": [],
                    }
                )
            stable_ids = {
                f"{r['qid']}:c{c['claim_order']:04d}": c["claim_id"]
                for r in records
                for c in r["generation"]["claims"]
                if c["citations"]
            }
            selected = (
                sample_claim_ids(
                    list(stable_ids),
                    config.verification.judge_sample_rate,
                    config.verification.seed,
                )
                if judge
                else set()
            )
            report["judge_sample_keys"] = sorted(selected)
            sample = {stable_ids[key] for key in selected}
            for record in records:
                record["verification"] = verify_answer(
                    record["generation"], config, verifier, judge, sample
                )
            metrics = citation_metrics(records)
            expected, predicted = [], []
            judge_expected, judge_predicted = [], []
            for record in records:
                by_id = {c["claim_id"]: c for c in record["generation"]["claims"]}
                local = {
                    (v["claim_id"], v["chunk_id"]): v["label"]
                    for v in record["verification"]
                    if v["verifier"] == "minicheck"
                }
                for result in record["verification"]:
                    if result["label"] is None:
                        continue
                    key = (
                        text_hash(by_id[result["claim_id"]]["text"]),
                        result["chunk_id"],
                        text_hash(chunks[result["chunk_id"]]["text"]),
                    )
                    if result["verifier"] == "minicheck" and key in manual:
                        expected.append(manual[key])
                        predicted.append(result["label"])
                    if result["verifier"] == "llm_judge":
                        label = local[(result["claim_id"], result["chunk_id"])]
                        if label is not None:
                            judge_expected.append(label)
                            judge_predicted.append(result["label"])
            metrics.update(
                verifier_agreement_kappa=cohens_kappa(expected, predicted),
                manual_matched_pairs=len(expected),
                judge_agreement_kappa=cohens_kappa(judge_expected, judge_predicted),
                judge_matched_pairs=len(judge_expected),
            )
            for name in [f"recall@{k}" for k in config.evaluation.ks] + ["mrr"]:
                values = [
                    r["retrieval_metrics"][name]
                    for r in records
                    if r["retrieval_metrics"][name] is not None
                ]
                metrics[name] = sum(values) / len(values) if values else None
            report["metrics"] = metrics
            report["status"] = (
                "ok"
                if not (
                    metrics["failed_question_count"]
                    or metrics["unverified_pair_count"]
                    or any(v["label"] is None for r in records for v in r["verification"])
                )
                else "incomplete"
            )
            annotation_path = Path("data") / "annotations" / (run_id.replace(":", "-") + ".jsonl")
            report["annotation_pair_count"] = export_annotations(records, chunks, annotation_path)
            report["annotation_path"] = str(annotation_path)
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = (
                f"Evaluation failed ({type(exc).__name__}); see persisted question reports"
            )
            raise
        finally:
            report["finished_at"] = datetime.now(UTC).isoformat()
            report["completed_questions"] = len(records)
            report["elapsed_seconds"] = time.perf_counter() - started
            report["resources"] = process_resources()
            report["verifier_computed_pairs"] = verifier.computed_pairs - calls_before
            report["verifier_cache_hits"] = verifier.cache_hits - hits_before
            report["models"]["reported_generator_models"] = sorted(
                {a["model"] for a in client.attempts[attempts_before:] if a.get("model")}
            )
            report["models"]["reported_judge_models"] = sorted(
                {
                    a["model"]
                    for a in (judge.client.attempts[judge_before:] if judge else [])
                    if a.get("model")
                }
            )
            for name, model in (
                ("embedding_backend", retriever.embedder),
                ("reranker_backend", retriever.reranker),
            ):
                report["models"][name] = (
                    f"{type(model).__module__}.{type(model).__qualname__}" if model else None
                )
            report["vector_version"] = (
                retriever.store.table.version if retriever.store.table is not None else None
            )
            report["usage"] = {}
            for name, attempts in (
                ("generation", client.attempts[attempts_before:]),
                ("judge", judge.client.attempts[judge_before:] if judge else []),
            ):
                report["usage"][name] = {
                    "backend_calls": sum(not a["cache_hit"] for a in attempts),
                    "cache_hits": sum(a["cache_hit"] for a in attempts),
                    "input_tokens": sum(a.get("billed_input_tokens") or 0 for a in attempts),
                    "output_tokens": sum(a.get("billed_output_tokens") or 0 for a in attempts),
                    "unknown_usage_attempts": sum(
                        not a["cache_hit"]
                        and (
                            a.get("billed_input_tokens") is None
                            or a.get("billed_output_tokens") is None
                        )
                        for a in attempts
                    ),
                }
            try:
                if run_started:
                    with closing(connect_corpus(config, writable=True)) as connection, connection:
                        connection.execute(
                            "UPDATE run SET finished_at=?, notes=? WHERE run_id=?",
                            (
                                report["finished_at"],
                                json.dumps(
                                    {
                                        "status": report["status"],
                                        "metrics": report.get("metrics"),
                                        "usage": report["usage"],
                                        "report_path": report["report_path"],
                                    }
                                ),
                                run_id,
                            ),
                        )
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = f"Evaluation persistence failed ({type(exc).__name__})"
                raise
            finally:
                _write_results(directory, report, records)
            logger.info("Citation evaluation %s: %s; report=%s", mode, report["status"], directory)
        reports.append(report)
    return reports
