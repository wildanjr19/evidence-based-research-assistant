import json
import logging
import subprocess
import time
from contextlib import closing
from dataclasses import asdict, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from rag.config import Config
from rag.generation.citations import ResponseFormatError, parse_claims
from rag.generation.client import CachedLLM, LLMBackend, LLMError
from rag.generation.prompt import build_messages
from rag.generation.render import render_answer
from rag.generation.store import connect_corpus, finish_run, load_context, start_run
from rag.ids import make_run_id
from rag.indexing.embedding import text_hash
from rag.retrieval.pipeline import MODES, Retriever

logger = logging.getLogger(__name__)


def _code_version() -> str:
    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        )
        dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        return result.strip() + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def generate_answer(
    question: str,
    chunks: list[dict],
    config: Config,
    backend: LLMBackend | None = None,
    allow_api: bool = False,
    mode: str | None = None,
) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string")
    mode = mode or ("hybrid+rerank" if config.retrieval.use_reranker else "hybrid")
    if mode not in MODES:
        raise ValueError("Unknown retrieval mode")
    context, corpus_ids = load_context(chunks, config)
    context_ids = {chunk["chunk_id"] for chunk in context}
    started = time.perf_counter()
    run_id = make_run_id()
    effective = asdict(
        replace(config, retrieval=replace(config.retrieval, use_reranker=mode == "hybrid+rerank"))
    )
    path = Path(config.paths.index_dir) / "reports" / f"generation-{run_id.replace(':', '-')}.json"
    report = {
        "run_id": run_id,
        "answer_id": run_id + ":a01",
        "stage": "generation",
        "status": "failed",
        "question": question,
        "config": effective,
        "config_hash": text_hash(json.dumps(effective, sort_keys=True)),
        "seed": config.verification.seed,
        "code_version": _code_version(),
        "retrieval_mode": mode,
        "started_at": datetime.now(UTC).isoformat(),
        "report_path": str(path),
        "context_chunk_ids": [chunk["chunk_id"] for chunk in context],
        "context_sha256": text_hash(json.dumps(context, sort_keys=True, ensure_ascii=False)),
        "versions": {name: version(name) for name in ("openai", "httpx2")},
        "claims": [],
        "rejected_citations": [],
        "format_failures": [],
        "verification_status": "not_run",
    }
    llm = CachedLLM(config, backend, allow_api)
    report["backend"] = llm.backend_name
    raw_response = None
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("x", encoding="utf-8") as stream,
        closing(connect_corpus(config, writable=True)) as connection,
    ):
        run_started = False
        try:
            start_run(connection, report)
            run_started = True
            if context:
                for attempt in range(2):
                    response = llm.complete(build_messages(question, context, retry=bool(attempt)))
                    raw_response = response.content
                    try:
                        if response.finish_reason != "stop":
                            raise ResponseFormatError("LLM response did not finish normally")
                        claims, rejected = parse_claims(raw_response, corpus_ids, context_ids)
                        report["claims"] = [
                            dict(
                                claim,
                                claim_order=ordinal,
                                claim_id=f"{report['answer_id']}:c{ordinal:02d}",
                            )
                            for ordinal, claim in enumerate(claims, 1)
                        ]
                        report["rejected_citations"] = rejected
                        break
                    except ResponseFormatError as exc:
                        report["format_failures"].append(str(exc))
                        if attempt == 1:
                            raise
            report["status"] = "ok" if report["claims"] else "no_evidence"
            report.update(render_answer(report["claims"], context))
        except (LLMError, ResponseFormatError) as exc:
            report["error"] = str(exc)
            report["markdown"] = "Generasi gagal; lihat laporan run."
            report["references"] = []
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = f"Generation failed ({type(exc).__name__})"
            raise
        finally:
            report["finished_at"] = datetime.now(UTC).isoformat()
            report["elapsed_seconds"] = time.perf_counter() - started
            report["attempts"] = llm.attempts
            report["backend_calls"] = llm.calls
            report["cache_hits"] = sum(a["cache_hit"] for a in llm.attempts)
            for key in ("input_tokens", "output_tokens"):
                report[key] = sum(a.get("billed_" + key) or 0 for a in llm.attempts)
            report["unknown_usage_attempts"] = sum(
                not a["cache_hit"]
                and (a.get("billed_input_tokens") is None or a.get("billed_output_tokens") is None)
                for a in llm.attempts
            )
            report["hallucinated_citation_count"] = sum(
                event["reason"] in {"invalid_id", "not_in_corpus"}
                for event in report["rejected_citations"]
            )
            try:
                if run_started:
                    finish_run(connection, report, raw_response)
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = f"Persistence failed ({type(exc).__name__})"
                raise
            finally:
                json.dump(report, stream, ensure_ascii=True, indent=2, allow_nan=False)
                logger.info("Generation %s; report=%s", report["status"], path)
    return report


def answer_question(
    question: str,
    config: Config,
    mode: str | None = None,
    backend: LLMBackend | None = None,
    allow_api: bool = False,
) -> dict:
    chunks = Retriever(config).retrieve(question, mode)
    return generate_answer(question, chunks, config, backend, allow_api, mode)
