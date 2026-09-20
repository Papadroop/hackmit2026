"""The event envelope: the one format shared by fixtures, live runs and replay (design-doc D8).

Domain payloads (claims, evidence, verdicts, ...) belong to the data contract (roadmap step 2)
and are opaque here. This module owns the wrapper and the lifecycle events the transport needs.
The rules are written down in fixtures/README.md; keep the two in step.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

ANALYSIS_STARTED = "analysis.started"
ANALYSIS_COMPLETED = "analysis.completed"
ANALYSIS_FAILED = "analysis.failed"
STAGE_STARTED = "stage.started"
STAGE_COMPLETED = "stage.completed"

TERMINAL_TYPES = frozenset({ANALYSIS_COMPLETED, ANALYSIS_FAILED})
LIFECYCLE_TYPES = frozenset({ANALYSIS_STARTED, STAGE_STARTED, STAGE_COMPLETED, *TERMINAL_TYPES})


class Event(BaseModel):
    """One line of an event log."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1, description="Position in the log, 1-based and contiguous.")
    t_ms: int = Field(ge=0, description="Milliseconds since the analysis started.")
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _type_shape(cls, value: str) -> str:
        if not TYPE_PATTERN.match(value):
            raise ValueError(
                f"type {value!r} must be lowercase 'namespace.verb' with at least one dot"
            )
        return value

    @model_validator(mode="after")
    def _lifecycle_payloads(self) -> "Event":
        if self.type == ANALYSIS_FAILED and not isinstance(self.payload.get("error"), str):
            raise ValueError("analysis.failed payload needs a string 'error'")
        if self.type in (STAGE_STARTED, STAGE_COMPLETED) and not isinstance(
            self.payload.get("stage"), str
        ):
            raise ValueError(f"{self.type} payload needs a string 'stage'")
        return self

    @property
    def terminal(self) -> bool:
        return self.type in TERMINAL_TYPES

    def to_line(self) -> str:
        return self.model_dump_json() + "\n"


class LogError(ValueError):
    """A log violates the envelope rules. The message names the source and line."""


def is_safe_name(name: str) -> bool:
    """A fixture or run name that maps to one file inside its directory."""
    return bool(SAFE_NAME_PATTERN.match(name)) and ".." not in name


def parse_log(lines: Iterable[str], *, source: str = "<log>") -> list[Event]:
    """Parse and validate a JSONL event log.

    `seq` may be omitted in files; it is assigned from position and checked when present.
    """
    events: list[Event] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        where = f"{source}:{lineno}"
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LogError(f"{where}: not valid JSON ({exc.msg})") from exc
        if not isinstance(data, dict):
            raise LogError(f"{where}: each line must be a JSON object")
        position = len(events) + 1
        data.setdefault("seq", position)
        try:
            event = Event.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            msg = first["msg"].removeprefix("Value error, ")
            raise LogError(f"{where}: {loc + ': ' if loc else ''}{msg}") from exc
        if event.seq != position:
            raise LogError(f"{where}: seq is {event.seq}, expected {position}")
        if events and event.t_ms < events[-1].t_ms:
            raise LogError(
                f"{where}: t_ms {event.t_ms} is earlier than the previous event ({events[-1].t_ms})"
            )
        if position == 1 and event.type != ANALYSIS_STARTED:
            raise LogError(f"{where}: first event must be {ANALYSIS_STARTED}, got {event.type}")
        if position > 1 and event.type == ANALYSIS_STARTED:
            raise LogError(f"{where}: {ANALYSIS_STARTED} may only appear first")
        if events and events[-1].terminal:
            raise LogError(
                f"{where}: {events[-1].type} on the previous line must be the last event"
            )
        events.append(event)
    if not events:
        raise LogError(f"{source}: log is empty")
    if not events[-1].terminal:
        raise LogError(
            f"{source}: last event must be {ANALYSIS_COMPLETED} or {ANALYSIS_FAILED}, "
            f"got {events[-1].type}"
        )
    return events


def read_log(path: Path) -> list[Event]:
    with path.open("r", encoding="utf-8") as handle:
        return parse_log(handle, source=path.name)


def log_summary(events: list[Event]) -> dict[str, Any]:
    """What a listing shows about a log: size, duration, and a count per type."""
    return {
        "events": len(events),
        "duration_ms": events[-1].t_ms if events else 0,
        "types": dict(sorted(Counter(event.type for event in events).items())),
    }
