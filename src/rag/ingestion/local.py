"""Admit bounded local PDFs with hashed identity and article-license evidence."""

import hashlib
import json
import logging
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pymupdf

from rag.config import Config
from rag.files import atomic_write
from rag.ids import make_paper_id, make_run_id, paper_file_stem
from rag.ingestion.arxiv import license_from_url
from rag.ingestion.bibliography import normalize_doi
from rag.ingestion.downloads import ArticlePage, _coverage, _words
from rag.ingestion.store import PAPER_SCHEMA

logger = logging.getLogger(__name__)


def _checked_file(path: Path, expected: str) -> bytes:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"Local evidence hash differs: {path}")
    return content


def _compact(text: str) -> str:
    return re.sub(r"[\s\u200b\u00ad]", "", unicodedata.normalize("NFKC", text)).lower()


def _pdf_has_doi(doi: str, text: str) -> bool:
    text = unicodedata.normalize("NFKC", text).replace("\u200b", "").replace("\u00ad", "")
    text = re.sub(r"([/.-])\s+(?=[A-Za-z0-9])", r"\1", text)
    return doi in {
        normalize_doi(value.rstrip(".,;:"))
        for value in re.findall(r"10\.\d{4,9}/[A-Za-z0-9._;()/:-]+", text)
    }


def prepare_local(
    config: Config,
    manifest_path: Path,
    *,
    max_documents: int | None = None,
    local_collection: bool = False,
) -> dict:
    """Validate the entire bounded local manifest before writing a fresh corpus, offline."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if local_collection and manifest.get("admission_policy") != "user_local_collection":
        raise ValueError("Local collection requires an explicit manifest policy")
    records = manifest["papers"]
    if max_documents is None:
        max_documents = min(3, config.ingestion.max_papers)
    if type(max_documents) is not int or not 1 <= max_documents <= config.ingestion.max_papers:
        raise ValueError("max_documents must be within ingestion.max_papers")
    if not 1 <= len(records) <= max_documents:
        raise ValueError("Local manifest exceeds the explicit document limit")
    root = Path(manifest["input_root"]).resolve()
    db = Path(config.paths.db_path)
    if db.exists():
        raise ValueError("Local admission requires a new database")
    for target in (db, Path(config.paths.raw_dir), Path(config.paths.index_dir)):
        if target.resolve().is_relative_to(root) or root.is_relative_to(target.resolve()):
            raise ValueError("Local source directory is protected")
    bibliography = Path(manifest["bibliography_run"])
    if set(manifest["bibliography_sha256"]) != {"entries.jsonl", "references.jsonl"}:
        raise ValueError("Both bibliography hashes are required")
    for name, expected in manifest["bibliography_sha256"].items():
        _checked_file(bibliography / name, expected)
    entries = {}
    for line in (bibliography / "entries.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        entries.setdefault(entry["citation_key"], []).append(entry)
    prepared, seen = [], set()
    for record in records:
        matches = entries.get(record["citation_key"], [])
        if matches and all(
            (e["reference_id"], e["metadata"])
            == (matches[0]["reference_id"], matches[0]["metadata"])
            for e in matches
        ):
            matches = matches[:1]
        if len(matches) != 1:
            raise ValueError("Local citation key is absent or ambiguous")
        entry = matches[0]
        metadata = entry["metadata"]
        private = record.get("identity_evidence") == "user_local_collection"
        if private and not local_collection:
            raise ValueError("User-provided identity requires local_collection opt-in")
        doi = normalize_doi(record["doi"]) if record.get("doi") else None
        if (not doi and not private) or (entry["doi"] and entry["doi"] != doi):
            raise ValueError("Local DOI conflicts with bibliography")
        source = root / record["file"]
        if not source.resolve().is_relative_to(root) or source.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files inside the input directory may be admitted")
        if source.stat().st_size > config.ingestion.max_pdf_bytes:
            raise ValueError("Local PDF exceeds configured size")
        content = _checked_file(source, record["pdf_sha256"])
        if not content.startswith(b"%PDF-"):
            raise ValueError("Local input is not a PDF")
        page = ArticlePage()
        identity = record.get("identity_evidence", "publisher")
        url = urlsplit(record["landing_url"])
        if private and record["landing_url"] != source.resolve().as_uri():
            raise ValueError("Local collection location differs from source PDF")
        if not private and (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Publisher evidence URL differs or is invalid")
        surname = metadata["author"].split(" and ")[0].split()[-1]
        prior = None
        if identity == "publisher":
            proof = record["publisher_evidence"]
            if proof["url"] != record["landing_url"]:
                raise ValueError("Publisher evidence URL differs")
            page.feed(_checked_file(Path(proof["path"]), proof["sha256"]).decode("utf-8"))
            titles = page.meta["citation_title"]
            page_dois = page.meta["citation_doi"] + page.meta["dc.identifier.doi"]
            if (
                len(titles) != 1
                or _coverage(metadata["title"], titles[0]) < 0.9
                or doi not in {normalize_doi(value) for value in page_dois}
                or not (_words(surname) <= _words(" ".join(page.meta["citation_author"])))
            ):
                raise ValueError("Publisher identity does not match local bibliography/DOI")
        elif identity == "prior_snapshot_report":
            proof = record["prior_snapshot_evidence"]
            report = json.loads(_checked_file(Path(proof["path"]), proof["sha256"]))
            matches = [
                row
                for row in report["references"]
                if row.get("status") == "pdf_ready"
                and row.get("pdf_sha256") == record["pdf_sha256"]
                and row.get("reference_id") == entry["reference_id"]
            ]
            if len(matches) != 1:
                raise ValueError("Prior snapshot identity absent or ambiguous")
            prior = matches[0]
            if any(
                prior[name] != record[name]
                for name in ("license", "license_url", "landing_url", "pages")
            ):
                raise ValueError("Prior snapshot provenance differs")
        elif identity not in {"pdf_doi", "user_local_collection"}:
            raise ValueError("Unsupported local identity evidence")
        license_url = record["license_url"]
        if private and (
            record["license"] != "LicenseRef-UserProvided-Unverified"
            or license_url is not None
            or record["license_evidence"] != "user_local_collection"
        ):
            raise ValueError("Unverified collection must not claim a verified article license")
        if not private and (
            record["license"] not in config.ingestion.allowed_licenses
            or license_from_url(license_url) != record["license"]
        ):
            raise ValueError("Local license is invalid or outside allowlist")
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or len(document) != record["pages"] or not len(document):
                raise ValueError("Local PDF page count/encryption differs")
            opening = "\n".join(p.get_text() for p in list(document)[:2])
            if identity == "pdf_doi" and not _pdf_has_doi(doi, opening):
                raise ValueError("Local DOI is absent from PDF identity pages")
            if not private and (
                _coverage(metadata["title"], opening) < 0.9
                or not (_words(surname) <= _words(opening))
                or metadata["year"] not in opening
            ):
                raise ValueError("Local PDF title/author/year differs")
            if private:
                pass
            elif record["license_evidence"] == "prior_snapshot_report":
                if prior is None:
                    raise ValueError("Prior license requires bound snapshot identity evidence")
            elif record["license_evidence"] == "pdf_article_license":
                numbers = record["license_pages"]
                if (
                    not 1 <= len(numbers) <= 2
                    or any(type(n) is not int or not 1 <= n <= len(document) for n in numbers)
                    or numbers != list(range(numbers[0], numbers[-1] + 1))
                ):
                    raise ValueError("Article license requires one or two consecutive PDF pages")
                text = " ".join(" ".join(document[n - 1].get_text().split()) for n in numbers)
                statement = " ".join(record["license_statement"].split())
                links = {
                    link.get("uri", "").replace("http://", "https://").rstrip("/")
                    for n in numbers
                    for link in document[n - 1].get_links()
                }
                if (
                    not statement
                    or statement not in text
                    or not re.search(
                        r"this (?:(?:article|work) is "
                        r"(?:licensed|an open.access article|distributed)"
                        r"|is an.?open.access article)",
                        statement,
                        re.I,
                    )
                    or not re.search(r"creative commons|cc.?by", statement, re.I)
                    or (
                        _compact(license_url).replace("http://", "https://").rstrip("/")
                        not in _compact(text).replace("http://", "https://")
                        and license_url.replace("http://", "https://").rstrip("/") not in links
                    )
                ):
                    raise ValueError("PDF article license statement/link is not confirmed")
            elif record["license_evidence"] == "publisher_rel_license":
                if identity != "publisher":
                    raise ValueError("Publisher license requires publisher identity evidence")
                licenses = {license_from_url(link) for link in page.explicit_licenses}
                if licenses != {record["license"]}:
                    raise ValueError("Publisher article license absent or ambiguous")
            elif record["license_evidence"] == "pdf_copyright_page":
                number = record["license_page"]
                if type(number) is not int or not 1 <= number <= len(document):
                    raise ValueError("Invalid PDF license page")
                license_page = document[number - 1]
                text = license_page.get_text().lower()
                links = {
                    link.get("uri", "").replace("http://", "https://").rstrip("/")
                    for link in license_page.get_links()
                }
                if (
                    license_url.replace("http://", "https://").rstrip("/") not in links
                    or "copyright" not in text
                    or not (_words(surname) <= _words(text))
                    or "creative commons" not in text
                ):
                    raise ValueError("PDF copyright license evidence absent")
            else:
                raise ValueError("Unsupported local license evidence")
        observed = datetime.fromisoformat(record["observed_at"])
        if observed.utcoffset() is None:
            raise ValueError("Local observed_at requires a timezone")
        namespace = "local" if private else "crossref"
        source_id = (
            f"sha256_{record['pdf_sha256']}" if private else f"{doi}_sha256_{record['pdf_sha256']}"
        )
        paper_id = make_paper_id(namespace, source_id)
        if paper_id in seen or record["pdf_sha256"] in seen:
            raise ValueError("Duplicate local PDF snapshot")
        seen.update((paper_id, record["pdf_sha256"]))
        path = Path(config.paths.raw_dir) / "pdf" / (paper_file_stem(paper_id) + ".pdf")
        if path.exists() and path.read_bytes() != content:
            raise ValueError("Existing raw PDF differs")
        values = (
            paper_id,
            namespace,
            source_id,
            metadata["title"],
            json.dumps(metadata["author"].split(" and "), ensure_ascii=False),
            int(metadata["year"]),
            None,
            doi,
            record["license"],
            license_url,
            record["landing_url"],
            record["pdf_sha256"],
            record["observed_at"],
        )
        prepared.append(
            (
                values,
                path,
                content,
                dict(
                    record,
                    paper_id=paper_id,
                    pdf_path=str(path),
                    reference_id=entry["reference_id"],
                ),
            )
        )
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db)) as connection:
        connection.executescript(PAPER_SCHEMA)
        with connection:
            for values, path, content, _ in prepared:
                if not path.exists():
                    atomic_write(path, content)
                connection.execute(
                    "INSERT INTO paper (paper_id, source, source_id, title, authors, year, "
                    "venue, doi, license, license_url, landing_url, pdf_sha256, fetched_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
    report = dict(
        run_id=make_run_id(),
        kind="user_local_collection" if local_collection else "evidence_checked_local_pdf_manifest",
        admission_policy="user_local_collection"
        if local_collection
        else "verified_article_license",
        reviewer="ai_assistant_not_human_ground_truth",
        max_documents=max_documents,
        manifest=str(manifest_path),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        papers=[p[3] for p in prepared],
        fetched_at_semantics="local_observation_time_not_download_receipt",
        network_requests=0,
    )
    destination = (
        Path(config.paths.index_dir)
        / "reports"
        / ("prepare-local-" + report["run_id"].replace(":", "-") + ".json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    logger.info("Prepared %d reviewed local PDFs: %s", len(prepared), destination)
    return report
