from datetime import datetime, timedelta, timezone

import pytest

from rag.ids import (
    is_valid_chunk_id,
    is_valid_paper_id,
    is_valid_run_id,
    make_chunk_id,
    make_paper_id,
    make_run_id,
)


@pytest.mark.parametrize(
    ("source", "source_id"),
    [
        ("arxiv", "2401.12345v1"),
        ("arxiv", "hep-th/9901001v12"),
        ("pmc", "PMC10234567"),
    ],
)
def test_paper_id_round_trip(source: str, source_id: str) -> None:
    paper_id = make_paper_id(source, source_id)
    assert paper_id == f"{source}:{source_id}"
    assert is_valid_paper_id(paper_id)


@pytest.mark.parametrize(
    "paper_id",
    [
        "arxiv:2401.12345",
        "arxiv:2401.12345v0",
        "arxiv:2401.12345v01",
        "arxiv:v1",
        "Arxiv:2401.12345v1",
        "arxiv:",
        "arxiv:2401.12345v1\n",
        "arxiv:2401.12345v1:p1:c01",
        "pmc:paper with spaces",
        "missing-colon",
        "",
    ],
)
def test_reject_invalid_paper_ids(paper_id: str) -> None:
    assert not is_valid_paper_id(paper_id)
    if ":" in paper_id:
        with pytest.raises(ValueError):
            make_paper_id(*paper_id.split(":", 1))


@pytest.mark.parametrize(
    ("page", "ordinal", "suffix"),
    [(1, 1, "p1:c01"), (7, 3, "p7:c03"), (20, 100, "p20:c100"), (9999, 9999, "p9999:c9999")],
)
def test_chunk_id_is_deterministic(page: int, ordinal: int, suffix: str) -> None:
    paper_id = "arxiv:2401.12345v1"
    chunk_id = make_chunk_id(paper_id, page, ordinal)
    assert chunk_id == make_chunk_id(paper_id, page, ordinal) == f"{paper_id}:{suffix}"
    assert is_valid_chunk_id(chunk_id)


@pytest.mark.parametrize(
    "chunk_id",
    ["pmc:PMC10234567:p1:c01", "arxiv:hep-th/9901001v2:p10:c12"],
)
def test_chunk_ids_support_other_sources_and_legacy_arxiv(chunk_id: str) -> None:
    assert is_valid_chunk_id(chunk_id)


@pytest.mark.parametrize(
    "chunk_id",
    [
        "arxiv:2401.12345:p1:c01",
        "arxiv:2401.12345v1:p0:c01",
        "arxiv:2401.12345v1:p1:c00",
        "arxiv:2401.12345v1:p1:c1",
        "arxiv:2401.12345v1:p10000:c01",
        "arxiv:2401.12345v1:p1:c10000",
        "arxiv:2401.12345v1:p-1:c01",
        "arxiv:2401.12345v1:p1:c01\n",
        "arxiv:2401.12345v1:p1:c01:section",
        "arxiv:2401.12345v1:p١:c01",
        "",
    ],
)
def test_reject_invalid_chunk_ids(chunk_id: str) -> None:
    assert not is_valid_chunk_id(chunk_id)


@pytest.mark.parametrize("value", [0, -1, 10000, True, 1.5, "1"])
def test_chunk_builder_rejects_invalid_page_and_ordinal(value: object) -> None:
    with pytest.raises(ValueError, match="page"):
        make_chunk_id("arxiv:2401.12345v1", value, 1)
    with pytest.raises(ValueError, match="ordinal"):
        make_chunk_id("arxiv:2401.12345v1", 1, value)


def test_chunk_builder_rejects_unversioned_paper() -> None:
    with pytest.raises(ValueError, match="paper ID"):
        make_chunk_id("arxiv:2401.12345", 1, 1)


def test_run_id_converts_to_utc_and_uses_random_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    suffixes = iter(["ab12cd", "123456"])
    monkeypatch.setattr("rag.ids.secrets.token_hex", lambda size: next(suffixes))
    started_at = datetime(2026, 11, 18, 9, 10, tzinfo=timezone(timedelta(hours=7)))
    first = make_run_id(started_at)
    second = make_run_id(started_at)
    assert first == "2026-11-18T02:10:00Z_ab12cd"
    assert second == "2026-11-18T02:10:00Z_123456"
    assert is_valid_run_id(first) and is_valid_run_id(second)


def test_run_id_default_and_naive_timestamp() -> None:
    assert is_valid_run_id(make_run_id())
    with pytest.raises(ValueError, match="timezone"):
        make_run_id(datetime(2026, 11, 18))


@pytest.mark.parametrize(
    "run_id",
    [
        "2026-02-30T02:10:00Z_ab12cd",
        "2026-11-18T25:10:00Z_ab12cd",
        "2026-11-18T02:10:00+07:00_ab12cd",
        "2026-11-18T02:10:00Z_xyz123",
        "2026-11-18T02:10:00Z_ab12cd\n",
        "2026-11-18T02:10:00Z",
        "",
    ],
)
def test_reject_invalid_run_ids(run_id: str) -> None:
    assert not is_valid_run_id(run_id)


@pytest.mark.parametrize("value", [None, 12, [], {}])
def test_validation_rejects_non_strings(value: object) -> None:
    assert not is_valid_paper_id(value)
    assert not is_valid_chunk_id(value)
    assert not is_valid_run_id(value)
