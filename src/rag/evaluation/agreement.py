import json
from contextlib import closing
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from rag.config import Config
from rag.evaluation.annotations import load_manual_labels
from rag.evaluation.metrics import cohens_kappa
from rag.evaluation.resources import process_resources
from rag.evaluation.retrieval import _code_version
from rag.generation.store import connect_corpus, start_run
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash
from rag.retrieval.pipeline import Retriever
from rag.verification.minicheck import CachedVerifier, SupportBackend


def _write_results(directory: Path, report: dict, records: list[dict]) -> None:
    with (directory / "per_pair.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    with (directory / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(
            f"# Manual verifier agreement\n\nRun: `{report['run_id']}`. "
            f"Status: {report['status']}.\n\n"
            f"Config SHA-256: `{report['config_hash']}`. Seed: {report['seed']}.\n\n"
            f"Model: `{json.dumps(report['model'], sort_keys=True)}`.\n\n"
            f"Manual labels SHA-256: `{report['manual_labels_sha256']}`. "
            f"Pairs: {report['annotation_count']}.\n\n"
            f"Metrics: `{json.dumps(report.get('metrics'))}`.\n\n"
            "Kappa is unweighted across all three labels. MiniCheck emits binary labels; "
            "partially_supported manual labels remain distinct. Undefined kappa is null.\n"
        )


def evaluate_agreement(
    config: Config,
    annotations_path: str | Path | None = None,
    backend: SupportBackend | None = None,
) -> dict:
    chunks = Retriever(config).store.chunks
    path = Path(annotations_path or config.evaluation.gold_labels_path)
    labels, digest = load_manual_labels(path, chunks)
    if not labels:
        raise ValueError("Human labels are required; pending or AI labels cannot replace them")
    content = path.read_bytes().decode("utf-8")
    if text_hash(content) != digest:
        raise ValueError("Annotation file changed during validation")
    items = [json.loads(line) for line in content.splitlines() if line.strip()]
    run_id = make_run_id()
    directory = Path(config.evaluation.output_dir) / run_id.replace(":", "-")
    directory.mkdir(parents=True, exist_ok=False)
    verifier = CachedVerifier(config, backend)
    effective = asdict(
        replace(config, evaluation=replace(config.evaluation, gold_labels_path=str(path)))
    )
    report = {
        "run_id": run_id,
        "stage": "manual_agreement",
        "status": "failed",
        "config": effective,
        "config_hash": text_hash(json.dumps(effective, sort_keys=True)),
        "seed": config.verification.seed,
        "code_version": _code_version(),
        "model": verifier.identity,
        "manual_labels_sha256": digest,
        "annotation_count": len(items),
        "started_at": datetime.now(UTC).isoformat(),
        "paid_api_calls": 0,
    }
    records = []
    run_started = False
    try:
        with closing(connect_corpus(config, writable=True)) as connection:
            start_run(connection, dict(report, retrieval_mode="bm25"))
            run_started = True
            with connection:
                connection.execute(
                    "UPDATE run SET kind='eval', model_gen=NULL, model_verify=? WHERE run_id=?",
                    (config.verification.minicheck_model, run_id),
                )
        for item in items:
            result = verifier.verify(item["claim"], chunks[item["chunk_id"]]["text"])
            records.append(
                {
                    "claim": item["claim"],
                    "chunk_id": item["chunk_id"],
                    "text_sha256": item["text_sha256"],
                    "manual_label": item["label"],
                    "annotator": item["annotator"],
                    **result,
                }
            )
        report["metrics"] = {
            "verifier_agreement_kappa": cohens_kappa(
                [r["manual_label"] for r in records], [r["label"] for r in records]
            ),
            "matched_pairs": len(records),
            "exact_agreement": sum(r["manual_label"] == r["label"] for r in records) / len(records),
        }
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"Agreement evaluation failed ({type(exc).__name__})"
        raise
    finally:
        report["resources"] = process_resources()
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["verifier_computed_pairs"] = verifier.computed_pairs
        report["verifier_cache_hits"] = verifier.cache_hits
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
                                    "report_path": str(directory / "metrics.json"),
                                }
                            ),
                            run_id,
                        ),
                    )
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = f"Agreement persistence failed ({type(exc).__name__})"
            raise
        finally:
            _write_results(directory, report, records)
    return report
