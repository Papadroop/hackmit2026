"""Self-consistency evaluator (roadmap step 15; design-doc D5 "Self-consistency" and D6
Consistency): does the company say the same thing elsewhere, and did it say the same thing
before?

Every other evaluator asks whether the page is right. This one asks only whether the page
agrees with its own author, which is why it is the demo headliner (D2): a company contradicted
by an independent source can argue about the source, and a company contradicted by its own
annual report cannot. Two axes, searched in parallel:

1. **Elsewhere.** Claude searches the company's own publications — the annual report and the
   20-F and above all their risk factors and cautionary statements, the assured GHG statement,
   the transition strategy report where targets are set and retired, the other pages on the
   same subject — for the same target stated with a different number, the same figure with a
   different scope, or a condition the filings disclose and the page omits. Only the company's
   own material counts here; independent evidence is step 14's job, and keeping the two apart
   is what makes this stage's finding hard to argue with.
2. **Over time.** The Wayback Machine's captures of this very page are read with the same
   ingestion the live page went through, sampled across the years the archive covers, and
   compared with the page as it stands today. A target lowered, delayed or quietly dropped is
   the pattern the contract tags `greenrinsing`, and the archive is the only place it shows.
   A capture that is a JavaScript shell — which is what the archive holds for most modern
   corporate pages — is read from the content model captured nearest the same moment, with the
   timestamp read back from the archive's redirect so a 2025 shell is never paired with 2026
   content.

Citation integrity is the same bar as step 14 and is what makes either axis worth showing. A
quote from the company's other material is fetched from its URL here and looked for in the
page; a quote from an archived version is looked for in the capture this module holds, so that
check needs no network at all. **An unverified quote is never displayed** (D5); the item stays,
listed by name, and the run says so.

Then Consistency is scored per claim from both axes. One band is worth stating because it
inverts the other evaluators: **finding no contradiction is mildly good news, not a problem.**
For Support, nothing found means the claim is unsubstantiated and the score sits mid-range;
here, having looked through the filings and the archive and found the company saying the same
thing throughout, the honest score is low with modest confidence. A claim the model skips gets
a placeholder low and unconfident for the same reason, so an evaluator that finds nothing can
never by itself push a claim's likelihood (the weakest link, CONTRACT.md §6) above neutral.

    python -m auditor.consistency <file or url> [--golden fixtures/shell-climate.analysis.json]
    python -m auditor.consistency --history <url>

The second form only lists what the Wayback Machine holds for a page, which is how to tell
before a demo whether its archive axis has anything to say.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .documents import normalise_url
from .extract import document_system
from .knowledge import page_text, quote_in
from .language import claims_listing, clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm, web_tools

# ----------------------------------------------------------------------------- what Claude returns

Relation = Literal["supports", "contradicts", "contradicts_framing", "context"]
# What the company publishes about itself. Anything else belongs to step 14: this stage's whole
# claim to attention is that the contradiction comes from the author of the page.
SourceKind = Literal["filing", "report", "company_page", "press_release", "other"]
Independence = Literal["assured_filing", "company"]

# D5's ladder, for the two rungs this stage can reach. An assured filing is tier 2 because a
# third party signed it; everything else the company says about itself is tier 5.
TIERS: dict[str, int] = {"assured_filing": 2, "company": 5}

ChangeKind = Literal["weakened", "dropped", "delayed", "scope_narrowed", "restated", "softened", "strengthened", "unchanged"]

# The relation an archived version bears to a claim follows from what changed, and is derived
# here rather than asked for, for the same reason `tier` is derived from `independence` in step
# 14: it follows from the facts, not from the argument. An archived capture is the company's
# own page, so it can never substantiate a claim (D5). What it can do is show that today's
# impression of steady progress is not what the company was saying a year ago — which
# contradicts the framing, not the literal words, since "15-20% by 2030" is still true today.
CHANGE_RELATION: dict[str, str] = {
    "weakened": "contradicts_framing",
    "dropped": "contradicts_framing",
    "delayed": "contradicts_framing",
    "scope_narrowed": "contradicts_framing",
    "restated": "contradicts_framing",
    "softened": "contradicts_framing",
    "strengthened": "context",
    "unchanged": "context",
}
# A target changed before it was met: the contract's `greenrinsing` tag, which step 17 assigns
# and this stage finds the evidence for.
GREENRINSING: frozenset[str] = frozenset({"weakened", "dropped", "delayed"})


class Bearing(BaseModel):
    claim_id: str = Field(description="A claim id from the list.")
    relation: Relation = Field(description="From that claim's point of view: contradicts when the company's other words contradict what the claim literally says, contradicts_framing when the words stand but the impression does not, supports when the company says the same thing with the same scope elsewhere, context for background.")


class Statement(BaseModel):
    kind: SourceKind = Field(description="What the company publication is.")
    independence: Independence = Field(description="assured_filing for an audited or assured annual report, 20-F or GHG statement; company for everything else the company publishes about itself, including its unassured reports, pages and releases.")
    name: str = Field(description="The publication, as a reader would cite it: the document and the part of it.")
    publisher: str = Field(default="", description="Who published it, normally the company.")
    date: str = Field(default="", description="Publication date, ISO where known.")
    locator: str = Field(default="", description="Page, section or note reference.")
    url: str = Field(description="The page the quote is on. It will be fetched and the quote looked for.")
    quote: str = Field(description="One or two contiguous sentences, word for word from that page.")
    bears_on: list[Bearing] = Field(description="The claims this bears on, each with its own relation.")
    note: str = Field(default="", description="One sentence: what the company says here that the page under analysis does not, or says differently.")


class Statements(BaseModel):
    statements: list[Statement] = Field(description="What the company says elsewhere, most telling first; nothing for a claim where its other material says nothing different.")


class Change(BaseModel):
    claim_ids: list[str] = Field(description="The claims this bears on, by id from the list.")
    then_quote: str = Field(description="One or two contiguous sentences from the EARLIER version, word for word. It is checked against the capture after this call.")
    change: ChangeKind = Field(description="What happened between then and now.")
    note: str = Field(description="One sentence contrasting what the page said then with what it says now, naming both numbers or both dates where there are any.")


class Changes(BaseModel):
    changes: list[Change] = Field(description="One entry per thing the earlier version says about a claim; nothing at all if the capture is not a version of this page.")


class Assessment(BaseModel):
    claim_id: str
    score: float = Field(description="The Consistency problem score, 0 to 1, from the bands in the task.")
    confidence: float = Field(description="0 to 1: how far the company's own material settles the question.")
    basis: str = Field(description="One sentence naming the filing, page or capture that decides it.")
    evidence_ids: list[str] = Field(default_factory=list, description="The evidence the score rests on.")
    gap: str = Field(default="", description="What the page would have to say for it to match the company's own other words, in one sentence; empty when it already does.")


class Assessments(BaseModel):
    assessments: list[Assessment] = Field(description="Exactly one entry per claim under review, in the list's order.")


# ----------------------------------------------------------------------------- the tasks

ELSEWHERE_TASK = """Find where this company says something different from this page, in its own other words.

Below are the claims found in the document. Search the web for the company's own publications and open them.

Where to look, in this order:
- **The annual report and the 20-F or equivalent, and above all their risk factors and cautionary statements.** This is where a company writes down what its marketing pages do not: that a target sits outside the planning period, that the business plan does not reflect it, that it depends on things outside the company's control, that a figure is unassured. This is the single richest source for this question.
- The assured GHG or sustainability statement, and what the assurance opinion actually covers.
- The energy transition, climate or sustainability strategy report, where targets are set, revised, lowered and retired, and where the company explains why.
- The company's other pages on the same subject: an FAQ, a targets page, a methodology or basis-of-reporting note. These routinely state the same target with a different scope, a different baseline or a different word.
- Its press releases and results announcements.

You are not asking whether a claim is true — another evaluator does that with independent evidence, and it has already run. You are asking one question only: **does the company say the same thing here as it says on this page?** What counts:
- The same target with a different number, a different baseline, a different date or a different scope.
- A condition, caveat or qualification the filings state and this page leaves out.
- The company's own account of having lowered, delayed or retired a target the page still presents as progress.
- Small print that the page's impression cannot survive.
- Equally: the company stating the same thing, with the same scope, in an assured filing. That is a real finding and the audit gives credit for it.

Rules:
- **Only the company's own material.** A regulator, a journalist or an independent dataset does not belong in this answer, however relevant; that evidence is gathered elsewhere and duplicating it here helps nobody.
- The quote must be one or two contiguous sentences copied word for word from the page at the URL you give. Every quote is fetched from that URL and looked for in the page after this call. A quote that is not found is not displayed, so the finding is wasted. Do not paraphrase, do not join two passages with an ellipsis, do not tidy the punctuation, and do not write a quote from memory.
- Give the URL of the page the quote is actually on, not a landing page or a search result.
- Do not quote the page under analysis back at itself. The document above is what everything here is being compared with.

Return `statements`: one entry per source and quote, with `bears_on` naming the claims it bears on and the relation to each separately — one filing can confirm one claim and contradict the framing of another. Aim for the two or three that decide a claim, not a reading list. Return nothing for a claim where the company's other material says nothing different."""

ARCHIVE_TASK = """Compare an earlier version of this very page with the version under analysis, and say what the company changed.

The document above is the page as it stands today. Below are the claims found in it, then the same page as the Wayback Machine captured it on an earlier date.

The question is whether the company has quietly changed its own story. What to look for, claim by claim:
- **A target weakened**: a number lowered, a range widened downwards, a percentage cut.
- **A target dropped**: a commitment the earlier version made that the page no longer mentions at all.
- **A target delayed**: the same commitment carrying a later date.
- **A scope narrowed**: the same words now covering less — "our emissions" become "our operated assets", "our products" become "the products we sell".
- **A figure restated**: the same year's number given differently.
- **A commitment softened**: "we will" become "we aim to", a "target" become an "ambition".

A target changed before it was met is the pattern this audit calls greenrinsing, and an archived capture is the only place it can be seen. The earlier version is still the company's own page, so it can never prove a claim true; what it can do is show the company saying something else.

Return `changes`, one entry per thing the earlier version says about a claim:
- `claim_ids`: the claims it bears on.
- `then_quote`: one or two contiguous sentences from the EARLIER version below, word for word. It is checked against that capture after this call and dropped if it is not found there, so copy it exactly and do not join two passages together.
- `change`: which of weakened, dropped, delayed, scope_narrowed, restated, softened, strengthened, unchanged it is.
- `note`: one sentence contrasting what the page said then with what it says now, naming both numbers or both dates where there are any.

Return an entry for every claim that states a target, a number or a date, whether or not it changed: `unchanged` is a real finding and the audit gives credit for it. For a claim with no figure and no date, return an entry only when something did change. For a target the earlier version stated and this page no longer states at all, use `dropped` and quote the earlier version's sentence.

If the text below is not a version of this page — a different page, an error page, a cookie notice, a navigation menu — return no changes at all."""

SCORE_TASK = """Score each claim's Consistency: does the company say the same thing in its own other words, and did it say the same thing before?

Below are the claims to score, then the evidence this evaluator gathered: what the company says elsewhere in its own material (S ids) and what earlier versions of this page said (A ids). Read the document too.

**Consistency** is a problem score, 0 to 1, on the company contradicting itself. It is not about whether the claim is true — that is scored elsewhere from independent evidence. Bands:
- 0.05 to 0.2: the company says the same thing, with the same scope and baseline, in its filings and its other material, and the archived versions show the claim unchanged. Confidence 0.7 to 0.9 when an assured filing states it in the same terms.
- 0.3 to 0.4: nothing found either way, or a difference of wording that does not change what is being claimed. **This is where a claim lands when the search found no contradiction, and the confidence is 0.4 to 0.6, not lower and not higher: having looked and found nothing is weak evidence of consistency, and it is the honest answer for most claims on most pages.**
- 0.5 to 0.6: the company states the same claim elsewhere with a different scope, a different baseline or a different date; or the wording has drifted between a target and an ambition; or an archived version shows the claim's figure restated.
- 0.7 to 0.85: the company's own filing, report or earlier page states something this claim's impression cannot survive — a plan that cannot reflect the target, a condition the page omits, a target the archive shows was lowered, delayed or dropped before it was met.
- 0.85 to 1.0: the company's own words directly contradict what the claim literally says. Only a verified quote from the company's own material can reach this band.

Confidence is how far the company's own material settles it: 0.4 to 0.6 when nothing was found either way; 0.7 to 0.85 when a company page or an unassured report speaks to it directly; 0.9 or more when an assured filing or a capture of this very page does.

Rules:
- **Nothing found is not a contradiction.** An evaluator that scores every claim in the high bands because it could not check them has done the opposite of its job. The score for "we looked through the filings and the archive and the company says the same thing throughout" is low.
- An item marked "quote not verified" was retrieved but its quote could not be found on the page. Do not let it decide a score; if it is all there is for a claim, that claim's confidence is low.
- An assured filing weighs more than a company page, and the company's own page weighs more here than it would anywhere else: contradicting itself is exactly what this stage is entitled to conclude from it.
- Credit where due: a claim the filings state in the same terms, or one the archive shows standing unchanged for years, scores low and says so.

Return `assessments`: one entry per claim in the list, none twice, in the list's order, each with the score, the confidence, a one-sentence basis naming the filing, page or capture that decides it, the evidence ids it rests on (only ids from the listing), and `gap`: one sentence on what the page would have to say to match the company's own other words, empty when it already does."""

ELSEWHERE_MAX_OUTPUT_TOKENS = 16000
ARCHIVE_MAX_OUTPUT_TOKENS = 16000
SCORE_MAX_OUTPUT_TOKENS = 16000

# Claims per search call and per scoring call. Searching is the slow one: every call runs its
# own searches and fetches, so the batches are small and go out together.
BATCH_SIZE = int(os.environ.get("AUDITOR_CONSISTENCY_BATCH", "8"))
SCORE_BATCH_SIZE = int(os.environ.get("AUDITOR_CONSISTENCY_SCORE_BATCH", "9"))
MAX_SEARCHES = int(os.environ.get("AUDITOR_CONSISTENCY_SEARCHES", "6"))
MAX_FETCHES = int(os.environ.get("AUDITOR_CONSISTENCY_FETCHES", "6"))

# How many captures of the page to read. Each is a fetch, sometimes two, so this is the knob
# that decides how long the archive axis takes.
ARCHIVE_SNAPSHOTS = int(os.environ.get("AUDITOR_CONSISTENCY_SNAPSHOTS", "3"))
# A capture nearer than this to the page under analysis cannot show a change worth the fetch.
ARCHIVE_MIN_AGE_DAYS = int(os.environ.get("AUDITOR_CONSISTENCY_MIN_AGE_DAYS", "30"))
# Below this, what came back is chrome or an error page, not a version of the document.
ARCHIVE_MIN_WORDS = 120
# And above this it is not a page any more. A corporate page is two or three thousand words;
# a capture of a PDF report can be a hundred times that, and the comparison is with the page,
# so the tail is cut rather than the call abandoned. A quote from past the cut simply fails
# its check and goes undisplayed, which is the same answer as any other unverified quote.
ARCHIVE_MAX_CHARS = int(os.environ.get("AUDITOR_CONSISTENCY_MAX_CHARS", "60000"))

ELSEWHERE_EFFORT = os.environ.get("AUDITOR_CONSISTENCY_ELSEWHERE_EFFORT", "medium")
ARCHIVE_EFFORT = os.environ.get("AUDITOR_CONSISTENCY_ARCHIVE_EFFORT", "medium")
SCORE_EFFORT = os.environ.get("AUDITOR_CONSISTENCY_EFFORT", "medium")

STATEMENT_PREFIX = "S"
ARCHIVE_PREFIX = "A"
PLACEHOLDER_BASIS = "Not assessed by the self-consistency evaluator; neutral placeholder."
# Deliberately low, not the 0.5 the other evaluators use for an unassessed claim: on this
# dimension an absent answer means no contradiction was found, and a placeholder must never be
# the thing that pushes a claim's likelihood (the weakest link, CONTRACT.md §6) above neutral.
PLACEHOLDER_SCORE = 0.3
PLACEHOLDER_CONFIDENCE = 0.2

Emit = Callable[[str, dict[str, Any]], Any]
FetchText = Callable[[str], str]


def today() -> str:
    return date.today().isoformat()


# ----------------------------------------------------------------------------- the page over time


@dataclass
class ArchivedVersion:
    """One earlier version of the page under analysis, as this module read it."""

    stamp: str
    """The capture's real timestamp, `YYYYMMDDhhmmss`, read back from the archive's redirect."""
    url: str
    """The capture as a person opens it: the URL that goes on the evidence item."""
    text: str
    """Its canonical text, produced by the same ingestion the live page went through."""
    words: int
    via_model: bool = False

    @property
    def date(self) -> str:
        return f"{self.stamp[:4]}-{self.stamp[4:6]}-{self.stamp[6:8]}"


def stamp_date(stamp: str) -> datetime:
    return datetime.strptime(stamp[:14], "%Y%m%d%H%M%S")


def spread(history: list[Any], count: int, *, before: str | None = None) -> list[Any]:
    """`count` captures spread evenly over the time the archive covers, oldest first.

    Evenly over *time*, not over the list: the archive captures a page in bursts, so ten
    captures in one week and one a year later would otherwise be read as eleven equal steps and
    the year would go unexamined. `before` drops captures too close to the page under analysis
    to have changed."""
    usable = list(history)
    if before:
        cutoff = stamp_date(before)
        older = [s for s in usable if (cutoff - stamp_date(s.stamp)).days >= ARCHIVE_MIN_AGE_DAYS]
        usable = older or usable  # a page the archive has only just noticed: read it anyway
    if count <= 0 or not usable:
        return []
    if len(usable) <= count:
        return usable
    first, last = stamp_date(usable[0].stamp), stamp_date(usable[-1].stamp)
    span = (last - first).total_seconds()
    chosen: list[Any] = []
    for i in range(count):
        target = first.timestamp() + (span * i / (count - 1) if count > 1 else 0)
        nearest = min(usable, key=lambda s: abs(stamp_date(s.stamp).timestamp() - target))
        if nearest not in chosen:
            chosen.append(nearest)
    return sorted(chosen, key=lambda s: s.stamp)


def read_capture(snapshot: Any, original_url: str, *, fetcher: Any = None) -> tuple[ArchivedVersion | None, str]:
    """Read one Wayback capture into canonical text, the way ingestion read the live page.
    Returns (version, note); a capture that cannot be read is a None and a note, never a raise,
    because one missing capture must not cost the stage its other ones.

    Two things here are not obvious. The archive holds the HTML it was served, which for a
    modern corporate page is a JavaScript shell with no words in it; the live ingester answers
    that with the page's AEM content model, and so does this, asking the archive for the model
    captured nearest the same moment. And the timestamp is read back from the URL the archive
    redirects to, not taken from the one we asked for, so a capture of the shell from 2025 is
    never labelled with content the archive only holds from 2026."""
    from .ingest.aem import aem_blocks, looks_like_model, model_url_for
    from .ingest.blocks import DocumentMeta, build_document
    from .ingest.canonical import CanonicalError
    from .ingest.fetch import FetchError, fetch, wayback_url
    from .ingest.html import html_blocks, is_thin
    from .ingest.pdf import pdf_blocks

    get = _retrying(fetcher or fetch)
    try:
        fetched = get(snapshot.url)
    except FetchError as exc:
        return None, f"The capture of {snapshot.date} could not be fetched ({exc})."

    stamp, via_model = captured_stamp(fetched.url) or snapshot.stamp, False
    if fetched.is_pdf:
        result = pdf_blocks(fetched.body)
    elif fetched.is_json and looks_like_model(_json_or_none(fetched)):
        result = aem_blocks(fetched.json())
    else:
        result = html_blocks(fetched.text, fetched.url)
        if is_thin(result):
            # The archive kept the JavaScript shell. Ask it for the content model instead, and
            # believe the timestamp it answers with rather than the one requested.
            model_url = result.meta.aem_model_url or model_url_for(original_url)
            try:
                model_fetched = get(wayback_url(model_url, snapshot.stamp))
                model = _json_or_none(model_fetched)
            except FetchError as exc:
                return None, f"The capture of {snapshot.date} is {result.words} words of JavaScript shell and its content model is not archived ({exc})."
            if not looks_like_model(model):
                return None, f"The capture of {snapshot.date} is {result.words} words of JavaScript shell and no content model was captured with it."
            result = aem_blocks(model)
            stamp, via_model = captured_stamp(model_fetched.url) or stamp, True

    meta = DocumentMeta(
        title=f"Archived capture of {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
        company="", method="archive", retrieved=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
        url=original_url, archive_url=snapshot.viewable,
    )
    try:
        text = build_document(result.blocks, meta)["text"]
    except CanonicalError as exc:
        return None, f"The capture of {snapshot.date} did not read as canonical text ({exc})."
    words = len(text.split())
    if words < ARCHIVE_MIN_WORDS:
        return None, f"The capture of {snapshot.date} has only {words} words; too little to compare."
    viewable = wayback_url(original_url, stamp).replace("id_/", "/", 1)
    return ArchivedVersion(stamp, viewable, text, words, via_model), ""


def _retrying(get: Any, *, pause: float = 2.0) -> Any:
    """The archive answers 429 and 503 when it is busy, which on a bad afternoon is most of the
    time and has nothing to do with whether the capture exists. One retry turns most of those
    into the page; more than one would cost the demo more time than the capture is worth."""
    from .ingest.fetch import FetchError

    def attempt(url: str) -> Any:
        try:
            return get(url)
        except FetchError as exc:
            if getattr(exc, "status", None) not in (429, 503):
                raise
        time.sleep(pause)
        return get(url)

    return attempt


def captured_stamp(url: str) -> str | None:
    """The timestamp the archive actually served, from the URL it redirected to."""
    match = re.search(r"/web/(\d{14})", url or "")
    return match.group(1) if match else None


def _json_or_none(fetched: Any) -> Any:
    try:
        return fetched.json()
    except ValueError:
        return None


def archived_versions(
    document: dict[str, Any],
    *,
    count: int = ARCHIVE_SNAPSHOTS,
    history: Any = None,
    fetcher: Any = None,
) -> tuple[list[ArchivedVersion], list[str]]:
    """Earlier versions of the page under analysis, oldest first, with the notes that say what
    the archive held and what could be read. Empty and explained when the document has no URL,
    when the archive has nothing, or when nothing it has is readable."""
    from .ingest.fetch import wayback_history

    url = (document.get("source") or {}).get("url")
    if not url:
        return [], ["No URL for this document, so there is nothing for the Wayback Machine to have captured."]
    lookup = history or wayback_history
    captures = lookup(url)
    if not captures:
        return [], [f"The Wayback Machine holds no usable capture of {url} (or did not answer), so the page could not be compared with its earlier versions."]
    retrieved = (document.get("source") or {}).get("retrieved") or ""
    before = retrieved.replace("-", "") + "000000" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved) else None
    chosen = spread(captures, count, before=before)
    notes = [
        f"The Wayback Machine holds {len(captures)} distinct captures of this page, {captures[0].date} to {captures[-1].date}; "
        f"reading {len(chosen)} spread across that range ({', '.join(s.date for s in chosen)})."
    ]
    versions: list[ArchivedVersion] = []
    seen: set[str] = set()
    for snapshot in chosen:
        version, why = read_capture(snapshot, url, fetcher=fetcher)
        if version is None:
            notes.append(why)
        elif version.stamp in seen:
            # Several captures of the shell can resolve to one capture of the content model.
            notes.append(f"The capture of {snapshot.date} resolves to the same archived content as {version.date}; read once.")
        else:
            seen.add(version.stamp)
            versions.append(version)
            drift = abs((stamp_date(version.stamp) - stamp_date(snapshot.stamp)).days)
            if drift > ARCHIVE_MIN_AGE_DAYS:
                notes.append(
                    f"The capture of {snapshot.date} is a JavaScript shell; the nearest archived content for it is from "
                    f"{version.date}, {drift} days away, and that is the date it is reported and compared under."
                )
    if versions:
        notes.append(
            f"Read {len(versions)} earlier versions of the page: "
            + "; ".join(f"{v.date}, {v.words} words" + (" (from the archived content model)" if v.via_model else "") for v in versions)
        )
    else:
        notes.append("None of the captures could be read, so the page could not be compared with its earlier versions.")
    return sorted(versions, key=lambda v: v.stamp), notes


# ----------------------------------------------------------------------------- citation integrity


@dataclass
class Page:
    """What came back from fetching a URL, so one bad link never stops the stage."""

    url: str
    text: str | None = None
    error: str | None = None


def load_page(url: str, fetch_text: FetchText | None = None) -> Page:
    """Fetch a page for the quote check. Never raises: a page that cannot be read is a Page
    with an error, and its quote goes undisplayed like any other unverified one."""
    reader = fetch_text or page_text
    try:
        return Page(url, text=reader(url))
    except Exception as exc:  # noqa: BLE001 - reported on the evidence item, never raised
        detail = str(exc).strip() or type(exc).__name__
        return Page(url, error=detail[:160])


def check_quote(page: Page, quote: str) -> tuple[bool, str]:
    """(verified, why) for one quote against one page, by the contract's `fetched_exact` bar."""
    if page.error is not None:
        return False, f"Quote not verified: {page.url} could not be read from here ({page.error}). Open the link by hand."
    if page.text is None:
        return False, f"Quote not verified: {page.url} was not fetched."
    if quote_in(page.text, quote):
        return True, ""
    return False, f"Quote not found on {page.url} when it was fetched on {today()}, so it is not shown (citation integrity, design-doc D5)."


# ----------------------------------------------------------------------------- assembly


@dataclass
class ConsistencyResult:
    evidence: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    unverified: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    versions: list[ArchivedVersion] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def statements(self) -> list[dict[str, Any]]:
        return [e for e in self.evidence if e["kind"] != "archive"]

    @property
    def archived(self) -> list[dict[str, Any]]:
        return [e for e in self.evidence if e["kind"] == "archive"]

    @property
    def contradictions(self) -> list[dict[str, Any]]:
        """The items that make this stage worth running: the company against itself, quote
        verified. This is what the visual check for roadmap step 15 looks at."""
        return [
            e for e in self.evidence
            if e["verified"] and any(l["relation"] in ("contradicts", "contradicts_framing") for l in e["links"])
        ]

    @property
    def greenrinsing(self) -> list[dict[str, Any]]:
        return [e for e in self.archived if e.get("ext", {}).get("greenrinsing")]


class Assembler:
    """Turns statements, changes and assessments into contract entities one at a time, emitting
    each as it is built, so the stream and the batch path share one code path."""

    def __init__(
        self,
        claims: list[dict[str, Any]],
        prior_evidence: list[dict[str, Any]] | None = None,
        emit: Emit | None = None,
    ) -> None:
        self.claims = {c["id"]: c for c in claims}
        self.order = [c["id"] for c in claims]
        self.emit = emit
        self.evidence: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self.prior: dict[str, dict[str, Any]] = {e["id"]: e for e in (prior_evidence or [])}
        # Seeded with what the earlier stages already put on the table, so this stage never
        # shows the reader the same filing and the same sentence a second time.
        self.seen: set[tuple[str, str]] = {
            (normalise_url(e.get("url") or ""), " ".join((e.get("quote") or "").split()).lower())
            for e in (prior_evidence or []) if e.get("url") and e.get("quote")
        }
        self.scores: list[dict[str, Any]] = []
        self.scored: set[str] = set()
        self.unverified: list[str] = []
        self.placeholders: list[str] = []
        self.duplicates = 0
        self.unknown_claims = 0
        self.unknown_ids = 0
        self.repeated = 0
        self.downgraded = 0
        self.not_in_capture: list[str] = []

    # -- ids

    def _next_id(self, prefix: str) -> str:
        n = sum(1 for e in self.evidence if e["id"].startswith(prefix)) + 1
        while f"{prefix}{n}" in self.by_id or f"{prefix}{n}" in self.prior:
            n += 1
        return f"{prefix}{n}"

    def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.emit is not None:
            self.emit(type_, payload)

    def _add_evidence(self, item: dict[str, Any]) -> dict[str, Any]:
        self.by_id[item["id"]] = item
        self.evidence.append(item)
        self._emit("evidence.added", {"evidence": item})
        return item

    def _links(self, bears_on: list[Bearing]) -> list[dict[str, str]]:
        """The contract links for what the model said this bears on: unknown claims dropped,
        one link per claim, the first relation given for it kept."""
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for bearing in bears_on:
            if bearing.claim_id not in self.claims:
                self.unknown_claims += 1
            elif bearing.claim_id not in seen:
                seen.add(bearing.claim_id)
                out.append({"target": bearing.claim_id, "relation": bearing.relation})
        return out

    def _no_self_substantiation(self, links: list[dict[str, str]], tier: int, note: str) -> str:
        """D5: the company's own material cannot substantiate the company's own claim. The item
        stays and the link becomes what it honestly is. This stage deals in little else, so the
        rule earns its keep here more than anywhere."""
        if tier < 5 or not any(l["relation"] == "supports" for l in links):
            return note
        for link in links:
            if link["relation"] == "supports":
                link["relation"] = "context"
                self.downgraded += 1
        return (note + " " if note else "") + "The company's own material, so it is context, not substantiation (design-doc D5)."

    # -- what the company says elsewhere

    def add_statement(self, statement: Statement, page: Page) -> dict[str, Any] | None:
        """One of the company's other publications, its quote checked against the page it names."""
        links = self._links(statement.bears_on)
        if not links:
            return None
        key = (normalise_url(statement.url), " ".join(statement.quote.split()).lower())
        if key in self.seen:
            self.duplicates += 1
            return None
        self.seen.add(key)
        verified, why = check_quote(page, statement.quote)
        tier = TIERS[statement.independence]
        note = self._no_self_substantiation(links, tier, statement.note.strip())
        if not verified:
            self.unverified.append(statement.url)
            note = (note + " " if note else "") + why
        source = {"name": statement.name.strip() or statement.url}
        for key_, value in (("publisher", statement.publisher), ("date", statement.date), ("locator", statement.locator)):
            if value.strip():
                source[key_] = value.strip()
        item: dict[str, Any] = {
            "id": self._next_id(STATEMENT_PREFIX),
            "kind": statement.kind,
            "tier": tier,
            "source": source,
            "url": statement.url,
            "verified": verified,
            "verification": "fetched_exact" if verified else "unverified",
            "retrieved": today(),
            "stage": "consistency",
            "links": links,
            "ext": {"independence": statement.independence, "axis": "elsewhere"},
        }
        if verified:
            item["quote"] = statement.quote.strip()
        if note:
            item["note"] = note
        return self._add_evidence(item)

    # -- what the page said before

    def add_change(self, change: Change, version: ArchivedVersion) -> dict[str, Any] | None:
        """One thing an earlier version of the page said. The quote is checked against the
        capture this module holds, so the check is exact and needs no network."""
        links = self._links([Bearing(claim_id=cid, relation=CHANGE_RELATION[change.change]) for cid in change.claim_ids])
        if not links:
            return None
        key = (version.url, " ".join(change.then_quote.split()).lower())
        if key in self.seen:
            self.duplicates += 1
            return None
        self.seen.add(key)
        verified = quote_in(version.text, change.then_quote)
        note = change.note.strip()
        if not verified:
            # The model wrote a sentence the capture does not contain. Nothing about that
            # capture can be shown, so the item says only that the comparison was attempted.
            self.not_in_capture.append(f"{version.date}: {' '.join(change.then_quote.split())[:70]}")
            self.unverified.append(version.url)
            note = (note + " " if note else "") + (
                f"Quote not found in the capture of {version.date} when it was read, so it is not shown "
                "(citation integrity, design-doc D5)."
            )
        item: dict[str, Any] = {
            "id": self._next_id(ARCHIVE_PREFIX),
            "kind": "archive",
            # An archived version of the company's own page is still the company's own material.
            "tier": 5,
            "source": {
                "name": f"This page as it stood on {version.date} (Wayback Machine capture)",
                "publisher": "Internet Archive",
                "date": version.date,
                "locator": f"capture {version.stamp}",
            },
            "url": version.url,
            "verified": verified,
            "verification": "fetched_exact" if verified else "unverified",
            "retrieved": today(),
            "stage": "consistency",
            "links": links,
            "ext": {"axis": "archive", "change": change.change, "captured": version.stamp},
        }
        if change.change in GREENRINSING:
            # A target changed before it was met: the contract's `greenrinsing` tag, which the
            # verdict stage (step 17) assigns and this is the evidence for.
            item["ext"]["greenrinsing"] = True
        if verified:
            item["quote"] = change.then_quote.strip()
        if note:
            item["note"] = note
        return self._add_evidence(item)

    # -- scores

    def add_assessment(self, item: Assessment) -> dict[str, Any] | None:
        if item.claim_id not in self.claims:
            self.unknown_claims += 1
            return None
        if item.claim_id in self.scored:
            self.repeated += 1
            return None
        cited = [e for e in dict.fromkeys(item.evidence_ids) if e in self.by_id or e in self.prior]
        self.unknown_ids += len(set(item.evidence_ids)) - len(cited)
        score: dict[str, Any] = {
            "claim_id": item.claim_id,
            "dimension": "consistency",
            "score": clamp01(item.score),
            "confidence": clamp01(item.confidence),
            "basis": item.basis.strip() or "No basis given.",
            "stage": "consistency",
        }
        if cited:
            score["evidence_ids"] = cited
        if item.gap.strip():
            score["ext"] = {"gap": item.gap.strip()}
        self.scored.add(item.claim_id)
        self.scores.append(score)
        self._emit("dimension.scored", {"score": score})
        return score

    def finish(self, versions: list[ArchivedVersion] | None = None) -> ConsistencyResult:
        for cid in self.order:
            if cid not in self.scored:
                self.placeholders.append(cid)
                self.add_assessment(Assessment(
                    claim_id=cid, score=PLACEHOLDER_SCORE, confidence=PLACEHOLDER_CONFIDENCE, basis=PLACEHOLDER_BASIS,
                ))
        result = ConsistencyResult(
            self.evidence, self.scores, list(self.unverified), list(self.placeholders), list(versions or []),
        )
        linked = {l["target"] for e in self.evidence for l in e["links"]}
        result.notes.append(
            f"{len(result.statements)} statements from the company's other material and {len(result.archived)} from earlier "
            f"versions of this page, for {len(linked)} of {len(self.order)} claims; "
            f"{len(self.evidence) - len(self.unverified)} with the quote verified, {len(self.unverified)} listed without one; "
            f"{len(result.contradictions)} contradict the page or its framing"
            + (f", {len(result.greenrinsing)} of them a target changed before it was met" if result.greenrinsing else "")
            + (f"; {self.downgraded} tier-5 'supports' links made 'context'" if self.downgraded else "")
            + (f"; {self.duplicates} already on the table from an earlier stage, or repeated" if self.duplicates else "")
            + (f"; {self.unknown_ids} unknown evidence ids ignored" if self.unknown_ids else "")
            + (f"; {self.unknown_claims} unknown claim ids ignored" if self.unknown_claims else "")
            + (f"; {self.repeated} repeated assessments ignored" if self.repeated else "")
        )
        for line in self.not_in_capture[:6]:
            result.notes.append(f"Not in the capture, so not shown: {line}")
        if self.unverified:
            result.notes.append(f"Quote not verified, so not displayed: {', '.join(dict.fromkeys(self.unverified))[:300]}")
        if self.placeholders:
            result.notes.append(
                f"Placeholder consistency score ({PLACEHOLDER_SCORE}, confidence {PLACEHOLDER_CONFIDENCE}) for "
                f"{len(self.placeholders)} claims the model did not assess: {', '.join(self.placeholders[:10])}"
            )
        return result


# ----------------------------------------------------------------------------- what the model sees


def evidence_listing(items: list[dict[str, Any]]) -> str:
    """The evidence so far, as the scoring call reads it."""
    lines = []
    for item in items:
        links = ", ".join(f"{l['target']} ({l['relation']})" for l in item.get("links", []))
        head = f"{item['id']} [tier {item['tier']}; {item['kind']}] {item['source']['name']}"
        if item.get("source", {}).get("locator"):
            head += f" — {item['source']['locator']}"
        if item.get("ext", {}).get("change"):
            head += f" — the page's wording {item['ext']['change'].replace('_', ' ')}"
        body = item.get("quote") or item.get("note") or ""
        if not item.get("verified", False):
            body = "(quote not verified, so not shown) " + (item.get("note") or "")
        lines.append(f"{head}\n  Bears on: {links or 'nothing'}.\n  {' '.join(body.split())[:600]}")
    return "\n".join(lines) or "(nothing found)"


def known_sources(items: list[dict[str, Any]]) -> str:
    """What earlier stages already put on the table, by name, so the search does not spend a
    call finding it again."""
    names = dict.fromkeys(
        f"{e['source']['name']} ({e['url']})" for e in items if e.get("url") and e.get("source", {}).get("name")
    )
    return "\n".join(f"- {n}" for n in list(names)[:25])


def elsewhere_prompt(claims: list[dict[str, Any]], batch: list[dict[str, Any]] | None = None, prior: list[dict[str, Any]] | None = None) -> str:
    listing = claims_listing(claims)
    review = ""
    if batch is not None and len(batch) < len(claims):
        ids = ", ".join(c["id"] for c in batch)
        review = f"\n\n<review>\nIn this call, look for the company's other words on these claims only: {ids}. The other claims are listed for context; another call is looking for theirs.\n</review>"
    already = known_sources(prior or [])
    known = f"\n\n<already_found>\nEarlier stages have already put these sources in front of the reader. Do not return the same source and sentence again; a different part of the same document is fine.\n{already}\n</already_found>" if already else ""
    return f"{ELSEWHERE_TASK}\n\n<claims>\n{listing}\n</claims>{known}{review}"


def archive_prompt(claims: list[dict[str, Any]], version: ArchivedVersion) -> str:
    text = version.text
    cut = ""
    if len(text) > ARCHIVE_MAX_CHARS:
        text = text[:ARCHIVE_MAX_CHARS]
        cut = ' truncated="true"'
    return (
        f"{ARCHIVE_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n"
        f'<earlier_version captured="{version.date}" words="{version.words}"{cut}>\n{text}\n</earlier_version>'
    )


def score_prompt(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], batch: list[dict[str, Any]] | None = None) -> str:
    review = ""
    if batch is not None and len(batch) < len(claims):
        ids = ", ".join(c["id"] for c in batch)
        review = f"\n\n<review>\nIn this call, score only these claims: {ids}. The other claims are listed for context; return no assessment for them.\n</review>"
    return f"{SCORE_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<evidence>\n{evidence_listing(evidence)}\n</evidence>{review}"


# ----------------------------------------------------------------------------- the stage


def apply_consistency(
    statements: Statements,
    changes: dict[str, Changes],
    assessments: Assessments,
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    versions: list[ArchivedVersion] | None = None,
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    *,
    fetch_text: FetchText | None = None,
) -> ConsistencyResult:
    """The batch path: whole results at once (tests and fakes), in contract order — the
    company's other words, then what its earlier pages said, then the scores that cite both.
    `changes` is keyed by the capture's timestamp, so each quote is checked against the version
    it was read from."""
    assembler = Assembler(claims, prior_evidence, emit)
    pages: dict[str, Page] = {}
    for statement in statements.statements:
        if statement.url not in pages:
            pages[statement.url] = load_page(statement.url, fetch_text)
        assembler.add_statement(statement, pages[statement.url])
    by_stamp = {v.stamp: v for v in (versions or [])}
    for stamp, found in changes.items():
        version = by_stamp.get(stamp)
        if version is None:
            continue
        for change in found.changes:
            assembler.add_change(change, version)
    for assessment in assessments.assessments:
        assembler.add_assessment(assessment)
    return assembler.finish(versions)


async def consistency(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    llm: Llm | None = None,
    fetch_text: FetchText | None = None,
    fetcher: Any = None,
    history: Any = None,
    snapshots: int = ARCHIVE_SNAPSHOTS,
) -> ConsistencyResult:
    """Run the self-consistency evaluator on an ingested document and its claims: the company's
    other words searched for in parallel batches while the page's earlier versions are read
    from the archive, every quote checked against the page or the capture it came from, then
    Consistency scored from both. An axis that fails is reported and the stage carries on with
    the other; a failure to score raises LlmError, because the stage owes the verdict its
    dimension."""
    if not claims:
        return ConsistencyResult([], [], notes=["No claims to check for consistency."])
    llm = llm or get_llm()
    assembler = Assembler(claims, prior_evidence, emit)
    system = document_system(document)
    tools = web_tools(searches=MAX_SEARCHES, fetches=MAX_FETCHES)
    batches = [claims[i : i + max(1, BATCH_SIZE)] for i in range(0, len(claims), max(1, BATCH_SIZE))]
    started = time.perf_counter()
    usages: list[Usage] = []
    counts = {"statements": 0, "changes": 0, "assessments": 0, "invalid": 0, "out_of_batch": 0}
    failures: list[str] = []
    archive_notes: list[str] = []
    versions: list[ArchivedVersion] = []
    pages: dict[str, Page] = {}
    page_lock = asyncio.Lock()
    first: list[float] = []

    async def page_for(url: str) -> Page:
        async with page_lock:
            if url in pages:
                return pages[url]
            pages[url] = Page(url, error="pending")
        fetched = await asyncio.to_thread(load_page, url, fetch_text)
        async with page_lock:
            pages[url] = fetched
        return fetched

    async def place(statement: Statement) -> None:
        page = await page_for(statement.url)
        if assembler.add_statement(statement, page) is not None and not first:
            first.append(time.perf_counter() - started)

    # -- axis 1: what the company says elsewhere, in its own material

    async def run_elsewhere(batch: list[dict[str, Any]]) -> None:
        ids = {c["id"] for c in batch}
        handed: list[Statement] = []
        placing: list[asyncio.Task[None]] = []

        async def on_element(key: str, item: dict[str, Any]) -> None:
            if key != "statements":
                return
            try:
                statement = Statement.model_validate(item)
            except ValidationError:
                counts["invalid"] += 1
                return
            if not ({b.claim_id for b in statement.bears_on} & ids):
                counts["out_of_batch"] += 1
                return
            handed.append(statement)
            placing.append(asyncio.create_task(place(statement)))

        try:
            result, usage = await llm.extract_streaming(
                elsewhere_prompt(claims, batch=batch, prior=prior_evidence), Statements, on_element=on_element,
                system=system, cache=True, tools=tools, max_tokens=ELSEWHERE_MAX_OUTPUT_TOKENS, effort=ELSEWHERE_EFFORT,
            )
        except LlmError as exc:
            # One search that fails must not lose the other batches' evidence.
            failures.append(f"the company's other words on {', '.join(sorted(ids))}: {exc}")
            if placing:
                await asyncio.gather(*placing)
            return
        usages.append(usage)
        counts["statements"] += len(result.statements)
        seen = {(s.url, s.quote) for s in handed}
        for statement in result.statements:
            if (statement.url, statement.quote) not in seen and {b.claim_id for b in statement.bears_on} & ids:
                placing.append(asyncio.create_task(place(statement)))
        if placing:
            await asyncio.gather(*placing)

    # -- axis 2: what this page said before

    async def run_archive() -> None:
        found, notes = await asyncio.to_thread(
            archived_versions, document, count=snapshots, history=history, fetcher=fetcher,
        )
        archive_notes.extend(notes)
        versions.extend(found)
        if not found:
            return

        async def compare(version: ArchivedVersion) -> None:
            handed = 0

            async def on_element(key: str, item: dict[str, Any]) -> None:
                nonlocal handed
                if key != "changes":
                    return
                handed += 1
                try:
                    change = Change.model_validate(item)
                except ValidationError:
                    counts["invalid"] += 1
                    return
                if assembler.add_change(change, version) is not None and not first:
                    first.append(time.perf_counter() - started)

            try:
                found, usage = await llm.extract_streaming(
                    archive_prompt(claims, version), Changes, on_element=on_element,
                    system=system, cache=True, max_tokens=ARCHIVE_MAX_OUTPUT_TOKENS, effort=ARCHIVE_EFFORT,
                )
                for change in found.changes[handed:]:  # anything the incremental pass missed
                    assembler.add_change(change, version)
                counts["changes"] += len(found.changes)
                usages.append(usage)
            except LlmError as exc:
                failures.append(f"the capture of {version.date}: {exc}")

        async with asyncio.TaskGroup() as group:
            for version in found:
                group.create_task(compare(version))

    async with asyncio.TaskGroup() as group:
        for batch in batches:
            group.create_task(run_elsewhere(batch))
        group.create_task(run_archive())

    # -- the scores, once every item they can cite exists (contract §2, rule 3)
    listing = [*(prior_evidence or []), *assembler.evidence]
    score_batches = [claims[i : i + max(1, SCORE_BATCH_SIZE)] for i in range(0, len(claims), max(1, SCORE_BATCH_SIZE))]

    async def run_scoring(batch: list[dict[str, Any]]) -> None:
        ids = {c["id"] for c in batch}
        handed = 0

        async def on_element(key: str, item: dict[str, Any]) -> None:
            nonlocal handed
            if key != "assessments":
                return
            handed += 1
            try:
                assessment = Assessment.model_validate(item)
            except ValidationError:
                counts["invalid"] += 1
                return
            if assessment.claim_id not in ids:
                counts["out_of_batch"] += 1
                return
            assembler.add_assessment(assessment)

        result, usage = await llm.extract_streaming(
            score_prompt(claims, listing, batch=batch), Assessments, on_element=on_element,
            system=system, cache=True, max_tokens=SCORE_MAX_OUTPUT_TOKENS, effort=SCORE_EFFORT,
        )
        for assessment in result.assessments[handed:]:
            if assessment.claim_id in ids:
                assembler.add_assessment(assessment)
        counts["assessments"] += len(result.assessments)
        usages.append(usage)

    try:
        async with asyncio.TaskGroup() as group:
            for batch in score_batches:
                group.create_task(run_scoring(batch))
    except* LlmError as errors:
        raise errors.exceptions[0]

    result = assembler.finish(versions)
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = (
        f"Claude searched the company's own material for {len(claims)} claims over {len(batches)} parallel calls of up to {BATCH_SIZE}"
        + (f", compared {len(versions)} archived versions of the page" if versions else ", with no archived version to compare")
        + (f" (first item after {first[0]:.1f} s)" if first else "")
        + f", returned {counts['statements']} statements and {counts['changes']} changes, and scored {counts['assessments']} claims over {len(score_batches)} calls"
    )
    if counts["invalid"]:
        note += f", {counts['invalid']} malformed"
    if counts["out_of_batch"]:
        note += f", {counts['out_of_batch']} for claims outside their call ignored"
    result.notes.insert(0, note + f" ({result.usage.describe()})")
    # Spliced, not inserted one by one: the archive's notes tell a story in order (what the
    # Wayback Machine held, which captures were read, what each one cost), and inserting each
    # at the same index would tell it backwards.
    result.notes[1:1] = [*(f"Failed: {failure}" for failure in failures), *archive_notes]
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class ConsistencyComparison:
    """The reference's consistency-stage findings against a live run's. Hand-curated URLs and a
    live search rarely land on the same page, so sources are matched by host; what the check is
    really asking is whether the live run found the company contradicting itself about the same
    claims the golden reference did."""

    reference_hosts: list[str]
    found_hosts: list[str]
    live_sources: int
    verified: int
    reference_contradicted: list[str]
    live_contradicted: list[str]

    @property
    def agreed(self) -> list[str]:
        return sorted(set(self.reference_contradicted) & set(self.live_contradicted))

    @property
    def missed(self) -> list[str]:
        return sorted(set(self.reference_contradicted) - set(self.live_contradicted))

    def describe(self) -> str:
        return (
            f"{len(self.found_hosts)} of {len(self.reference_hosts)} reference sources matched by host "
            f"({', '.join(sorted(self.found_hosts)) or 'none'}); {self.live_sources} live sources, {self.verified} with the quote verified; "
            f"the company contradicts itself on {len(self.live_contradicted)} claims against the reference's {len(self.reference_contradicted)}, "
            f"{len(self.agreed)} the same ({', '.join(self.agreed) or 'none'})"
            + (f", {len(self.missed)} missed ({', '.join(self.missed)})" if self.missed else "")
        )


def host_of(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).netloc.lower().removeprefix("www.")


def contradicted_claims(evidence: list[dict[str, Any]]) -> list[str]:
    """The claims some consistency-stage item contradicts, literally or in their framing."""
    out: set[str] = set()
    for item in evidence:
        if item.get("stage") != "consistency":
            continue
        for link in item.get("links", []):
            if link["relation"] in ("contradicts", "contradicts_framing"):
                out.add(link["target"])
    return sorted(out)


def compare_consistency(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> ConsistencyComparison:
    live_sources = [e for e in live if e.get("url")]
    live_hosts = {host_of(e["url"]) for e in live_sources}
    # An archived capture is served by the archive, so match it on the page it is a copy of.
    live_hosts |= {host_of(re.sub(r"^https?://web\.archive\.org/web/\d+/", "", e["url"])) for e in live_sources}
    reference_hosts = sorted({host_of(e["url"]) for e in reference if e.get("stage") == "consistency" and e.get("url")})
    return ConsistencyComparison(
        reference_hosts,
        sorted(h for h in reference_hosts if h in live_hosts),
        len(live_sources),
        sum(1 for e in live_sources if e["verified"]),
        contradicted_claims(reference),
        contradicted_claims(live),
    )


# ----------------------------------------------------------------------------- command line


def _print_evidence(item: dict[str, Any]) -> None:
    targets = ",".join(l["target"] for l in item["links"])
    mark = "ok  " if item["verified"] else "FAIL"
    change = f" [{item['ext']['change']}]" if item.get("ext", {}).get("change") else ""
    rinse = " GREENRINSING" if item.get("ext", {}).get("greenrinsing") else ""
    print(f"{mark} {item['id']:>4}  {item['links'][0]['relation']:<20} tier {item['tier']} {targets:<20} {item['source']['name'][:60]}{change}{rinse}")
    if item.get("quote"):
        print(f"          “{' '.join(item['quote'].split())[:150]}”")
    if item.get("url"):
        print(f"          {item['url']}")
    if item.get("note"):
        print(f"          {' '.join(item['note'].split())[:150]}")


async def _main(args: argparse.Namespace) -> int:
    from .extract import extract_claims
    from .ingest import IngestError, ingest_file, ingest_url
    from .language import reanchored_claims
    from .substantiate import substantiate

    try:
        if args.source.startswith(("http://", "https://")):
            ingested = ingest_url(args.source, demo_dir=Path(__file__).resolve().parents[2] / "demo-documents")
        else:
            ingested = ingest_file(Path(args.source))
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = ingested.document
    print(f"{document['title']} — {document['word_count']} words", file=sys.stderr)
    analysis = json.loads(Path(args.golden).read_text(encoding="utf-8")) if args.golden else None
    try:
        if analysis is not None:
            claims = reanchored_claims(analysis["claims"], document["text"], analysis["document"]["text"])
            print(f"using the reference's {len(claims)} claims as input", file=sys.stderr)
        else:
            extracted = await extract_claims(document)
            claims = extracted.claims
        prior: list[dict[str, Any]] = []
        if not args.no_knowledge:
            matched = await substantiate(document, claims, score=False)
            prior = matched.evidence

        def emit(type_: str, payload: dict[str, Any]) -> None:
            if args.json:
                return
            if type_ == "evidence.added":
                _print_evidence(payload["evidence"])
            else:
                s = payload["score"]
                print(f"     {s['claim_id']:>4}  {s['dimension']:<12} {s['score']:<5} confidence {s['confidence']:<5} [{','.join(s.get('evidence_ids', []))}] {s['basis'][:100]}")

        result = await consistency(document, claims, prior_evidence=prior, emit=emit, snapshots=args.snapshots)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps({"evidence": result.evidence, "scores": result.scores}, ensure_ascii=False, indent=2))
    if analysis is not None:
        print(f"\nagainst {Path(args.golden).name}: {compare_consistency(result.evidence, analysis['evidence']).describe()}")
        from .verify import compare_scores

        comparison = compare_scores(result.scores, analysis["scores"], "consistency")
        print(comparison.describe())
        for cid, live, ref in comparison.pairs:
            flag = "  <-- other side of 0.6" if (live > 0.6) != (ref > 0.6) else ""
            print(f"  {cid:>4} live {live:<5} reference {ref:<5} diff {live - ref:+.2f}{flag}")
    return 0


def _history(url: str, count: int) -> int:
    """What the Wayback Machine holds for a page, and which captures this stage would read."""
    from .ingest.fetch import wayback_history

    captures = wayback_history(url)
    if not captures:
        print(f"The Wayback Machine holds no usable capture of {url} (or did not answer).")
        return 1
    chosen = {s.stamp for s in spread(captures, count)}
    print(f"{len(captures)} distinct captures, {captures[0].date} to {captures[-1].date}; the stage would read {len(chosen)}:")
    for snapshot in captures:
        print(f"  {'-->' if snapshot.stamp in chosen else '   '} {snapshot.date}  {snapshot.viewable}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.consistency", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims are the input and its consistency scores the reference")
    parser.add_argument("--no-knowledge", action="store_true", help="skip the substantiation matching that usually precedes this stage")
    parser.add_argument("--snapshots", type=int, default=ARCHIVE_SNAPSHOTS, help=f"how many archived versions of the page to read (default {ARCHIVE_SNAPSHOTS}; 0 for none)")
    parser.add_argument("--json", action="store_true", help="print the evidence and scores as JSON")
    parser.add_argument("--history", metavar="URL", help="only list what the Wayback Machine holds for a page, and which captures this stage would read")
    args = parser.parse_args(argv)
    if args.history:
        return _history(args.history, args.snapshots)
    if not args.source:
        parser.error("a source is required unless --history is given")
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
