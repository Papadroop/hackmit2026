"""Company aggregation (roadmap step 18, second half; design-doc D6 "Aggregation" and D2's
third zoom level): every analysis of one company's documents, side by side, with the trend.

The document summary (`auditor.summary`) reads one page from the claims beneath it. This reads
a company from the pages beneath it, under the same discipline: every number is arithmetic over
rows that are listed underneath it, each number records the documents that drove it in
`ext.drivers`, each document records its own `weight` and its `share` of the headline, and
`--explain` prints the whole derivation without calling a model. Claude is asked for one thing,
after the numbers are settled: the narrative.

**Leaning to the worst of the record.** The dilution risk repeats one level up: a company with
one misleading page and five bland ones must not read clean. So the combination is the same
weighted Lehmer mean at power 3 the document summary uses — each document's say is its weight
times its headline to `power - 1` — applied to the documents' headlines rather than to a page's
claims. One page at 0.90 among five at 0.10 gives 0.85; the plain mean of the same six pages is
0.23, and twenty bland pages still leave it at 0.74. What was rejected, and why:

- *A plain mean over the documents* (power 1): 0.23 for the page above. It is the same failure
  weakest-link prevents at claim level and the Lehmer mean prevents at page level, and a company
  with a communications budget can buy its way out of it by publishing.
- *The worst document* (the maximum): it reads 0.90, but one page then speaks for the company
  forever and nothing a company publishes afterwards can move the number, so the view could
  never show improvement — which is the one thing a company view is for.
- *The most recent document only*: a page published a week after a misleading one would reset
  the record (0.10 against the 0.89 the pair actually reads here), and the company view would
  be a copy of the document view with extra steps.

**Recency is the company-level prominence.** In a page, a claim's say is scaled by how loudly
the page makes it. Across pages, the analogue is how currently the company says it: a document's
weight is `recency x confidence`, where recency halves every `AUDITOR_COMPANY_HALFLIFE_DAYS`
(default 730 — about how often a corporate climate page is rewritten). A page two years old
still counts half; it is the company's own record, not noise. A document with no date cannot
claim to be the current one, so it is counted as if it were exactly one half-life old and is
left off the trend, which `ext.notes` says in words.

This means a company that cleaned up its page still reads high: 2024 at 0.90 replaced by 2026
at 0.20 gives 0.83, not 0.20. That is deliberate. The headline says what the worst of the record
is; **the trend says which way it is moving**. One number cannot do both without either erasing
a company's 2024 page the moment it is replaced or condemning it for that page forever.

**The trend, and when there is not one.** The documents are put in time order — by the capture
date behind an `archive_url` where there is one, because the ingester stamps `retrieved` with
today even when it reads a 2024 snapshot — and the trend is the movement of the headline across
them. It carries a `direction`, the `change` and its rate, and, like every other reading in this
project, a separate confidence saying how much of it to believe: two documents are worth 0.35
before anything else is taken into account, because two points are a line, not a trend; a third
and fourth are worth more; the confidence can never exceed that of the two headlines that moved,
and it is scaled by how one-way the movement was, so a zig-zag does not become a direction. One
document is `undetermined`, not "steady", and `note` says so in a sentence the page can print.

**What is pooled and what is not.** The numbers aggregate documents, not claims: a company is a
set of pages, each already read as a whole, and pooling every claim would let a long page outvote
a short one by sheer count. The *ranking* does pool, because a list of findings is about
individual findings: each claim and omission keeps the title its own document's summary gave it,
and is weighted by its page's recency as well as by its own prominence and confidence. A
company-level target is `(document_id, target)`: claim ids are unique within an analysis only,
so `C1` is a different claim in every document.

    python -m auditor.company "Shell plc" [--explain] [--json]
    python -m auditor.company --analysis fixtures/shell-climate.analysis.json [--explain]

With no `--analysis`, the recordings in `fixtures/` and the saved runs in `backend/data/runs/`
are read and grouped by the company each document names; the fullest analysis of a document
wins and the duplicates are counted in `ext.duplicates`. `GET /api/company/{name}` serves the
same object and calls no model, so a company page never waits on one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import BaseModel, Field

from .envelope import Event, LogError, read_log
from .language import clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm
from .summary import (
    CATEGORIES,
    PROFILE,
    Aggregate,
    Row,
    aggregate_rows,
    contributions,
    fallback_titles,
    prominence_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# How far the company number leans toward the worst of the record. The same exponent the
# document summary uses, for the same reason: at 3 a page twice as bad as another has four times
# the say. 1 is a plain mean, which a company can dilute by publishing.
POWER = float(os.environ.get("AUDITOR_COMPANY_POWER", "3"))

# How fast a document stops speaking for the company. 730 days: a corporate climate page is
# rewritten about every two years, so a page a half-life old counts half.
HALFLIFE_DAYS = float(os.environ.get("AUDITOR_COMPANY_HALFLIFE_DAYS", "730"))

# What a document with no date is worth: exactly one half-life. It cannot claim to be the page
# on the site today, and it is not nothing either.
UNDATED_RECENCY = 0.5

# How many of the largest contributors a number records as having driven it.
DRIVERS = int(os.environ.get("AUDITOR_COMPANY_DRIVERS", "6"))

TOP_ISSUES = int(os.environ.get("AUDITOR_COMPANY_ISSUES", "6"))
CREDIT_ENTRIES = int(os.environ.get("AUDITOR_COMPANY_CREDIT", "4"))

# Below this the headline has not moved. Scores are recorded to two decimals and dimension
# scores move in steps of about 0.05, so a smaller difference is not a direction.
EPSILON = float(os.environ.get("AUDITOR_COMPANY_EPSILON", "0.05"))

# How much older than the retrieval date a capture has to be before it is taken to be where the
# text came from. An `archive_url` a few days either side of the fetch is a permalink for the
# live page (the golden reference carries one); a capture months or years older is the document.
ARCHIVE_GAP_DAYS = float(os.environ.get("AUDITOR_COMPANY_ARCHIVE_GAP_DAYS", "30"))

# How many documents a direction needs before it is worth calling a trend. Two is a line.
MIN_POINTS = int(os.environ.get("AUDITOR_COMPANY_MIN_POINTS", "3"))

# What the number of points alone is worth: two documents 0.35, each further one 0.25 more, and
# never more than 0.85, because a handful of pages is never the whole of how a company writes.
TWO_POINTS = 0.35
POINT_GAIN = 0.25
POINTS_CAP = 0.85

DIRECTIONS = ("improving", "worsening", "steady", "undetermined")

# A recording the team curated is what the demo shows; an ad-hoc run of the same page fills in
# where there is no recording; a run still in this process is the freshest of the three.
ORIGIN_RANK = {"fixture": 3, "live": 2, "run": 1}

WRITE_EFFORT = os.environ.get("AUDITOR_COMPANY_EFFORT", "medium")
WRITE_MAX_OUTPUT_TOKENS = 4000

COMPANY_SYSTEM = (
    "You are the writing stage of a greenwashing audit, at the company level: several documents "
    "of one company, already analysed, seen side by side. The numbers are settled arithmetic and "
    "are not yours to change."
)


# ----------------------------------------------------------------------------- one analysis, as this reads it


@dataclass
class Record:
    """One analysis of one document: the document it read and the header it produced, plus the
    claims, verdicts and omissions the ranking pools. This is the row the company view is built
    from — `fold_record` makes one from an event log, and a fixture's folded analysis is already
    in this shape."""

    document: dict[str, Any]
    summary: dict[str, Any]
    claims: list[dict[str, Any]] = field(default_factory=list)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    omissions: list[dict[str, Any]] = field(default_factory=list)
    analysis_id: str = ""
    origin: dict[str, Any] = field(default_factory=dict)
    """Where the analysis was read from: {"kind": "fixture" | "run" | "live", "name": ...}."""
    duplicates: int = 0
    """Other analyses of the same document that this one stood in for."""
    read_at: float = 0.0
    """When the log was written, for choosing between analyses of the same document."""

    @property
    def company(self) -> str:
        return ((self.document.get("company") or {}).get("name") or "").strip()

    @property
    def document_id(self) -> str:
        return self.document.get("id") or self.analysis_id

    @property
    def title(self) -> str:
        return self.document.get("title") or self.document_id

    @property
    def url(self) -> str:
        return (self.document.get("source") or {}).get("url") or ""

    @property
    def date(self) -> str:
        return document_date(self.document)[0]

    @property
    def date_basis(self) -> str:
        return document_date(self.document)[1]

    @property
    def headline(self) -> dict[str, float]:
        entry = self.summary.get("headline") or {}
        return {"score": float(entry.get("score", 0.0)), "confidence": float(entry.get("confidence", 0.0))}

    def dimension(self, name: str) -> dict[str, float]:
        entry = (self.summary.get("dimensions") or {}).get(name) or {}
        return {"score": float(entry.get("score", 0.0)), "confidence": float(entry.get("confidence", 0.0))}

    def titles(self) -> dict[str, str]:
        """What each of this document's claims and omissions is called: the title its own summary
        gave it (written by Claude at document level, so it names the finding), and otherwise the
        claim's own words."""
        written = {
            entry["target"]: entry["title"]
            for entry in [*self.summary.get("top_issues", []), *self.summary.get("credit", [])]
            if entry.get("title")
        }
        fallbacks = fallback_titles({c["id"]: c for c in self.claims}, {o["id"]: o for o in self.omissions})
        return {**fallbacks, **written}


def fold_record(events: Iterable[Event], origin: dict[str, Any] | None = None) -> Record | None:
    """The company view's row from an event log. Returns None when the log has no document or
    never reached a header: a cancelled or half-finished run has no number to aggregate, and
    counting it as a clean page would be the worst kind of dilution."""
    document: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    claims: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    analysis_id = ""
    for event in events:
        payload = event.payload
        if event.type == "analysis.started":
            analysis_id = payload.get("analysis_id") or analysis_id
        elif event.type == "document.ingested" and isinstance(payload.get("document"), dict):
            document = payload["document"]
        elif event.type == "claim.extracted" and isinstance(payload.get("claim"), dict):
            claims.append(payload["claim"])
        elif event.type == "verdict.issued" and isinstance(payload.get("verdict"), dict):
            verdicts.append(payload["verdict"])
        elif event.type == "omission.found" and isinstance(payload.get("omission"), dict):
            omissions.append(payload["omission"])
        elif event.type == "summary.updated" and isinstance(payload.get("summary"), dict):
            summary = payload["summary"]
    if not document or not summary:
        return None
    return Record(
        document=document, summary=summary, claims=claims, verdicts=verdicts, omissions=omissions,
        analysis_id=analysis_id, origin=dict(origin or {}),
    )


def record_from_analysis(analysis: dict[str, Any], origin: dict[str, Any] | None = None) -> Record | None:
    """The same row from a folded analysis file (a fixture, or `contract.py fold` of a log)."""
    if not analysis.get("document") or not analysis.get("summary"):
        return None
    return Record(
        document=analysis["document"], summary=analysis["summary"], claims=analysis.get("claims", []),
        verdicts=analysis.get("verdicts", []), omissions=analysis.get("omissions", []),
        analysis_id=analysis.get("analysis_id", ""), origin=dict(origin or {}),
    )


# ----------------------------------------------------------------------------- when a document is from


ARCHIVE_STAMP = re.compile(r"/web/(\d{8})\d*(?:id_)?/")


def days_between(earlier: str, later: str) -> int:
    return (date_type.fromisoformat(later) - date_type.fromisoformat(earlier)).days


def document_date(document: dict[str, Any]) -> tuple[str, str]:
    """(date, what the date is) for one document: `archive` when the source carries a Wayback
    capture whose timestamp can be read, otherwise `retrieved`, otherwise `unknown`.

    The distinction matters for the trend. The ingester stamps `retrieved` with the day it ran,
    even when what it read was a 2024 snapshot of a page that has since been replaced, so dating
    an archived page by `retrieved` would stack both versions on today and flatten exactly the
    movement the company view exists to show. A capture within `ARCHIVE_GAP_DAYS` of the fetch is
    read the other way round: it is a permalink for the page as fetched, not where the text came
    from, which is how the golden reference cites its own source."""
    source = document.get("source") or {}
    match = ARCHIVE_STAMP.search(source.get("archive_url") or "") or ARCHIVE_STAMP.search(source.get("url") or "")
    stamp = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:8]}" if match else ""
    retrieved = (source.get("retrieved") or "").strip() if isinstance(source.get("retrieved"), str) else ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved):
        retrieved = ""
    if stamp and (not retrieved or days_between(stamp, retrieved) >= ARCHIVE_GAP_DAYS):
        return stamp, "archive"
    if retrieved:
        return retrieved, "retrieved"
    return (stamp, "archive") if stamp else ("", "unknown")


def recency(date: str, newest: str, halflife_days: float = HALFLIFE_DAYS) -> float:
    """How much of a say a document of this date still has, against the company's most recent
    one: 1.0 for the current page and half for every `halflife_days` before it. Never zero — an
    old page is the company's own record, not noise."""
    if not date or not newest:
        return UNDATED_RECENCY
    age = max(days_between(date, newest), 0)
    return float(0.5 ** (age / halflife_days)) if halflife_days > 0 else 1.0


def order_records(records: Iterable[Record]) -> list[Record]:
    """Oldest first: the trend's order, and the order the view lists documents in. Undated
    documents sort first, because a page that cannot say when it is from cannot be the latest."""
    return sorted(records, key=lambda r: (r.date or "", r.document_id))


# ----------------------------------------------------------------------------- the trend


def points_confidence(points: int) -> float:
    """What the number of documents alone is worth, before the readings and the shape of the
    movement are taken into account."""
    if points < 2:
        return 0.0
    return min(POINTS_CAP, TWO_POINTS + POINT_GAIN * (points - 2))


@dataclass
class Point:
    document_id: str
    date: str
    score: float
    confidence: float
    dimensions: dict[str, dict[str, float]]

    def entry(self) -> dict[str, Any]:
        return {"document_id": self.document_id, "date": self.date, "score": round(self.score, 2)}


def build_trend(points: list[Point], *, epsilon: float = EPSILON) -> dict[str, Any]:
    """The movement of the headline across the company's documents, with a separate confidence
    saying how much of it to believe and a `note` that says plainly when there is too little of
    it to call. Fewer than two dated documents is `undetermined`, never `steady`: a company with
    one page has not held still, it has not been watched."""
    trend: dict[str, Any] = {
        "direction": "undetermined", "points": len(points), "change": None, "per_year": None,
        "span_days": None, "confidence": 0.0, "first": None, "last": None, "note": "", "ext": {},
    }
    if len(points) < 2:
        trend["note"] = (
            "No document carries a date, so they cannot be put in time order."
            if not points
            else "One document, so there is nothing to compare it with: a trend needs a second page of the same company's, and an older version of this one is the usual second point."
        )
        if points:
            trend["first"] = trend["last"] = points[0].entry()
        return trend

    first, last = points[0], points[-1]
    change = round(last.score - first.score, 2)
    span = days_between(first.date, last.date) if first.date and last.date else 0
    steps = [b.score - a.score for a, b in zip(points, points[1:])]
    gross = sum(abs(step) for step in steps)
    consistency = 1.0 if gross <= 1e-9 else min(1.0, abs(change) / gross)
    direction = "steady" if abs(change) < epsilon else ("worsening" if change > 0 else "improving")
    confidence = clamp01(min(points_confidence(len(points)), first.confidence, last.confidence) * consistency)

    trend.update({
        "direction": direction,
        "change": change,
        "per_year": round(change * 365.25 / span, 2) if span else None,
        "span_days": span,
        "confidence": confidence,
        "first": first.entry(),
        "last": last.entry(),
        "note": trend_note(points, change, span, consistency, direction, epsilon),
        "ext": {
            "consistency": round(consistency, 2),
            "dimension_change": {
                name: round(last.dimensions.get(name, {}).get("score", 0.0) - first.dimensions.get(name, {}).get("score", 0.0), 2)
                for name in PROFILE
            },
        },
    })
    return trend


def trend_note(points: list[Point], change: float, span: int, consistency: float, direction: str, epsilon: float) -> str:
    """One sentence a company page can print under the arrow, saying what the direction rests
    on — including, when it rests on two documents, that two documents are not a trend."""
    first, last = points[0], points[-1]
    if len(points) < MIN_POINTS:
        lead = "Two documents captured the same day: a step, not a trend." if not span else f"Two documents {span} days apart: a step, not a trend."
    else:
        lead = f"{len(points)} documents captured the same day." if not span else f"{len(points)} documents over {span} days."
    if direction == "steady":
        movement = f"The headline moved {change:+.2f}, less than the {epsilon} below which these numbers are not read, so it has not moved."
    else:
        rate = f", about {change * 365.25 / span:+.2f} a year" if span else ""
        movement = f"The headline moved {change:+.2f}, from {first.score:.2f} on {first.date} to {last.score:.2f} on {last.date}{rate}."
    if len(points) < MIN_POINTS:
        tail = " One more document could move it either way."
    elif consistency >= 0.9:
        tail = " Every step goes the same way."
    else:
        tail = f" The movement is not one way ({sum(abs(b.score - a.score) for a, b in zip(points, points[1:])):.2f} of movement for {abs(change):.2f} of change), so the direction is weakly held."
    return f"{lead} {movement}{tail}"


# ----------------------------------------------------------------------------- the ranking


@dataclass
class Finding:
    """One claim or omission of one document, as the company-level list names it. `document_id`
    is half the identity: claim ids are unique within an analysis only."""

    document_id: str
    target: str
    title: str
    row: Row


def findings(record: Record, weight: float) -> list[Finding]:
    """This document's claims and omissions as company-level rows. A claim's say is its own
    prominence and its verdict's confidence, as at document level, scaled by how current the page
    it sits on is."""
    titles = record.titles()
    by_claim = {c["id"]: c for c in record.claims}
    out = []
    for verdict in record.verdicts:
        claim_id = verdict.get("claim_id")
        if claim_id not in by_claim:
            continue
        row = Row(claim_id, float(verdict["likelihood"]), float(verdict["confidence"]), prominence_of(by_claim[claim_id]) * weight)
        out.append(Finding(record.document_id, claim_id, titles.get(claim_id, claim_id), row))
    for omission in record.omissions:
        row = Row(omission["id"], float(omission.get("score", 0.5)), float(omission.get("confidence", 0.5)), weight)
        out.append(Finding(record.document_id, omission["id"], titles.get(omission["id"], omission["id"]), row))
    return out


def rank_issues(found: list[Finding], limit: int) -> list[Finding]:
    """The company's worst findings, in the order the same severity the aggregation weighs by
    puts them."""
    return sorted(found, key=lambda f: (-f.row.severity, -f.row.score, f.document_id, f.target))[:limit]


def rank_credit(records: list[Record], weights: dict[str, float], limit: int) -> list[Finding]:
    """Credit where due (D6) across the documents: the best-substantiated claims the company
    makes, most prominent and most current first. Only `supported` verdicts."""
    out = []
    for record in records:
        titles = record.titles()
        by_claim = {c["id"]: c for c in record.claims}
        for verdict in record.verdicts:
            claim_id = verdict.get("claim_id")
            if verdict.get("category") != "supported" or claim_id not in by_claim:
                continue
            row = Row(claim_id, float(verdict["likelihood"]), float(verdict["confidence"]),
                      prominence_of(by_claim[claim_id]) * weights.get(record.document_id, 1.0))
            out.append(Finding(record.document_id, claim_id, titles.get(claim_id, claim_id), row))
    return sorted(out, key=lambda f: (f.row.score, -f.row.weight, f.document_id, f.target))[:limit]


# ----------------------------------------------------------------------------- the arithmetic


def aggregate_company(
    records: Iterable[Record],
    *,
    company: str | None = None,
    power: float = POWER,
    halflife_days: float = HALFLIFE_DAYS,
) -> tuple[dict[str, Any], dict[str, Aggregate]]:
    """The company's numbers, and the aggregate behind each one so it can be explained. No model
    is called and no number is anyone's opinion; the narrative is left empty for `describe_company`
    to fill."""
    ordered = order_records(records)
    newest = max((r.date for r in ordered if r.date), default="")
    recencies = {r.document_id: (recency(r.date, newest, halflife_days) if r.date else UNDATED_RECENCY) for r in ordered}

    head_rows = [Row(r.document_id, r.headline["score"], r.headline["confidence"], recencies[r.document_id]) for r in ordered]
    parts: dict[str, Aggregate] = {"headline": aggregate_rows(head_rows, power)}
    for name in PROFILE:
        parts[name] = aggregate_rows(
            [Row(r.document_id, r.dimension(name)["score"], r.dimension(name)["confidence"], recencies[r.document_id]) for r in ordered],
            power,
        )
    shares = dict(contributions(head_rows, power))

    distribution: Counter[str] = Counter()
    for record in ordered:
        for category, count in (record.summary.get("verdict_distribution") or {}).items():
            if category in CATEGORIES:
                distribution[category] += int(count)

    found: list[Finding] = []
    for record in ordered:
        found.extend(findings(record, recencies[record.document_id]))
    issues = rank_issues(found, TOP_ISSUES)
    credit = rank_credit(ordered, recencies, CREDIT_ENTRIES)

    points = [
        Point(r.document_id, r.date, r.headline["score"], r.headline["confidence"], r.summary.get("dimensions") or {})
        for r in ordered if r.date
    ]
    undated = len(ordered) - len(points)
    notes = []
    if undated:
        notes.append(
            f"{undated} document{'' if undated == 1 else 's'} without a date, counted as if "
            f"{'it were' if undated == 1 else 'they were'} {halflife_days:.0f} days old and left off the trend"
        )

    name = company if company is not None else (ordered[-1].company if ordered else "")
    view: dict[str, Any] = {
        "company": (ordered[-1].document.get("company") if ordered else None) or {"name": name},
        **({"industry": ordered[-1].document["industry"]} if ordered and ordered[-1].document.get("industry") else {}),
        "headline": parts["headline"].entry(),
        "dimensions": {dimension: parts[dimension].entry() for dimension in PROFILE},
        "verdict_distribution": {category: distribution.get(category, 0) for category in CATEGORIES},
        "documents": [document_entry(r, recencies[r.document_id], shares.get(r.document_id, 0.0)) for r in ordered],
        "trend": build_trend(points),
        "top_issues": [
            {"rank": i + 1, "document_id": f.document_id, "target": f.target, "title": f.title}
            for i, f in enumerate(issues)
        ],
        "credit": [{"document_id": f.document_id, "target": f.target, "title": f.title} for f in credit],
        "document_count": len(ordered),
        "claim_count": sum(int(r.summary.get("claim_count", len(r.claims))) for r in ordered),
        "omission_count": sum(int(r.summary.get("omission_count", len(r.omissions))) for r in ordered),
        "ext": {
            "power": round(power, 2),
            "halflife_days": halflife_days,
            "drivers": {name_: parts[name_].drivers[:DRIVERS] for name_ in ("headline", *PROFILE)},
            "duplicates": sum(r.duplicates for r in ordered),
            "notes": notes,
        },
    }
    return view, parts


def document_entry(record: Record, current: float, share: float) -> dict[str, Any]:
    """One document as the company page lists it: its own header numbers, what it is worth here
    (`current` is its recency) and how much of the company's headline it is."""
    entry: dict[str, Any] = {
        "document_id": record.document_id,
        "title": record.title,
        "date_basis": record.date_basis,
        "headline": record.headline,
        "dimensions": {name: record.dimension(name) for name in PROFILE},
        "verdict_distribution": {
            category: int((record.summary.get("verdict_distribution") or {}).get(category, 0)) for category in CATEGORIES
        },
        "claim_count": int(record.summary.get("claim_count", len(record.claims))),
        "omission_count": int(record.summary.get("omission_count", len(record.omissions))),
        "recency": round(current, 3),
        "weight": round(current * record.headline["confidence"], 3),
        "share": round(share, 3),
        "ext": {},
    }
    if record.date:
        entry["date"] = record.date
    if record.analysis_id:
        entry["analysis_id"] = record.analysis_id
    if record.url:
        entry["url"] = record.url
    if record.document.get("text_type"):
        entry["text_type"] = record.document["text_type"]
    if record.origin:
        entry["ext"]["source"] = record.origin
    if record.duplicates:
        entry["ext"]["duplicates"] = record.duplicates
    return entry


def explain(view: dict[str, Any], parts: dict[str, Aggregate]) -> list[str]:
    """One line per number saying which documents it came from, then one per document saying what
    it was worth: the step's visual check, a level up."""
    lines = []
    for name in ("headline", *PROFILE):
        part = parts[name]
        lines.append(
            f"{name:<13} {part.score:.2f} at confidence {part.confidence:.2f}, "
            f"driven by {', '.join(part.drivers) or 'nothing scored'}"
        )
    for entry in view["documents"]:
        lines.append(
            f"  {entry.get('date', 'undated'):>10}  {entry['document_id']:<28} headline {entry['headline']['score']:.2f} "
            f"x recency {entry['recency']:.2f} x confidence {entry['headline']['confidence']:.2f} "
            f"-> share {entry['share'] * 100:.0f}% of the company's number"
        )
    lines.append(f"trend         {view['trend']['direction']} at confidence {view['trend']['confidence']:.2f}: {view['trend']['note']}")
    return lines


# ----------------------------------------------------------------------------- the words


class Words(BaseModel):
    narrative: str = Field(
        default="",
        description="Two or three sentences a reader should take from this company's pages seen together.",
    )


WRITE_TASK = """Write the narrative for a company page in an audit of environmental claims. The numbers below are already settled and are not yours to change; what is missing is the two or three sentences a reader sees under them.

Below are the company's documents in time order, each with the date it was published or captured and the headline likelihood the audit gave it, then what the audit found worst across them, then what it gives the company credit for, then what the trend arithmetic says about the movement between the documents.

Write `narrative`: two or three sentences for someone who has not read the documents. Say what these pages, taken together, are doing; name the strongest finding with its figure; and say what changed between the documents, in the terms the trend gives you. Where the trend says there is too little to call, say so plainly rather than describing a direction ("two pages eighteen months apart is a step, not a trend").

Name figures, dates and documents rather than gesturing at them. Do not describe the audit's own machinery, do not give a score in words, do not tell the reader what to think of the company, and do not invent any comparison the numbers below do not contain."""


def write_prompt(view: dict[str, Any]) -> str:
    documents = "\n".join(
        f"{entry['document_id']} | {entry.get('date', 'no date')} | headline {entry['headline']['score']:.2f} "
        f"at confidence {entry['headline']['confidence']:.2f} | {entry['claim_count']} claims, {entry['omission_count']} omissions\n"
        f"  {entry['title']}"
        for entry in view["documents"]
    ) or "(none)"
    issues = "\n".join(f"{i['rank']}. {i['document_id']} / {i['target']}: {i['title']}" for i in view["top_issues"]) or "(none)"
    credit = "\n".join(f"{c['document_id']} / {c['target']}: {c['title']}" for c in view["credit"]) or "(none)"
    profile = ", ".join(f"{name} {view['dimensions'][name]['score']:.2f}" for name in PROFILE)
    return (
        f"{WRITE_TASK}\n\n<company>{(view.get('company') or {}).get('name', '')}</company>\n\n"
        f"<headline>{view['headline']['score']:.2f} at confidence {view['headline']['confidence']:.2f}; "
        f"profile: {profile}</headline>\n\n"
        f"<documents>\n{documents}\n</documents>\n\n<issues>\n{issues}\n</issues>\n\n"
        f"<credit>\n{credit}\n</credit>\n\n<trend>\n{view['trend']['note']}\n</trend>"
    )


@dataclass
class CompanyResult:
    view: dict[str, Any]
    parts: dict[str, Aggregate] = field(default_factory=dict)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


def build_company(
    records: Iterable[Record],
    *,
    company: str | None = None,
    narrative: str = "",
    power: float = POWER,
    halflife_days: float = HALFLIFE_DAYS,
) -> CompanyResult:
    """The batch path: the arithmetic, plus whatever narrative is in hand (the API, tests, fakes)."""
    view, parts = aggregate_company(records, company=company, power=power, halflife_days=halflife_days)
    words = " ".join(narrative.split())
    if words:
        view["narrative"] = words
    result = CompanyResult(view, parts)
    result.notes.extend(explain(view, parts))
    return result


async def describe_company(
    records: Iterable[Record],
    *,
    company: str | None = None,
    llm: Llm | None = None,
    power: float = POWER,
    halflife_days: float = HALFLIFE_DAYS,
) -> CompanyResult:
    """Aggregate the company's analyses and write the narrative. One call, for the words only;
    every number is fixed before Claude sees anything. Raises LlmError when Claude cannot answer."""
    view, parts = aggregate_company(records, company=company, power=power, halflife_days=halflife_days)
    started = time.perf_counter()
    words, usage = Words(), None
    if view["documents"]:
        words, usage = await (llm or get_llm()).extract(
            write_prompt(view), Words, system=COMPANY_SYSTEM, cache=False,
            max_tokens=WRITE_MAX_OUTPUT_TOKENS, effort=WRITE_EFFORT,
        )
    narrative = " ".join(words.narrative.split())
    if narrative:
        view["narrative"] = narrative
    result = CompanyResult(view, parts)
    result.usage = combine_usage([usage] if usage else [], time.perf_counter() - started)
    note = (
        f"{(view.get('company') or {}).get('name', 'The company')} reads {view['headline']['score']} at confidence "
        f"{view['headline']['confidence']} over {view['document_count']} document(s), leaning to the worst of the record "
        f"by recency and confidence; trend {view['trend']['direction']} at confidence {view['trend']['confidence']}"
    )
    if usage is not None:
        note += f"; Claude wrote the narrative ({result.usage.describe()})"
    result.notes.append(note)
    result.notes.extend(explain(view, parts))
    return result


# ----------------------------------------------------------------------------- finding the analyses


TRANSLITERATE = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "ae", "å": "a", "Å": "A",
                               "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ß": "ss", "þ": "th", "ð": "d"})


def company_slug(name: str) -> str:
    """A company name as it appears in a URL: `Ørsted A/S` is `orsted-a-s`. Diacritics are folded
    so a demo does not turn on a keyboard layout."""
    folded = unicodedata.normalize("NFKD", name.translate(TRANSLITERATE))
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", plain.lower())).strip("-")


def find_company(names: Iterable[str], wanted: str) -> str | None:
    """The company one of these names refers to: the name itself, its slug, or an unambiguous
    prefix of it (`shell` for `Shell plc`). An ambiguous prefix is not a match — the page would
    otherwise be about whichever company sorted first."""
    wanted_slug = company_slug(wanted)
    if not wanted_slug:
        return None
    known = list(dict.fromkeys(names))
    for name in known:
        if company_slug(name) == wanted_slug:
            return name
    prefixed = [name for name in known if company_slug(name).startswith(wanted_slug)]
    return prefixed[0] if len(prefixed) == 1 else None


def load_records(sources: list[tuple[Path, str]]) -> tuple[list[Record], list[str]]:
    """Every analysis on disk that reached a header, and the logs that could not be read. Each
    source is a directory and what its logs are (`fixture`, `run`); a log that is still being
    written, or is broken, is reported rather than failing the page."""
    records: list[Record] = []
    skipped: list[str] = []
    for directory, kind in sources:
        if directory is None or not Path(directory).is_dir():
            continue
        for path in sorted(Path(directory).glob("*.jsonl")):
            try:
                events = read_log(path)
            except LogError as exc:
                skipped.append(f"{path.name}: {exc}")
                continue
            name = path.name.removesuffix(".jsonl").removesuffix(".events")
            record = fold_record(events, {"kind": kind, "name": name})
            if record is None or not record.company:
                continue
            record.read_at = path.stat().st_mtime
            records.append(record)
    return records, skipped


def quality(record: Record) -> tuple[int, int, int, float]:
    """How good an analysis of its document this is: the one with verdicts on the most claims
    wins, then a curated recording over an ad-hoc run, then the most recent."""
    return (
        len(record.verdicts), len(record.claims),
        ORIGIN_RANK.get(record.origin.get("kind", ""), 0), record.read_at,
    )


def collapse(records: Iterable[Record], key: Callable[[Record], str]) -> list[Record]:
    """One record per key, the best of those that share it, counting the rest in `duplicates`."""
    kept: dict[str, Record] = {}
    for record in records:
        here = key(record)
        before = kept.get(here)
        if before is None:
            kept[here] = record
            continue
        best, dropped = (record, before) if quality(record) > quality(before) else (before, record)
        best.duplicates = before.duplicates + dropped.duplicates + 1
        kept[here] = best
    return list(kept.values())


def group_by_company(records: Iterable[Record]) -> dict[str, list[Record]]:
    """The analyses grouped by the company their document names, one per document: the same page
    analysed twenty times is one document, and the rest are counted in `duplicates` so the page
    can say so. A page is identified by its URL, and then by its document id as well, so the ids
    the view is keyed by are unique however a document was reached."""
    def by_url(record: Record) -> str:
        return (record.url or record.document_id).strip().rstrip("/").lower()

    def by_id(record: Record) -> str:
        return record.document_id

    grouped: dict[str, list[Record]] = {}
    for record in records:
        grouped.setdefault(record.company, []).append(record)
    return {
        name: order_records(collapse(collapse(found, by_url), by_id))
        for name, found in sorted(grouped.items())
    }


# ----------------------------------------------------------------------------- command line


def _records_from_args(args: argparse.Namespace) -> tuple[list[Record], str]:
    if args.analysis:
        records = []
        for path in args.analysis:
            record = record_from_analysis(json.loads(Path(path).read_text(encoding="utf-8")), {"kind": "fixture", "name": Path(path).stem})
            if record is None:
                print(f"note: {path} has no document or no summary; skipped", file=sys.stderr)
                continue
            records.append(record)
        name = args.company or (records[-1].company if records else "")
        return [r for r in records if not name or r.company == name], name
    sources = [(Path(args.fixtures), "fixture"), (Path(args.runs), "run")]
    found, skipped = load_records(sources)
    for line in skipped:
        print(f"note: skipped {line}", file=sys.stderr)
    grouped = group_by_company(found)
    name = find_company(grouped, args.company or "") or ""
    if not name:
        print(f"error: no analyses for {args.company!r}. Analysed so far: {', '.join(grouped) or 'nothing'}", file=sys.stderr)
        return [], args.company or ""
    return grouped[name], name


async def _main(args: argparse.Namespace) -> int:
    records, name = _records_from_args(args)
    if not records:
        return 1
    if args.explain:
        result = build_company(records, company=name, power=args.power, halflife_days=args.halflife)
    else:
        try:
            result = await describe_company(records, company=name, power=args.power, halflife_days=args.halflife)
        except LlmError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.view, ensure_ascii=False, indent=2))
        return 0
    view = result.view
    print(f"{(view.get('company') or {}).get('name', name)}: {view['headline']['score']} at confidence {view['headline']['confidence']} over {view['document_count']} document(s)")
    for entry in view["documents"]:
        print(f"  {entry.get('date', '  undated '):>10}  {entry['headline']['score']:.2f}  {entry['share'] * 100:>3.0f}%  {entry['title'][:70]}")
    print(f"  trend: {view['trend']['direction']} (confidence {view['trend']['confidence']}) — {view['trend']['note']}")
    for issue in view["top_issues"]:
        print(f"  {issue['rank']}. {issue['document_id']} / {issue['target']}  {issue['title']}")
    if view.get("narrative"):
        print(f"\n{view['narrative']}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.company", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company", nargs="?", default="", help="the company, by name, slug or unambiguous prefix")
    parser.add_argument("--analysis", action="append", default=[], help="a folded analysis.json; repeatable, instead of reading the directories")
    parser.add_argument("--fixtures", default=str(REPO_ROOT / "fixtures"), help="directory of recordings")
    parser.add_argument("--runs", default=str(REPO_ROOT / "backend" / "data" / "runs"), help="directory of saved runs")
    parser.add_argument("--explain", action="store_true", help="print the arithmetic only; call no model")
    parser.add_argument("--power", type=float, default=POWER, help=f"how far the number leans to the worst of the record (default {POWER})")
    parser.add_argument("--halflife", type=float, default=HALFLIFE_DAYS, help=f"days in which a document's say halves (default {HALFLIFE_DAYS})")
    parser.add_argument("--json", action="store_true", help="print the company view as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
