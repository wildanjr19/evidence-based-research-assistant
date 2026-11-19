import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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

    def query(question: str, config: object, mode: str) -> dict:
        calls.append((question, mode))
        return answer

    monkeypatch.setattr("rag.ui.app.run_question", query)
    app = app_test(demo, monkeypatch)
    app.radio[0].set_value("Tanya korpus").run()
    app.button[0].click().run()
    assert "Tulis pertanyaan" in app.error[0].value
    app.text_area[0].set_value("  Compare the evidence.  ")
    app.button[0].click().run()
    assert not app.exception
    assert calls == [("Compare the evidence.", "hybrid+rerank")]
    app.run()
    assert len(calls) == 1
    assert any("Alpha evidence" in text.value for text in app.text)


def test_app_reports_missing_demo_and_config(demo: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rag.ui.app.load_config",
        lambda _: replace(demo[0], paths=replace(demo[0].paths, db_path="missing.db")),
    )
    app = AppTest.from_function(launch_app, kwargs=dict(demo_dir=str(demo[1]))).run()
    assert not app.exception
    assert "Demo tidak cocok" in app.error[0].value

    def invalid(_: str) -> None:
        raise ValueError("invalid config")

    monkeypatch.setattr("rag.ui.app.load_config", invalid)
    app.run()
    assert "Config tidak dapat dibaca" in app.error[0].value
