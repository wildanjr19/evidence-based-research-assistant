"""Serial, cached downloads with a persistent request budget."""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import yaml

from rag.files import atomic_write


@dataclass(frozen=True)
class DownloadSettings:
    bibliography_run: str
    output_dir: str
    cache_dir: str
    budget_path: str
    allowed_hosts: list[str]
    preferred_keys: list[str]
    allowed_licenses: list[str]
    max_requests: int
    max_pdfs: int
    max_pdf_bytes: int
    max_metadata_bytes: int
    request_delay_seconds: float
    timeout_seconds: float
    max_redirects: int
    min_title_coverage: float


def load_download_settings(path: Path) -> DownloadSettings:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid download YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Download settings must be a mapping")
    try:
        settings = DownloadSettings(**raw)
    except TypeError as exc:
        raise ValueError(f"Invalid download settings: {exc}") from exc
    for name in (
        "max_requests",
        "max_pdfs",
        "max_pdf_bytes",
        "max_metadata_bytes",
        "max_redirects",
    ):
        value = getattr(settings, name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name}: expected a positive integer")
    for name in ("request_delay_seconds", "timeout_seconds", "min_title_coverage"):
        value = getattr(settings, name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name}: expected a positive finite number")
    if settings.request_delay_seconds < 3 or settings.min_title_coverage > 1:
        raise ValueError("Require request delay >= 3s and title coverage <= 1")
    for name in ("allowed_hosts", "preferred_keys", "allowed_licenses"):
        value = getattr(settings, name)
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise ValueError(f"{name}: expected a nonempty list of strings")
    for name in ("bibliography_run", "output_dir", "cache_dir", "budget_path"):
        if not isinstance(getattr(settings, name), str) or not getattr(settings, name).strip():
            raise ValueError(f"{name}: expected a path")
    return settings


class BudgetExhausted(ValueError):
    pass


class DownloadHTTP:
    def __init__(self, settings: DownloadSettings, client: httpx.Client, allow_network: bool):
        self.settings = settings
        self.client = client
        self.allow_network = allow_network
        self.cache_hits = 0
        self.ledger_path = Path(settings.budget_path)
        self.ledger = {
            "max_requests": settings.max_requests,
            "max_pdfs": settings.max_pdfs,
            "requests": [],
            "pdf_attempts": [],
        }
        if self.ledger_path.exists():
            self.ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if (self.ledger.get("max_requests"), self.ledger.get("max_pdfs")) != (
                settings.max_requests,
                settings.max_pdfs,
            ):
                raise ValueError("Budget limits changed; a new authorization is required")
            if not isinstance(self.ledger.get("requests"), list) or not isinstance(
                self.ledger.get("pdf_attempts"), list
            ):
                raise ValueError("Invalid download budget ledger")
        self.initial_requests = len(self.ledger["requests"])
        self._last_request = None

    def _save_ledger(self) -> None:
        atomic_write(self.ledger_path, json.dumps(self.ledger, indent=2).encode("utf-8"))

    def checked_url(self, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or url.username
            or url.password
            or url.hostname not in self.settings.allowed_hosts
            or url.port not in (None, 80, 443)
            or url.fragment
        ):
            raise ValueError("URL is outside the configured public source hosts")
        return urlunsplit(("https", url.hostname, url.path or "/", url.query, ""))

    def pdf_slots_used(self) -> int:
        """Count received PDFs and unknown outcomes; complete HTML uses no PDF slot."""
        count = 0
        for url in self.ledger["pdf_attempts"]:
            key = hashlib.sha256(url.encode()).hexdigest()
            cache = Path(self.settings.cache_dir) / f"{key}.json"
            if cache.exists():
                record = json.loads(cache.read_text(encoding="utf-8"))
                content = cache.with_suffix(".bin").read_bytes()
                if hashlib.sha256(content).hexdigest() == record[
                    "sha256"
                ] and not content.startswith(b"%PDF-"):
                    continue
            count += 1
        return count

    def get(self, url: str, *, pdf: bool = False) -> tuple[bytes, str, str]:
        original_url = self.checked_url(url)
        limit = self.settings.max_pdf_bytes if pdf else self.settings.max_metadata_bytes
        key = hashlib.sha256(original_url.encode()).hexdigest()
        cache = Path(self.settings.cache_dir) / f"{key}.json"
        if cache.exists():
            record = json.loads(cache.read_text(encoding="utf-8"))
            content = (cache.parent / f"{key}.bin").read_bytes()
            if len(content) > limit:
                raise ValueError("Cached response exceeds configured size limit")
            if hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError("Cached response hash differs")
            self.checked_url(record["url"])
            self.cache_hits += 1
            return content, record["url"], record["content_type"]
        if not self.allow_network:
            raise ValueError("Download cache miss; use --allow-network for authorized requests")
        if pdf:
            if self.pdf_slots_used() >= self.settings.max_pdfs:
                raise BudgetExhausted("PDF attempt budget exhausted")
            self.ledger["pdf_attempts"].append(original_url)
            self._save_ledger()
        url = original_url
        for _ in range(self.settings.max_redirects + 1):
            url = self.checked_url(url)
            if len(self.ledger["requests"]) >= self.settings.max_requests:
                raise BudgetExhausted("HTTP request budget exhausted")
            if self._last_request is not None:
                time.sleep(
                    max(
                        0,
                        self.settings.request_delay_seconds
                        - (time.monotonic() - self._last_request),
                    )
                )
            event = {"url": url, "at": datetime.now(UTC).isoformat(), "status": "attempted"}
            self.ledger["requests"].append(event)
            self._save_ledger()
            self._last_request = time.monotonic()
            with self.client.stream(
                "GET", url, follow_redirects=False, timeout=self.settings.timeout_seconds
            ) as response:
                event["status"] = response.status_code
                self._save_ledger()
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                if int(response.headers.get("content-length", "0")) > limit:
                    raise ValueError("Response exceeds configured size limit")
                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > limit:
                        raise ValueError("Response exceeds configured size limit")
                    content.extend(chunk)
                content = bytes(content)
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
            atomic_write(cache.with_suffix(".bin"), content)
            atomic_write(
                cache,
                json.dumps(
                    {
                        "url": url,
                        "content_type": content_type,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ).encode("utf-8"),
            )
            return content, url, content_type
        raise ValueError("Too many redirects")
