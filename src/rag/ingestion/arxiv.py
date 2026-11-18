import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from rag.config import IngestionConfig
from rag.files import atomic_write
from rag.ids import make_paper_id, paper_file_stem

logger = logging.getLogger(__name__)
ATOM = "{http://www.w3.org/2005/Atom}"
RAW = "{http://arxiv.org/OAI/arXivRaw/}"
OAI = "{http://www.openarchives.org/OAI/2.0/}"
SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
SOURCE_ID_RE = re.compile(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-zA-Z][a-zA-Z0-9.-]*/[0-9]{7})v[1-9][0-9]*")
LICENSES = {
    "https://creativecommons.org/licenses/by/4.0": "CC-BY-4.0",
    "https://creativecommons.org/licenses/by/3.0": "CC-BY-3.0",
    "https://creativecommons.org/licenses/by-sa/4.0": "CC-BY-SA-4.0",
    "https://creativecommons.org/publicdomain/zero/1.0": "CC0-1.0",
}


def license_from_url(url: str) -> str:
    normalized = url.strip().replace("http://", "https://", 1).rstrip("/")
    if normalized not in LICENSES:
        raise ValueError("missing or unrecognized reuse license")
    return LICENSES[normalized]


@dataclass(frozen=True)
class Paper:
    source_id: str
    title: str
    authors: list[str]
    year: int
    venue: str | None
    doi: str | None
    license: str
    license_url: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("invalid versioned arXiv source_id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("paper title is required")
        if (
            not isinstance(self.authors, list)
            or not self.authors
            or not all(isinstance(author, str) and author.strip() for author in self.authors)
        ):
            raise ValueError("authors must be a non-empty list of names")
        if type(self.year) is not int or not 1 <= self.year <= 9999:
            raise ValueError("invalid publication year")
        if any(
            value is not None and not isinstance(value, str) for value in (self.venue, self.doi)
        ):
            raise ValueError("venue and doi must be strings or null")
        if (
            not isinstance(self.license_url, str)
            or license_from_url(self.license_url) != self.license
        ):
            raise ValueError("license does not match its source URL")

    @property
    def paper_id(self) -> str:
        return make_paper_id("arxiv", self.source_id)

    @property
    def landing_url(self) -> str:
        return f"https://arxiv.org/abs/{self.source_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.source_id}"

    @property
    def filename(self) -> str:
        # Keep canonical IDs in metadata; sanitize only filenames for Windows.
        return f"{paper_file_stem(self.paper_id)}.pdf"


def _text(element: ET.Element, path: str) -> str:
    return " ".join((element.findtext(path) or "").split())


def _search_metadata(entry: ET.Element) -> dict:
    url = urlsplit(_text(entry, f"{ATOM}id"))
    source_id = url.path.removeprefix("/abs/")
    if (
        url.scheme not in {"http", "https"}
        or url.hostname != "arxiv.org"
        or not url.path.startswith("/abs/")
        or not SOURCE_ID_RE.fullmatch(source_id)
    ):
        raise ValueError("search result lacks a valid versioned arXiv ID")
    return {
        "source_id": source_id,
        "title": _text(entry, f"{ATOM}title"),
        "authors": [_text(author, f"{ATOM}name") for author in entry.findall(f"{ATOM}author")],
        "year": datetime.fromisoformat(_text(entry, f"{ATOM}published")).year,
        "venue": _text(entry, "{http://arxiv.org/schemas/atom}journal_ref") or None,
        "doi": _text(entry, "{http://arxiv.org/schemas/atom}doi") or None,
    }


def parse_license_record(xml: bytes, source_id: str) -> tuple[str, str]:
    root = ET.fromstring(xml)
    if (error := root.find(f"{OAI}error")) is not None:
        raise ValueError(f"OAI-PMH error: {error.attrib.get('code')}")
    record = root.find(f"{OAI}GetRecord/{OAI}record/{OAI}metadata/{RAW}arXivRaw")
    if record is None or _text(record, f"{RAW}id") != source_id.rsplit("v", 1)[0]:
        raise ValueError("license record does not match the requested paper")
    versions = [version.attrib.get("version", "") for version in record.findall(f"{RAW}version")]
    if not versions or any(not re.fullmatch(r"v[1-9][0-9]*", version) for version in versions):
        raise ValueError("license record has no valid version history")
    latest = max(versions, key=lambda version: int(version[1:]))
    # OAI exposes latest-version metadata; applying that license to an older version is unsafe.
    if source_id.rsplit("v", 1)[1] != latest[1:]:
        raise ValueError("search version differs from latest licensed OAI version")
    license_url = _text(record, f"{RAW}license")
    return license_from_url(license_url), license_url


class ArxivClient:
    def __init__(self, config: IngestionConfig, cache_dir: Path, client: httpx.Client) -> None:
        self.config = config
        self.cache_dir = cache_dir / "arxiv"
        self.client = client
        self._last_request: float | None = None

    def _wait(self) -> None:
        if self._last_request is not None:
            remaining = self.config.request_delay_seconds - (time.monotonic() - self._last_request)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request = time.monotonic()

    def _xml(self, url: str, params: dict) -> bytes:
        request = self.client.build_request("GET", url, params=params)
        day = datetime.now(UTC).date().isoformat()
        key = hashlib.sha256(str(request.url).encode()).hexdigest()
        path = self.cache_dir / day / f"{key}.xml"
        if path.exists():
            content = path.read_bytes()
        else:
            self._wait()
            response = self.client.send(request)
            response.raise_for_status()
            content = response.content
            ET.fromstring(content)
            atomic_write(path, content)
        return content

    def discover(self) -> list[Paper]:
        """Inspect at most max_papers search hits; rejected licenses do not trigger backfilling."""
        papers: list[Paper] = []
        seen: set[str] = set()
        inspected = 0
        while inspected < self.config.max_papers:
            limit = min(self.config.page_size, self.config.max_papers - inspected)
            xml = self._xml(
                "https://export.arxiv.org/api/query",
                {
                    "search_query": self.config.query,
                    "start": inspected,
                    "max_results": limit,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                },
            )
            root = ET.fromstring(xml)
            if root.tag != f"{ATOM}feed":
                raise ValueError("arXiv search response is not an Atom feed")
            entries = root.findall(f"{ATOM}entry")[:limit]
            if any("/api/errors" in _text(entry, f"{ATOM}id") for entry in entries):
                raise ValueError("arXiv search API returned an error entry")
            if not entries:
                break
            for entry in entries:
                entry_id = _text(entry, f"{ATOM}id")
                try:
                    metadata = _search_metadata(entry)
                    source_id = metadata["source_id"]
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    xml = self._xml(
                        "https://oaipmh.arxiv.org/oai",
                        {
                            "verb": "GetRecord",
                            "metadataPrefix": "arXivRaw",
                            "identifier": f"oai:arXiv.org:{source_id.rsplit('v', 1)[0]}",
                        },
                    )
                    license_id, license_url = parse_license_record(xml, source_id)
                    if license_id not in self.config.allowed_licenses:
                        raise ValueError(f"license {license_id} is not allowed by config")
                    papers.append(Paper(**metadata, license=license_id, license_url=license_url))
                except (ValueError, ET.ParseError) as exc:
                    logger.warning("Rejected %s: %s", entry_id, exc)
            inspected += len(entries)
            total = root.findtext(f"{SEARCH}totalResults")
            if total is not None and inspected >= int(total):
                break
        logger.info("Inspected %d search hits; accepted %d licensed papers", inspected, len(papers))
        return papers

    def download_pdf(self, paper: Paper) -> bytes:
        self._wait()
        content = bytearray()
        with self.client.stream("GET", paper.pdf_url) as response:
            response.raise_for_status()
            for block in response.iter_bytes():
                if len(content) + len(block) > self.config.max_pdf_bytes:
                    raise ValueError(f"{paper.paper_id}: PDF exceeds ingestion.max_pdf_bytes")
                content.extend(block)
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"{paper.paper_id}: response is not a PDF")
        return bytes(content)
