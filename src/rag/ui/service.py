import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from rag.config import Config
from rag.generation.pipeline import generate_answer
from rag.generation.render import render_answer
from rag.generation.store import connect_corpus
from rag.ids import is_valid_chunk_id, make_run_id
from rag.indexing.embedding import text_hash
from rag.indexing.pipeline import load_chunks
from rag.retrieval.pipeline import Retriever
from rag.verification.minicheck import CachedVerifier
from rag.verification.pipeline import verify_answer

MAX_API_CALLS_PER_SUBMIT = 2


def source_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        return (
            value if parsed.scheme == "https" and parsed.hostname and not parsed.username else None
        )
    except ValueError:
        return None


def load_demo(config: Config, directory: Path) -> list[dict]:
    """Bind saved evaluation answers to the exact corpus, without running models."""
    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    with closing(connect_corpus(config)) as connection:
        chunks = {row["chunk_id"]: row for row in load_chunks(connection)}
        digest = text_hash(json.dumps(chunks, sort_keys=True, ensure_ascii=False))
        if metrics["corpus_sha256"] != digest:
            raise ValueError("Korpus berbeda dari run demo. Gunakan config korpus yang sesuai.")
        records = []
        with (directory / "per_question.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                answer_id = record["generation"]["answer_id"]
                stored = connection.execute(
                    "SELECT question FROM answer WHERE answer_id = ?", (answer_id,)
                ).fetchone()
                if stored is None or stored[0] != record["question"]:
                    raise ValueError("Jawaban demo tidak cocok dengan database lokal.")
                records.append(
                    dict(qid=record["qid"], question=record["question"], answer_id=answer_id)
                )
    return records


def load_answer(config: Config, answer_id: str) -> dict:
    with closing(connect_corpus(config)) as connection:
        connection.row_factory = sqlite3.Row
        stored = connection.execute(
            """SELECT answer.question, answer.run_id, run.notes, run.model_gen
               FROM answer JOIN run USING (run_id) WHERE answer_id = ?""",
            (answer_id,),
        ).fetchone()
        if stored is None:
            raise ValueError("Jawaban tidak ditemukan. Pilih contoh lain.")
        notes = json.loads(stored["notes"])
        claims, chunks, verification = [], {}, []
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        for row in connection.execute(
            "SELECT * FROM claim WHERE answer_id = ? ORDER BY claim_order", (answer_id,)
        ).fetchall():
            claim = dict(row)
            identifiers = json.loads(claim["citations"])
            if not isinstance(identifiers, list) or not all(
                is_valid_chunk_id(identifier) for identifier in identifiers
            ):
                raise ValueError("Sitasi tersimpan tidak valid; periksa laporan run.")
            claim["citations"] = []
            for identifier in dict.fromkeys(identifiers):
                chunk = connection.execute(
                    """SELECT chunk.*, paper.title, paper.landing_url, paper.license
                       FROM chunk JOIN paper USING (paper_id) WHERE chunk_id = ?""",
                    (identifier,),
                ).fetchone()
                if chunk is None:
                    raise ValueError("Chunk sitasi hilang dari korpus; periksa database.")
                chunks[identifier] = dict(chunk)
                claim["citations"].append(identifier)
            claim["unsupported"] = bool(claim["unsupported"] or not claim["citations"])
            claims.append(claim)
            if "verification" in tables:
                verification.extend(
                    dict(result)
                    for result in connection.execute(
                        "SELECT * FROM verification WHERE claim_id = ? ORDER BY chunk_id, verifier",
                        (claim["claim_id"],),
                    )
                    if result["chunk_id"] in claim["citations"]
                )
    rendered = render_answer(claims, list(chunks.values()))
    for reference in rendered["references"]:
        chunk = chunks[reference["chunk_id"]]
        reference.update(url=source_url(chunk["landing_url"]), license=chunk["license"])
    return dict(
        rendered,
        answer_id=answer_id,
        run_id=stored["run_id"],
        question=stored["question"],
        model=stored["model_gen"],
        status=notes["status"],
        claims=claims,
        verification=verification,
    )


def support_label(claim: dict, verification: list[dict]) -> str:
    if claim["unsupported"] or not claim["citations"]:
        return "Tidak ada bukti"
    labels = {
        result["chunk_id"]: result["label"]
        for result in verification
        if result["claim_id"] == claim["claim_id"] and result["verifier"] == "minicheck"
    }
    values = [labels.get(identifier) for identifier in claim["citations"]]
    if all(value == "supported" for value in values):
        return "Didukung MiniCheck"
    if any(value in {"not_supported", "partially_supported"} for value in values):
        return "Perlu diperiksa"
    return "Belum diverifikasi"


def run_question(question: str, config: Config, mode: str, *, allow_api: bool = False) -> dict:
    """Keep query writes in a new snapshot; the benchmark database stays read-only."""
    if not question.strip():
        raise ValueError("Tulis pertanyaan sebelum mencari bukti.")
    directory = Path(config.paths.cache_dir) / "ui-runs" / make_run_id().replace(":", "-")
    directory.mkdir(parents=True, exist_ok=False)
    database = directory / "corpus.db"
    with closing(connect_corpus(config)) as source, closing(sqlite3.connect(database)) as target:
        source.backup(target)
    retrieval_config = replace(config, paths=replace(config.paths, db_path=str(database)))
    chunks = Retriever(retrieval_config).retrieve(question, mode)
    query_config = replace(
        retrieval_config,
        paths=replace(retrieval_config.paths, index_dir=str(directory)),
        generation=replace(
            config.generation,
            max_calls_per_run=min(config.generation.max_calls_per_run, MAX_API_CALLS_PER_SUBMIT),
        ),
    )
    generation = generate_answer(question, chunks, query_config, allow_api=allow_api, mode=mode)
    verification = []
    if generation["status"] == "ok":
        verification = verify_answer(generation, query_config, CachedVerifier(query_config))
    answer = load_answer(query_config, generation["answer_id"])
    answer["verification"] = verification
    answer["report_path"] = generation["report_path"]
    answer["api_allowed"] = allow_api
    answer["usage"] = {
        key: generation[key]
        for key in (
            "backend_calls",
            "cache_hits",
            "input_tokens",
            "output_tokens",
            "unknown_usage_attempts",
        )
    }
    return answer
