"""Audit bibliography metadata without admitting unlicensed documents into the corpus."""

import hashlib
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit

import bibtexparser
from bibtexparser.model import DuplicateBlockKeyBlock, Entry, ParsingFailedBlock

from rag.files import atomic_write
from rag.ids import make_run_id

logger = logging.getLogger(__name__)
METADATA_FIELDS = ("title", "author", "year", "doi", "url", "file")


def normalize_doi(value: str) -> str | None:
    """Accept bare DOIs and DOI resolver URLs; retain the original value elsewhere."""
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    if value.lower().startswith(("http://", "https://")):
        try:
            url = urlsplit(value)
        except ValueError:
            return None
        if url.hostname not in {"doi.org", "dx.doi.org"} or url.username or url.password:
            return None
        if url.query or url.fragment:
            return None
        value = unquote(url.path.lstrip("/"))
    return value.lower() if re.fullmatch(r"10\.\d{4,9}/[^\s{}]+", value) else None


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def audit_bibliography(text: str) -> dict:
    """Preserve every input entry, including duplicate keys, and flag uncertain matches."""
    library = bibtexparser.parse_string(text)
    entries = []
    failures = []
    for block in library.blocks:
        duplicate_key = isinstance(block, DuplicateBlockKeyBlock)
        if duplicate_key and isinstance(block.ignore_error_block, Entry):
            # Duplicate blocks bypass default middleware; parse each in an isolated library.
            isolated = bibtexparser.parse_string(block.raw)
            entry = isolated.entries[0] if not isolated.failed_blocks and isolated.entries else None
        else:
            entry = block if isinstance(block, Entry) else None
        if entry is None:
            if isinstance(block, ParsingFailedBlock):
                failures.append(
                    {
                        "line": block.start_line + 1,
                        "kind": type(block).__name__,
                        "message": str(block.error),
                    }
                )
            continue
        metadata = {
            name: str(entry.get(name).value) if entry.get(name) else "" for name in METADATA_FIELDS
        }
        doi = normalize_doi(metadata["doi"]) if metadata["doi"] else None
        issues = [
            f"missing_{name}" for name in ("title", "author", "year") if not metadata[name].strip()
        ]
        if metadata["year"] and not re.fullmatch(r"\d{4}", metadata["year"].strip()):
            issues.append("invalid_year")
        if metadata["doi"] and doi is None:
            issues.append("invalid_doi")
        if not doi:
            issues.append("doi_unavailable")
        identity = {"doi": doi} if doi else {"type": entry.entry_type.lower(), **metadata}
        entries.append(
            {
                "entry_ordinal": len(entries) + 1,
                "source_line": block.start_line + 1,
                "citation_key": entry.key,
                "entry_type": entry.entry_type.lower(),
                "metadata": metadata,
                "doi": doi,
                "reference_id": "ref_" + _digest(identity),
                "issues": issues,
            }
        )
    if not entries and not failures:
        raise ValueError("Bibliography contains no entries")

    groups = defaultdict(list)
    keys = defaultdict(list)
    titles = defaultdict(set)
    for entry in entries:
        groups[entry["reference_id"]].append(entry)
        keys[entry["citation_key"]].append(entry["entry_ordinal"])
        title = re.sub(
            r"[\W_]+", " ", unicodedata.normalize("NFC", entry["metadata"]["title"]).casefold()
        ).strip()
        if title:
            titles[title].add(entry["reference_id"])

    references = []
    for reference_id, members in groups.items():
        conflicts = [
            name
            for name in ("title", "author", "year")
            if len({m["metadata"][name].strip() for m in members if m["metadata"][name].strip()})
            > 1
        ]
        references.append(
            {
                "reference_id": reference_id,
                "doi": members[0]["doi"],
                "entry_ordinals": [m["entry_ordinal"] for m in members],
                "citation_keys": list(dict.fromkeys(m["citation_key"] for m in members)),
                "metadata_conflicts": conflicts,
                "status": "needs_metadata_review" if conflicts else "pending_pdf",
            }
        )
    return {
        "entries": entries,
        "references": references,
        "summary": {
            "input_entries": len(entries),
            "unique_references": len(references),
            "entry_types": dict(Counter(e["entry_type"] for e in entries)),
            "duplicate_keys": {
                key: ordinals for key, ordinals in keys.items() if len(ordinals) > 1
            },
            "duplicate_references": [
                r["entry_ordinals"] for r in references if len(r["entry_ordinals"]) > 1
            ],
            "title_match_candidates": [sorted(ids) for ids in titles.values() if len(ids) > 1],
            "missing_metadata": dict(Counter(issue for e in entries for issue in e["issues"])),
            "metadata_conflicts": sum(bool(r["metadata_conflicts"]) for r in references),
            "parse_failures": failures,
        },
    }


def import_bibliography(source: Path, output_dir: Path) -> tuple[Path, dict]:
    """Write a new audit run; repeated imports preserve prior runs and reference identities."""
    content = source.read_bytes()
    audit = audit_bibliography(content.decode("utf-8-sig"))
    run_id = make_run_id()
    destination = output_dir / run_id.replace(":", "-")
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("entries", "references"):
        encoded = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audit[name])
        atomic_write(destination / f"{name}.jsonl", encoded.encode("utf-8"))
    report = {
        "run_id": run_id,
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "parser": {"name": "bibtexparser", "version": version("bibtexparser")},
        "config": {"metadata_fields": list(METADATA_FIELDS), "merge_by": "doi_or_exact_metadata"},
        "status": "needs_review" if audit["summary"]["parse_failures"] else "complete",
        **audit["summary"],
    }
    report["config_sha256"] = _digest(report["config"])
    atomic_write(
        destination / "report.json",
        json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    logger.info(
        "Imported %d entries into %d references; report: %s",
        report["input_entries"],
        report["unique_references"],
        destination / "report.json",
    )
    return destination, report
