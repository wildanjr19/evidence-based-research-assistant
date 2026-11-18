"""Identifiers defined by ARCHITECTURE.md §5; validation does not check database existence."""

import re
import secrets
from datetime import UTC, datetime

CHUNK_ID_PATTERN = r"^[a-z]+:[A-Za-z0-9._\-/]+:p[0-9]{1,4}:c[0-9]{2,4}$"
_CHUNK_ID_RE = re.compile(CHUNK_ID_PATTERN)
_PAPER_ID_RE = re.compile(r"[a-z]+:[A-Za-z0-9._\-/]+")
_RUN_ID_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z_[0-9a-f]{6}")


def is_valid_paper_id(paper_id: str) -> bool:
    """Check syntax and require an explicit, positive version for arXiv papers."""
    if not isinstance(paper_id, str) or not _PAPER_ID_RE.fullmatch(paper_id):
        return False
    source, source_id = paper_id.split(":", 1)
    return source != "arxiv" or re.search(r".+v[1-9][0-9]*$", source_id) is not None


def make_paper_id(source: str, source_id: str) -> str:
    """Build a paper ID without silently adding an arXiv version."""
    if not isinstance(source, str) or not isinstance(source_id, str):
        raise ValueError("source and source_id must be strings")
    paper_id = f"{source}:{source_id}"
    if not is_valid_paper_id(paper_id):
        raise ValueError(f"Invalid paper ID: {paper_id!r}; arXiv IDs must include a version")
    return paper_id


def is_valid_chunk_id(chunk_id: str) -> bool:
    """Check the fixed regex plus paper version and positive page/ordinal constraints."""
    if not isinstance(chunk_id, str) or not _CHUNK_ID_RE.fullmatch(chunk_id):
        return False
    paper_id, page, ordinal = chunk_id.rsplit(":", 2)
    return is_valid_paper_id(paper_id) and int(page[1:]) > 0 and int(ordinal[1:]) > 0


def make_chunk_id(paper_id: str, page: int, ordinal: int) -> str:
    """Build a deterministic chunk ID with a paper-wide, 1-indexed ordinal."""
    if not is_valid_paper_id(paper_id):
        raise ValueError(f"Invalid paper ID: {paper_id!r}")
    if type(page) is not int or not 1 <= page <= 9999:
        raise ValueError("page must be an integer between 1 and 9999")
    if type(ordinal) is not int or not 1 <= ordinal <= 9999:
        raise ValueError("ordinal must be an integer between 1 and 9999")
    return f"{paper_id}:p{page}:c{ordinal:02d}"


def paper_file_stem(paper_id: str) -> str:
    """Use the same Windows-safe paper filename across ingestion, parsing, and chunking."""
    if not is_valid_paper_id(paper_id):
        raise ValueError(f"Invalid paper ID: {paper_id!r}")
    return paper_id.replace(":", "_").replace("/", "_")


def make_run_id(started_at: datetime | None = None) -> str:
    """Build a UTC timestamp plus random suffix, so runs never reuse a timestamp alone."""
    started_at = started_at if started_at is not None else datetime.now(UTC)
    if started_at.utcoffset() is None:
        raise ValueError("started_at must include a timezone")
    timestamp = started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{timestamp}_{secrets.token_hex(3)}"


def is_valid_run_id(run_id: str) -> bool:
    """Check both the run ID format and its calendar timestamp."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        return False
    try:
        datetime.strptime(run_id.split("_", 1)[0], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True
