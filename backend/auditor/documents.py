"""The documents a person can choose from.

The demo texts in demo-documents/ (verbatim, with a front-matter header) are joined with the
recorded analyses in fixtures/ by source URL: a recording announces its document in
`analysis.started.payload.document_ref` (contract/schema.json). A recording whose URL matches
no demo text is listed on its own; one with no URL at all (the transport smoke test) is not
a document and is left out. The demo text's `role` (the team's expected verdict) is never
exposed: the interface must not pre-judge what the analysis is about to show.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .envelope import Event, LogError, log_summary, read_log


class Recording(BaseModel):
    fixture: str
    events: int
    duration_ms: int


class DemoDocument(BaseModel):
    id: str
    title: str
    company: str | None = None
    url: str | None = None
    retrieved: str | None = None
    words: int | None = None
    text_type: str | None = None
    industry: str | None = None
    order: int | None = None
    curated: bool = True
    """From demo-documents/ (True) or known only through a recording (False)."""
    recordings: list[Recording] = []


class InvalidRecording(BaseModel):
    file: str
    error: str


class DocumentsResponse(BaseModel):
    documents: list[DemoDocument]
    live_analysis: bool
    invalid_recordings: list[InvalidRecording]


def parse_frontmatter(text: str) -> dict[str, str]:
    """Flat `key: value` pairs between the leading `---` lines. No YAML library needed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key.strip()):
            fields[key.strip()] = value.strip()
    return fields


def parse_int(value: str | None) -> int | None:
    """`4093`, `~700` or `2,164` become integers; anything else is unknown."""
    if value is None:
        return None
    match = re.search(r"\d[\d,]*", value)
    return int(match.group().replace(",", "")) if match else None


def normalise_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def log_name(filename: str) -> str:
    """`shell-climate.events.jsonl` and `smoke.jsonl` are the recordings `shell-climate` and `smoke`."""
    return filename.removesuffix(".jsonl").removesuffix(".events")


def document_ref(events: list[Event]) -> dict[str, Any]:
    ref = events[0].payload.get("document_ref") if events else None
    return ref if isinstance(ref, dict) else {}


def document_title(events: list[Event]) -> str | None:
    """From `analysis.started.document_ref`, or from the ingested document once a live run has
    read it (a URL request does not know its title until then)."""
    title = document_ref(events).get("title")
    if isinstance(title, str) and title:
        return title
    ingested = ingested_document(events).get("title")
    return ingested if isinstance(ingested, str) and ingested else None


def ingested_document(events: list[Event]) -> dict[str, Any]:
    for event in events:
        if event.type == "document.ingested":
            document = event.payload.get("document")
            return document if isinstance(document, dict) else {}
    return {}


def load_demo_documents(demo_dir: Path) -> list[DemoDocument]:
    documents: list[DemoDocument] = []
    if not demo_dir.is_dir():
        return documents
    for path in sorted(demo_dir.glob("*.md")):
        fields = parse_frontmatter(path.read_text(encoding="utf-8"))
        if "title" not in fields:
            continue
        documents.append(
            DemoDocument(
                id=path.stem,
                title=fields["title"],
                company=fields.get("company") or None,
                url=fields.get("url") or None,
                retrieved=fields.get("retrieved") or None,
                words=parse_int(fields.get("words_total")),
                text_type=fields.get("text_type") or None,
                industry=fields.get("industry") or None,
                order=parse_int(fields.get("order")),
            )
        )
    return documents


def recording_for_url(fixtures_dir: Path | None, url: str | None) -> tuple[str, list[Event]] | None:
    """The first valid recording whose `document_ref.url` is this URL: (name, events)."""
    if fixtures_dir is None or not url or not fixtures_dir.is_dir():
        return None
    wanted = normalise_url(url)
    for path in sorted(fixtures_dir.glob("*.jsonl")):
        try:
            events = read_log(path)
        except LogError:
            continue
        ref_url = document_ref(events).get("url")
        if isinstance(ref_url, str) and ref_url and normalise_url(ref_url) == wanted:
            return log_name(path.name), events
    return None


def list_documents(demo_dir: Path, fixtures_dir: Path, *, live_analysis: bool) -> DocumentsResponse:
    documents = load_demo_documents(demo_dir)
    by_url = {normalise_url(d.url): d for d in documents if d.url}
    invalid: list[InvalidRecording] = []

    for path in sorted(fixtures_dir.glob("*.jsonl")) if fixtures_dir.is_dir() else []:
        try:
            events = read_log(path)
        except LogError as exc:
            invalid.append(InvalidRecording(file=path.name, error=str(exc)))
            continue
        ref = document_ref(events)
        url = ref.get("url")
        if not isinstance(url, str) or not url:
            continue
        summary = log_summary(events)
        recording = Recording(fixture=log_name(path.name), events=summary["events"], duration_ms=summary["duration_ms"])
        ingested = ingested_document(events)
        document = by_url.get(normalise_url(url))
        if document is None:
            company = ingested.get("company")
            document = DemoDocument(
                id=recording.fixture,
                title=document_title(events) or recording.fixture,
                curated=False,
                company=company.get("name") if isinstance(company, dict) else None,
                url=url,
                retrieved=(ingested.get("source") or {}).get("retrieved") if isinstance(ingested.get("source"), dict) else None,
                words=ingested.get("word_count") if isinstance(ingested.get("word_count"), int) else None,
            )
            documents.append(document)
            by_url[normalise_url(url)] = document
        if document.text_type is None and isinstance(ingested.get("text_type"), str):
            document.text_type = ingested["text_type"]
        document.recordings.append(recording)

    # Openable first (a recording exists), then the team's demo texts before stray recordings,
    # then the team's `order` front-matter key if present, then company and title.
    documents.sort(
        key=lambda d: (not d.recordings, not d.curated, d.order if d.order is not None else 10**6, d.company or "", d.title)
    )
    return DocumentsResponse(documents=documents, live_analysis=live_analysis, invalid_recordings=invalid)
