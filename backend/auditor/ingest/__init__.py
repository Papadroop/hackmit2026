"""Ingestion (roadmap step 10): text, URL and PDF to a contract Document with canonical text,
regions and stable character offsets.

    ingest_text(text)            pasted text, or a curated copy with front matter
    ingest_url(url)              live page (HTML, AEM content model, PDF or plain text)
    ingest_pdf(bytes)            an uploaded PDF
    ingest_file(path)            any of the above from disk
    ingest_request(dict)         the API's request body: {"kind": "text" | "url" | "pdf", ...}

Every path ends in `blocks.build_document`, which assembles the canonical text and computes
regions while writing it, then proves the canonical form. Offsets are therefore exact for the
text they were computed on, and `anchor.anchor_span` places spans written against another copy
of the same document (the curated demo text, an earlier fetch) by their text, context and
occurrence, the contract's own rules.

Fallbacks for a URL, in order: the live page; for a demo document, the curated copy under
demo-documents/ (verified text, and what the offline demo needs); otherwise the closest Wayback
Machine snapshot. A page that is only a JavaScript shell is read from its AEM content model
when it has one (shell.com), or reported as unreadable with the word count that proves it.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..documents import normalise_url
from . import fetch as fetch_module
from .aem import aem_blocks, looks_like_model, model_url_for
from .blocks import Block, DocumentMeta, build_document, slug
from .canonical import CanonicalError, canonical_line
from .fetch import FetchError, Fetched
from .html import HtmlResult, company_from_host, html_blocks, is_thin
from .pdf import pdf_blocks
from .text import split_frontmatter, text_blocks

Fetcher = Callable[[str], Fetched]


class IngestError(Exception):
    """The input could not be turned into a document. The message is for the person."""


@dataclass
class Ingested:
    document: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    """Lines for the debug drawer: what was fetched, what was dropped, what was read."""


def today() -> str:
    """The team's local date, which is how the demo documents record `retrieved`."""
    return datetime.now().date().isoformat()


# ----------------------------------------------------------------------------- curated copies


def curated_copies(demo_dir: Path | None) -> dict[str, Path]:
    """Normalised URL -> curated text under demo-documents/."""
    out: dict[str, Path] = {}
    if demo_dir is None or not demo_dir.is_dir():
        return out
    for path in sorted(demo_dir.glob("*.md")):
        fields, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if fields.get("url"):
            out[normalise_url(fields["url"])] = path
    return out


def _split_codes(value: str | None) -> list[str]:
    return [c.strip() for c in (value or "").split(",") if c.strip()]


def _repo_relative(path: Path) -> str:
    try:
        from ..main import REPO_ROOT  # local import: main imports pipeline imports this module
    except Exception:  # pragma: no cover
        return path.name
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return f"{path.parent.name}/{path.name}"


def ingest_curated(path: Path, *, reason: str | None = None) -> Ingested:
    """A curated copy: its front matter is the metadata, its body the text."""
    raw = path.read_text(encoding="utf-8")
    result = text_blocks(raw)
    fm = result.frontmatter
    if not result.blocks:
        raise IngestError(f"{path.name} has no text")
    title = fm.get("title") or _first_title(result.blocks) or path.stem
    method = fm.get("method") or "curated copy"
    if reason:
        method = f"Curated copy ({fm.get('retrieved', 'undated')}) used because the live page could not be read: {reason}. Original method: {method}"
    meta = DocumentMeta(
        title=title,
        company=fm.get("company") or company_from_host(fm.get("url")) or "Not identified",
        method=method,
        retrieved=fm.get("retrieved") or today(),
        text_type=fm.get("text_type") or "web_page",
        industry=fm.get("industry") or "Not identified",
        sasb_codes=_split_codes(fm.get("sasb_codes")),
        url=fm.get("url") or None,
        archive_url=fm.get("archive_url") or None,
        fixture_path=_repo_relative(path),
        id=slug(path.stem),
    )
    document = _build(result.blocks, meta)
    return Ingested(document, [f"Read the curated copy {meta.fixture_path}: {document['word_count']} words"])


# ----------------------------------------------------------------------------- text and PDF


def ingest_text(text: str, *, title: str | None = None) -> Ingested:
    if not text or not text.strip():
        raise IngestError("The text is empty")
    result = text_blocks(text)
    fm = result.frontmatter
    if not result.blocks:
        raise IngestError("The text has no readable lines")
    first_line = result.blocks[0].lines[0]
    title = canonical_line(title or "") or fm.get("title") or _first_title(result.blocks) or (first_line[:77] + "…" if len(first_line) > 80 else first_line)
    meta = DocumentMeta(
        title=title,
        company=fm.get("company") or "Not identified",
        method="Pasted text; blank lines separate paragraphs, '#' headings and '-' bullets recognised.",
        retrieved=fm.get("retrieved") or today(),
        text_type=fm.get("text_type") or "other",
        industry=fm.get("industry") or "Not identified",
        sasb_codes=_split_codes(fm.get("sasb_codes")),
        url=fm.get("url") or None,
        id=slug("pasted", today(), _digest(text)),
    )
    document = _build(result.blocks, meta)
    return Ingested(document, [f"Read pasted text: {document['word_count']} words, {len(result.blocks)} blocks"])


def ingest_pdf(data: bytes, *, filename: str | None = None, url: str | None = None, archive_url: str | None = None) -> Ingested:
    if data[:5] != b"%PDF-":
        raise IngestError("The file is not a PDF")
    try:
        result = pdf_blocks(data)
    except Exception as exc:  # pymupdf raises a range of types for broken files
        raise IngestError(f"The PDF could not be read: {exc}") from exc
    if not result.blocks:
        raise IngestError(f"The PDF has no text layer ({result.pages} pages); it may be scanned images")
    stem = Path(filename).stem if filename else None
    title = result.title or (stem.replace("-", " ").replace("_", " ") if stem else None) or "PDF document"
    meta = DocumentMeta(
        title=title,
        company=company_from_host(url) or "Not identified",
        method=(
            f"Text of the PDF ({result.pages} pages) read by PyMuPDF; {result.dropped} running header, footer and page-number "
            "lines removed; hyphenation at line ends repaired; headings by font size."
        ),
        retrieved=today(),
        text_type="report",
        url=url,
        archive_url=archive_url,
        id=slug(stem or title, today()),
    )
    document = _build(result.blocks, meta)
    notes = [f"Read PDF {filename or url or ''}: {result.pages} pages, {document['word_count']} words, {result.dropped} header/footer lines dropped"]
    return Ingested(document, notes)


# ----------------------------------------------------------------------------- URLs


def ingest_url(url: str, *, demo_dir: Path | None = None, fetcher: Fetcher | None = None) -> Ingested:
    url = url.strip()
    fetcher = fetcher or fetch_module.fetch
    curated = curated_copies(demo_dir).get(normalise_url(url))
    curated_fm: dict[str, str] = {}
    if curated is not None:
        curated_fm, _ = split_frontmatter(curated.read_text(encoding="utf-8"))
    notes: list[str] = []
    archive_url: str | None = None

    try:
        fetched = fetcher(url)
    except FetchError as exc:
        notes.append(str(exc))
        if curated is not None:
            ingested = ingest_curated(curated, reason=str(exc))
            return Ingested(ingested.document, notes + ingested.notes)
        snapshot = fetch_module.wayback_snapshot(url)
        if snapshot is None:
            raise IngestError(f"{exc}, and the Wayback Machine has no copy of it") from exc
        snapshot_url, stamp = snapshot
        try:
            fetched = fetcher(snapshot_url)
        except FetchError as exc2:
            raise IngestError(f"{exc}; the Wayback Machine copy of {stamp} could not be fetched either ({exc2})") from exc2
        archive_url = snapshot_url.replace("id_/", "/", 1)
        notes.append(f"Using the Wayback Machine snapshot of {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}")
    notes.append(f"Fetched {len(fetched.body) // 1024} KB ({fetched.content_type.split(';')[0] or 'unknown type'}) from {fetched.url}")

    if fetched.is_pdf:
        ingested = ingest_pdf(fetched.body, filename=Path(fetched.url).name, url=url, archive_url=archive_url)
        return _with_curated_meta(ingested, curated_fm, curated, notes)

    if fetched.url.endswith(".model.json") or (fetched.is_json and looks_like_model(_json_or_none(fetched))):
        model = _json_or_none(fetched)
        if not looks_like_model(model):
            raise IngestError(f"{fetched.url} is JSON but not an AEM content model")
        return _from_model(model, url, fetched.url, curated_fm, curated, notes, archive_url)

    if fetched.content_type.startswith("text/plain"):
        ingested = ingest_text(fetched.text)
        ingested.document["source"]["url"] = url
        return _with_curated_meta(ingested, curated_fm, curated, notes)

    result = html_blocks(fetched.text, fetched.url)
    if is_thin(result):
        notes.append(f"The HTML has only {result.words} words of readable text; looking for a content model")
        model_url = result.meta.aem_model_url or model_url_for(fetched.url)
        model = None
        try:
            model_fetched = fetcher(model_url)
            model = _json_or_none(model_fetched)
        except FetchError as exc:
            notes.append(f"{model_url}: {exc}")
        if looks_like_model(model):
            return _from_model(model, url, model_url, curated_fm, curated, notes, archive_url)
        if curated is not None:
            reason = f"the page is rendered by JavaScript ({result.words} words without it)"
            ingested = ingest_curated(curated, reason=reason)
            return Ingested(ingested.document, notes + ingested.notes)
        raise IngestError(
            f"The page has only {result.words} words of readable text without JavaScript, and no content model was found. Paste the text instead."
        )

    notes.append(f"Read {result.root}: {len(result.blocks)} blocks kept, {result.dropped} chrome elements dropped")
    meta = _page_document_meta(result, url, fetched.url, archive_url)
    _apply_curated_meta(meta, curated_fm, curated)
    document = _build(result.blocks, meta)
    notes.append(_describe(document))
    return Ingested(document, notes)


def _from_model(model: dict[str, Any], url: str, model_url: str, curated_fm: dict[str, str], curated: Path | None, notes: list[str], archive_url: str | None) -> Ingested:
    result = aem_blocks(model)
    if not result.blocks:
        raise IngestError(f"The content model at {model_url} has no text")
    notes.append(f"Read the AEM content model {model_url}: {len(result.blocks)} blocks, {result.dropped} navigation nodes dropped")
    meta = DocumentMeta(
        title=result.title or url,
        company=company_from_host(url) or "Not identified",
        method=f"Text fields of the page's AEM content model ({Path(model_url).name}); headings and list bullets reconstructed; navigation and link cards omitted.",
        retrieved=today(),
        text_type="web_page",
        url=url,
        archive_url=archive_url,
        id=slug(_url_slug(url), today()),
    )
    _apply_curated_meta(meta, curated_fm, curated)
    document = _build(result.blocks, meta)
    notes.append(_describe(document))
    return Ingested(document, notes)


def _page_document_meta(result: HtmlResult, url: str, final_url: str, archive_url: str | None) -> DocumentMeta:
    page = result.meta
    title = page.title or page.extra.get("og_title") or _first_title(result.blocks) or url
    press = page.og_type == "article" and re.search(r"newsroom|press|release|news", url, re.I) is not None
    return DocumentMeta(
        title=title,
        company=page.organisation or company_from_host(url) or "Not identified",
        method=f"Main content of the page's HTML ({result.root}); navigation, media, share and contact blocks removed; headings and list items kept.",
        retrieved=today(),
        text_type="press_release" if press else "web_page",
        url=url,
        archive_url=archive_url,
        language=page.language or "en",
        id=slug(_url_slug(url), today()),
    )


def _apply_curated_meta(meta: DocumentMeta, fm: dict[str, str], path: Path | None) -> None:
    """The team's metadata for a demo document wins over what the page says about itself; the
    text stays the live page's."""
    if path is None:
        return
    meta.title = fm.get("title") or meta.title
    meta.company = fm.get("company") or meta.company
    meta.text_type = fm.get("text_type") or meta.text_type
    meta.industry = fm.get("industry") or meta.industry
    meta.sasb_codes = _split_codes(fm.get("sasb_codes")) or meta.sasb_codes
    meta.fixture_path = _repo_relative(path)
    meta.id = slug(path.stem)


def _with_curated_meta(ingested: Ingested, fm: dict[str, str], path: Path | None, notes: list[str]) -> Ingested:
    if path is not None:
        doc = ingested.document
        doc["title"] = fm.get("title") or doc["title"]
        if fm.get("company"):
            doc["company"]["name"] = fm["company"]
        if fm.get("industry"):
            doc["industry"]["label"] = fm["industry"]
        if fm.get("sasb_codes"):
            doc["industry"]["sasb_codes"] = _split_codes(fm["sasb_codes"])
        if fm.get("text_type"):
            doc["text_type"] = fm["text_type"]
        doc["source"]["fixture_path"] = _repo_relative(path)
        doc["id"] = slug(path.stem)
    return Ingested(ingested.document, notes + ingested.notes)


# ----------------------------------------------------------------------------- files and requests


def ingest_file(path: Path) -> Ingested:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return ingest_pdf(path.read_bytes(), filename=path.name)
    if suffix == ".json":
        model = json.loads(path.read_text(encoding="utf-8"))
        if not looks_like_model(model):
            raise IngestError(f"{path.name} is not an AEM content model")
        return _from_model(model, path.name, path.name, {}, None, [], None)
    if suffix in (".html", ".htm"):
        result = html_blocks(path.read_text(encoding="utf-8"), None)
        meta = _page_document_meta(result, path.name, path.name, None)
        meta.url = None
        return Ingested(_build(result.blocks, meta), [f"Read {path.name}: {result.root}"])
    raw = path.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(raw)
    if fm:
        return ingest_curated(path)
    return ingest_text(raw, title=path.stem)


def ingest_request(request: dict[str, Any], *, demo_dir: Path | None = None) -> Ingested:
    kind = request.get("kind")
    if kind == "text":
        return ingest_text(str(request.get("text") or ""), title=request.get("title"))
    if kind == "url":
        return ingest_url(str(request.get("url") or ""), demo_dir=demo_dir)
    if kind == "pdf":
        try:
            data = base64.b64decode(str(request.get("data_base64") or ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise IngestError("The PDF upload is not valid base64") from exc
        return ingest_pdf(data, filename=request.get("filename"))
    raise IngestError(f"Unknown input kind {kind!r}")


# ----------------------------------------------------------------------------- helpers


def _build(blocks: list[Block], meta: DocumentMeta) -> dict[str, Any]:
    try:
        return build_document(blocks, meta)
    except CanonicalError as exc:  # an adapter bug; surface it as a failure of this analysis
        raise IngestError(f"Ingestion produced non-canonical text: {exc}") from exc


def _first_title(blocks: list[Block]) -> str | None:
    for b in blocks:
        if b is not None and b.kind == "title":
            return b.lines[0]
    for b in blocks:
        if b is not None and b.kind == "heading":
            return b.lines[0]
    return None


def _json_or_none(fetched: Fetched) -> Any:
    try:
        return fetched.json()
    except ValueError:
        return None


def _url_slug(url: str) -> str:
    from urllib.parse import urlparse

    parts = urlparse(url)
    host = (parts.hostname or "").removeprefix("www.")
    path = re.sub(r"\.(html?|pdf|aspx?|php)$", "", parts.path.strip("/"))
    return f"{host}-{path}" if path else host


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _describe(document: dict[str, Any]) -> str:
    kinds: dict[str, int] = {}
    for r in document["regions"]:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    parts = ", ".join(f"{n} {kind.replace('_', ' ')}{'s' if n != 1 else ''}" for kind, n in sorted(kinds.items()))
    return f"Canonical text: {document['word_count']} words, {len(document['text'])} characters; regions: {parts}"


__all__ = [
    "IngestError",
    "Ingested",
    "ingest_curated",
    "ingest_file",
    "ingest_pdf",
    "ingest_request",
    "ingest_text",
    "ingest_url",
    "today",
]
