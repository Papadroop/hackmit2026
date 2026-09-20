"""HTTP API: create analyses, list fixtures, stream events over Server-Sent Events.

Everything lives under /api so the Vite dev server can proxy it, and a production build of
the frontend (frontend/dist) is served from / by this same process when it exists.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from . import pipeline
from .documents import DocumentsResponse, document_title, list_documents, log_name
from .envelope import LogError, is_safe_name, log_summary, read_log
from .replay import run_replay
from .store import Analysis, AnalysisStore, Status

REPO_ROOT = Path(__file__).resolve().parents[2]
KEEPALIVE_SECONDS = 15.0


class Settings(BaseModel):
    fixtures_dir: Path = REPO_ROOT / "fixtures"
    demo_documents_dir: Path = REPO_ROOT / "demo-documents"
    runs_dir: Path | None = REPO_ROOT / "backend" / "data" / "runs"
    calibration_file: Path = REPO_ROOT / "backend" / "data" / "calibration.json"
    frontend_dist: Path | None = REPO_ROOT / "frontend" / "dist"

    @classmethod
    def from_env(cls) -> "Settings":
        values: dict[str, Any] = {}
        if fixtures := os.environ.get("AUDITOR_FIXTURES_DIR"):
            values["fixtures_dir"] = Path(fixtures)
        if demo := os.environ.get("AUDITOR_DEMO_DOCUMENTS_DIR"):
            values["demo_documents_dir"] = Path(demo)
        if runs := os.environ.get("AUDITOR_RUNS_DIR"):
            values["runs_dir"] = Path(runs)
        if calibration := os.environ.get("AUDITOR_CALIBRATION_FILE"):
            values["calibration_file"] = Path(calibration)
        return cls(**values)


class ReplayRequest(BaseModel):
    kind: Literal["replay"]
    fixture: str | None = Field(default=None, description="Name of a file in the fixtures directory")
    run: str | None = Field(default=None, description="Name of a saved run in the runs directory")
    speed: float = Field(default=1.0, gt=0, description="1 = original timing, 4 = four times faster")

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "ReplayRequest":
        if (self.fixture is None) == (self.run is None):
            raise ValueError("give exactly one of 'fixture' or 'run'")
        return self


class TextRequest(BaseModel):
    kind: Literal["text"]
    text: str = Field(min_length=1)
    title: str | None = None
    speed: float = Field(default=1.0, gt=0, description="Pace of any stages replayed from a recording")


class UrlRequest(BaseModel):
    kind: Literal["url"]
    url: str = Field(min_length=1)
    speed: float = Field(default=1.0, gt=0, description="Pace of any stages replayed from a recording")


class PdfRequest(BaseModel):
    kind: Literal["pdf"]
    filename: str | None = None
    data_base64: str = Field(min_length=1, description="The PDF file, base64-encoded")
    speed: float = Field(default=1.0, gt=0, description="Pace of any stages replayed from a recording")


AnalysisRequest = Annotated[ReplayRequest | TextRequest | UrlRequest | PdfRequest, Field(discriminator="kind")]


class AnalysisSummary(BaseModel):
    analysis_id: str
    created_at: datetime
    source: dict[str, Any]
    title: str | None
    status: Status
    event_count: int
    last_seq: int
    events_url: str

    @classmethod
    def of(cls, analysis: Analysis) -> "AnalysisSummary":
        return cls(
            analysis_id=analysis.id,
            created_at=analysis.created_at,
            source=analysis.source,
            title=document_title(analysis.events),
            status=analysis.status,
            event_count=len(analysis.events),
            last_seq=analysis.last_seq,
            events_url=f"/api/analyses/{analysis.id}/events",
        )


class FixtureInfo(BaseModel):
    name: str
    file: str
    title: str | None = None
    events: int | None = None
    duration_ms: int | None = None
    types: dict[str, int] | None = None
    error: str | None = None


async def sse(analysis: Analysis, request: Request, cursor: int) -> AsyncIterator[str]:
    """Tail the analysis log from `cursor` (a seq) until its terminal event.

    The event type travels inside `data:` rather than in the SSE `event:` field so that a
    single EventSource `onmessage` handler receives every type, known or not.
    """
    yield ": connected\n\n"
    while True:
        while cursor < len(analysis.events):
            event = analysis.events[cursor]
            cursor += 1
            yield f"id: {event.seq}\ndata: {event.model_dump_json()}\n\n"
        if analysis.done:
            return
        if not await analysis.wait_changed(cursor, KEEPALIVE_SECONDS):
            if await request.is_disconnected():
                return
            yield ": keepalive\n\n"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.runs_dir is not None:
            settings.runs_dir.mkdir(parents=True, exist_ok=True)
        app.state.store = AnalysisStore(runs_dir=settings.runs_dir)
        yield
        await app.state.store.shutdown()

    app = FastAPI(title="Greenwashing Auditor API", version="0.0.1", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def store(request: Request) -> AnalysisStore:
        return request.app.state.store

    def get_analysis(request: Request, analysis_id: str) -> Analysis:
        analysis = store(request).get(analysis_id)
        if analysis is None:
            raise HTTPException(404, f"unknown analysis {analysis_id!r}")
        return analysis

    def resolve_log(directory: Path | None, name: str, what: str) -> Path:
        """`<name>` maps to `<name>.events.jsonl` (the contract tooling's convention) or
        `<name>.jsonl`, whichever exists."""
        if directory is None or not is_safe_name(name):
            raise HTTPException(404, f"unknown {what} {name!r}")
        stem = log_name(name)
        for candidate in (directory / f"{stem}.events.jsonl", directory / f"{stem}.jsonl"):
            if candidate.is_file():
                return candidate
        raise HTTPException(404, f"unknown {what} {name!r}")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "fixtures_dir": str(settings.fixtures_dir),
            "runs_dir": str(settings.runs_dir) if settings.runs_dir else None,
        }

    @app.get("/api/fixtures")
    async def list_fixtures() -> list[FixtureInfo]:
        if not settings.fixtures_dir.is_dir():
            return []
        infos: list[FixtureInfo] = []
        for path in sorted(settings.fixtures_dir.glob("*.jsonl")):
            name = log_name(path.name)
            try:
                events = read_log(path)
            except LogError as exc:
                infos.append(FixtureInfo(name=name, file=path.name, error=str(exc)))
                continue
            infos.append(
                FixtureInfo(name=name, file=path.name, title=document_title(events), **log_summary(events))
            )
        return infos

    @app.get("/api/calibration")
    async def calibration_report() -> dict[str, Any]:
        """The metrics page's data (roadmap step 19): the precedent set run leave-one-out, with
        precision, recall, the calibration curve and what the set cannot support. Written by
        `python -m auditor.calibration run --out data/calibration.json`, so the app never waits
        on a model; 404 until that has been run."""
        path = settings.calibration_file
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"No calibration report yet. Run `python -m auditor.calibration run --out {path}`.",
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"{path} is not readable JSON: {exc}") from exc

    @app.get("/api/documents")
    async def list_demo_documents() -> DocumentsResponse:
        return list_documents(
            settings.demo_documents_dir, settings.fixtures_dir, live_analysis=pipeline.LIVE_AVAILABLE
        )

    @app.post("/api/analyses", status_code=201)
    async def create_analysis(request: Request, body: AnalysisRequest) -> AnalysisSummary:
        analyses = store(request)
        if body.kind == "replay":
            if body.fixture is not None:
                path = resolve_log(settings.fixtures_dir, body.fixture, "fixture")
                source: dict[str, Any] = {"kind": "replay", "fixture": log_name(path.name), "speed": body.speed}
            else:
                assert body.run is not None
                path = resolve_log(settings.runs_dir, body.run, "run")
                source = {"kind": "replay", "run": log_name(path.name), "speed": body.speed}
            try:
                events = read_log(path)
            except LogError as exc:
                raise HTTPException(422, str(exc)) from exc
            analysis = analyses.create(source)
            speed = body.speed
            analyses.start(analysis, lambda a: run_replay(a, events, speed))
        else:
            if not pipeline.LIVE_AVAILABLE:
                raise HTTPException(
                    501, "Live analysis is not built yet (roadmap step 10 onward). Replay a recording instead."
                )
            live_input = body.model_dump()
            analysis = analyses.create(pipeline.public_source(live_input))
            speed = body.speed
            analyses.start(
                analysis,
                lambda a: pipeline.run_live(
                    a, live_input, fixtures_dir=settings.fixtures_dir, demo_dir=settings.demo_documents_dir, speed=speed
                ),
            )
        return AnalysisSummary.of(analysis)

    @app.get("/api/analyses")
    async def list_analyses(request: Request) -> list[AnalysisSummary]:
        return [AnalysisSummary.of(a) for a in store(request).all()]

    @app.get("/api/analyses/{analysis_id}")
    async def get_analysis_summary(request: Request, analysis_id: str) -> AnalysisSummary:
        return AnalysisSummary.of(get_analysis(request, analysis_id))

    @app.get("/api/analyses/{analysis_id}/events")
    async def stream_events(
        request: Request,
        analysis_id: str,
        after: Annotated[int, Query(ge=0, description="Resume after this seq")] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        analysis = get_analysis(request, analysis_id)
        cursor = after
        if last_event_id is not None:
            try:
                cursor = int(last_event_id)
            except ValueError as exc:
                raise HTTPException(400, "Last-Event-ID must be an event seq") from exc
        if cursor > analysis.last_seq:
            raise HTTPException(400, f"after={cursor} is beyond the last event ({analysis.last_seq})")
        return StreamingResponse(
            sse(analysis, request, cursor),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/analyses/{analysis_id}/log")
    async def download_log(request: Request, analysis_id: str) -> Response:
        analysis = get_analysis(request, analysis_id)
        body = "".join(event.to_line() for event in analysis.events)
        return Response(
            body,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'inline; filename="{analysis.id}.jsonl"'},
        )

    @app.delete("/api/analyses/{analysis_id}", status_code=204)
    async def cancel_analysis(request: Request, analysis_id: str) -> Response:
        await get_analysis(request, analysis_id).cancel()
        return Response(status_code=204)

    dist = settings.frontend_dist
    if dist is not None and (dist / "index.html").is_file():
        # Built frontend. Assets are served as files; every other non-API path gets index.html,
        # so client-side routes such as /a/<analysis id> survive a reload.
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "unknown API route")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
