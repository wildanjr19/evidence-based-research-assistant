import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from rag.chunking.__main__ import main as chunk_main
from rag.chunking.pipeline import chunk_corpus
from rag.config import Config, load_config
from rag.ids import paper_file_stem
from rag.ingestion.arxiv import Paper
from rag.ingestion.store import PAPER_SCHEMA, save_paper
from rag.parsing.__main__ import main as parse_main
from rag.parsing.pipeline import parse_corpus, write_report

PAPER_ID = "arxiv:2401.12345v1"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    base = load_config()
    return replace(
        base,
        paths=replace(
            base.paths,
            raw_dir=str(tmp_path / "raw"),
            parsed_dir=str(tmp_path / "parsed"),
            db_path=str(tmp_path / "corpus.db"),
        ),
        chunking=replace(base.chunking, target_tokens=12, min_tokens=4, overlap_tokens=3),
    )


def pdf_bytes() -> bytes:
    with pymupdf.open() as document:
        for number in range(1, 3):
            page = document.new_page(width=600, height=800)
            page.insert_text((50, 100), "1 Methods", fontsize=14, fontname="hebo")
            for offset in range(4):
                page.insert_text(
                    (50, 140 + offset * 20),
                    f"Synthetic evidence on page {number} line {offset} remains traceable.",
                    fontsize=11,
                )
        return document.tobytes()


def add_paper(
    config: Config, source_id: str = "2401.12345v1", content: bytes | None = None
) -> Path:
    content = pdf_bytes() if content is None else content
    paper = Paper(
        source_id,
        "Synthetic fixture",
        ["Fixture Author"],
        2024,
        None,
        None,
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
    )
    path = Path(config.paths.raw_dir) / "pdf" / paper.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    with sqlite3.connect(config.paths.db_path) as connection:
        connection.executescript(PAPER_SCHEMA)
        save_paper(connection, paper, hashlib.sha256(content).hexdigest(), "2026-11-18T03:00:00Z")
    return path


def chunk_rows(config: Config) -> list[tuple]:
    with sqlite3.connect(config.paths.db_path) as connection:
        return connection.execute("SELECT * FROM chunk ORDER BY chunk_order").fetchall()


def test_parse_chunk_and_repeat_are_idempotent(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_paper(config)
    first = parse_corpus(config, PAPER_ID)
    assert first["ok"] == 1 and first["failed"] == 0
    assert chunk_corpus(config, PAPER_ID)["ok"] == 1
    original = chunk_rows(config)
    assert original
    assert all(row[2] <= row[3] and row[8] >= 4 for row in original)
    with sqlite3.connect(config.paths.db_path) as connection:
        assert connection.execute("SELECT parse_status FROM paper").fetchone()[0] == "ok"

    def unexpected_parse(*args: object) -> None:
        raise AssertionError("cached parsing must not reopen PDF with PyMuPDF")

    monkeypatch.setattr("rag.parsing.pipeline.parse_pdf", unexpected_parse)
    repeated = parse_corpus(config, PAPER_ID)
    assert repeated["papers"][0]["cached"] is True
    assert chunk_corpus(config, PAPER_ID)["ok"] == 1
    assert chunk_rows(config) == original
    reports = list((Path(config.paths.parsed_dir) / "reports").glob("*.json"))
    assert len(reports) == 4


def test_corrupt_paper_is_counted_failed_without_stopping_other_papers(config: Config) -> None:
    add_paper(config)
    add_paper(config, "2401.99999v1", b"%PDF-1.7 broken fixture")
    report = parse_corpus(config)
    assert (report["ok"], report["failed"]) == (1, 1)
    assert report["papers"][1]["error"]
    with sqlite3.connect(config.paths.db_path) as connection:
        statuses = connection.execute("SELECT parse_status FROM paper ORDER BY paper_id").fetchall()
        assert statuses == [("ok",), ("failed",)]
    chunk_report = chunk_corpus(config)
    assert (chunk_report["ok"], chunk_report["failed"]) == (1, 1)


def test_changed_pdf_or_parser_config_does_not_overwrite_artifacts(config: Config) -> None:
    path = add_paper(config)
    parse_corpus(config)
    artifact = Path(config.paths.parsed_dir) / f"{paper_file_stem(PAPER_ID)}.json"
    original = artifact.read_bytes()
    changed = replace(config, parsing=replace(config.parsing, heading_max_words=8))
    assert parse_corpus(changed)["failed"] == 1
    assert artifact.read_bytes() == original
    path.write_bytes(b"%PDF-1.7 different bytes")
    report = parse_corpus(config)
    assert report["failed"] == 1
    assert "hash differs" in report["papers"][0]["error"]
    assert artifact.read_bytes() == original


def test_changed_chunking_refuses_to_delete_or_replace_existing_chunks(config: Config) -> None:
    add_paper(config)
    parse_corpus(config)
    chunk_corpus(config)
    original = chunk_rows(config)
    changed = replace(config, chunking=replace(config.chunking, target_tokens=8))
    report = chunk_corpus(changed)
    assert report["failed"] == 1
    assert "existing chunks differ" in report["papers"][0]["error"]
    assert chunk_rows(config) == original


def test_parsed_text_tampering_is_detected_before_chunk_insertion(config: Config) -> None:
    add_paper(config)
    parse_corpus(config)
    artifact = Path(config.paths.parsed_dir) / f"{paper_file_stem(PAPER_ID)}.json"
    raw = json.loads(artifact.read_text())
    raw["document"]["blocks"][0]["text"] = "Invented source text"
    artifact.write_text(json.dumps(raw), encoding="utf-8")
    report = chunk_corpus(config)
    assert report["failed"] == 1
    assert "hash or paper ID" in report["papers"][0]["error"]
    assert chunk_rows(config) == []


def test_chunking_requires_successful_parsing_and_missing_database_is_not_created(
    config: Config,
) -> None:
    with pytest.raises(ValueError, match="database is missing"):
        parse_corpus(config)
    with pytest.raises(ValueError, match="database is missing"):
        chunk_corpus(config)
    assert not Path(config.paths.db_path).exists()
    add_paper(config)
    assert chunk_corpus(config)["failed"] == 1
    with pytest.raises(ValueError, match="No matching papers"):
        parse_corpus(config, "arxiv:2401.00000v1")


def test_preparation_cli_runs_offline_and_reports_failures(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    add_paper(config)
    monkeypatch.setattr("rag.parsing.__main__.load_config", lambda path: config)
    monkeypatch.setattr("rag.chunking.__main__.load_config", lambda path: config)

    def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("M2 must not access network")

    monkeypatch.setattr(httpx.Client, "send", network_forbidden)
    monkeypatch.setattr("sys.argv", ["rag.parsing", "--paper-id", PAPER_ID])
    assert parse_main() == 0
    monkeypatch.setattr("sys.argv", ["rag.chunking", "--paper-id", PAPER_ID])
    assert chunk_main() == 0
    monkeypatch.setattr("sys.argv", ["rag.parsing", "--paper-id", "arxiv:2401.00000v1"])
    assert parse_main() == 1


def test_report_id_collision_does_not_overwrite_previous_run(
    config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("rag.parsing.pipeline.make_run_id", lambda: "2026-11-18T04:00:00Z_123456")
    write_report(config, "parse", [{"paper_id": PAPER_ID, "status": "ok"}])
    path = next((Path(config.paths.parsed_dir) / "reports").glob("*.json"))
    original = path.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_report(config, "parse", [])
    assert path.read_bytes() == original
