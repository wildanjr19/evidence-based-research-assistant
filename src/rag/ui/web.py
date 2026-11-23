"""Loopback-only HTTP adapter for the local React evidence reader."""

import argparse
import json
import logging
import mimetypes
import secrets
import sqlite3
from contextlib import suppress
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, RLock
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from rag.config import Config, load_config
from rag.evaluation.answer_quality import MAX_CALLS, MAX_OUTPUT_TOKENS, evaluate_answer_quality
from rag.retrieval.pipeline import MODES
from rag.ui.catalog import CORPORA
from rag.ui.service import (
    MAX_API_CALLS_PER_SUBMIT,
    license_label,
    load_answer,
    load_corpus,
    load_demo,
    load_pdf_page,
    run_diagnostics,
    run_question,
    source_url,
    support_label,
)

logger = logging.getLogger(__name__)
FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "dist"
FAILURE = dict(status="failed", scores=dict(faithfulness=None, response_relevancy=None))


@dataclass
class Session:
    lock: RLock = field(default_factory=RLock)
    identity: tuple[str, str] | None = None
    current: dict | None = None
    requests: dict = field(default_factory=dict)


def string_field(data: dict, name: str, limit: int = 8000) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Nilai {name} kosong atau tidak valid.")
    return value.strip()


class Application:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = Lock()
        self.work_lock = Lock()

    def session(self, cookie: str) -> tuple[str, Session]:
        parsed = SimpleCookie()
        try:
            parsed.load(cookie)
            token = parsed["bukti_session"].value if "bukti_session" in parsed else ""
        except (ValueError, CookieError):
            token = ""
        with self.sessions_lock:
            if token not in self.sessions:
                token = secrets.token_urlsafe(32)
                self.sessions[token] = Session()
            return token, self.sessions[token]

    def context(self, corpus_id: str) -> tuple[Config, dict, str | None]:
        choices = list(CORPORA.values())
        if corpus_id not in [str(i) for i in range(len(choices))]:
            raise ValueError("Korpus tidak tersedia. Pilih korpus dari daftar.")
        config_path, demo_dir, receipt = choices[int(corpus_id)]
        config = load_config(config_path)
        corpus = load_corpus(config, Path(receipt) if receipt else None)
        return config, corpus, demo_dir

    def select(self, session: Session, corpus_id: str, fingerprint: str | None = None) -> tuple:
        config, corpus, demo_dir = self.context(corpus_id)
        if fingerprint is not None and fingerprint != corpus["fingerprint"]:
            raise ValueError("Korpus atau config berubah. Muat ulang halaman sebelum melanjutkan.")
        identity = (corpus_id, corpus["fingerprint"])
        if session.identity != identity:
            session.identity, session.current = identity, None
        return config, corpus, demo_dir

    def corpus(self, session: Session, corpus_id: str) -> dict:
        config, corpus, demo_dir = self.select(session, corpus_id)
        demos, demo_error = [], None
        if demo_dir:
            try:
                demos = load_demo(config, Path(demo_dir))
            except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
                logger.exception("Saved demo is unavailable")
                demo_error = "Demo tidak cocok atau belum tersedia. Periksa snapshot demo lokal."
        papers = [
            dict(
                paper,
                license_label=license_label(paper["license"]),
                url=source_url(paper["landing_url"]),
            )
            for paper in corpus["papers"]
        ]
        return dict(
            corpus=dict(corpus, papers=papers),
            choices=[dict(id=str(i), label=label) for i, label in enumerate(CORPORA)],
            selected=corpus_id,
            modes=list(MODES),
            default_mode="hybrid+rerank" if config.retrieval.use_reranker else "hybrid",
            demos=demos,
            demo_error=demo_error,
            current=session.current,
            limits=dict(
                generator_calls=min(config.generation.max_calls_per_run, MAX_API_CALLS_PER_SUBMIT),
                generator_tokens=config.generation.max_output_tokens,
                evaluator_calls=MAX_CALLS,
                evaluator_tokens=MAX_OUTPUT_TOKENS,
                model=config.generation.model,
                provider=config.generation.provider,
            ),
        )

    def store(self, session: Session, answer: dict) -> dict:
        session.current = dict(
            handle=secrets.token_urlsafe(24), answer=answer, quality={}, diagnostics=None
        )
        return session.current

    def action(self, session: Session, route: str, data: dict) -> dict:
        corpus_id = string_field(data, "corpus", 8)
        fingerprint = string_field(data, "fingerprint", 128)
        config, _, demo_dir = self.select(session, corpus_id, fingerprint)
        if route in {"question", "demo"}:
            request_id = string_field(data, "request_id", 36)
            UUID(request_id)
            identity = (corpus_id, fingerprint, request_id)
            if identity in session.requests:
                result = session.requests[identity]
                if result is None:
                    raise ValueError(
                        "Request sudah dicoba. Periksa laporan lokal sebelum submit baru."
                    )
                return result
            if route == "question":
                question = string_field(data, "question")
                mode = string_field(data, "mode", 32)
                if mode not in MODES:
                    raise ValueError("Metode retrieval tidak tersedia.")
                # Mark before generation so a lost response cannot repeat paid calls.
                session.requests[identity] = None
                answer = run_question(question, config, mode, allow_api=True)
            else:
                if not demo_dir:
                    raise ValueError("Run demo belum tersedia untuk korpus ini.")
                answer_id = string_field(data, "answer_id", 256)
                records = load_demo(config, Path(demo_dir))
                if answer_id not in {record["answer_id"] for record in records}:
                    raise ValueError("Jawaban bukan bagian dari demo korpus aktif.")
                answer = load_answer(config, answer_id)
            result = self.store(session, answer)
            session.requests[identity] = result
            return result
        current = session.current
        if current is None or string_field(data, "handle", 64) != current["handle"]:
            raise ValueError("Jawaban berubah. Muat ulang halaman untuk membaca jawaban aktif.")
        answer = current["answer"]
        if route == "quality":
            claim_id = string_field(data, "claim_id", 256)
            if answer["status"] != "ok" or claim_id not in {
                claim["claim_id"] for claim in answer["claims"]
            }:
                raise ValueError("Evaluasi memerlukan klaim dari jawaban yang selesai.")
            if claim_id not in current["quality"]:
                current["quality"][claim_id] = FAILURE.copy()
                try:
                    current["quality"][claim_id] = evaluate_answer_quality(
                        config, answer, allow_api=True, claim_id=claim_id
                    )
                except (ValueError, RuntimeError, OSError, KeyError):
                    logger.exception("Claim quality evaluation failed")
            return current["quality"][claim_id]
        if route == "diagnostics":
            if current["diagnostics"] is None:
                records = answer["verification"] or run_diagnostics(config, answer)
                current["diagnostics"] = dict(
                    records=records,
                    labels={
                        claim["claim_id"]: support_label(claim, records)
                        for claim in answer["claims"]
                    },
                )
            return current["diagnostics"]
        raise ValueError("Tindakan tidak tersedia.")


class Handler(BaseHTTPRequestHandler):
    server: "LocalServer"

    def respond(self, status: int, content: bytes, content_type: str, filename: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if getattr(self, "session_token", None):
            self.send_header(
                "Set-Cookie",
                f"bukti_session={self.session_token}; HttpOnly; SameSite=Strict; Path=/",
            )
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def json(self, payload: dict, status: int = 200) -> None:
        self.respond(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def trusted(self) -> bool:
        host = self.headers.get("Host", "")
        allowed = {
            f"{name}:{port}"
            for name in ("127.0.0.1", "localhost")
            for port in (self.server.server_port, 5173)
        }
        origin = self.headers.get("Origin")
        return host in allowed and (origin is None or origin == f"http://{host}")

    def dispatch(self, post: bool = False) -> None:
        if not self.trusted() or (post and self.headers.get("X-Requested-With") != "BuktiRiset"):
            self.json(dict(error="Akses hanya dari antarmuka lokal."), 403)
            return
        self.session_token, session = self.server.application.session(
            self.headers.get("Cookie", "")
        )
        try:
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            with session.lock:
                if post:
                    if self.headers.get("Content-Type") != "application/json":
                        raise ValueError("Request harus berupa JSON.")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 16384:
                        raise ValueError("Ukuran request tidak valid.")
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise ValueError("Request harus berupa objek JSON.")
                    route = parsed.path.removeprefix("/api/")
                    if route not in {"question", "demo", "quality", "diagnostics"}:
                        self.json(dict(error="Tindakan tidak tersedia."), 404)
                        return
                    with self.server.application.work_lock:
                        self.json(self.server.application.action(session, route, data))
                elif parsed.path == "/api/corpus":
                    self.json(
                        self.server.application.corpus(session, params.get("corpus", ["0"])[0])
                    )
                elif parsed.path in {"/api/pdf", "/api/page"}:
                    config, _, _ = self.server.application.select(
                        session, params["corpus"][0], params["fingerprint"][0]
                    )
                    source = load_pdf_page(config, params["paper"][0], int(params["page"][0]))
                    if parsed.path == "/api/pdf":
                        self.respond(200, source["pdf"], "application/pdf", source["filename"])
                    else:
                        self.respond(200, source["image"], "image/png")
                elif parsed.path.startswith("/api/"):
                    self.json(dict(error="Resource tidak tersedia."), 404)
                else:
                    self.static(parsed.path)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError, sqlite3.Error):
            logger.exception("Local UI request failed")
            self.json(
                dict(
                    error="Proses lokal gagal. Periksa korpus, config, dan laporan run; "
                    "muat ulang halaman sebelum mencoba lagi."
                ),
                400,
            )

    def static(self, path: str) -> None:
        target = (FRONTEND / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
        if not target.is_relative_to(FRONTEND.resolve()) or not target.is_file():
            self.respond(
                404,
                b"Frontend belum dibangun. Jalankan npm run build di frontend/.",
                "text/plain; charset=utf-8",
            )
            return
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            kind = "text/javascript"
        self.respond(200, target.read_bytes(), kind)

    def do_GET(self) -> None:
        self.dispatch()

    def do_POST(self) -> None:
        self.dispatch(post=True)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("Local HTTP %s", args[1] if len(args) > 1 else "request")


class LocalServer(ThreadingHTTPServer):
    def __init__(self, port: int, application: Application | None = None) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.application = application or Application()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bukti Riset: local React UI and bounded RAG API")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with LocalServer(args.port) as server:
        logger.info("Bukti Riset: http://127.0.0.1:%s", server.server_port)
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
