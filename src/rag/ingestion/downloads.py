"""Match bibliography entries to licensed publisher PDFs before corpus ingestion."""

import hashlib
import json
import logging
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx
import pymupdf

from rag.files import atomic_write
from rag.ids import make_run_id
from rag.ingestion.arxiv import license_from_url
from rag.ingestion.bibliography import normalize_doi
from rag.ingestion.download_http import BudgetExhausted, DownloadHTTP, DownloadSettings

logger = logging.getLogger(__name__)


def _words(value: str) -> set[str]:
    text = unicodedata.normalize("NFKD", unescape(value)).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[^\W\d_]+|\d+", text))


def _coverage(expected: str, actual: str) -> float:
    words = _words(expected)
    return len(words & _words(actual)) / len(words) if words else 0.0


class ArticlePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = defaultdict(list)
        self.license_links = []
        self.explicit_licenses = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta":
            key = (values.get("name") or values.get("property") or "").lower()
            self.meta[key].append(values.get("content") or "")
        if tag in {"a", "link"} and values.get("href"):
            href = values["href"]
            if "license" in (values.get("rel") or "").lower().split():
                self.explicit_licenses.append(href)
            if urlsplit(href).hostname in {"creativecommons.org", "www.creativecommons.org"}:
                self.license_links.append(href)


def match_work(entry: dict, work: dict, settings: DownloadSettings) -> None:
    if normalize_doi(work.get("DOI", "")) != entry["doi"]:
        raise ValueError("Crossref DOI differs from bibliography")
    titles = work.get("title") or []
    if not titles or _coverage(entry["metadata"]["title"], titles[0]) < settings.min_title_coverage:
        raise ValueError("Crossref title differs; manual matching required")
    expected_year = int(entry["metadata"]["year"])
    years = {
        part[0]
        for field in ("published", "published-print", "published-online", "issued")
        for part in work.get(field, {}).get("date-parts", [])
        if part
    }
    if expected_year not in years:
        raise ValueError("Crossref year differs; manual matching required")
    authors = work.get("author") or []
    first_author = entry["metadata"]["author"].split(" and ")[0]
    if (
        not authors
        or not _words(authors[0].get("family", ""))
        or not (_words(authors[0]["family"]) <= _words(first_author))
    ):
        raise ValueError("Crossref first author differs; manual matching required")


def article_pdf(
    entry: dict, work: dict, page: ArticlePage, page_url: str, settings: DownloadSettings
) -> dict:
    doi_values = page.meta["citation_doi"] + page.meta["dc.identifier.doi"]
    if entry["doi"] not in {normalize_doi(v) for v in doi_values}:
        raise ValueError("Publisher page has no matching DOI; manual matching required")
    titles = page.meta["citation_title"]
    if not titles or _coverage(entry["metadata"]["title"], titles[0]) < settings.min_title_coverage:
        raise ValueError("Publisher title differs; manual matching required")
    links = page.explicit_licenses or page.license_links
    licenses = {license_from_url(url): url for url in links}
    if len(licenses) != 1:
        raise ValueError("Article license missing or ambiguous")
    license_id, license_url = next(iter(licenses.items()))
    if license_id not in settings.allowed_licenses:
        raise ValueError("Article license is outside configured allowed licenses")
    pdf_urls = list(dict.fromkeys(page.meta["citation_pdf_url"]))
    if len(pdf_urls) != 1:
        raise ValueError("Article PDF link missing or ambiguous")
    pdf_url = urljoin(page_url, pdf_urls[0])
    linked_versions = [
        link.get("content-version")
        for link in work.get("link", [])
        if link.get("URL") == pdf_url and link.get("content-version")
    ]
    return {
        "pdf_url": pdf_url,
        "license": license_id,
        "license_url": license_url,
        "license_evidence": "article_rel_license"
        if page.explicit_licenses
        else "article_link_requires_pdf_confirmation",
        "publisher_title": titles[0],
        "declared_language": (page.meta["citation_language"] or [None])[0],
        "content_version": linked_versions[0] if linked_versions else "publisher_linked_pdf",
    }


def validate_pdf(
    content: bytes, content_type: str, entry: dict, candidate: dict, settings: DownloadSettings
) -> dict:
    if content_type not in {
        "application/pdf",
        "application/octet-stream",
    } or not content.startswith(b"%PDF-"):
        raise ValueError("Response is not a PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or document.page_count < 1:
                raise ValueError("PDF is encrypted or has no pages")
            text = "\n".join(document[i].get_text() for i in range(min(2, document.page_count)))
            pages = document.page_count
    except RuntimeError as exc:
        raise ValueError("PDF cannot be opened") from exc
    coverage = _coverage(entry["metadata"]["title"], text)
    first_author = entry["metadata"]["author"].split(" and ")[0]
    surname = first_author.split()[-1] if first_author.split() else ""
    if (
        coverage < settings.min_title_coverage
        or not _words(surname)
        or not (_words(surname) <= _words(text))
        or entry["metadata"]["year"] not in text
    ):
        raise ValueError(
            "PDF title, first author, or year does not match; manual matching required"
        )
    compact = re.sub(r"\s+", "", text).lower()
    license_url = (
        candidate["license_url"].replace("http://", "").replace("https://", "").rstrip("/")
    )
    license_confirmed = license_url.lower() in compact
    if candidate["license_evidence"] != "article_rel_license" and not license_confirmed:
        raise ValueError("Publisher license link not confirmed in PDF; license remains unverified")
    return {
        "pages": pages,
        "title_word_coverage": coverage,
        "first_author_matched": True,
        "year_matched": True,
        "license_url_in_pdf": license_confirmed,
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
    }


def _attempt(entry: dict, http: DownloadHTTP, settings: DownloadSettings) -> dict:
    if not entry["doi"]:
        raise ValueError("DOI unavailable; manual matching required")
    content, metadata_url, _ = http.get(
        "https://api.crossref.org/works/" + quote(entry["doi"], safe="")
    )
    work = json.loads(content)["message"]
    match_work(entry, work, settings)
    page_url = work.get("resource", {}).get("primary", {}).get("URL", "")
    if not page_url:
        raise ValueError("Publisher landing URL unavailable")
    content, page_url, media_type = http.get(page_url)
    if media_type != "text/html":
        raise ValueError("Publisher landing response is not HTML")
    page = ArticlePage()
    page.feed(content.decode("utf-8", errors="replace"))
    candidate = article_pdf(entry, work, page, page_url, settings)
    content, pdf_url, media_type = http.get(candidate["pdf_url"], pdf=True)
    validation = validate_pdf(content, media_type, entry, candidate, settings)
    destination = Path(settings.output_dir) / "pdf" / f"{entry['reference_id']}.pdf"
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != validation["pdf_sha256"]:
            raise ValueError("Existing PDF differs; refusing to overwrite")
    else:
        atomic_write(destination, content)
    return {
        **candidate,
        **validation,
        "pdf_url": pdf_url,
        "landing_url": page_url,
        "metadata_url": metadata_url,
        "pdf_path": str(destination),
        "snapshot_version": "sha256:" + validation["pdf_sha256"],
        "fetched_at": datetime.fromtimestamp(destination.stat().st_mtime, UTC).isoformat(),
    }


def _download_bibliography(
    settings: DownloadSettings, *, allow_network: bool = False, client: httpx.Client | None = None
) -> tuple[Path, dict]:
    """Write statuses for every reference; spend only the persisted campaign budget."""
    root = Path(settings.bibliography_run)
    entries = [
        json.loads(s) for s in (root / "entries.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    references = [
        json.loads(s) for s in (root / "references.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    input_hashes = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("entries.jsonl", "references.jsonl")
    }
    previous = {}
    for path in sorted(
        Path(settings.output_dir).glob("*/report.json"), key=lambda p: p.stat().st_mtime_ns
    ):
        past = json.loads(path.read_text(encoding="utf-8"))
        if past.get("input_sha256") == input_hashes:
            for record in past["references"]:
                if record["status"] != "not_attempted" or record["reference_id"] not in previous:
                    previous[record["reference_id"]] = record
    entries_by_id = {entry["reference_id"]: entry for entry in reversed(entries)}
    for reference in references:
        if not re.fullmatch(r"ref_[0-9a-f]{64}", reference["reference_id"]):
            raise ValueError("Invalid audit reference ID")
        if reference["reference_id"] not in entries_by_id:
            raise ValueError("Reference has no source entry")
    order = {key: i for i, key in enumerate(settings.preferred_keys)}
    references.sort(
        key=lambda r: min(
            (order.get(k, len(order)) for k in r["citation_keys"]), default=len(order)
        )
    )
    run_id = make_run_id()
    destination = Path(settings.output_dir) / run_id.replace(":", "-")
    destination.mkdir(parents=True, exist_ok=False)
    owned_client = client is None
    if owned_client:
        client = httpx.Client(
            headers={"User-Agent": "evidence-based-research-assistant/0.1.0"},
            follow_redirects=False,
        )
    http = DownloadHTTP(settings, client, allow_network)
    statuses = []
    stopped = False
    try:
        for reference in references:
            record = {
                "reference_id": reference["reference_id"],
                "citation_keys": reference["citation_keys"],
                "status": "not_attempted",
                "reason": "pilot_limit",
                "attempted_this_run": False,
            }
            if stopped and reference["reference_id"] in previous:
                record.update(previous[reference["reference_id"]], attempted_this_run=False)
            statuses.append(record)
            if stopped:
                continue
            record["attempted_this_run"] = True
            if reference["metadata_conflicts"]:
                record.update(
                    status="needs_manual_match", reason="conflicting_bibliography_metadata"
                )
                continue
            try:
                details = _attempt(entries_by_id[reference["reference_id"]], http, settings)
                record.update(status="pdf_ready", reason=None, **details)
                logger.info(
                    "PDF ready: %s (%s)", ", ".join(record["citation_keys"]), details["license"]
                )
                if sum(s["status"] == "pdf_ready" for s in statuses) >= settings.max_pdfs:
                    stopped = True
            except BudgetExhausted as exc:
                record.update(status="not_attempted", reason=str(exc))
                stopped = True
            except (ValueError, OSError, KeyError, TypeError, httpx.HTTPError) as exc:
                reason = str(exc)
                status = "needs_manual_match"
                if "license" in reason.lower():
                    status = "license_unverified"
                elif "cache miss" in reason.lower():
                    status = "not_attempted"
                elif reason == "Response is not a PDF" or isinstance(exc, httpx.HTTPError):
                    status = "download_failed"
                record.update(status=status, reason=reason)
                logger.warning("Not ready: %s (%s)", ", ".join(record["citation_keys"]), reason)
    finally:
        if owned_client:
            client.close()
        report = {
            "run_id": run_id,
            "config": asdict(settings),
            "config_sha256": hashlib.sha256(
                json.dumps(asdict(settings), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "versions": {name: version(name) for name in ("httpx", "pymupdf")},
            "allow_network": allow_network,
            "input_sha256": input_hashes,
            "counts": dict(Counter(s["status"] for s in statuses)),
            "request_count_this_run": len(http.ledger["requests"]) - http.initial_requests,
            "request_count_campaign": len(http.ledger["requests"]),
            "pdf_attempts_campaign": len(http.ledger["pdf_attempts"]),
            "pdf_slots_campaign": http.pdf_slots_used(),
            "cache_hits": http.cache_hits,
            "references": statuses,
        }
        atomic_write(
            destination / "report.json",
            json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        lines = [
            "# Status PDF referensi skripsi",
            "",
            f"Request kampanye: {report['request_count_campaign']}/{settings.max_requests}; "
            f"slot PDF: {report['pdf_slots_campaign']}/{settings.max_pdfs}; "
            f"percobaan tautan PDF: {report['pdf_attempts_campaign']}.",
            "",
            "| Citation key | Status | Catatan |",
            "|---|---|---|",
        ]
        for record in statuses:
            note = str(record["reason"] or record.get("license", ""))
            note = note.replace("|", "/").replace("\n", " ")
            keys = ", ".join(record["citation_keys"]).replace("|", "/").replace("\n", " ")
            lines.append(f"| {keys} | {record['status']} | {note} |")
        atomic_write(destination / "status.md", ("\n".join(lines) + "\n").encode("utf-8"))
    logger.info("Download report: %s", destination / "report.json")
    return destination, report


def download_bibliography(
    settings: DownloadSettings,
    *,
    allow_network: bool = False,
    client: httpx.Client | None = None,
) -> tuple[Path, dict]:
    """Serialize campaign runs so concurrent processes cannot spend the same budget."""
    lock_path = Path(settings.budget_path).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock = lock_path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError(
            f"Campaign locked: {lock_path}; check for a running downloader or stale lock"
        ) from exc
    try:
        with lock:
            lock.write(str(os.getpid()))
            lock.flush()
            return _download_bibliography(settings, allow_network=allow_network, client=client)
    finally:
        lock_path.unlink()
