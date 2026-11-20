import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rag.generation.client import Completion, LLMError, OpenAIBackend
from rag.indexing.embedding import text_hash
from rag.indexing.pipeline import load_chunks
from rag.ui import service
from rag.verification.minicheck import CachedVerifier
from rag.verification.pipeline import verify_answer
from test_generation import FIRST, SECOND, FakeLLM, completion
from test_generation import corpus as corpus
from test_verification import FakeSupport


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import httpx2
    import requests

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("UI tests must not download models or call paid APIs")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "send", forbidden)


@pytest.fixture
def demo(corpus: tuple, tmp_path: Path) -> tuple:
    config, rows = corpus
    generation = service.generate_answer(
        "Compare the evidence.",
        rows[:2],
        config,
        FakeLLM(
            [
                completion(
                    [
                        {"text": "<script>alert('claim')</script>", "citations": [FIRST, SECOND]},
                        {"text": "A claim without evidence.", "citations": []},
                    ]
                )
            ]
        ),
    )
    verify_answer(generation, config, CachedVerifier(config, FakeSupport()))
    empty = service.generate_answer("An unanswerable question.", [], config, FakeLLM([]))
    with sqlite3.connect(config.paths.db_path) as connection:
        chunks = {row["chunk_id"]: row for row in load_chunks(connection)}
    directory = tmp_path / "evaluation"
    directory.mkdir()
    (directory / "metrics.json").write_text(
        json.dumps(
            dict(corpus_sha256=text_hash(json.dumps(chunks, sort_keys=True, ensure_ascii=False)))
        ),
        encoding="utf-8",
    )
    (directory / "per_question.jsonl").write_text(
        "\n".join(
            json.dumps(dict(qid=str(i), question=answer["question"], generation=answer))
            for i, answer in enumerate([generation, empty])
        ),
        encoding="utf-8",
    )
    return config, directory, generation


def test_demo_readonly_canonical_evidence_and_verification(demo: tuple) -> None:
    config, directory, generation = demo
    before = Path(config.paths.db_path).read_bytes()
    records = service.load_demo(config, directory)
    answer = service.load_answer(config, records[0]["answer_id"])
    assert answer["question"] == generation["question"]
    assert answer["references"][0]["quote"] == "Alpha evidence supports the first result."
    assert answer["references"][0]["page_start"] == 1
    assert answer["references"][0]["url"].startswith("https://arxiv.org/")
    assert (
        service.support_label(answer["claims"][0], answer["verification"]) == "Didukung MiniCheck"
    )
    assert service.support_label(answer["claims"][1], answer["verification"]) == "Tidak ada bukti"
    assert not service.load_answer(config, records[1]["answer_id"])["claims"]
    assert Path(config.paths.db_path).read_bytes() == before


def test_demo_rejects_different_corpus_and_missing_answer(demo: tuple) -> None:
    config, directory, _ = demo
    metrics = directory / "metrics.json"
    original = metrics.read_text()
    metrics.write_text(json.dumps(dict(corpus_sha256="wrong")))
    with pytest.raises(ValueError, match="Korpus berbeda"):
        service.load_demo(config, directory)
    metrics.write_text(original)
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("UPDATE answer SET question='changed'")
    with pytest.raises(ValueError, match="tidak cocok"):
        service.load_demo(config, directory)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["supported", "supported"], "Didukung MiniCheck"),
        (["supported", None], "Belum diverifikasi"),
        (["supported", "not_supported"], "Perlu diperiksa"),
        (["partially_supported", None], "Perlu diperiksa"),
        ([None, None], "Belum diverifikasi"),
    ],
)
def test_support_requires_every_citation_and_ignores_judge(labels: list, expected: str) -> None:
    claim = dict(claim_id="c", citations=[FIRST, SECOND], unsupported=False)
    records = [
        dict(claim_id="c", chunk_id=identifier, verifier="minicheck", label=label)
        for identifier, label in zip(claim["citations"], labels, strict=True)
    ]
    records.append(dict(claim_id="c", chunk_id=FIRST, verifier="llm_judge", label="supported"))
    assert service.support_label(claim, records) == expected


@pytest.mark.parametrize(
    "url", [None, "javascript:alert(1)", "http://example.com", "https://u@host/", "https://[bad"]
)
def test_source_links_only_allow_https_without_credentials(url: str | None) -> None:
    assert service.source_url(url) is None


def test_cached_query_failure_uses_separate_database(corpus: tuple) -> None:
    config, _ = corpus
    before = Path(config.paths.db_path).read_bytes()
    answer = service.run_question("Alpha evidence uncached question", config, "bm25")
    assert answer["status"] == "failed"
    assert answer["claims"] == []
    assert Path(config.paths.db_path).read_bytes() == before
    report = json.loads(Path(answer["report_path"]).read_text())
    assert report["backend_calls"] == 0
    assert report["config"]["paths"]["db_path"] != config.paths.db_path


def test_query_verifies_cached_answer_and_preserves_unknown(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows = corpus
    original = service.generate_answer

    class FixedRetriever:
        def __init__(self, selected: object) -> None:
            pass

        def retrieve(self, question: str, mode: str) -> list[dict]:
            return rows[:1]

    def generate(question: str, chunks: list, selected: object, **kwargs: object) -> dict:
        assert kwargs["allow_api"] is False
        return original(
            question,
            chunks,
            selected,
            FakeLLM([completion([dict(text="Alpha result", citations=[FIRST])])]),
        )

    monkeypatch.setattr(service, "Retriever", FixedRetriever)
    monkeypatch.setattr(service, "generate_answer", generate)
    monkeypatch.setattr(
        service,
        "CachedVerifier",
        lambda selected: CachedVerifier(selected, FakeSupport([float("nan")])),
    )
    answer = service.run_question("Alpha result?", config, "hybrid+rerank")
    assert answer["status"] == "ok"
    assert answer["verification"][0]["label"] is None
    assert (
        service.support_label(answer["claims"][0], answer["verification"]) == "Belum diverifikasi"
    )


def launch_app(demo_dir: str) -> None:
    from rag.ui.app import main

    main(demo_dir=demo_dir)


def app_test(demo: tuple, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    config, directory, _ = demo
    monkeypatch.setattr("rag.ui.app.load_config", lambda _: config)
    return AppTest.from_function(launch_app, kwargs=dict(demo_dir=str(directory))).run()


def test_app_demo_empty_answer_quotes_and_no_evidence(
    demo: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_test(demo, monkeypatch)
    assert not app.exception
    assert "Pilih contoh" in app.info[0].value
    app.selectbox[0].select(0).run()
    assert not app.exception
    assert any("Tidak ada bukti" in text.value for text in app.markdown)
    assert any("Alpha evidence" in text.value for text in app.text)
    assert any("<script>" in text.value for text in app.text)
    app.selectbox[0].select(1).run()
    assert "Tidak ada bukti" in app.info[0].value


def test_app_query_validation_submit_and_rerun(
    demo: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer = service.load_answer(demo[0], demo[2]["answer_id"])
    calls = []

    def query(question: str, config: object, mode: str, *, allow_api: bool = False) -> dict:
        calls.append((question, mode, allow_api))
        return answer

    monkeypatch.setattr("rag.ui.app.run_question", query)
    app = app_test(demo, monkeypatch)
    app.radio[0].set_value("Tanya korpus").run()
    assert app.checkbox[0].value is False
    app.button[0].click().run()
    assert "Tulis pertanyaan" in app.error[0].value
    app.text_area[0].set_value("  Compare the evidence.  ")
    app.button[0].click().run()
    assert not app.exception
    assert calls == [("Compare the evidence.", "hybrid+rerank", False)]
    app.run()
    assert len(calls) == 1
    assert any("Alpha evidence" in text.value for text in app.text)
    app.checkbox[0].check()
    app.button[0].click().run()
    assert calls[-1] == ("Compare the evidence.", "hybrid+rerank", True)
    app.run()
    assert len(calls) == 2


def test_app_reports_missing_demo_and_config(demo: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rag.ui.app.load_config",
        lambda _: replace(demo[0], paths=replace(demo[0].paths, db_path="missing.db")),
    )
    app = AppTest.from_function(launch_app, kwargs=dict(demo_dir=str(demo[1]))).run()
    assert not app.exception
    assert "Korpus belum tersedia" in app.error[0].value

    def invalid(_: str) -> None:
        raise ValueError("invalid config")

    monkeypatch.setattr("rag.ui.app.load_config", invalid)
    app.run()
    assert "Config tidak dapat dibaca" in app.error[0].value


def test_api_opt_in_generates_caches_and_reports_usage_without_network(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = corpus
    before = Path(config.paths.db_path).read_bytes()
    observed = []

    def complete(self: object, messages: list, selected: object) -> Completion:
        observed.append(selected)
        return completion([dict(text="Alpha evidence is reported.", citations=[FIRST])])

    monkeypatch.setattr(OpenAIBackend, "complete", complete)
    monkeypatch.setattr(
        service, "CachedVerifier", lambda selected: CachedVerifier(selected, FakeSupport())
    )
    question = "What does the Alpha evidence report?"
    missing = service.run_question(question, config, "bm25")
    assert missing["status"] == "failed"
    assert not observed
    generated = service.run_question(question, config, "bm25", allow_api=True)
    assert generated["status"] == "ok"
    assert len(observed) == 1
    assert observed[0].generation.max_calls_per_run == 2
    assert generated["usage"] == dict(
        backend_calls=1, cache_hits=0, input_tokens=100, output_tokens=20, unknown_usage_attempts=0
    )
    replay = service.run_question(question, config, "bm25")
    assert replay["status"] == "ok"
    assert replay["api_allowed"] is False
    assert replay["usage"]["backend_calls"] == 0
    assert replay["usage"]["cache_hits"] == 1
    assert len(observed) == 1
    assert Path(config.paths.db_path).read_bytes() == before
    assert config.generation.max_calls_per_run == 200


@pytest.mark.parametrize("configured, expected", [(1, 1), (60, 2)])
def test_ui_api_request_limit_includes_format_retry(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch, configured: int, expected: int
) -> None:
    config, _ = corpus
    config = replace(config, generation=replace(config.generation, max_calls_per_run=configured))
    observed = []

    def invalid(self: object, messages: list, selected: object) -> Completion:
        observed.append(selected.generation.max_calls_per_run)
        return Completion("not JSON", "fixture-model", 100, 10)

    monkeypatch.setattr(OpenAIBackend, "complete", invalid)
    answer = service.run_question("Alpha evidence format test", config, "bm25", allow_api=True)
    assert answer["status"] == "failed"
    assert len(observed) == expected
    assert answer["usage"]["backend_calls"] == expected
    assert observed == [expected] * expected
    report = json.loads(Path(answer["report_path"]).read_text())
    assert report["config"]["generation"]["max_calls_per_run"] == expected


def test_api_permission_does_not_call_provider_without_evidence(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = corpus

    def forbidden(*args: object) -> None:
        raise AssertionError("No evidence must not call the provider")

    monkeypatch.setattr(OpenAIBackend, "complete", forbidden)
    answer = service.run_question("!!!", config, "bm25", allow_api=True)
    assert answer["status"] == "no_evidence"
    assert answer["usage"]["backend_calls"] == 0
    assert answer["claims"] == []


def test_api_missing_key_is_failure_not_abstention(
    corpus: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _ = corpus

    def missing_key(variable: str) -> None:
        raise LLMError(f"Missing {variable}; set it in the environment or .env")

    monkeypatch.setattr("rag.generation.client._api_key", missing_key)
    answer = service.run_question("Alpha evidence key test", config, "bm25", allow_api=True)
    assert answer["status"] == "failed"
    assert answer["api_allowed"] is True
    assert answer["usage"]["unknown_usage_attempts"] == 1
    assert answer["claims"] == []


def test_api_transport_error_is_not_retried(corpus: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _ = corpus
    calls = []

    def failed(*args: object) -> None:
        calls.append(1)
        raise OSError("fixture connection failure")

    monkeypatch.setattr(OpenAIBackend, "complete", failed)
    answer = service.run_question("Alpha evidence transport test", config, "bm25", allow_api=True)
    assert answer["status"] == "failed"
    assert answer["usage"]["backend_calls"] == 1
    assert len(calls) == 1


def test_app_api_error_shows_setup_and_usage_not_cache_message(
    demo: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer = service.load_answer(demo[0], demo[2]["answer_id"])
    answer.update(
        status="failed",
        api_allowed=True,
        report_path="local-report.json",
        usage=dict(
            backend_calls=1, cache_hits=0, input_tokens=0, output_tokens=0, unknown_usage_attempts=1
        ),
    )
    monkeypatch.setattr("rag.ui.app.run_question", lambda *args, **kwargs: answer)
    app = app_test(demo, monkeypatch)
    app.radio[0].set_value("Tanya korpus").run()
    app.text_area[0].set_value("A new question")
    app.checkbox[0].check()
    app.button[0].click().run()
    assert not app.exception
    assert "API key provider" in app.error[0].value
    assert any("Percobaan API: 1" in caption.value for caption in app.caption)
    assert any("belum diketahui" in caption.value for caption in app.caption)
    assert any("local-report.json" in text.value for text in app.text)


@pytest.fixture
def bibliography(demo: tuple, tmp_path: Path) -> Path:
    config, _, _ = demo
    refs = tmp_path / "references.jsonl"
    refs.write_text(
        json.dumps(dict(reference_id="indexed", citation_keys=["Fixture2024"]))
        + "\n"
        + json.dumps(dict(reference_id="unavailable", citation_keys=["Unavailable2025"])),
        encoding="utf-8",
    )
    download = tmp_path / "download.json"
    download.write_text(
        json.dumps(
            dict(
                config=dict(bibliography_run=str(tmp_path)),
                input_sha256={"references.jsonl": hashlib.sha256(refs.read_bytes()).hexdigest()},
                references=[
                    dict(
                        reference_id="indexed",
                        status="pdf_ready",
                        pdf_sha256="a" * 64,
                        citation_keys=["Fixture2024"],
                    )
                ],
            )
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(config.paths.db_path) as connection:
        paper_id, digest = connection.execute("SELECT paper_id, pdf_sha256 FROM paper").fetchone()
    prepared = tmp_path / "prepare.json"
    prepared.write_text(
        json.dumps(
            dict(
                download_report=str(download),
                download_report_sha256=hashlib.sha256(download.read_bytes()).hexdigest(),
                papers=[
                    dict(
                        paper_id=paper_id,
                        pdf_sha256=digest,
                        reference_id="indexed",
                        citation_keys=["Fixture2024"],
                    )
                ],
            )
        ),
        encoding="utf-8",
    )
    return prepared


def test_corpus_counts_aliases_and_readonly_identity(demo: tuple, bibliography: Path) -> None:
    config, _, _ = demo
    before = Path(config.paths.db_path).read_bytes()
    corpus = service.load_corpus(config, bibliography)
    assert corpus["registered"] == 2
    assert corpus["indexed"] == 1
    assert corpus["chunks"] == 4
    assert list(corpus["citation_keys"].values()) == [["Fixture2024"]]
    assert service.load_corpus(config, bibliography) == corpus
    assert service.load_corpus(config)["registered"] is None
    assert Path(config.paths.db_path).read_bytes() == before


def test_corpus_rejects_incomplete_keyword_index(demo: tuple, bibliography: Path) -> None:
    with sqlite3.connect(demo[0].paths.db_path) as connection:
        connection.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (FIRST,))
    with pytest.raises(ValueError, match="Keyword index differs"):
        service.load_corpus(demo[0], bibliography)


@pytest.mark.parametrize("field", ["paper_id", "pdf_sha256", "citation_keys", "duplicate"])
def test_corpus_rejects_foreign_snapshot_or_alias(
    demo: tuple, bibliography: Path, field: str
) -> None:
    record = json.loads(bibliography.read_text())
    if field == "duplicate":
        record["papers"].append(record["papers"][0])
    else:
        record["papers"][0][field] = ["Invented2025"] if field == "citation_keys" else "wrong"
    bibliography.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        service.load_corpus(demo[0], bibliography)


@pytest.mark.parametrize("filename", ["references.jsonl", "download.json"])
def test_corpus_rejects_modified_provenance(demo: tuple, bibliography: Path, filename: str) -> None:
    path = bibliography.parent / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="berbeda"):
        service.load_corpus(demo[0], bibliography)


def launch_bibliography_app(report: str) -> None:
    from rag.ui.app import main

    main(bibliography_report=report)


def test_bibliography_app_query_first_and_citation_keys(
    demo: tuple, bibliography: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, generation = demo
    monkeypatch.setattr("rag.ui.app.load_config", lambda _: config)
    monkeypatch.setattr(
        "rag.ui.app.run_question",
        lambda *args, **kwargs: service.load_answer(config, generation["answer_id"]),
    )
    app = AppTest.from_function(
        launch_bibliography_app, kwargs=dict(report=str(bibliography))
    ).run()
    assert not app.exception
    assert not app.radio
    assert any("2 referensi terdaftar · 1 paper terindeks" in c.value for c in app.caption)
    assert app.checkbox[0].value is False
    app.text_area[0].set_value("Apa buktinya?")
    app.button[0].click().run()
    assert not app.exception
    assert any("Fixture2024" in exp.label and "hal. PDF 1" in exp.label for exp in app.expander)
    assert not any("Unavailable2025" in exp.label for exp in app.expander)
    assert any(FIRST in element.value for element in app.text)
    assert any("perkiraan parser" in c.value for c in app.caption)
    app.checkbox[0].check()
    app.button[0].click().run()
    assert app.checkbox[0].value is True
    changed = replace(config, generation=replace(config.generation, model="changed-model"))
    monkeypatch.setattr("rag.ui.app.load_config", lambda _: changed)
    app.run()
    assert not app.exception
    assert app.checkbox[0].value is False
    assert not any("Klaim 1" in m.value for m in app.markdown)


def test_local_receipt_binds_ui_aliases_and_explains_unverified_license(tmp_path):
    bib = tmp_path / "bibliography"
    bib.mkdir()
    entry = dict(citation_key="Local2026", reference_id="ref-local")
    (bib / "entries.jsonl").write_text(json.dumps(entry))
    (bib / "references.jsonl").write_text(json.dumps(dict(reference_id="ref-local")))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            dict(
                bibliography_run=str(bib),
                bibliography_sha256={
                    name: hashlib.sha256((bib / name).read_bytes()).hexdigest()
                    for name in ["entries.jsonl", "references.jsonl"]
                },
            )
        )
    )
    paper = dict(paper_id="local:sha256_fixture", pdf_sha256="fixture")
    receipt = dict(
        manifest=str(manifest),
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        papers=[dict(paper, **entry)],
    )
    aliases, registered = service._local_aliases([paper], receipt)
    assert aliases == {paper["paper_id"]: ["Local2026"]}
    assert registered == 1
    assert "Belum diverifikasi" in service.license_label("LicenseRef-UserProvided-Unverified")
    assert service.source_url("file:///D:/local/paper.pdf") is None
    receipt["papers"][0]["pdf_sha256"] = "other"
    with pytest.raises(ValueError, match="Identitas"):
        service._local_aliases([paper], receipt)
