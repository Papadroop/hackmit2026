"""Replay a saved event log with its original timing (design-doc D7, D8)."""

from __future__ import annotations

import asyncio

from .envelope import Event
from .store import Analysis


async def run_replay(analysis: Analysis, events: list[Event], speed: float = 1.0) -> None:
    """Emit each event at `t_ms / speed` after the start. Targets are absolute from the
    start time, so sleep jitter does not accumulate."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    for event in events:
        delay = start + event.t_ms / 1000 / speed - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        analysis.emit(event.type, event.payload, t_ms=event.t_ms)
