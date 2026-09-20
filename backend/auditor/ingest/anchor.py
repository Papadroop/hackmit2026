"""Re-anchoring spans onto another copy of the text (contract/CONTRACT.md §3).

A span carries its text and code-point offsets, with the text authoritative. When the same
document is ingested again (live instead of curated), offsets may move. The rules here are the
contract tool's: trust the offsets when the slice matches; else place by `context` (must occur
once and contain the text); else by `occurrence`; else the unique occurrence; and as a last
resort the occurrence the span had in the copy it was written against, when both copies repeat
the phrase the same number of times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def find_all(hay: str, needle: str) -> list[int]:
    out: list[int] = []
    if not needle:
        return out
    i = 0
    while True:
        j = hay.find(needle, i)
        if j < 0:
            return out
        out.append(j)
        i = j + 1


def anchor_span(text: str, span: dict[str, Any], old_text: str | None = None) -> tuple[int, int, str] | None:
    needle = span.get("text")
    if not isinstance(needle, str) or not needle:
        return None
    start, end = span.get("start"), span.get("end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == needle:
        return start, end, "offset"
    context = span.get("context")
    if isinstance(context, str) and context:
        hits = find_all(text, context)
        rel = context.find(needle)
        if len(hits) == 1 and rel >= 0:
            return hits[0] + rel, hits[0] + rel + len(needle), "context"
        return None
    hits = find_all(text, needle)
    occurrence = span.get("occurrence")
    if isinstance(occurrence, int) and occurrence >= 1:
        if occurrence <= len(hits):
            return hits[occurrence - 1], hits[occurrence - 1] + len(needle), "occurrence"
        return None
    if len(hits) == 1:
        return hits[0], hits[0] + len(needle), "unique"
    if len(hits) > 1 and old_text is not None and isinstance(start, int):
        old_hits = find_all(old_text, needle)
        if start in old_hits and len(old_hits) == len(hits):
            index = old_hits.index(start)
            return hits[index], hits[index] + len(needle), "same_occurrence"
    return None


@dataclass
class AnchorStats:
    by_method: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)

    @property
    def anchored(self) -> int:
        return sum(self.by_method.values())

    def describe(self) -> str:
        parts = [f"{n} by {method.replace('_', ' ')}" for method, n in sorted(self.by_method.items())]
        text = f"{self.anchored} spans anchored" + (f" ({', '.join(parts)})" if parts else "")
        if self.failed:
            text += f"; {len(self.failed)} could not be placed: " + ", ".join(self.failed[:5]) + (" …" if len(self.failed) > 5 else "")
        return text


def reanchor_payload(payload: dict[str, Any], text: str, old_text: str | None, stats: AnchorStats) -> dict[str, Any]:
    """A copy of a claim.extracted or language.signal payload with its spans placed in `text`."""
    import copy

    out = copy.deepcopy(payload)
    entity = out.get("claim") or out.get("signal")
    if not isinstance(entity, dict):
        return out
    for index, span in enumerate(entity.get("spans") or []):
        placed = anchor_span(text, span, old_text)
        if placed is None:
            stats.failed.append(f"{entity.get('id', '?')}[{index}]")
            continue
        span["start"], span["end"], method = placed
        stats.by_method[method] = stats.by_method.get(method, 0) + 1
    return out
