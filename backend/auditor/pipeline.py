"""Live analysis: every stage of the pipeline, on any document (roadmap phase 2, complete).

A request reads its text, URL or PDF into a contract Document; the model decomposes it into atomic
claims; the linguistic evaluator marks how each is worded and scores its Clarity; the
substantiation evaluator matches every claim to the criteria it is measured against and the
precedents on similar wording; external verification searches the web for the facts, checks
every quote against the page it came from, recomputes the numbers and scores Support and
Materiality; the self-consistency evaluator reads the company against its own filings and
against the Wayback Machine's captures of this very page, and scores Consistency; the omissions
stage measures the page against the material topics its industry's reference names; a
prosecutor and a defence then argue every claim and a judge decides it; and the summary
aggregates the lot into the header. Each entity is streamed as it is written, and each stage
fails with its own name on it.

Nothing is replayed. A recording of the same page, when one exists, is a *reference to measure
against*, not a source of events: the live claims are aligned with the recording's by span
overlap so the ids line up, and each stage emits a `debug.note` comparing what it found with
what the golden reference records — the recall of the claims and marks, the sources matched by
host, the scores' mean absolute difference, the categories that agree, the header's profile.
Those notes are each step's visual check, and they are the only thing the recording is for. A
page nobody has ever recorded runs exactly the same way, and finishes.

Roadmap steps 10-18 are all here: `ingest`, `extract`, `language`, `substantiate`, `verify`,
`consistency`, `omissions`, `verdict` and `summary`, in the order CONTRACT.md §2 names them.
A claim some evaluator left unscored on one of the four dimensions gets no verdict and stays
neutral, which is what the contract allows; everything else is decided and aggregated.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import consistency as consistency_module
from . import extract as extract_module
from . import ingest
from . import language as language_module
from . import omissions as omissions_module
from . import substantiate as substantiate_module
from . import summary as summary_module
from . import verdict as verdict_module
from . import verify as verify_module
from .documents import recording_for_url
from .envelope import (
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    ANALYSIS_STARTED,
    STAGE_COMPLETED,
    STAGE_STARTED,
    Event,
)
from .extract import compare
from .knowledge import KnowledgeError
from .llm import LlmError
from .store import Analysis
from .verdict import DIMENSIONS

# contract/schema.json version this producer writes. The real pipeline should share this
# constant with contract/tools/contract.py rather than keep its own copy.
CONTRACT_VERSION = "1.0.0"

# Text, URL and PDF requests are accepted: ingestion (step 10) is built.
LIVE_AVAILABLE = True

INGEST_LABEL = "Reading the document"
EXTRACT_LABEL = "Finding claims"
LANGUAGE_LABEL = "Reading how claims are worded"
SUBSTANTIATE_LABEL = "Checking criteria and precedents"
VERIFY_LABEL = "Gathering evidence and recomputing numbers"
OMISSIONS_LABEL = "Looking for what the page leaves out"
CONSISTENCY_LABEL = "Comparing the company with itself"
VERDICT_LABEL = "Arguing each claim and deciding it"
SUMMARY_LABEL = "Adding up the page"
CLAIM_STAGGER_SECONDS = 0.04

# The evaluator stages in the order the contract names them, so a replay can say which of them
# ran live and which the recording still supplies.
STAGE_ORDER = ("ingest", "extract", "language", "substantiate", "verify", "consistency", "omissions", "verdict", "summary")


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

    # -- ingest (step 10)
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

    # -- extract (step 11)
    recording = recording_for_url(fixtures_dir, document.get("source", {}).get("url"))
    analysis.emit(STAGE_STARTED, {"stage": "extract", "label": EXTRACT_LABEL})
    reading = time.perf_counter()

    async def found_so_far(count: int) -> None:
        # The claims cannot be emitted yet - their ids follow document order, which needs the
        # whole list - so this is the only sign the stage is alive while the model writes.
        if count == 1 or count % 3 == 0:
            analysis.emit("debug.note", {"text": f"Reading: {count} claims so far ({time.perf_counter() - reading:.0f} s)."})

    try:
        result = await extract_module.extract_claims(document, on_progress=found_so_far)
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"Claim extraction failed: {exc}", "stage": "extract"})
        return
    for note in result.notes:
        analysis.emit("debug.note", {"text": note})
    kept_recorded: set[str] = set()
    if recording is not None:
        name, events = recording
        reference = recorded_claims(events)
        old_text = recorded_text(events)
        comparison = compare(result.claims, reference, document["text"], old_text)
        kept_recorded = align_ids(result.claims, comparison, reference)
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {comparison.describe()}."})
        # (align_ids renamed the live ids inside `comparison` too, so the note shows the ids the log carries)
    for claim in result.claims:
        analysis.emit("claim.extracted", {"claim": claim})
        await asyncio.sleep(CLAIM_STAGGER_SECONDS / speed)
    analysis.emit(STAGE_COMPLETED, {"stage": "extract"})

    # -- language (step 12): every signal and score is emitted as the model writes it
    analysis.emit(STAGE_STARTED, {"stage": "language", "label": LANGUAGE_LABEL})
    try:
        review = await language_module.review_language(document, result.claims, emit=analysis.emit)
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"Language review failed: {exc}", "stage": "language"})
        return
    for note in review.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        signals = language_module.compare_signals(review.signals, recorded_signals(events), document["text"], old_text)
        clarity = language_module.compare_clarity(review.scores, recorded_scores(events))
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {signals.describe()}; {clarity.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "language"})

    # -- substantiate (step 13): criteria and precedents from the knowledge stores. Support is
    # not scored here: it is the dimension external verification owns once it exists (D6), and
    # the contract allows exactly one score per claim per dimension.
    analysis.emit(STAGE_STARTED, {"stage": "substantiate", "label": SUBSTANTIATE_LABEL})
    try:
        substantiation = await substantiate_module.substantiate(document, result.claims, emit=analysis.emit, score=False)
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"Substantiation failed: {exc}", "stage": "substantiate"})
        return
    except KnowledgeError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The knowledge stores could not be read: {exc}", "stage": "substantiate"})
        return
    for note in substantiation.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        links = substantiate_module.compare_links(substantiation.evidence, recorded_evidence(events))
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {links.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "substantiate"})

    # -- verify (step 14): live retrieval, every quote checked against its page, the numbers
    # recomputed, then Support and Materiality scored from all of it
    analysis.emit(STAGE_STARTED, {"stage": "verify", "label": VERIFY_LABEL})
    try:
        verification = await verify_module.verify(document, result.claims, prior_evidence=substantiation.evidence, emit=analysis.emit)
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"External verification failed: {exc}", "stage": "verify"})
        return
    for note in verification.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        sources = verify_module.compare_sources(verification.evidence, recorded_evidence(events))
        support = verify_module.compare_scores(verification.scores, recorded_scores(events), "support")
        materiality = verify_module.compare_scores(verification.scores, recorded_scores(events), "materiality")
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {sources.describe()}; {support.describe()}; {materiality.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "verify"})

    # -- consistency (step 15): the company against itself. Its own filings and pages are
    # searched for what it says elsewhere, and the Wayback Machine's captures of this very page
    # for what it said before; every quote is checked against the page or the capture it came
    # from, and Consistency is scored from both. Nothing here rests on an outside source, which
    # is what makes it the demo headliner (D2): the contradiction is in the company's own words.
    analysis.emit(STAGE_STARTED, {"stage": "consistency", "label": CONSISTENCY_LABEL})
    try:
        against_itself = await consistency_module.consistency(
            document, result.claims, prior_evidence=[*substantiation.evidence, *verification.evidence], emit=analysis.emit,
        )
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The self-consistency evaluator failed: {exc}", "stage": "consistency"})
        return
    for note in against_itself.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        sources = consistency_module.compare_consistency(against_itself.evidence, recorded_evidence(events))
        scores = verify_module.compare_scores(against_itself.scores, recorded_scores(events), "consistency")
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {sources.describe()}; {scores.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "consistency"})

    # -- omissions (step 16): the materiality reference for the company's industry against what
    # the page covers. It needs only the claims and the evidence already on the table, so the
    # contract lets it run beside the evaluators (§2 rule 1); it runs here, after verify and
    # consistency, so a margin card can cite the filings, the computations and the company's own
    # admissions that establish the fact left out.
    analysis.emit(STAGE_STARTED, {"stage": "omissions", "label": OMISSIONS_LABEL})
    try:
        missing = await omissions_module.find_omissions(
            document, result.claims,
            prior_evidence=[*substantiation.evidence, *verification.evidence, *against_itself.evidence],
            emit=analysis.emit,
        )
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The omissions stage failed: {exc}", "stage": "omissions"})
        return
    except KnowledgeError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The materiality reference could not be read: {exc}", "stage": "omissions"})
        return
    for note in missing.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        against = omissions_module.compare_omissions(missing.omissions, recorded_omissions(events))
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {against.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "omissions"})

    # -- verdict (step 17): a prosecutor and a defence argue each claim from everything above,
    # and a judge decides it. The likelihood, category and confidence are the contract's rules.
    scores = [*review.scores, *verification.scores, *against_itself.scores]
    evidence = [*substantiation.evidence, *verification.evidence, *against_itself.evidence, *missing.evidence]
    analysis.emit(STAGE_STARTED, {"stage": "verdict", "label": VERDICT_LABEL})
    ready, neutral = fully_scored(result.claims, scores)
    if neutral:
        # The contract wants all four dimensions before a verdict (§2, rule 3), so a claim some
        # evaluator left unscored stays neutral rather than being decided on three of them.
        analysis.emit("debug.note", {"text": f"{len(neutral)} claims are not scored on every dimension and are left without a verdict: {', '.join(neutral[:10])}."})
    try:
        decided = await verdict_module.issue_verdicts(document, ready, scores, evidence, review.signals, emit=analysis.emit)
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The verdict layer failed: {exc}", "stage": "verdict"})
        return
    for note in decided.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        against = verdict_module.compare_verdicts(decided.verdicts, recorded_verdicts(events))
        analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {against.describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "verdict"})

    # -- summary (step 18): the header, aggregated from the real results. Every number records
    # the claims it came from, which is the step's visual check.
    analysis.emit(STAGE_STARTED, {"stage": "summary", "label": SUMMARY_LABEL})
    try:
        header = await summary_module.summarise(
            document, result.claims, scores, decided.verdicts, missing.omissions, emit=analysis.emit,
        )
    except LlmError as exc:
        analysis.emit(ANALYSIS_FAILED, {"error": f"The summary failed: {exc}", "stage": "summary"})
        return
    for note in header.notes:
        analysis.emit("debug.note", {"text": note})
    if recording is not None:
        recorded = recorded_summary(events)
        if recorded is not None:
            analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {summary_module.compare_summaries(header.summary, recorded).describe()}."})
    analysis.emit(STAGE_COMPLETED, {"stage": "summary"})
    analysis.emit(ANALYSIS_COMPLETED, {"counts": {
        "claims": len(result.claims),
        "signals": len(review.signals),
        "evidence": len(evidence),
        "omissions": len(missing.omissions),
    }})


def public_source(request: dict[str, Any]) -> dict[str, Any]:
    """What the log records about the request: never the pasted text or the PDF bytes."""
    kind = request.get("kind")
    if kind == "text":
        return {"kind": "text", "title": request.get("title"), "chars": len(str(request.get("text") or ""))}
    if kind == "pdf":
        data = str(request.get("data_base64") or "")
        return {"kind": "pdf", "filename": request.get("filename"), "bytes": len(data) * 3 // 4}
    return {"kind": "url", "url": request.get("url")}


# ----------------------------------------------------------------------------- recordings


def recorded_claims(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["claim"] for e in events if e.type == "claim.extracted" and isinstance(e.payload.get("claim"), dict)]


def recorded_signals(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["signal"] for e in events if e.type == "language.signal" and isinstance(e.payload.get("signal"), dict)]


def recorded_scores(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["score"] for e in events if e.type == "dimension.scored" and isinstance(e.payload.get("score"), dict)]


def fully_scored(claims: list[dict[str, Any]], scores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """(the claims with all four dimensions, the ids of the rest). The verdict stage decides
    the first; the second have no verdict, which is what the contract allows and the panel
    shows as neutral."""
    by_claim: dict[str, set[str]] = defaultdict(set)
    for score in scores:
        by_claim[score["claim_id"]].add(score["dimension"])
    ready = [c for c in claims if by_claim[c["id"]] >= set(DIMENSIONS)]
    return ready, [c["id"] for c in claims if by_claim[c["id"]] < set(DIMENSIONS)]


def recorded_verdicts(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["verdict"] for e in events if e.type == "verdict.issued" and isinstance(e.payload.get("verdict"), dict)]


def recorded_evidence(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["evidence"] for e in events if e.type == "evidence.added" and isinstance(e.payload.get("evidence"), dict)]


def recorded_summary(events: list[Event]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.type == "summary.updated" and isinstance(event.payload.get("summary"), dict):
            return event.payload["summary"]
    return None


def recorded_omissions(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["omission"] for e in events if e.type == "omission.found" and isinstance(e.payload.get("omission"), dict)]


def recorded_text(events: list[Event]) -> str | None:
    for event in events:
        if event.type == "document.ingested":
            document = event.payload.get("document")
            if isinstance(document, dict) and isinstance(document.get("text"), str):
                return document["text"]
    return None


def align_ids(live: list[dict[str, Any]], comparison: extract_module.Comparison, reference: list[dict[str, Any]]) -> set[str]:
    """Give each matched live claim the id of the recorded claim it matches, so recorded scores
    and verdicts attach to it; number the rest after the recording's highest. Returns the
    recorded ids now carried by live claims."""
    by_live = {m.live_id: m.reference_id for m in comparison.matches}
    numbers = [int(n) for c in reference for n in re.findall(r"\d+", c["id"])[:1]]
    next_number = (max(numbers) if numbers else len(reference)) + 1
    used = {c["id"] for c in reference}
    renamed: dict[str, str] = {}
    for claim in live:
        if claim["id"] in by_live:
            renamed[claim["id"]] = by_live[claim["id"]]
        else:
            while f"C{next_number}" in used:
                next_number += 1
            renamed[claim["id"]] = f"C{next_number}"
            used.add(f"C{next_number}")
            next_number += 1
    for claim in live:
        claim["id"] = renamed[claim["id"]]
    for match in comparison.matches:
        match.live_id = renamed.get(match.live_id, match.live_id)
    comparison.extra = [renamed.get(x, x) for x in comparison.extra]
    return set(by_live.values())


