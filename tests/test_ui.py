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
    monkeypatch.setattr(
        "rag.ui.app.evaluate_answer_quality",
        lambda *args, **kwargs: dict(
            status="evaluated",
            scores=dict(faithfulness=0.9, response_relevancy=0.8),
            usage=dict(
                backend_calls=1,
                cache_hits=0,
                input_tokens=200,
                output_tokens=30,
                unknown_usage_attempts=0,
            ),
        ),
    )


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
    ("label", "expected"),
    [
        ("supported", "Belum diverifikasi"),
        (None, "Belum diverifikasi"),
        ("not_supported", "Perlu diperiksa"),
        ("partially_supported", "Perlu diperiksa"),
    ],
)
def test_support_missing_result_is_not_filled_by_other_verifiers_or_claims(
    label: str | None, expected: str
) -> None:
    claim = dict(claim_id="c", citations=[FIRST, SECOND], unsupported=False)
    records = [dict(claim_id="c", chunk_id=FIRST, verifier="minicheck", label=label)]
    records.extend(
        dict(claim_id=claim_id, chunk_id=SECOND, verifier=verifier, label="supported")
        for claim_id, verifier in [("c", "llm_judge"), ("c", "manual"), ("other", "minicheck")]
    )
    assert service.support_label(claim, records) == expected


@pytest.mark.parametrize("citations, unsupported", [([FIRST], True), ([], False)])
def test_support_cannot_override_missing_claim_evidence(citations: list, unsupported: bool) -> None:
    claim = dict(claim_id="c", citations=citations, unsupported=unsupported)
    records = [dict(claim_id="c", chunk_id=FIRST, verifier="minicheck", label="supported")]
    assert service.support_label(claim, records) == "Tidak ada bukti"


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
    answer = service.run_question("Alpha result?", config, "hybrid+rerank", verify=True)
    assert answer["status"] == "ok"
    assert answer["verification"][0]["label"] is None
    assert (
        service.support_label(answer["claims"][0], answer["verification"]) == "Belum diverifikasi"
    )


def launch_app(demo_dir: str) -> None:
    from rag.ui.app import main

    main(demo_dir=demo_dir)


def launch_default_app() -> None:
    from rag.ui.app import main

    main()


def test_default_corpus_query_and_switch_reset_answer(demo, monkeypatch):
    config, directory, generation = demo
    monkeypatch.setattr(
        "rag.ui.app.CORPORA",
        {
            "Full corpus": ("full", str(directory), None),
            "Pilot corpus": ("pilot", str(directory), None),
        },
    )
    monkeypatch.setattr(
        "rag.ui.app.load_config",
        lambda path: (
            config
            if path == "full"
            else replace(config, generation=replace(config.generation, model="different-model"))
        ),
    )
    monkeypatch.setattr(
        "rag.ui.app.run_question",
        lambda *args, **kwargs: service.load_answer(config, generation["answer_id"]),
    )
    app = AppTest.from_function(launch_default_app).run()
    assert not app.exception
    assert app.selectbox[0].value == "Full corpus"
    assert app.radio[0].value == "Tanya korpus"
    app.text_area[0].set_value("Compare the evidence.")
    app.button[0].click().run()
    assert any("Klaim 1" in m.value for m in app.markdown)
    app.selectbox[0].set_value("Pilot corpus").run()
    assert not app.exception
    assert not any("Klaim 1" in m.value for m in app.markdown)


def test_pdf_preview_uses_admitted_hash_and_original_page(corpus):
    import pymupdf

    from rag.ids import paper_file_stem
    from test_generation import PAPER_ID

    config, _ = corpus
    directory = Path(config.paths.raw_dir) / "pdf"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (paper_file_stem(PAPER_ID) + ".pdf")
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Original source page")
        pdf.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.execute("UPDATE paper SET pdf_sha256=? WHERE paper_id=?", (digest, PAPER_ID))
    preview = service.load_pdf_page(config, PAPER_ID, 1)
    assert preview["image"].startswith(b"\x89PNG")
    assert preview["pdf"] == path.read_bytes()
    with pytest.raises(ValueError, match="Halaman"):
        service.load_pdf_page(config, PAPER_ID, 2)
    path.write_bytes(b"changed PDF")
    with pytest.raises(ValueError, match="Hash"):
        service.load_pdf_page(config, PAPER_ID, 1)


def test_cache_miss_preserves_retrieved_evidence(corpus):
    config, _ = corpus
    answer = service.run_question("Alpha evidence", config, "bm25")
    assert answer["status"] == "failed"
    assert not answer["claims"]
    assert answer["retrieved_chunks"][0]["chunk_id"] == FIRST
    assert answer["usage"]["backend_calls"] == 0


def test_query_skips_minicheck_until_requested(corpus, monkeypatch):
    config, _ = corpus

    def forbidden(*args, **kwargs):
        raise AssertionError("MiniCheck is optional")

    monkeypatch.setattr(service, "CachedVerifier", forbidden)
    monkeypatch.setattr(
        OpenAIBackend,
        "complete",
        lambda *args: completion([dict(text="Alpha supports the result.", citations=[FIRST])]),
    )
    answer = service.run_question("Alpha evidence", config, "bm25", allow_api=True)
    assert answer["status"] == "ok" and answer["verification"] == []


def test_quality_runs_automatically_per_card_and_not_on_rerun(demo, monkeypatch):
    calls = []

    def evaluate(config, answer, *, allow_api=False, claim_id=None):
        calls.append((claim_id, allow_api))
        first = claim_id == answer["claims"][0]["claim_id"]
        return dict(
            status="evaluated",
            scores=dict(
                faithfulness=0.9 if first else 0.2, response_relevancy=0.8 if first else 0.3
            ),
        )

    monkeypatch.setattr("rag.ui.app.evaluate_answer_quality", evaluate)
    app = app_test(demo, monkeypatch)
    assert not calls
    app.selectbox[0].select(0).run()
    first, second = [claim["claim_id"] for claim in demo[2]["claims"]]
    assert not app.exception and calls == [(first, True), (second, True)]
    assert [m.value for m in app.metric] == ["0.900", "0.800", "0.200", "0.300"]
    assert not any("Izinkan API" in checkbox.label for checkbox in app.checkbox)
    app.run()
    assert len(calls) == 2
    app.checkbox(key="pdf_claim_1_1").check().run()
    assert not app.exception and len(calls) == 2
    app.selectbox[0].select(1).run()
    assert not app.metric
    assert len(calls) == 2
    app.selectbox[0].select(0).run()
    assert len(calls) == 4
    assert [m.value for m in app.metric] == ["0.900", "0.800", "0.200", "0.300"]


def test_quality_failure_keeps_answer_and_unknown_scores(demo, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs["claim_id"])
        raise RuntimeError("fixture evaluator failure")

    monkeypatch.setattr("rag.ui.app.evaluate_answer_quality", fail)
    app = app_test(demo, monkeypatch)
    app.selectbox[0].select(0).run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["Belum tersedia"] * 4
    assert any("<script>" in t.value for t in app.text)
    assert any("belum lengkap" in warning.value for warning in app.warning)
    app.run()
    assert len(calls) == 2


def test_token_usage_separates_generation_evaluation_and_cache(demo, monkeypatch):
    answer = service.load_answer(demo[0], demo[2]["answer_id"])
    answer["usage"] = dict(
        input_tokens=100, output_tokens=20, backend_calls=1, cache_hits=0, unknown_usage_attempts=0
    )
    calls = []

    def evaluate(config, answer, *, claim_id, allow_api):
        calls.append(claim_id)
        assert allow_api is True
        cached = claim_id == answer["claims"][1]["claim_id"]
        return dict(
            status="evaluated",
            scores=dict(faithfulness=1.0, response_relevancy=0.8),
            usage=dict(
                input_tokens=0 if cached else 10,
                output_tokens=0 if cached else 2,
                backend_calls=0 if cached else 1,
                cache_hits=1 if cached else 0,
                unknown_usage_attempts=0,
            ),
        )

    monkeypatch.setattr("rag.ui.app.run_question", lambda *args, **kwargs: answer)
    monkeypatch.setattr("rag.ui.app.evaluate_answer_quality", evaluate)
    app = app_test(demo, monkeypatch)
    app.radio[0].set_value("Tanya korpus").run()
    app.text_area[0].set_value("Compare evidence")
    app.button[0].click().run()
    assert not app.exception
    assert app.table[0].value.to_dict("records") == [
        dict(Tahap="Generator", Input="100", Output="20"),
        dict(Tahap="Evaluasi RAGAS", Input="10", Output="2"),
        dict(Tahap="Total tercatat", Input="110", Output="22"),
    ]
    assert any("Request API: 2 · Cache hit: 1" in c.value for c in app.caption)
    app.run()
    assert len(calls) == 2
    assert app.table[0].value.iloc[2]["Input"] == "110"


def test_saved_demo_does_not_count_historical_generation_as_new_tokens(demo, monkeypatch):
    app = app_test(demo, monkeypatch)
    app.selectbox[0].select(0).run()
    assert not app.exception
    assert app.table[0].value.iloc[0]["Input"] == "Belum tersedia"
    assert app.table[0].value.iloc[2]["Input"] == "400"
    assert any("Sebagian pemakaian belum diketahui" in c.value for c in app.caption)


def test_optional_minicheck_does_not_write_source(corpus, monkeypatch):
    config, rows = corpus
    generation = service.generate_answer(
        "Alpha?",
        rows[:1],
        config,
        FakeLLM([completion([dict(text="Alpha supports the result.", citations=[FIRST])])]),
    )
    answer = service.load_answer(config, generation["answer_id"])
    before = Path(config.paths.db_path).read_bytes()
    monkeypatch.setattr(service, "CachedVerifier", lambda cfg: CachedVerifier(cfg, FakeSupport()))
    records = service.run_diagnostics(config, answer)
    assert records[0]["label"] == "supported"
    assert Path(config.paths.db_path).read_bytes() == before


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
    assert not app.checkbox
    app.button[0].click().run()
    assert "Tulis pertanyaan" in app.error[0].value
    app.text_area[0].set_value("  Compare the evidence.  ")
    app.button[0].click().run()
    assert not app.exception
    assert calls == [("Compare the evidence.", "hybrid+rerank", True)]
    app.run()
    assert len(calls) == 1
    assert any("Alpha evidence" in text.value for text in app.text)
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
    app.button[0].click().run()
    assert not app.exception
    assert "API key provider" in app.error[0].value
    assert any("Request API: 1" in caption.value for caption in app.caption)
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
    assert not app.checkbox
    app.text_area[0].set_value("Apa buktinya?")
    app.button[0].click().run()
    assert not app.exception
    assert any("Fixture2024" in exp.label and "hal. PDF 1" in exp.label for exp in app.expander)
    assert not any("Unavailable2025" in exp.label for exp in app.expander)
    assert any(FIRST in element.value for element in app.text)
    assert any("perkiraan parser" in c.value for c in app.caption)
    app.button[0].click().run()
    assert not any("Izinkan API" in checkbox.label for checkbox in app.checkbox)
    changed = replace(config, generation=replace(config.generation, model="changed-model"))
    monkeypatch.setattr("rag.ui.app.load_config", lambda _: changed)
    app.run()
    assert not app.exception
    assert not app.checkbox
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
