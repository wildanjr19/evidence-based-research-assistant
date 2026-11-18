import argparse
import hashlib
import json
import logging
import random
import statistics
import time
from collections import Counter
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

from rag.config import Config, load_config
from rag.evaluation.metrics import cohens_kappa
from rag.evaluation.resources import process_resources
from rag.evaluation.retrieval import _code_version
from rag.generation.client import LLMBackend, LLMError
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash
from rag.retrieval.pipeline import Retriever
from rag.verification.jev import JevJudge
from rag.verification.minicheck import CachedVerifier, SupportBackend

logger = logging.getLogger(__name__)


def _write_results(directory: Path, report: dict, records: list[dict]) -> None:
    with (directory / "per_pair.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
    with (directory / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=True, allow_nan=False)
    lines = [
        "# Jev / MiniCheck pilot comparison",
        "",
        f"Run: `{report['run_id']}`. Status: {report['status']}.",
        "",
        f"Config SHA-256: `{report['config_hash']}`.",
        "",
        f"Input SHA-256: `{report['input_sha256']}`. Seed: {report['seed']}.",
        "",
        f"Selected pairs: {report['selected_pair_count']}. Completed: {len(records)}.",
        "",
        "Jev identity: `" + json.dumps(report["jev"], sort_keys=True) + "`.",
        "",
        "MiniCheck identity: `" + json.dumps(report["minicheck"], sort_keys=True) + "`.",
        "",
        "Metrics: `" + json.dumps(report["metrics"], sort_keys=True) + "`.",
        "",
        "Usage: `" + json.dumps(report["usage"], sort_keys=True) + "`.",
        "",
        "Resources: `" + json.dumps(report["resources"], sort_keys=True) + "`.",
        "",
        "| Input row | Chunk | MiniCheck | Jev | Jev confidence |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['input_row']} | {r['chunk_id']} | {r['minicheck'].get('label')} | "
            f"{r['jev'].get('label')} | {r['jev'].get('confidence')} |"
        )
    lines += [
        "",
        "This is agreement between automated verifiers, not accuracy against human gold.",
        "Partially supported remains a distinct class; it is not promoted to supported.",
        "MiniCheck errors remain unverified; agreement excludes them and reports coverage.",
        "Jev HTTP latency excludes local work. MiniCheck timing includes first model loading.",
        "No generator calls, human annotations, or gold labels were created by this run.",
    ]
    if report.get("error"):
        lines += ["", report["error"]]
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def compare_decisions(
    config: Config,
    pairs_path: str | Path,
    limit: int = 12,
    *,
    allow_api: bool = False,
    backend: LLMBackend | None = None,
    support_backend: SupportBackend | None = None,
) -> dict:
    if type(limit) is not int or limit < 1:
        raise ValueError("Pair limit must be a positive integer")
    path = Path(pairs_path)
    content = path.read_bytes()
    chunks = Retriever(config).store.chunks
    pairs, seen = [], set()
    for number, line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            claim, chunk_id = item["claim"], item["chunk_id"]
            if not isinstance(claim, str) or not claim.strip() or chunk_id not in chunks:
                raise ValueError("Invalid pair")
            digest = text_hash(chunks[chunk_id]["text"])
            key = (text_hash(claim), chunk_id, digest)
            if item["text_sha256"] != digest or key in seen:
                raise ValueError("Duplicate pair or changed source text")
            seen.add(key)
            pairs.append(
                {"claim": claim, "chunk_id": chunk_id, "text_sha256": digest, "input_row": number}
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid decision comparison pair at row {number}") from exc
    if not pairs:
        raise ValueError("Comparison input contains no pairs")
    selected = random.Random(config.verification.seed).sample(pairs, min(limit, len(pairs)))
    config = replace(
        config,
        verification=replace(
            config.verification,
            judge_max_calls_per_run=min(len(selected), config.verification.judge_max_calls_per_run),
            judge_provider="surplus",
        ),
    )
    judge = JevJudge(config, backend, allow_api)
    config = judge.config
    verifier = CachedVerifier(config, support_backend)
    run_id = make_run_id()
    directory = Path(config.evaluation.output_dir) / run_id.replace(":", "-")
    directory.mkdir(parents=True, exist_ok=False)
    effective = {"config": asdict(config), "limit": limit, "pairs_path": str(path)}
    report = {
        "run_id": run_id,
        "stage": "decision_comparison",
        "status": "failed",
        "config": effective,
        "config_hash": text_hash(json.dumps(effective, sort_keys=True)),
        "code_version": _code_version(),
        "seed": config.verification.seed,
        "input_path": str(path),
        "input_sha256": hashlib.sha256(content).hexdigest(),
        "corpus_sha256": text_hash(json.dumps(chunks, sort_keys=True, ensure_ascii=False)),
        "selected_pair_count": len(selected),
        "selected_input_rows": [r["input_row"] for r in selected],
        "jev": judge.identity,
        "minicheck": verifier.identity,
        "allow_api": allow_api,
        "versions": {name: version(name) for name in ("torch", "transformers", "httpx")},
        "report_path": str(directory / "report.md"),
    }
    records = []
    started = time.perf_counter()
    try:
        with (directory / "selection.jsonl").open("x", encoding="utf-8") as stream:
            for item in selected:
                stream.write(json.dumps(item, ensure_ascii=True) + "\n")
        for item in selected:
            record = dict(item, jev={}, minicheck={})
            records.append(record)
            evidence = chunks[item["chunk_id"]]["text"]
            record["jev"] = judge.verify(item["claim"], evidence)
            record["jev_cache_hit"] = judge.client.attempts[-1]["cache_hit"]
            local_started = time.perf_counter()
            try:
                record["minicheck"] = verifier.verify(item["claim"], evidence)
            except (ValueError, RuntimeError, OSError, ImportError) as exc:
                record["minicheck"] = {
                    "label": None,
                    "error_type": type(exc).__name__,
                    "token_limit_exceeded": isinstance(exc, ValueError)
                    and "token limit" in str(exc),
                }
            record["minicheck_elapsed_seconds"] = time.perf_counter() - local_started
        report["status"] = (
            "ok" if all(r["minicheck"].get("label") for r in records) else "incomplete"
        )
    except (LLMError, ValueError, OSError, RuntimeError) as exc:
        report["error"] = f"Decision comparison stopped ({type(exc).__name__}): {exc}"
    finally:
        comparable = [r for r in records if r["jev"].get("label") and r["minicheck"].get("label")]
        report["metrics"] = {
            "comparable_pairs": len(comparable),
            "jev_completed_pairs": sum(bool(r["jev"].get("label")) for r in records),
            "minicheck_unverified_pairs": sum(not r["minicheck"].get("label") for r in records),
            "inter_model_agreement": sum(
                r["jev"]["label"] == r["minicheck"]["label"] for r in comparable
            )
            / len(comparable)
            if comparable
            else None,
            "inter_model_kappa": cohens_kappa(
                [r["minicheck"]["label"] for r in comparable],
                [r["jev"]["label"] for r in comparable],
            ),
            "accuracy_against_human_gold": None,
            "human_gold_pair_count": 0,
            "jev_label_counts": dict(
                Counter(r["jev"]["label"] for r in records if r["jev"].get("label"))
            ),
            "minicheck_label_counts": dict(
                Counter(r["minicheck"]["label"] for r in records if r["minicheck"].get("label"))
            ),
        }
        report["usage"] = {
            "backend_calls": judge.client.calls,
            "cache_hits": sum(a["cache_hit"] for a in judge.client.attempts),
            "input_tokens": sum(a.get("billed_input_tokens") or 0 for a in judge.client.attempts),
            "output_tokens": sum(a.get("billed_output_tokens") or 0 for a in judge.client.attempts),
            "unknown_usage_attempts": sum(
                not a["cache_hit"]
                and (a.get("billed_input_tokens") is None or a.get("billed_output_tokens") is None)
                for a in judge.client.attempts
            ),
        }
        report["attempts"] = judge.client.attempts
        report["reported_jev_models"] = sorted(
            {r["jev"]["model"] for r in records if r["jev"].get("model")}
        )
        latencies = [
            r["jev"]["http_elapsed_seconds"]
            for r in records
            if r.get("jev_cache_hit") is False and r["jev"].get("http_elapsed_seconds") is not None
        ]
        report["new_request_median_http_seconds"] = (
            statistics.median(latencies) if latencies else None
        )
        report["verifier_cache_hits"] = verifier.cache_hits
        report["verifier_computed_pairs"] = verifier.computed_pairs
        report["elapsed_seconds"] = time.perf_counter() - started
        report["resources"] = process_resources()
        _write_results(directory, report, records)
        logger.info("Decision comparison %s; report=%s", report["status"], directory)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Jev and MiniCheck on a bounded pilot sample"
    )
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = compare_decisions(
            load_config(args.config), args.pairs, args.limit, allow_api=args.allow_api
        )
        return 0 if report["status"] == "ok" else 1
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        logger.error("Decision comparison failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
