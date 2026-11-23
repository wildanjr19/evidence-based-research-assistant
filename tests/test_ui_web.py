import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest

from rag.ui import service, web
from test_generation import corpus as corpus
from test_ui import demo as demo


@pytest.fixture
def application(demo: tuple, monkeypatch: pytest.MonkeyPatch) -> tuple:
    config, directory, generation = demo
    monkeypatch.setattr(web, "CORPORA", {"Fixture": ("fixture", str(directory), None)})
    monkeypatch.setattr(web, "load_config", lambda _: config)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Web UI tests must not call APIs or load models")

    monkeypatch.setattr(web, "run_question", forbidden)
    monkeypatch.setattr(web, "evaluate_answer_quality", forbidden)
    monkeypatch.setattr(web, "run_diagnostics", forbidden)
    return web.Application(), config, generation


def context(application: tuple) -> tuple:
    app, config, generation = application
    session = web.Session()
    result = app.corpus(session, "0")
    data = dict(corpus="0", fingerprint=result["corpus"]["fingerprint"])
    return app, config, generation, session, data


def test_saved_answer_readonly_refresh_and_quality_once(application, monkeypatch):
    app, config, generation, session, data = context(application)
    before = Path(config.paths.db_path).read_bytes()
    reading = app.action(
        session,
        "demo",
        dict(data, request_id=str(uuid4()), answer_id=generation["answer_id"]),
    )
    assert reading["answer"]["references"][0]["quote"].startswith("Alpha evidence")
    assert app.corpus(session, "0")["current"]["handle"] == reading["handle"]
    calls = []

    def evaluate(selected, answer, **kwargs):
        calls.append(kwargs)
        return dict(status="partial", scores=dict(faithfulness=0, response_relevancy=None))

    monkeypatch.setattr(web, "evaluate_answer_quality", evaluate)
    payload = dict(
        data, handle=reading["handle"], claim_id=reading["answer"]["claims"][0]["claim_id"]
    )
    assert app.action(session, "quality", payload)["scores"]["faithfulness"] == 0
    app.action(session, "quality", payload)
    assert calls == [dict(allow_api=True, claim_id=payload["claim_id"])]
    assert Path(config.paths.db_path).read_bytes() == before


def test_query_duplicate_request_and_failed_attempt_never_repeat(application, monkeypatch):
    app, config, generation, session, data = context(application)
    calls = []

    def generate(question, selected, mode, **kwargs):
        calls.append((question, mode, kwargs))
        return service.load_answer(config, generation["answer_id"])

    monkeypatch.setattr(web, "run_question", generate)
    payload = dict(data, request_id=str(uuid4()), question="Bukti apa?", mode="hybrid")
    first = app.action(session, "question", payload)
    assert app.action(session, "question", payload)["handle"] == first["handle"]
    assert calls == [("Bukti apa?", "hybrid", dict(allow_api=True))]

    def fail(*args, **kwargs):
        calls.append("failed")
        raise RuntimeError("Lost response")

    monkeypatch.setattr(web, "run_question", fail)
    payload["request_id"] = str(uuid4())
    with pytest.raises(RuntimeError):
        app.action(session, "question", payload)
    with pytest.raises(ValueError, match="sudah dicoba"):
        app.action(session, "question", payload)
    assert calls.count("failed") == 1


def test_quality_failure_is_retained_and_claim_scope_checked(application, monkeypatch):
    app, _, generation, session, data = context(application)
    reading = app.action(
        session, "demo", dict(data, request_id=str(uuid4()), answer_id=generation["answer_id"])
    )
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("Evaluator unavailable")

    monkeypatch.setattr(web, "evaluate_answer_quality", fail)
    payload = dict(
        data, handle=reading["handle"], claim_id=reading["answer"]["claims"][0]["claim_id"]
    )
    assert app.action(session, "quality", payload)["scores"]["faithfulness"] is None
    assert app.action(session, "quality", payload)["status"] == "failed"
    assert calls == [1]
    with pytest.raises(ValueError, match="klaim"):
        app.action(session, "quality", dict(payload, claim_id="foreign-claim"))
    with pytest.raises(ValueError, match="Jawaban berubah"):
        app.action(web.Session(), "quality", payload)


def test_config_change_invalidates_current_and_rejects_stale_request(application, monkeypatch):
    app, config, generation, session, data = context(application)
    app.action(
        session, "demo", dict(data, request_id=str(uuid4()), answer_id=generation["answer_id"])
    )
    changed = replace(config, generation=replace(config.generation, model="changed-model"))
    monkeypatch.setattr(web, "load_config", lambda _: changed)
    with pytest.raises(ValueError, match="berubah"):
        app.action(
            session, "question", dict(data, request_id=str(uuid4()), question="Q", mode="bm25")
        )
    assert app.corpus(session, "0")["current"] is None
    with pytest.raises(ValueError, match="Korpus tidak tersedia"):
        app.corpus(session, "../../.env")


@pytest.fixture
def server(application, tmp_path, monkeypatch):
    app, _, _ = application
    (tmp_path / "index.html").write_text('<html lang="id">Fixture</html>', encoding="utf-8")
    monkeypatch.setattr(web, "FRONTEND", tmp_path)
    instance = web.LocalServer(0, app)
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()


def request(server, method="GET", path="/api/corpus", body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_http_same_origin_json_and_static_boundaries(server):
    status, headers, content = request(server)
    assert status == 200
    assert json.loads(content)["corpus"]["chunks"] == 4
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    assert headers["Cache-Control"] == "no-store"
    assert request(server, headers={"Host": "attacker.example"})[0] == 403
    assert request(server, headers={"Origin": "https://attacker.example"})[0] == 403
    assert request(server, "POST", "/api/question", "{}")[0] == 403
    status, _, _ = request(
        server,
        "POST",
        "/api/question",
        "not-json",
        {"X-Requested-With": "BuktiRiset", "Content-Type": "application/json"},
    )
    assert status == 400
    assert request(server, path="/../.env")[0] == 404
    assert request(server, path="/")[0] == 200


def test_http_concurrent_duplicate_submit_and_browser_isolation(server, application, monkeypatch):
    _, config, generation = application
    _, headers, content = request(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    calls = []

    def generate(*args, **kwargs):
        calls.append(1)
        return service.load_answer(config, generation["answer_id"])

    monkeypatch.setattr(web, "run_question", generate)
    payload = json.dumps(
        dict(
            corpus="0",
            fingerprint=json.loads(content)["corpus"]["fingerprint"],
            request_id=str(uuid4()),
            question="Bukti apa?",
            mode="hybrid",
        )
    )
    request_headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "X-Requested-With": "BuktiRiset",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: request(server, "POST", "/api/question", payload, request_headers),
                range(2),
            )
        )
    assert all(result[0] == 200 for result in results)
    assert json.loads(results[0][2])["handle"] == json.loads(results[1][2])["handle"]
    assert calls == [1]
    assert json.loads(request(server)[2])["current"] is None


def test_http_pdf_uses_selected_canonical_source(server, application, monkeypatch):
    from urllib.parse import urlencode

    _, config, _ = application
    metadata = json.loads(request(server)[2])
    calls = []

    def page(selected, paper_id, page_number):
        calls.append((selected, paper_id, page_number))
        return dict(pdf=b"%PDF-source", image=b"PNG-source", filename="source.pdf")

    monkeypatch.setattr(web, "load_pdf_page", page)
    params = urlencode(
        dict(corpus="0", fingerprint=metadata["corpus"]["fingerprint"], paper="paper-id", page=2)
    )
    status, headers, content = request(server, path=f"/api/pdf?{params}")
    assert status == 200 and content == b"%PDF-source"
    assert headers["Content-Type"] == "application/pdf"
    assert headers["Content-Disposition"] == 'attachment; filename="source.pdf"'
    assert request(server, path=f"/api/page?{params}")[2] == b"PNG-source"
    assert calls == [(config, "paper-id", 2), (config, "paper-id", 2)]
