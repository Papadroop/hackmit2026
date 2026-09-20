"""Live analysis: the pipeline stages plug in here, one at a time (roadmap phase 2).

Built so far: `ingest` (step 10). A live request reads its input (pasted text, a URL, or an
uploaded PDF) into a contract Document and emits it. Everything downstream stays fixture until
its turn: when a recording exists for the document's URL, the stages after `ingest` are replayed
from it with every span re-anchored to the live text, and the log says so (`mode` is `live`,
`source.downstream` names the recording, and a `debug.note` reports the anchoring). Without a
recording the run stops at `extract` with a clear message, the document still shown.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

from . import ingest
from .documents import recording_for_url
from .envelope import (
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    ANALYSIS_STARTED,
    STAGE_COMPLETED,
    STAGE_STARTED,
    Event,
)
from .ingest.anchor import AnchorStats, reanchor_payload
from .store import Analysis

# contract/schema.json version this producer writes. The real pipeline should share this
# constant with contract/tools/contract.py rather than keep its own copy.
CONTRACT_VERSION = "1.0.0"

# Text, URL and PDF requests are accepted: ingestion (step 10) is built.
LIVE_AVAILABLE = True

INGEST_LABEL = "Reading the document"
EXTRACT_LABEL = "Finding claims"
NOT_BUILT = "Claim extraction is not built yet (roadmap step 11). The document was read and is shown; the analysis stops here."


async def run_live(
    analysis: Analysis,
    request: dict[str, Any],
    *,
    fixtures_dir: Path | None = None,
    demo_dir: Path | None = None,
    speed: float = 1.0,
) -> None:
    source = public_source(request)
    started: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "mode": "live", "source": source}
    ref = {k: v for k, v in (("url", request.get("url")), ("title", request.get("title"))) if isinstance(v, str) and v}
    if ref:
        started["document_ref"] = ref
    analysis.emit(ANALYSIS_STARTED, started)
    analysis.emit(STAGE_STARTED, {"stage": "ingest", "label": INGEST_LABEL})

    try:
        ingested = await asyncio.to_thread(ingest.ingest_request, request, demo_dir=demo_dir)
    except ingest.IngestError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": str(exc), "stage": "ingest"})
        return
    for note in ingested.notes:
        analysis.emit("debug.note", {"text": note})
    document = ingested.document
    analysis.emit("document.ingested", {"document": document})
    analysis.emit(STAGE_COMPLETED, {"stage": "ingest"})

    recording = recording_for_url(fixtures_dir, document.get("source", {}).get("url"))
    if recording is None:
        analysis.emit(STAGE_STARTED, {"stage": "extract", "label": EXTRACT_LABEL})
        analysis.emit(ANALYSIS_FAILED, {"error": NOT_BUILT, "stage": "extract"})
        return
    name, events = recording
    await replay_downstream(analysis, name, events, document, speed=speed)


def public_source(request: dict[str, Any]) -> dict[str, Any]:
    """What the log records about the request: never the pasted text or the PDF bytes."""
    kind = request.get("kind")
    if kind == "text":
        return {"kind": "text", "title": request.get("title"), "chars": len(str(request.get("text") or ""))}
    if kind == "pdf":
        data = str(request.get("data_base64") or "")
        return {"kind": "pdf", "filename": request.get("filename"), "bytes": len(data) * 3 // 4}
    return {"kind": "url", "url": request.get("url")}


async def replay_downstream(analysis: Analysis, name: str, events: list[Event], document: dict[str, Any], *, speed: float) -> None:
    """Replay a recording's events after its `ingest` stage, spans re-anchored to `document`."""
    old_text = _recorded_text(events)
    start_index = next((i + 1 for i, e in enumerate(events) if e.type == STAGE_COMPLETED and e.payload.get("stage") == "ingest"), None)
    if start_index is None or start_index >= len(events):
        analysis.emit(STAGE_STARTED, {"stage": "extract", "label": EXTRACT_LABEL})
        analysis.emit(ANALYSIS_FAILED, {"error": f"Recording {name!r} has nothing after its ingest stage", "stage": "extract"})
        return
    stats = AnchorStats()
    prepared: list[tuple[int, str, dict[str, Any]]] = []
    for event in events[start_index:]:
        payload = event.payload
        if event.type in ("claim.extracted", "language.signal"):
            payload = reanchor_payload(payload, document["text"], old_text, stats)
        elif event.type == STAGE_STARTED:
            payload = dict(payload)
            payload["note"] = f"Replayed from recording {name}; this stage is not built yet"
        else:
            payload = copy.deepcopy(payload)
        prepared.append((event.t_ms, event.type, payload))
    analysis.emit(
        "debug.note",
        {"text": f"Stages after ingest are replayed from recording {name!r} until roadmap steps 11-17 exist. {stats.describe()}."},
    )
    loop = asyncio.get_running_loop()
    origin = loop.time()
    t0 = events[start_index - 1].t_ms
    for t_ms, type_, payload in prepared:
        delay = origin + (t_ms - t0) / 1000 / speed - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        if type_ == ANALYSIS_COMPLETED:
            payload = dict(payload)
            payload.pop("duration_ms", None)
        analysis.emit(type_, payload)


def _recorded_text(events: list[Event]) -> str | None:
    for event in events:
        if event.type == "document.ingested":
            document = event.payload.get("document")
            if isinstance(document, dict) and isinstance(document.get("text"), str):
                return document["text"]
    return None
