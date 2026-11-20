import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pymupdf
import pytest
import yaml

from rag.config import load_config
from rag.indexing.pipeline import index_corpus
from rag.ingestion.store import PAPER_SCHEMA
from rag.parsing.docling_pipeline import build, digest, write_json


class Encoder:
    dimension = 2
    max_tokens = 512

    def token_counts(self, texts):
        return [len(t.split()) for t in texts]

    def encode(self, texts):
        return [[0.6, 0.8] for _ in texts]


@pytest.fixture
def pilot(tmp_path: Path):
    source_db = tmp_path / "source.db"
    pdf = tmp_path / "source.pdf"
    text = "Independent narrative evidence for a synthetic research paper."
    with pymupdf.open() as doc:
        doc.new_page(width=300, height=400).insert_text((30, 60), text, fontsize=8)
        doc.save(pdf)
    paper = dict(
        paper_id="pmc:fixture",
        source="pmc",
        source_id="fixture",
        title="Synthetic paper",
        authors="[]",
        year=2024,
        venue=None,
        doi=None,
        license="CC-BY-4.0",
        license_url=None,
        landing_url="https://example.org",
        pdf_sha256=digest(pdf),
        fetched_at="2026-11-19T00:00:00Z",
        parse_status="ok",
    )
    with closing(sqlite3.connect(source_db)) as db:
        db.executescript(PAPER_SCHEMA)
        db.execute(
            "INSERT INTO paper VALUES (" + ",".join("?" for _ in paper) + ")", tuple(paper.values())
        )
        db.commit()
    source = asdict(load_config())
    source["paths"]["db_path"] = str(source_db)
    source_config = tmp_path / "source.yaml"
    source_config.write_text(yaml.safe_dump(source), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    config = asdict(load_config())
    config["paths"].update(
        db_path=str(run / "index/corpus.db"),
        index_dir=str(run / "index"),
        parsed_dir=str(run / "parsed"),
        cache_dir=str(run / "cache"),
    )
    config["chunking"].update(min_tokens=1, target_tokens=40, overlap_tokens=0)
    (run / "pipeline-config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    raw = dict(
        body=dict(children=[{"$ref": "#/texts/0"}]),
        texts=[
            dict(
                self_ref="#/texts/0",
                label="text",
                text=text,
                prov=[dict(page_no=1, bbox=dict(l=20, t=45, r=290, b=70, coord_origin="TOPLEFT"))],
            )
        ],
    )
    write_json(run / "fixture.json", raw)
    write_json(
        run / "extraction.json",
        dict(
            source_config=str(source_config),
            source_config_sha256=digest(source_config),
            config_sha256=digest(run / "pipeline-config.yaml"),
            policy=dict(native_word_coverage=0.8),
            documents=[
                dict(
                    status="ok",
                    key="fixture",
                    paper=paper,
                    pdf=str(pdf),
                    page_count=1,
                    artifact="fixture.json",
                    artifact_sha256=digest(run / "fixture.json"),
                )
            ],
        ),
    )
    return run, source_db, pdf


def test_build_new_corpus_index_and_replay_preserve_source(pilot):
    run, source_db, pdf = pilot
    source_hash, pdf_hash = digest(source_db), digest(pdf)
    first = build(run, Encoder())
    repeated = build(run, Encoder())
    assert first["papers"] == repeated["papers"]
    config = load_config(run / "pipeline-config.yaml")
    indexed = index_corpus(config, Encoder())
    assert indexed["chunks"] == indexed["vector_count"] == indexed["fts_count"] == 1
    assert index_corpus(config, Encoder())["computed_embeddings"] == 0
    with closing(sqlite3.connect(config.paths.db_path)) as db:
        assert len(db.execute("PRAGMA table_info(paper)").fetchall()) == 14
        assert len(db.execute("PRAGMA table_info(chunk)").fetchall()) == 10
        assert db.execute("SELECT chunk_id FROM chunk").fetchone() == ("pmc:fixture:p1:c01",)
    assert digest(source_db) == source_hash and digest(pdf) == pdf_hash


@pytest.mark.parametrize("changed", ["config", "artifact", "source_pdf"])
def test_stale_inputs_fail_with_new_report(pilot, changed):
    run, _, pdf = pilot
    target = {
        "config": run / "pipeline-config.yaml",
        "artifact": run / "fixture.json",
        "source_pdf": pdf,
    }[changed]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        build(run, Encoder())
    reports = list(run.glob("build-*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["status"] == "failed"


def test_failed_extraction_cannot_build_a_partial_corpus(pilot):
    run, _, _ = pilot
    path = run / "extraction.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["documents"][0].update(status="failed", error="conversion failed")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="extraction incomplete"):
        build(run, Encoder())
    assert not (run / "index/corpus.db").exists()


def test_local_collection_keeps_unsearchable_pdf_registered_without_bad_evidence(pilot):
    run, _, _ = pilot
    raw_path = run / "fixture.json"
    raw = json.loads(raw_path.read_text())
    raw["texts"][0]["text"] = "Unrelated OCR hallucination that cannot match native PDF."
    raw_path.write_text(json.dumps(raw))
    path = run / "extraction.json"
    manifest = json.loads(path.read_text())
    manifest["documents"][0]["artifact_sha256"] = digest(raw_path)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="no searchable chunks"):
        build(run, Encoder())
    manifest["admission_policy"] = "user_local_collection"
    path.write_text(json.dumps(manifest))
    report = build(run, Encoder())
    assert report["papers"][0]["status"] == "held"
    assert report["papers"][0]["chunks"] == 0
    with sqlite3.connect(run / "index/corpus.db") as db:
        assert db.execute("SELECT parse_status FROM paper").fetchone() == ("held",)
        assert db.execute("SELECT COUNT(*) FROM chunk").fetchone() == (0,)
