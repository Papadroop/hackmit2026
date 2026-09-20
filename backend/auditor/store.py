"""In-memory analyses, each an append-only event log with tailing and disk persistence.

Producers (a replay, or the live pipeline) append through `Analysis.emit`. The SSE endpoint
tails through `Analysis.wait_changed`. Both a replay and a live run go through the same
object, which is what keeps them indistinguishable to the frontend.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from .envelope import ANALYSIS_FAILED, ANALYSIS_STARTED, Event

log = logging.getLogger(__name__)

Producer = Callable[["Analysis"], Awaitable[None]]
Status = Literal["running", "completed", "failed"]


class Analysis:
    def __init__(self, analysis_id: str, source: dict[str, Any], file: Path | None) -> None:
        self.id = analysis_id
        self.created_at = datetime.now(timezone.utc)
        self.source = source
        self.events: list[Event] = []
        self.file = file
        self._changed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._t0: float | None = None

    @property
    def done(self) -> bool:
        return bool(self.events) and self.events[-1].terminal

    @property
    def status(self) -> Status:
        if not self.done:
            return "running"
        return "completed" if self.events[-1].type != ANALYSIS_FAILED else "failed"

    @property
    def last_seq(self) -> int:
        return len(self.events)

    def emit(self, type: str, payload: dict[str, Any] | None = None, *, t_ms: int | None = None) -> Event:
        """Append one event. `t_ms` is stamped from the clock unless the producer supplies it
        (a replay keeps the log's original timing)."""
        if self.done:
            raise RuntimeError(f"analysis {self.id} has already finished")
        now = asyncio.get_running_loop().time()
        if self._t0 is None:
            self._t0 = now
        if t_ms is None:
            t_ms = round((now - self._t0) * 1000)
        if self.events and t_ms < self.events[-1].t_ms:
            t_ms = self.events[-1].t_ms
        event = Event(seq=len(self.events) + 1, t_ms=t_ms, type=type, payload=payload or {})
        self.events.append(event)
        if self.file is not None:
            with self.file.open("a", encoding="utf-8") as handle:
                handle.write(event.to_line())
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()
        return event

    async def wait_changed(self, cursor: int, timeout: float) -> bool:
        """Wait until there is an event beyond `cursor` or the analysis is done.
        Returns False on timeout."""
        changed = self._changed
        if len(self.events) > cursor or self.done:
            return True
        try:
            await asyncio.wait_for(changed.wait(), timeout)
            return True
        except TimeoutError:
            return False

    async def cancel(self) -> bool:
        """Cancel the producer and wait for its terminal event, so callers see it in the log."""
        if self._task is None or self._task.done():
            return False
        self._task.cancel()
        await asyncio.wait({self._task}, timeout=2)
        return True

    async def _run(self, producer: Producer) -> None:
        try:
            await producer(self)
        except asyncio.CancelledError:
            self._fail("cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - the log must record any producer failure
            log.exception("analysis %s failed", self.id)
            self._fail(f"{type(exc).__name__}: {exc}")
        else:
            if not self.done:
                self._fail("producer finished without a terminal event")

    def _fail(self, error: str) -> None:
        if self.done:
            return
        if not self.events:
            self.emit(ANALYSIS_STARTED, {})
        self.emit(ANALYSIS_FAILED, {"error": error})


class AnalysisStore:
    def __init__(self, runs_dir: Path | None) -> None:
        self.runs_dir = runs_dir
        self._items: dict[str, Analysis] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def create(self, source: dict[str, Any]) -> Analysis:
        analysis_id = secrets.token_hex(5)
        file = None
        if self.runs_dir is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            file = self.runs_dir / f"{stamp}-{analysis_id}.jsonl"
        analysis = Analysis(analysis_id, source, file)
        self._items[analysis_id] = analysis
        return analysis

    def start(self, analysis: Analysis, producer: Producer) -> None:
        task = asyncio.create_task(analysis._run(producer), name=f"analysis-{analysis.id}")
        analysis._task = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def get(self, analysis_id: str) -> Analysis | None:
        return self._items.get(analysis_id)

    def all(self) -> list[Analysis]:
        return sorted(self._items.values(), key=lambda a: a.created_at, reverse=True)

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
