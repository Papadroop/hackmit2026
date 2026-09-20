"""Fetching a URL for ingestion: a browser-like request, a size cap, and the Wayback Machine as
the fallback when the live site refuses or is unreachable."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = 20.0
MAX_BYTES = 25 * 1024 * 1024
WAYBACK_AVAILABLE = "https://archive.org/wayback/available"


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    body: bytes
    encoding: str | None = None

    @property
    def text(self) -> str:
        for enc in (self.encoding, "utf-8"):
            if not enc:
                continue
            try:
                return self.body.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return self.body.decode("utf-8", errors="replace")

    @property
    def is_pdf(self) -> bool:
        return self.body[:5] == b"%PDF-" or "application/pdf" in self.content_type

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type or self.body[:1] in (b"{", b"[")

    def json(self) -> Any:
        return json.loads(self.text)


def fetch(url: str, *, timeout: float = TIMEOUT, max_bytes: int = MAX_BYTES) -> Fetched:
    """GET the URL, following redirects. Raises FetchError with the HTTP status when the server
    refuses, or without one when it cannot be reached."""
    if not re.match(r"^https?://", url, re.I):
        raise FetchError(f"Only http and https URLs can be fetched, not {url!r}")
    try:
        with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=timeout) as client:
            response = client.get(url)
    except httpx.TimeoutException as exc:
        raise FetchError(f"{url} did not respond within {timeout:.0f} s") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"{url} could not be fetched: {exc.__class__.__name__}: {exc}") from exc
    if response.status_code >= 400:
        raise FetchError(f"{url} answered HTTP {response.status_code}", status=response.status_code)
    if len(response.content) > max_bytes:
        raise FetchError(f"{url} is larger than {max_bytes // (1024 * 1024)} MB")
    return Fetched(str(response.url), response.status_code, response.headers.get("content-type", ""), response.content, response.encoding)


def wayback_snapshot(url: str, *, timeout: float = TIMEOUT) -> tuple[str, str] | None:
    """(snapshot URL without the archive toolbar, timestamp) of the closest Wayback Machine
    capture, or None when there is none or the archive is rate-limiting."""
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout) as client:
            response = client.get(WAYBACK_AVAILABLE, params={"url": url})
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    closest = (data.get("archived_snapshots") or {}).get("closest") or {}
    snapshot = closest.get("url")
    stamp = closest.get("timestamp")
    if not snapshot or not stamp:
        return None
    snapshot = re.sub(r"/web/(\d+)/", r"/web/\1id_/", snapshot, count=1)
    return snapshot, stamp


def wayback_url(url: str, stamp: str = "2") -> str:
    return f"https://web.archive.org/web/{stamp}id_/{quote(url, safe=':/?&=%')}"
