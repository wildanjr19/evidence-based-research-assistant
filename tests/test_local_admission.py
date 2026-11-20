import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from rag.config import load_config
from rag.ingestion.__main__ import main
from rag.ingestion.bibliography import import_bibliography
from rag.ingestion.local import prepare_local


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def local_pilot(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@article{fixture,title={Local Research Evidence},author={Jane Doe},"
        "year={2024},doi={10.1234/local}}",
        encoding="utf-8",
    )
    bibliography, _ = import_bibliography(bib, tmp_path / "bibliography")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    pdf = inputs / "paper.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 50), "Local Research Evidence\nJane Doe 2024")
        page.insert_text((40, 120), "Copyright Jane Doe. Creative Commons Attribution.")
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(40, 120, 100, 140),
                "uri": "https://creativecommons.org/licenses/by/4.0/",
            }
        )
        pdf.write_bytes(document.tobytes())
    html = tmp_path / "publisher.html"
    html.write_text(
        '<meta name="citation_title" content="Local Research Evidence">'
        '<meta name="citation_author" content="Jane Doe">'
        '<meta name="citation_doi" content="10.1234/local">'
        '<a rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY</a>',
        encoding="utf-8",
    )
    record = {
        "citation_key": "fixture",
        "file": "paper.pdf",
        "pdf_sha256": sha(pdf),
        "pages": 1,
        "doi": "10.1234/local",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence": "publisher_rel_license",
        "observed_at": "2026-11-20T00:00:00+00:00",
        "landing_url": "https://publisher.example/article/1",
        "publisher_evidence": {
            "path": str(html),
            "sha256": sha(html),
            "url": "https://publisher.example/article/1",
        },
    }
    manifest = {
        "input_root": str(inputs),
        "bibliography_run": str(bibliography),
        "bibliography_sha256": {
            name: sha(bibliography / name) for name in ["entries.jsonl", "references.jsonl"]
        },
        "papers": [record],
    }
    path = tmp_path / "manifest.json"
    base = load_config()
    config = replace(
        base,
        paths=replace(
            base.paths,
            raw_dir=str(tmp_path / "new/raw"),
            parsed_dir=str(tmp_path / "new/parsed"),
            index_dir=str(tmp_path / "new/index"),
            db_path=str(tmp_path / "new/index/corpus.db"),
        ),
    )
    return config, path, manifest


def save(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_local_admission_preserves_schema_ids_source_and_provenance(local_pilot):
    config, path, manifest = local_pilot
    save(path, manifest)
    report = prepare_local(config, path)
    record = report["papers"][0]
    assert record["paper_id"] == "crossref:10.1234/local_sha256_" + record["pdf_sha256"]
    assert sha(Path(record["pdf_path"])) == sha(Path(manifest["input_root"]) / "paper.pdf")
    assert report["network_requests"] == 0
    with sqlite3.connect(config.paths.db_path) as db:
        assert len(db.execute("PRAGMA table_info(paper)").fetchall()) == 14
        assert db.execute("SELECT parse_status FROM paper").fetchone() == ("pending",)
    with pytest.raises(ValueError, match="new database"):
        prepare_local(config, path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pdf_sha256", "wrong"),
        ("pages", 2),
        ("doi", "10.1234/wrong"),
        ("license", "CC0-1.0"),
        ("file", "../paper.pdf"),
        ("file", "paper.txt"),
        ("observed_at", "2026-11-20T00:00:00"),
        ("citation_key", "absent"),
        ("license_evidence", "unverified"),
        ("landing_url", "https://other.example/article"),
    ],
)
def test_invalid_local_records_never_create_database(local_pilot, field, value):
    config, path, manifest = local_pilot
    manifest["papers"][0][field] = value
    save(path, manifest)
    with pytest.raises((ValueError, FileNotFoundError)):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_publisher_evidence_is_hash_bound_and_license_is_required(local_pilot):
    config, path, manifest = local_pilot
    record = manifest["papers"][0]
    html = Path(record["publisher_evidence"]["path"])
    html.write_text(html.read_text().replace('rel="license"', 'rel="other"'))
    save(path, manifest)
    with pytest.raises(ValueError, match="hash differs"):
        prepare_local(config, path)
    record["publisher_evidence"]["sha256"] = sha(html)
    save(path, manifest)
    with pytest.raises(ValueError, match="license absent"):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_pdf_copyright_page_is_bound_to_same_file(local_pilot):
    config, path, manifest = local_pilot
    record = manifest["papers"][0]
    record.update(license_evidence="pdf_copyright_page", license_page=1)
    save(path, manifest)
    assert prepare_local(config, path)["papers"][0]["license_page"] == 1


@pytest.mark.parametrize("count", [0, 2, 4])
def test_empty_duplicate_or_oversized_pilot_is_rejected(local_pilot, count):
    config, path, manifest = local_pilot
    manifest["papers"] *= count
    save(path, manifest)
    with pytest.raises(ValueError):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_changed_bibliography_prevents_admission(local_pilot):
    config, path, manifest = local_pilot
    (Path(manifest["bibliography_run"]) / "entries.jsonl").write_text("changed")
    save(path, manifest)
    with pytest.raises(ValueError, match="hash differs"):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_local_cli_requires_explicit_new_corpus_and_manifest(monkeypatch):
    monkeypatch.setattr("sys.argv", ["rag.ingestion", "prepare-local"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2


def native_manifest(
    local_pilot, statement="This article is licensed under Creative Commons Attribution 4.0."
):
    config, path, manifest = local_pilot
    record = manifest["papers"][0]
    pdf = Path(manifest["input_root"]) / record["file"]
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((40, 50), "Local Research Evidence\nJane Doe 2024\n10.1234/local")
        page.insert_textbox(pymupdf.Rect(40, 100, 550, 400), statement)
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(40, 100, 100, 120),
                "uri": "https://creativecommons.org/licenses/by/4.0/",
            }
        )
        pdf.write_bytes(document.tobytes())
    record.update(
        pdf_sha256=sha(pdf),
        identity_evidence="pdf_doi",
        license_evidence="pdf_article_license",
        license_pages=[1],
        license_statement=statement,
    )
    return config, path, manifest


def test_native_pdf_identity_and_article_license_can_be_verified_offline(local_pilot):
    config, path, manifest = native_manifest(local_pilot)
    save(path, manifest)
    assert prepare_local(config, path)["papers"][0]["identity_evidence"] == "pdf_doi"


@pytest.mark.parametrize("change", ["quote", "page", "doi_prefix", "evidence_kind"])
def test_native_evidence_is_exact_and_bounded(local_pilot, change):
    config, path, manifest = native_manifest(local_pilot)
    record = manifest["papers"][0]
    if change == "quote":
        record["license_statement"] = "This work is licensed under Creative Commons."
    elif change == "page":
        record["license_pages"] = [1, 1]
    elif change == "doi_prefix":
        record["doi"] = "10.1234/loc"
        entry = Path(manifest["bibliography_run"]) / "entries.jsonl"
        data = json.loads(entry.read_text())
        data["doi"] = record["doi"]
        entry.write_text(json.dumps(data))
        manifest["bibliography_sha256"]["entries.jsonl"] = sha(entry)
    else:
        record["identity_evidence"] = "unverified"
    save(path, manifest)
    with pytest.raises(ValueError):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_dataset_license_cannot_be_used_as_article_license(local_pilot):
    config, path, manifest = native_manifest(
        local_pilot,
        "This article evaluates a dataset. The dataset uses Creative Commons Attribution.",
    )
    save(path, manifest)
    with pytest.raises(ValueError, match="article license"):
        prepare_local(config, path)
    assert not Path(config.paths.db_path).exists()


def test_prior_snapshot_license_is_bound_to_reference_and_pdf_hash(local_pilot):
    config, path, manifest = local_pilot
    record = manifest["papers"][0]
    entry = json.loads((Path(manifest["bibliography_run"]) / "entries.jsonl").read_text())
    prior = path.parent / "prior-report.json"
    row = {
        name: record[name]
        for name in ["pdf_sha256", "license", "license_url", "landing_url", "pages"]
    }
    row.update(status="pdf_ready", reference_id=entry["reference_id"])
    prior.write_text(json.dumps({"references": [row]}))
    record.update(
        identity_evidence="prior_snapshot_report",
        license_evidence="prior_snapshot_report",
        prior_snapshot_evidence={"path": str(prior), "sha256": sha(prior)},
    )
    save(path, manifest)
    assert prepare_local(config, path)["papers"][0]["identity_evidence"] == "prior_snapshot_report"


def test_explicit_document_limit_cannot_exceed_config(local_pilot):
    config, path, manifest = local_pilot
    save(path, manifest)
    with pytest.raises(ValueError, match="max_documents"):
        prepare_local(config, path, max_documents=config.ingestion.max_papers + 1)
    assert not Path(config.paths.db_path).exists()


def test_identical_bibliography_duplicates_are_not_ambiguous(local_pilot):
    config, path, manifest = local_pilot
    entry = Path(manifest["bibliography_run"]) / "entries.jsonl"
    entry.write_text(entry.read_text() * 2)
    manifest["bibliography_sha256"]["entries.jsonl"] = sha(entry)
    save(path, manifest)
    assert len(prepare_local(config, path)["papers"]) == 1


def test_default_limit_respects_smaller_ingestion_config(local_pilot):
    config, path, manifest = local_pilot
    config = replace(config, ingestion=replace(config.ingestion, max_papers=1))
    save(path, manifest)
    assert prepare_local(config, path)["max_documents"] == 1


def test_explicit_bounded_batch_admits_more_than_three_distinct_pdfs(local_pilot):
    from copy import deepcopy

    config, path, manifest = local_pilot
    records = []
    bib = path.parent / "batch.bib"
    bib.write_text(
        "\n".join(
            f"@article{{item{i},title={{Local Research Evidence}},author={{Jane Doe}},"
            f"year={{2024}},doi={{10.1234/item{i}}}" + "}"
            for i in range(4)
        )
    )
    bibliography, _ = import_bibliography(bib, path.parent / "batch-bibliography")
    manifest.update(
        bibliography_run=str(bibliography),
        bibliography_sha256={
            name: sha(bibliography / name) for name in ("entries.jsonl", "references.jsonl")
        },
    )
    for i in range(4):
        record = deepcopy(manifest["papers"][0])
        pdf = Path(manifest["input_root"]) / f"item{i}.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text(
                (40, 50), f"Local Research Evidence\nJane Doe 2024\nItem {i}"
            )
            pdf.write_bytes(doc.tobytes())
        html = path.parent / f"item{i}.html"
        original = Path(record["publisher_evidence"]["path"]).read_text()
        html.write_text(original.replace("10.1234/local", f"10.1234/item{i}"))
        record.update(
            citation_key=f"item{i}", file=pdf.name, pdf_sha256=sha(pdf), doi=f"10.1234/item{i}"
        )
        record["publisher_evidence"].update(path=str(html), sha256=sha(html))
        records.append(record)
    manifest["papers"] = records
    config = replace(config, ingestion=replace(config.ingestion, max_papers=4))
    save(path, manifest)
    with pytest.raises(ValueError, match="explicit document limit"):
        prepare_local(config, path)
    result = prepare_local(config, path, max_documents=4)
    assert len(result["papers"]) == 4
    with sqlite3.connect(config.paths.db_path) as db:
        assert db.execute("SELECT COUNT(DISTINCT paper_id) FROM paper").fetchone() == (4,)


def test_local_collection_admits_missing_doi_with_honest_label_and_hash(local_pilot):
    config, path, manifest = local_pilot
    bib = Path(manifest["bibliography_run"]) / "entries.jsonl"
    entries = [json.loads(line) for line in bib.read_text().splitlines()]
    entries[0]["doi"] = None
    bib.write_text("\n".join(json.dumps(e) for e in entries))
    manifest["bibliography_sha256"]["entries.jsonl"] = sha(bib)
    record = manifest["papers"][0]
    record.update(
        doi=None,
        identity_evidence="user_local_collection",
        license_evidence="user_local_collection",
        license="LicenseRef-UserProvided-Unverified",
        license_url=None,
        landing_url=(Path(manifest["input_root"]) / record["file"]).resolve().as_uri(),
    )
    manifest["admission_policy"] = "user_local_collection"
    save(path, manifest)
    with pytest.raises(ValueError, match="opt-in"):
        prepare_local(config, path)
    result = prepare_local(config, path, local_collection=True)
    assert result["papers"][0]["paper_id"] == "local:sha256_" + record["pdf_sha256"]
    with sqlite3.connect(config.paths.db_path) as db:
        assert db.execute("select doi, license from paper").fetchone() == (
            None,
            "LicenseRef-UserProvided-Unverified",
        )


@pytest.mark.parametrize("changed", ["policy", "license", "hash", "location"])
def test_local_collection_still_checks_provenance_and_cannot_claim_cc(local_pilot, changed):
    config, path, manifest = local_pilot
    record = manifest["papers"][0]
    manifest["admission_policy"] = "user_local_collection"
    record.update(
        identity_evidence="user_local_collection",
        license_evidence="user_local_collection",
        license="LicenseRef-UserProvided-Unverified",
        license_url=None,
        landing_url=(Path(manifest["input_root"]) / record["file"]).resolve().as_uri(),
    )
    if changed == "policy":
        manifest.pop("admission_policy")
    elif changed == "license":
        record["license"] = "CC-BY-4.0"
    elif changed == "hash":
        record["pdf_sha256"] = "0" * 64
    else:
        record["landing_url"] = "https://example.org"
    save(path, manifest)
    with pytest.raises(ValueError):
        prepare_local(config, path, local_collection=True)
    assert not Path(config.paths.db_path).exists()
