import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path

import pymupdf
import pytest

from rag.chunking.pipeline import chunk_corpus
from rag.config import load_config
from rag.ids import is_valid_chunk_id
from rag.indexing.pipeline import index_corpus
from rag.ingestion.__main__ import main
from rag.ingestion.bibliography import import_bibliography
from rag.ingestion.download_http import load_download_settings
from rag.ingestion.prepare import prepare_downloads
from rag.parsing.pipeline import parse_corpus


@pytest.fixture
def snapshot(tmp_path):
    source = tmp_path / "refs.bib"
    source.write_text(
        "@article{fixture,title={Synthetic Study About Research Evidence},"
        "author={Jane Doe},year={2024},doi={10.1234/fixture}}",
        encoding="utf-8",
    )
    bibliography, _ = import_bibliography(source, tmp_path / "bibliography")
    entry = json.loads((bibliography / "entries.jsonl").read_text())
    pdf = tmp_path / "downloads/pdf/fixture.pdf"
    pdf.parent.mkdir(parents=True)
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "Synthetic Study About Research Evidence\nJane Doe 2024")
        page.insert_text((50, 110), "1 Introduction", fontname="hebo")
        for i in range(8):
            page.insert_text(
                (50, 140 + 20 * i),
                "Synthetic evidence supports reliable research and traceable citations.",
            )
        pdf.write_bytes(document.tobytes())
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    report = {
        "config": asdict(
            replace(
                load_download_settings(Path("configs/skripsi-download.yaml")),
                bibliography_run=str(bibliography),
            )
        ),
        "input_sha256": {
            name: hashlib.sha256((bibliography / name).read_bytes()).hexdigest()
            for name in ("entries.jsonl", "references.jsonl")
        },
        "references": [
            {
                "reference_id": entry["reference_id"],
                "citation_keys": ["fixture"],
                "status": "pdf_ready",
                "pdf_path": str(pdf),
                "pdf_sha256": digest,
                "snapshot_version": "sha256:" + digest,
                "content_version": "publisher_linked_pdf",
                "publisher_title": entry["metadata"]["title"],
                "pages": 1,
                "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "license_evidence": "article_rel_license",
                "landing_url": "https://aclanthology.org/fixture/",
                "pdf_url": "https://aclanthology.org/fixture.pdf",
                "fetched_at": "2026-11-19T00:00:00+00:00",
            }
        ],
    }
    path = tmp_path / "downloads/run/report.json"
    path.parent.mkdir()
    path.write_text(json.dumps(report), encoding="utf-8")
    base = load_config()
    config = replace(
        base,
        paths=replace(
            base.paths,
            raw_dir=str(tmp_path / "corpus/raw"),
            parsed_dir=str(tmp_path / "corpus/parsed"),
            index_dir=str(tmp_path / "corpus/index"),
            db_path=str(tmp_path / "corpus/index/corpus.db"),
            cache_dir=str(tmp_path / "corpus/cache"),
        ),
        chunking=replace(
            base.chunking,
            target_tokens=40,
            overlap_tokens=5,
            min_tokens=10,
            short_chunk_policy="drop",
        ),
    )
    return config, path, report


def test_admission_preserves_snapshot_mapping_schema_and_parse_status(snapshot):
    config, path, report = snapshot
    result = prepare_downloads(config, path)
    paper = result["papers"][0]
    assert (
        paper["paper_id"]
        == "crossref:10.1234/fixture_sha256_" + report["references"][0]["pdf_sha256"]
    )
    assert paper["citation_keys"] == ["fixture"]
    with closing(sqlite3.connect(config.paths.db_path)) as db:
        assert db.execute("SELECT source, doi, license FROM paper").fetchone() == (
            "crossref",
            "10.1234/fixture",
            "CC-BY-4.0",
        )
        assert len(db.execute("PRAGMA table_info(paper)").fetchall()) == 14
        db.execute("UPDATE paper SET parse_status = 'ok'")
        db.commit()
    repeated = prepare_downloads(config, path)
    assert result["papers"] == repeated["papers"]
    with closing(sqlite3.connect(config.paths.db_path)) as db:
        assert db.execute("SELECT COUNT(*), parse_status FROM paper").fetchone() == (1, "ok")


def test_existing_pipeline_accepts_crossref_snapshots_and_replays(snapshot):
    class Embedder:
        dimension = 2
        max_tokens = 512

        def token_counts(self, texts):
            return [len(text.split()) for text in texts]

        def encode(self, texts):
            return [[0.6, 0.8] for _ in texts]

    config, path, _ = snapshot
    prepare_downloads(config, path)
    assert parse_corpus(config)["failed"] == 0
    assert chunk_corpus(config)["failed"] == 0
    first = index_corpus(config, Embedder())
    second = index_corpus(config, Embedder())
    assert first["chunks"] == first["vector_count"] == first["fts_count"] > 0
    assert second["computed_embeddings"] == 0
    with closing(sqlite3.connect(config.paths.db_path)) as db:
        assert all(is_valid_chunk_id(row[0]) for row in db.execute("SELECT chunk_id FROM chunk"))


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("license", "CC0-1.0", "license"),
        ("snapshot_version", "sha256:wrong", "snapshot version"),
        ("pages", 99, "page count"),
        ("fetched_at", "2026-11-19T00:00:00", "timezone"),
    ],
)
def test_rejects_invalid_admission_before_database_writes(snapshot, field, value, match):
    config, path, report = snapshot
    report["references"][0][field] = value
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        prepare_downloads(config, path)
    assert not Path(config.paths.db_path).exists()


def test_rejects_changed_source_pdf_and_existing_corpus_copy(snapshot):
    config, path, report = snapshot
    result = prepare_downloads(config, path)
    corpus_pdf = Path(result["papers"][0]["pdf_path"])
    corpus_pdf.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Existing corpus PDF"):
        prepare_downloads(config, path)
    assert corpus_pdf.read_bytes() == b"changed"
    Path(report["references"][0]["pdf_path"]).write_bytes(b"changed source")
    with pytest.raises(ValueError, match="hash or snapshot"):
        prepare_downloads(config, path)


def test_changed_bibliography_does_not_admit_metadata(snapshot):
    config, path, report = snapshot
    entries = Path(report["config"]["bibliography_run"]) / "entries.jsonl"
    entries.write_bytes(entries.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Bibliography differs"):
        prepare_downloads(config, path)
    assert not Path(config.paths.db_path).exists()


def test_admission_cli_requires_explicit_corpus_config(monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["rag.ingestion", "prepare-bib", "--download-report", "report.json"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
