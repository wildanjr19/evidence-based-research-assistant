import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

import httpx
import pytest

from rag.config import Config, load_config
from rag.files import atomic_write
from rag.ingestion.__main__ import main
from rag.ingestion.arxiv import ArxivClient, Paper, parse_license_record
from rag.ingestion.pipeline import discover, fetch, load_candidates

FIXTURES = Path(__file__).parent / "fixtures"
FEED = (FIXTURES / "arxiv_feed.xml").read_bytes()
RAW_RECORD = (FIXTURES / "arxiv_raw.xml").read_bytes()
PDF = b"%PDF-1.7\nSynthetic fixture bytes; no actual paper content.\n%%EOF\n"


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setattr("rag.ingestion.arxiv.time.sleep", lambda seconds: None)
    base = load_config(Path(__file__).resolve().parents[1] / "configs" / "config.yaml")
    return replace(
        base,
        ingestion=replace(base.ingestion, max_papers=2, page_size=1),
        paths=replace(
            base.paths,
            raw_dir=str(tmp_path / "raw"),
            cache_dir=str(tmp_path / "cache"),
            db_path=str(tmp_path / "corpus.db"),
        ),
    )


def client_for(
    config: Config,
    requests: list[httpx.Request],
    *,
    feed: bytes = FEED,
    raw: bytes = RAW_RECORD,
    pdf: bytes = PDF,
    status: int = 200,
) -> ArxivClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/query":
            return httpx.Response(status, content=feed)
        if request.url.path == "/oai":
            return httpx.Response(status, content=raw)
        if request.url.path.startswith("/pdf/"):
            return httpx.Response(status, content=pdf)
        raise AssertionError(f"Unexpected request: {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ArxivClient(config.ingestion, Path(config.paths.cache_dir), http)


def test_discovery_extracts_licensed_versioned_metadata(config: Config) -> None:
    requests: list[httpx.Request] = []
    papers = discover(config, client_for(config, requests))
    assert len(papers) == 1
    paper = papers[0]
    assert paper.paper_id == "arxiv:2401.12345v1"
    assert paper.title == "Synthetic RAG evaluation fixture"
    assert paper.authors == ["Fixture Author"]
    assert paper.year == 2024
    assert paper.doi == "10.0000/synthetic-fixture"
    assert paper.license == "CC-BY-4.0"
    assert paper.license_url == "http://creativecommons.org/licenses/by/4.0/"
    assert load_candidates(Path(config.paths.raw_dir) / "candidates.jsonl", 2) == papers
    assert len(requests) == 2
    assert requests[0].url.params["search_query"] == config.ingestion.query
    assert requests[1].url.params["identifier"] == "oai:arXiv.org:2401.12345"
    assert not Path(config.paths.db_path).exists()


def test_pagination_and_limit_include_rejected_hits(config: Config) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/query":
            offset = int(request.url.params["start"])
            assert request.url.params["max_results"] == "1"
            return httpx.Response(
                200,
                content=FEED.replace(b">1</opensearch", b">100</opensearch").replace(
                    b"2401.12345", f"2401.{12345 + offset}".encode()
                ),
            )
        identifier = request.url.params["identifier"].rsplit(":", 1)[1].encode()
        raw = RAW_RECORD.replace(b"2401.12345", identifier)
        if identifier.endswith(b"12345"):
            raw = raw.replace(b"<license>", b"<missing>").replace(b"</license>", b"</missing>")
        return httpx.Response(200, content=raw)

    client = ArxivClient(
        config.ingestion,
        Path(config.paths.cache_dir),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    papers = client.discover()
    assert [paper.source_id for paper in papers] == ["2401.12346v1"]
    assert [
        request.url.params["start"] for request in requests if request.url.path == "/api/query"
    ] == ["0", "1"]
    assert len(requests) == 4


@pytest.mark.parametrize(
    "replacement",
    [
        b"",
        b"https://example.org/unknown",
        b"https://creativecommons.org/licenses/by-nc/4.0/",
        b"https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
    ],
)
def test_missing_or_unknown_license_is_logged_and_rejected(
    config: Config,
    caplog: pytest.LogCaptureFixture,
    replacement: bytes,
) -> None:
    raw = RAW_RECORD.replace(b"http://creativecommons.org/licenses/by/4.0/", replacement)
    requests: list[httpx.Request] = []
    with caplog.at_level(logging.WARNING):
        assert discover(config, client_for(config, requests, raw=raw)) == []
    assert "Rejected" in caplog.text and "license" in caplog.text
    assert not any(request.url.path.startswith("/pdf/") for request in requests)


def test_recognized_but_disallowed_license_is_rejected(
    config: Config,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = replace(config, ingestion=replace(config.ingestion, allowed_licenses=["CC0-1.0"]))
    assert client_for(config, []).discover() == []
    assert "not allowed by config" in caplog.text


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (RAW_RECORD.replace(b"2401.12345", b"2401.99999"), "does not match"),
        (RAW_RECORD.replace(b'version="v1"', b'version="v2"'), "differs from latest"),
        (
            b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            b'<error code="idDoesNotExist">missing</error></OAI-PMH>',
            "idDoesNotExist",
        ),
    ],
)
def test_license_record_must_match_exact_latest_version(raw: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_license_record(raw, "2401.12345v1")


def test_unversioned_search_hit_is_not_guessed(
    config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    requests: list[httpx.Request] = []
    assert client_for(config, requests, feed=FEED.replace(b"12345v1", b"12345")).discover() == []
    assert len(requests) == 1
    assert "versioned arXiv ID" in caplog.text


def test_duplicate_search_hits_do_not_repeat_license_requests(config: Config) -> None:
    requests: list[httpx.Request] = []
    feed = FEED.replace(b">1</opensearch", b">2</opensearch")
    papers = client_for(config, requests, feed=feed).discover()
    assert len(papers) == 1
    assert len(requests) == 3


def test_cache_reuses_same_day_metadata_and_requests_are_spaced(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []
    monkeypatch.setattr("rag.ingestion.arxiv.time.monotonic", lambda: 10.0)
    monkeypatch.setattr("rag.ingestion.arxiv.time.sleep", delays.append)
    requests: list[httpx.Request] = []
    first = client_for(config, requests).discover()
    assert client_for(config, requests).discover() == first
    assert len(requests) == 2
    assert delays == [3.0]


@pytest.mark.parametrize("status", [429, 503])
def test_http_failure_stops_without_retry_loop(config: Config, status: int) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(httpx.HTTPStatusError):
        client_for(config, requests, status=status).discover()
    assert len(requests) == 1


def test_empty_results_stop_and_api_error_is_not_a_paper(config: Config) -> None:
    requests: list[httpx.Request] = []
    empty = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
    assert client_for(config, requests, feed=empty).discover() == []
    assert len(requests) == 1
    another = replace(
        config, paths=replace(config.paths, cache_dir=config.paths.cache_dir + "-error")
    )
    error = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>'
        b"http://arxiv.org/api/errors#bad_query</id></entry></feed>"
    )
    with pytest.raises(ValueError, match="error entry"):
        client_for(another, [], feed=error).discover()


def test_fetch_hashes_pdf_and_is_idempotent_without_resetting_parse_status(config: Config) -> None:
    requests: list[httpx.Request] = []
    client = client_for(config, requests)
    discover(config, client)
    assert fetch(config, client) == 1
    with sqlite3.connect(config.paths.db_path) as connection:
        row = connection.execute("SELECT * FROM paper").fetchone()
        assert row[0:3] == ("arxiv:2401.12345v1", "arxiv", "2401.12345v1")
        assert json.loads(row[4]) == ["Fixture Author"]
        assert row[8] == "CC-BY-4.0"
        assert row[11] == hashlib.sha256(PDF).hexdigest()
        assert row[13] == "pending"
        connection.execute("UPDATE paper SET parse_status = 'ok'")
    before = len(requests)
    assert fetch(config, client) == 1
    assert len(requests) == before
    with sqlite3.connect(config.paths.db_path) as connection:
        repeated = connection.execute("SELECT * FROM paper").fetchall()
        assert repeated == [(*row[:-1], "ok")]
    assert (Path(config.paths.raw_dir) / "pdf/arxiv_2401.12345v1.pdf").read_bytes() == PDF


@pytest.mark.parametrize("pdf", [b"<html>upstream error</html>", b"%PDF-" + b"x" * 200])
def test_failed_pdf_is_not_saved_or_inserted(config: Config, pdf: bytes) -> None:
    config = replace(config, ingestion=replace(config.ingestion, max_pdf_bytes=100))
    client = client_for(config, [], pdf=pdf)
    discover(config, client)
    with pytest.raises(ValueError, match="not a PDF|exceeds"):
        fetch(config, client)
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper").fetchone()[0] == 0
    assert not (Path(config.paths.raw_dir) / "pdf/arxiv_2401.12345v1.pdf").exists()


def test_changed_pdf_is_refused_without_changing_metadata(config: Config) -> None:
    client = client_for(config, [])
    paper = discover(config, client)[0]
    fetch(config, client)
    path = Path(config.paths.raw_dir) / "pdf" / paper.filename
    path.write_bytes(b"%PDF-1.7 changed bytes")
    with pytest.raises(ValueError, match="hash differs"):
        fetch(config, client)
    with sqlite3.connect(config.paths.db_path) as connection:
        assert (
            connection.execute("SELECT pdf_sha256 FROM paper").fetchone()[0]
            == hashlib.sha256(PDF).hexdigest()
        )


def test_fetch_rechecks_license_policy_before_downloading(config: Config) -> None:
    client = client_for(config, [])
    discover(config, client)
    config = replace(config, ingestion=replace(config.ingestion, allowed_licenses=["CC0-1.0"]))
    requests: list[httpx.Request] = []
    assert fetch(config, client_for(config, requests)) == 0
    assert requests == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("source_id", "../../outsidev1"),
        ("paper_id", "arxiv:2401.99999v1"),
        ("landing_url", "https://example.org/abs/2401.12345v1"),
        ("authors", "not a list"),
        ("license_url", "https://example.org/fake"),
    ],
)
def test_candidate_file_is_validated(config: Config, key: str, value: object) -> None:
    client = client_for(config, [])
    discover(config, client)
    path = Path(config.paths.raw_dir) / "candidates.jsonl"
    raw = json.loads(path.read_text())
    raw[key] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid candidate at line 1"):
        fetch(config, client)
    assert not Path(config.paths.db_path).exists()


def test_legacy_id_uses_safe_filename_and_preserves_canonical_id() -> None:
    paper = Paper(
        "hep-th/9901001v2",
        "Synthetic fixture",
        ["Fixture"],
        1999,
        None,
        None,
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
    )
    assert paper.filename == "arxiv_hep-th_9901001v2.pdf"
    assert paper.paper_id == "arxiv:hep-th/9901001v2"


def test_atomic_write_preserves_previous_content_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "candidates.jsonl"
    path.write_bytes(b"previous")

    def fail_replace(*args: object) -> None:
        raise OSError("fixture failure")

    monkeypatch.setattr("rag.files.os.replace", fail_replace)
    with pytest.raises(OSError, match="fixture failure"):
        atomic_write(path, b"new")
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


def test_cli_routes_both_stages_without_live_requests(
    config: Config,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(asdict(config)), encoding="utf-8")
    client = client_for(config, [])
    monkeypatch.setattr("rag.ingestion.__main__.ArxivClient", lambda *args: client)
    for stage in ("discover", "fetch"):
        monkeypatch.setattr("sys.argv", ["rag.ingestion", stage, "--config", str(path)])
        assert main() == 0
    monkeypatch.setattr(
        "sys.argv", ["rag.ingestion", "fetch", "--config", str(tmp_path / "missing")]
    )
    assert main() == 1
