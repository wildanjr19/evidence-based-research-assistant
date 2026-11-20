import hashlib
import json
from pathlib import Path

import pytest

from rag.ingestion.__main__ import main
from rag.ingestion.bibliography import audit_bibliography, import_bibliography, normalize_doi

SAMPLE = """@article{Riset2024,
    title = {Evaluasi {Model} untuk Layanan},
    author = {José Contoh and Peneliti Kedua},
    year = {2024},
    doi = {https://doi.org/10.1234/EXAMPLE},
    abstract = {Synthetic abstract that must not be exported}
}
@article{Riset2024,
    title = {Evaluasi {Model} untuk Layanan},
    author = {José Contoh and Peneliti Kedua},
    year = {2024},
    doi = {doi:10.1234/example}
}
@inbook{Bab2023, title = {Bab Tanpa DOI}, year = {2023}}
"""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" DOI:10.1234/ABC ", "10.1234/abc"),
        ("https://dx.doi.org/10.1234/A%28B%29", "10.1234/a(b)"),
        ("http://doi.org/10.1234/foo.bar", "10.1234/foo.bar"),
        ("https://example.org/10.1234/abc", None),
        ("https://doi.org.evil.test/10.1234/abc", None),
        ("https://user:secret@doi.org/10.1234/abc", None),
        ("https://doi.org/10.1234/abc?download=true", None),
        ("https://[bad", None),
        ("10.1234/with spaces", None),
        ("bad", None),
    ],
)
def test_normalize_doi(value: str, expected: str | None) -> None:
    assert normalize_doi(value) == expected


def test_duplicate_keys_preserve_entries_and_map_to_canonical_reference() -> None:
    audit = audit_bibliography(SAMPLE)
    entries = audit["entries"]
    assert len(entries) == 3
    assert len(audit["references"]) == 2
    assert entries[0]["reference_id"] == entries[1]["reference_id"]
    assert entries[0]["metadata"]["title"] == "Evaluasi {Model} untuk Layanan"
    assert entries[0]["metadata"]["author"] == "José Contoh and Peneliti Kedua"
    assert entries[1]["metadata"]["doi"] == "doi:10.1234/example"
    assert audit["summary"]["duplicate_keys"] == {"Riset2024": [1, 2]}
    assert audit["summary"]["duplicate_references"] == [[1, 2]]
    assert audit["summary"]["parse_failures"] == []
    assert "missing_author" in entries[2]["issues"]
    assert "doi_unavailable" in entries[2]["issues"]
    assert "Synthetic abstract" not in json.dumps(audit)


def test_conflicting_metadata_for_same_doi_is_not_silently_overwritten() -> None:
    text = SAMPLE.replace("Evaluasi {Model} untuk Layanan", "Different title", 1)
    audit = audit_bibliography(text)
    assert audit["references"][0]["metadata_conflicts"] == ["title"]
    assert audit["references"][0]["status"] == "needs_metadata_review"
    assert audit["entries"][0]["metadata"]["title"] == "Different title"
    assert audit["entries"][1]["metadata"]["title"] == "Evaluasi {Model} untuk Layanan"


def test_title_match_does_not_merge_different_dois() -> None:
    text = SAMPLE.replace("doi:10.1234/example", "10.1234/other")
    audit = audit_bibliography(text)
    assert len(audit["references"]) == 3
    assert len(audit["summary"]["title_match_candidates"]) == 1


def test_same_key_with_different_metadata_and_no_doi_remains_separate() -> None:
    audit = audit_bibliography("@misc{a,title={One}}\n@misc{a,title={Two}}")
    assert len(audit["references"]) == 2
    assert audit["summary"]["duplicate_keys"] == {"a": [1, 2]}


def test_malformed_blocks_are_reported_without_losing_valid_entries() -> None:
    audit = audit_bibliography("@article{broken,title={Unclosed\n@article{fine,title={Valid}}")
    assert len(audit["entries"]) == 1
    assert audit["entries"][0]["citation_key"] == "fine"
    assert audit["entries"][0]["source_line"] == 2
    assert len(audit["summary"]["parse_failures"]) == 1
    assert audit["summary"]["parse_failures"][0]["line"] == 1


def test_duplicate_fields_are_reported_as_conflicts() -> None:
    audit = audit_bibliography("@misc{bad,title={One},title={Two}}")
    assert audit["entries"] == []
    assert audit["summary"]["parse_failures"][0]["kind"] == "DuplicateFieldKeyBlock"


def test_invalid_optional_metadata_is_retained_for_review() -> None:
    audit = audit_bibliography("@misc{a,title={T},year={soon},doi={not a DOI}}")
    entry = audit["entries"][0]
    assert entry["doi"] is None
    assert entry["metadata"]["doi"] == "not a DOI"
    assert {"missing_author", "invalid_year", "invalid_doi"} <= set(entry["issues"])


def test_import_repeats_with_stable_references_and_new_reports(tmp_path: Path) -> None:
    source = tmp_path / "source.bib"
    source.write_text("\ufeff" + SAMPLE, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    first, report = import_bibliography(source, tmp_path / "runs")
    second, repeated = import_bibliography(source, tmp_path / "runs")
    assert first != second
    assert (first / "entries.jsonl").read_bytes() == (second / "entries.jsonl").read_bytes()
    assert (first / "references.jsonl").read_bytes() == (second / "references.jsonl").read_bytes()
    assert report["source_sha256"] == repeated["source_sha256"] == digest
    assert report["config_sha256"] == repeated["config_sha256"]
    assert report["parser"] == {"name": "bibtexparser", "version": "2.1.0"}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


def test_existing_run_directory_is_not_overwritten(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.bib"
    source.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr("rag.ingestion.bibliography.make_run_id", lambda: "same-run")
    first, _ = import_bibliography(source, tmp_path / "runs")
    before = (first / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        import_bibliography(source, tmp_path / "runs")
    assert (first / "report.json").read_bytes() == before


def test_cli_import_is_offline_and_does_not_require_corpus_config(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.bib"
    source.write_text(SAMPLE, encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("Offline import must not load corpus config or HTTP client")

    monkeypatch.setattr("rag.ingestion.__main__.load_config", unexpected)
    monkeypatch.setattr("rag.ingestion.__main__.httpx.Client", unexpected)
    monkeypatch.setattr(
        "sys.argv",
        [
            "rag.ingestion",
            "import-bib",
            "--bib",
            str(source),
            "--output-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert main() == 0
    assert len(list((tmp_path / "runs").glob("*/report.json"))) == 1


def test_cli_rejects_missing_input_and_reports_parse_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["rag.ingestion", "import-bib"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    source = tmp_path / "bad.bib"
    source.write_text("@misc{bad,title={One},title={Two}}", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "rag.ingestion",
            "import-bib",
            "--bib",
            str(source),
            "--output-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert main() == 1
    assert len(list((tmp_path / "runs").glob("*/report.json"))) == 1


def test_empty_bibliography_is_rejected() -> None:
    with pytest.raises(ValueError, match="no entries"):
        audit_bibliography("@comment{Nothing to import}")
