import json
from dataclasses import replace
from pathlib import Path

import httpx
import pymupdf
import pytest

from rag.ingestion.bibliography import import_bibliography
from rag.ingestion.download_http import BudgetExhausted, DownloadHTTP, load_download_settings
from rag.ingestion.downloads import ArticlePage, article_pdf, download_bibliography, validate_pdf


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr("rag.ingestion.download_http.time.sleep", lambda _: None)
    base = load_download_settings(Path("configs/skripsi-download.yaml"))
    return replace(
        base,
        cache_dir=str(tmp_path / "cache"),
        budget_path=str(tmp_path / "budget.json"),
        output_dir=str(tmp_path / "output"),
        allowed_hosts=["api.crossref.org", "aclanthology.org"],
    )


def test_redirects_failures_and_restarts_share_budget(settings):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "/failed"})
        return httpx.Response(503)

    settings = replace(settings, max_requests=2)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = DownloadHTTP(settings, client, True)
    with pytest.raises(httpx.HTTPStatusError):
        first.get("https://api.crossref.org/redirect")
    second = DownloadHTTP(settings, client, True)
    with pytest.raises(BudgetExhausted):
        second.get("https://api.crossref.org/new")
    assert len(calls) == 2
    assert [e["status"] for e in second.ledger["requests"]] == [302, 503]


def test_offline_cache_and_hash_validation(settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"fixture", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    online = DownloadHTTP(settings, client, True)
    assert online.get("https://aclanthology.org/fixture")[0] == b"fixture"
    offline = DownloadHTTP(settings, client, False)
    assert offline.get("https://aclanthology.org/fixture")[0] == b"fixture"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="cache miss"):
        offline.get("https://aclanthology.org/missing")
    next(Path(settings.cache_dir).glob("*.bin")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash differs"):
        offline.get("https://aclanthology.org/fixture")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/a",
        "https://127.0.0.1/a",
        "file:///a",
        "https://aclanthology.org.evil.test/a",
        "https://user:secret@aclanthology.org/a",
    ],
)
def test_rejects_unapproved_urls_before_requests(settings, url):
    http = DownloadHTTP(
        settings,
        httpx.Client(
            transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected network request"))
        ),
        True,
    )
    with pytest.raises(ValueError):
        http.get(url)
    assert http.ledger["requests"] == []


def test_rejects_redirect_outside_sources(settings):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "https://localhost/private"})
        )
    )
    http = DownloadHTTP(settings, client, True)
    with pytest.raises(ValueError, match="outside"):
        http.get("https://aclanthology.org/a")
    assert len(http.ledger["requests"]) == 1


def test_size_limit_and_pdf_attempt_limit(settings):
    settings = replace(settings, max_pdfs=1, max_pdf_bytes=5)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"%PDF-too-large"))
    )
    http = DownloadHTTP(settings, client, True)
    with pytest.raises(ValueError, match="size limit"):
        http.get("https://aclanthology.org/a.pdf", pdf=True)
    with pytest.raises(BudgetExhausted, match="PDF attempt"):
        http.get("https://aclanthology.org/b.pdf", pdf=True)
    assert len(http.ledger["requests"]) == 1


def test_transport_failure_has_no_retry(settings):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("fixture", request=request)

    http = DownloadHTTP(settings, httpx.Client(transport=httpx.MockTransport(handler)), True)
    with pytest.raises(httpx.ConnectError):
        http.get("https://api.crossref.org/a")
    assert len(calls) == len(http.ledger["requests"]) == 1


def test_rejects_changed_budget(settings):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    http = DownloadHTTP(settings, client, True)
    http.get("https://api.crossref.org/a")
    with pytest.raises(ValueError, match="authorization"):
        DownloadHTTP(replace(settings, max_requests=31), client, True)
    assert json.loads(Path(settings.budget_path).read_text())["max_requests"] == 30


BIB = """@article{fixture, title={Synthetic Study About Research Evidence},
    author={Jane Doe}, year={2024}, doi={10.1234/fixture}}
@misc{pending, title={Reference Without DOI}, author={John Other}, year={2023}}
"""
WORK = {
    "DOI": "10.1234/fixture",
    "title": ["Synthetic Study About Research Evidence"],
    "author": [{"family": "Doe", "given": "Jane"}],
    "published": {"date-parts": [[2024]]},
    "resource": {"primary": {"URL": "https://aclanthology.org/fixture/"}},
}
HTML = """<meta name="citation_doi" content="10.1234/fixture">
<meta name="citation_title" content="Synthetic Study About Research Evidence">
<meta name="citation_pdf_url" content="https://aclanthology.org/fixture.pdf">
<a rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY</a>
<footer><a href="https://creativecommons.org/licenses/by-nc-sa/3.0/">Other</a></footer>"""


def fixture_pdf(text="Synthetic Study About Research Evidence\nJane Doe\n2024"):
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), text)
        return document.tobytes()


def pilot(settings, tmp_path):
    source = tmp_path / "refs.bib"
    source.write_text(BIB, encoding="utf-8")
    run, _ = import_bibliography(source, tmp_path / "refs")
    return replace(settings, bibliography_run=str(run), preferred_keys=["fixture"], max_pdfs=1)


def transport(calls, *, work=None, page=HTML, pdf=None, pdf_type="application/pdf"):
    def handler(request):
        calls.append(str(request.url))
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": WORK if work is None else work})
        if request.url.path == "/fixture/":
            return httpx.Response(200, text=page, headers={"content-type": "text/html"})
        if request.url.path == "/fixture.pdf":
            return httpx.Response(
                200,
                content=fixture_pdf() if pdf is None else pdf,
                headers={"content-type": pdf_type},
            )
        raise AssertionError(f"Unexpected fixture URL: {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pilot_download_and_offline_replay_do_not_duplicate_or_mutate(tmp_path, settings):
    settings = pilot(settings, tmp_path)
    calls = []
    client = transport(calls)
    first, report = download_bibliography(settings, allow_network=True, client=client)
    assert report["counts"] == {"pdf_ready": 1, "not_attempted": 1}
    ready = report["references"][0]
    assert ready["license"] == "CC-BY-4.0"
    assert ready["pages"] == 1
    assert ready["title_word_coverage"] == 1
    assert Path(ready["pdf_path"]).is_file()
    second, replay = download_bibliography(settings, client=client)
    assert first != second
    assert report["references"] == replay["references"]
    assert replay["request_count_this_run"] == 0
    assert replay["cache_hits"] == len(calls) == 3
    assert len(list(Path(settings.output_dir).glob("pdf/*.pdf"))) == 1
    assert not list(tmp_path.rglob("*.db"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("DOI", "10.1234/wrong"),
        ("title", ["Different article"]),
        ("published", {"date-parts": [[1999]]}),
        ("author", [{"family": "Other"}]),
    ],
)
def test_metadata_mismatch_prevents_pdf_download(tmp_path, settings, field, value):
    settings = pilot(settings, tmp_path)
    calls = []
    _, report = download_bibliography(
        settings, allow_network=True, client=transport(calls, work={**WORK, field: value})
    )
    assert report["references"][0]["status"] == "needs_manual_match"
    assert not any(url.endswith(".pdf") for url in calls)


def test_missing_license_prevents_pdf_download(tmp_path, settings):
    settings = pilot(settings, tmp_path)
    calls = []
    page = "\n".join(HTML.splitlines()[:3])
    _, report = download_bibliography(
        settings, allow_network=True, client=transport(calls, page=page)
    )
    assert report["references"][0]["status"] == "license_unverified"
    assert not any(url.endswith(".pdf") for url in calls)


@pytest.mark.parametrize(
    "pdf,media",
    [
        (b"<html>Not a PDF</html>", "text/html"),
        (b"%PDF-1.7 invalid fixture", "application/pdf"),
        (fixture_pdf("Wrong paper\nJohn Other\n1999"), "application/pdf"),
    ],
)
def test_bad_or_mismatched_pdf_is_not_admitted(tmp_path, settings, pdf, media):
    settings = pilot(settings, tmp_path)
    _, report = download_bibliography(
        settings, allow_network=True, client=transport([], pdf=pdf, pdf_type=media)
    )
    expected = "download_failed" if media == "text/html" else "needs_manual_match"
    assert report["references"][0]["status"] == expected
    assert not list(Path(settings.output_dir).glob("pdf/*.pdf"))


def test_publisher_license_without_rel_requires_pdf_confirmation(settings):
    entry = {
        "doi": "10.1234/fixture",
        "metadata": {
            "title": "Synthetic Study About Research Evidence",
            "author": "Jane Doe",
            "year": "2024",
        },
    }
    page = ArticlePage()
    page.feed(HTML.replace('rel="license"', "").split("<footer>")[0])
    candidate = article_pdf(entry, WORK, page, "https://aclanthology.org/fixture/", settings)
    with pytest.raises(ValueError, match="not confirmed"):
        validate_pdf(fixture_pdf(), "application/pdf", entry, candidate, settings)
    confirmed = fixture_pdf(
        "Synthetic Study About Research Evidence\nJane Doe 2024\n"
        "https://creativecommons.org/licenses/by/4.0/"
    )
    assert validate_pdf(confirmed, "application/pdf", entry, candidate, settings)[
        "license_url_in_pdf"
    ]


def test_author_affiliation_numbers_do_not_change_name_match(settings):
    entry = {
        "doi": "10.1234/fixture",
        "metadata": {
            "title": "Synthetic Study About Research Evidence",
            "author": "Jane Doe",
            "year": "2024",
        },
    }
    candidate = {
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence": "article_rel_license",
    }
    pdf = fixture_pdf("Synthetic Study About Research Evidence\nJane Doe1*\n2024")
    assert validate_pdf(pdf, "application/pdf", entry, candidate, settings)["first_author_matched"]


def test_complete_html_response_spends_request_but_not_pdf_slot(settings):
    settings = replace(settings, max_pdfs=1)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"<html>Unavailable</html>"
                if request.url.path == "/bad"
                else b"%PDF-fixture",
            )
        )
    )
    http = DownloadHTTP(settings, client, True)
    http.get("https://aclanthology.org/bad", pdf=True)
    assert http.pdf_slots_used() == 0
    http.get("https://aclanthology.org/good", pdf=True)
    assert http.pdf_slots_used() == 1
    with pytest.raises(BudgetExhausted):
        http.get("https://aclanthology.org/extra", pdf=True)
    assert len(http.ledger["requests"]) == 2


def test_unknown_explicit_license_does_not_fall_back_to_footer(settings):
    entry = {
        "doi": "10.1234/fixture",
        "metadata": {"title": "Synthetic Study About Research Evidence"},
    }
    page = ArticlePage()
    page.feed(
        HTML.replace("licenses/by/4.0", "licenses/by-nc/4.0")
        + '<a href="https://creativecommons.org/licenses/by/4.0/">Footer</a>'
    )
    with pytest.raises(ValueError, match="unrecognized"):
        article_pdf(entry, WORK, page, "https://aclanthology.org/fixture/", settings)


def test_existing_modified_pdf_is_not_overwritten(tmp_path, settings):
    settings = pilot(settings, tmp_path)
    _, report = download_bibliography(settings, allow_network=True, client=transport([]))
    path = Path(report["references"][0]["pdf_path"])
    path.write_bytes(b"changed by user")
    _, repeated = download_bibliography(settings, client=transport([]))
    assert repeated["references"][0]["status"] == "needs_manual_match"
    assert path.read_bytes() == b"changed by user"


def test_campaign_lock_is_not_deleted_by_second_runner(tmp_path, settings):
    settings = pilot(settings, tmp_path)
    lock = Path(settings.budget_path).with_suffix(".lock")
    lock.write_text("another runner", encoding="utf-8")
    with pytest.raises(ValueError, match="Campaign locked"):
        download_bibliography(settings, client=transport([]))
    assert lock.read_text(encoding="utf-8") == "another runner"


def test_prior_attempt_status_is_preserved_after_pilot_limit(tmp_path, settings):
    settings = pilot(settings, tmp_path)
    _, first = download_bibliography(settings, allow_network=True, client=transport([]))
    past = dict(first)
    past["references"] = [dict(r) for r in first["references"]]
    past["references"][1].update(status="needs_manual_match", reason="known prior mismatch")
    history = Path(settings.output_dir) / "prior-history"
    history.mkdir()
    (history / "report.json").write_text(json.dumps(past), encoding="utf-8")
    _, replay = download_bibliography(settings, client=transport([]))
    assert replay["references"][1]["status"] == "needs_manual_match"
    assert not replay["references"][1]["attempted_this_run"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_requests", True),
        ("max_pdfs", 0),
        ("request_delay_seconds", 0.1),
        ("min_title_coverage", 2),
        ("allowed_hosts", "localhost"),
    ],
)
def test_download_settings_validation(tmp_path, field, value):
    import yaml

    raw = yaml.safe_load(Path("configs/skripsi-download.yaml").read_text())
    raw[field] = value
    config = tmp_path / "invalid.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_download_settings(config)


def test_download_cli_defaults_to_offline(tmp_path, settings, monkeypatch):
    from rag.ingestion.__main__ import main

    settings = pilot(settings, tmp_path)
    calls = []
    client = transport(calls)
    download_bibliography(settings, allow_network=True, client=client)
    monkeypatch.setattr("rag.ingestion.download_http.load_download_settings", lambda _: settings)
    monkeypatch.setattr("rag.ingestion.downloads.httpx.Client", lambda **_: client)
    monkeypatch.setattr("sys.argv", ["rag.ingestion", "download-bib"])
    assert main() == 0
    assert len(calls) == 3
