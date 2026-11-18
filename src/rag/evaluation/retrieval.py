import hashlib
import json
import logging
import platform
import sqlite3
import subprocess
import time
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

from rag.config import Config
from rag.evaluation.metrics import retrieval_metrics
from rag.ids import is_valid_chunk_id, is_valid_paper_id, make_run_id
from rag.indexing.embedding import Embedder, text_hash
from rag.indexing.store import FTS_TOKENIZER
from rag.retrieval.pipeline import MODES, Retriever
from rag.retrieval.rerank import Reranker, reranker_identity

logger = logging.getLogger(__name__)


def load_questions(path: Path, chunks: dict[str, dict]) -> tuple[list[dict], str]:
    content = path.read_bytes()
    questions = []
    seen = set()
    papers = {row["paper_id"] for row in chunks.values()}
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("question must be an object")
            for field in ("qid", "question"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError(f"{field} must be a non-empty string")
            if item["qid"] in seen:
                raise ValueError("duplicate qid")
            if item.get("qtype") not in {"lookup", "comparison", "synthesis", "unanswerable"}:
                raise ValueError("unknown qtype")
            for field, validator in (
                ("gold_chunk_ids", is_valid_chunk_id),
                ("gold_paper_ids", is_valid_paper_id),
            ):
                values = item.get(field)
                if not isinstance(values, list) or any(not validator(key) for key in values):
                    raise ValueError(f"invalid {field}")
                if len(set(values)) != len(values):
                    raise ValueError(f"duplicate {field}")
            if (item["qtype"] == "unanswerable") != (not item["gold_chunk_ids"]):
                raise ValueError("only unanswerable questions may have empty gold_chunk_ids")
            if not set(item["gold_paper_ids"]) <= papers:
                raise ValueError("gold paper is missing from corpus")
            for key in item["gold_chunk_ids"]:
                if key not in chunks:
                    raise ValueError(f"gold chunk is missing from corpus: {key}")
                if chunks[key]["paper_id"] not in item["gold_paper_ids"]:
                    raise ValueError("gold chunk does not belong to gold_paper_ids")
            seen.add(item["qid"])
            questions.append(item)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Invalid validation question at {path}:{line_number}: {exc}") from exc
    if not questions:
        raise ValueError("Validation dataset is empty")
    return questions, hashlib.sha256(content).hexdigest()


def _code_version() -> str:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        return revision + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_report(directory: Path, report: dict, records: list[dict]) -> None:
    with (directory / "per_question.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    with (directory / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    lines = [
        f"# Retrieval evaluation: {report['mode']}",
        "",
        f"Run: `{report['run_id']}`. Status: {report['status']}.",
        "",
        f"Config SHA-256: `{report['config_hash']}`.",
        "",
        f"Dataset SHA-256: `{report['dataset_sha256']}`.",
        "",
        f"Seed: {report['seed']}. Questions: {report['question_count']}. "
        f"MRR depth: {report['ranking_depth']}.",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for name, value in report.get("metrics", {}).items():
        lines.append(f"| {name} | {value if value is not None else 'undefined'} |")
    lines += [
        "",
        "Recall and MRR are macro averages over answerable questions only.",
        "Retrieval metrics do not measure citation support or answer correctness.",
    ]
    if "error" in report:
        lines += ["", "Error: " + report["error"]]
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def evaluate_retrieval(
    config: Config,
    dataset_path: str | Path | None = None,
    modes: tuple[str, ...] = MODES,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> list[dict]:
    if not modes or len(set(modes)) != len(modes) or any(mode not in MODES for mode in modes):
        raise ValueError("Specify unique retrieval modes from: " + ", ".join(MODES))
    retriever = Retriever(config, embedder, reranker)
    dataset = Path(dataset_path or config.evaluation.dataset_path)
    questions, digest = load_questions(dataset, retriever.store.chunks)
    corpus_hash = text_hash(json.dumps(retriever.store.chunks, sort_keys=True, ensure_ascii=False))
    reports = []
    depth = max(config.evaluation.ks)
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
        report = {
            "run_id": run_id,
            "stage": "retrieval_evaluation",
            "status": "failed",
            "mode": mode,
            "config": effective,
            "config_hash": text_hash(json.dumps(effective, sort_keys=True)),
            "seed": config.verification.seed,
            "code_version": _code_version(),
            "dataset_path": str(dataset),
            "dataset_sha256": digest,
            "corpus_sha256": corpus_hash,
            "question_count": len(questions),
            "ranking_depth": depth,
            "answerable_count": sum(bool(q["gold_chunk_ids"]) for q in questions),
            "versions": {
                name: version(name)
                for name in ("torch", "sentence-transformers", "transformers", "lancedb")
            },
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "fts_tokenizer": FTS_TOKENIZER,
            "reranker": reranker_identity(config) if mode == "hybrid+rerank" else None,
        }
        records = []
        try:
            for question in questions:
                query_started = time.perf_counter()
                hits = retriever.retrieve(question["question"], mode, top_k=depth)
                metrics = retrieval_metrics(
                    [hit["chunk_id"] for hit in hits],
                    question["gold_chunk_ids"],
                    config.evaluation.ks,
                )
                records.append(
                    {
                        "qid": question["qid"],
                        "qtype": question["qtype"],
                        "question": question["question"],
                        "gold_chunk_ids": question["gold_chunk_ids"],
                        "ranking": [
                            {key: hit[key] for key in ("chunk_id", "rank", "score", "score_type")}
                            for hit in hits
                        ],
                        "metrics": metrics,
                        "statistics": dict(retriever.statistics),
                        "elapsed_seconds": time.perf_counter() - query_started,
                    }
                )
            names = [f"recall@{k}" for k in config.evaluation.ks] + ["mrr"]
            report["metrics"] = {}
            for name in names:
                values = [r["metrics"][name] for r in records if r["metrics"][name] is not None]
                report["metrics"][name] = sum(values) / len(values) if values else None
            report["embedding"] = retriever.store.identity if mode != "bm25" else None
            report["status"] = "ok"
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            report["elapsed_seconds"] = time.perf_counter() - started
            report["completed_questions"] = len(records)
            report["vector_version"] = (
                retriever.store.table.version
                if mode != "bm25" and retriever.store.table is not None
                else None
            )
            report["backends"] = {
                name: f"{type(model).__module__}.{type(model).__qualname__}" if model else None
                for name, model in (
                    ("embedder", retriever.embedder if mode != "bm25" else None),
                    ("reranker", retriever.reranker if mode == "hybrid+rerank" else None),
                )
            }
            _write_report(directory, report, records)
            logger.info("Retrieval evaluation %s: %s; report=%s", mode, report["status"], directory)
        reports.append(report)
    return reports
