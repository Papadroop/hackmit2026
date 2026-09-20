"""Live analysis: the pipeline stages plug in here, one at a time (roadmap phase 2).

Every stage of phase 2 is built: `ingest` (step 10), `extract` (11), `language` (12),
`substantiate` (13), `verify` (14), `consistency` (15), `omissions` (16) and `verdict` (17).
A live request reads its text, URL or PDF into a contract Document; Claude decomposes it into
atomic claims; the linguistic evaluator marks how each is worded and scores its Clarity; the
substantiation evaluator matches every claim to the criteria it is measured against and the
precedents on similar wording from the curated stores; external verification searches the web
for the facts, checks every quote against the page it came from, recomputes the numbers and
scores Support and Materiality; the self-consistency evaluator reads the company against its
own filings and against the Wayback Machine's captures of this very page, and scores
Consistency; the omissions stage measures the page against the material topics its industry's
reference names and writes a margin card for each one it leaves out. Each entity is streamed
as it is written.

The verdict layer runs inside the replay rather than after it, because it argues from
everything emitted before it and the summary is still the recording's: `live_verdict` is
called where the recording's own verdict stage would have started. A prosecutor and a defence
argue each claim in two calls that cannot see each other, a judge reads both and decides, and
the likelihood, category and confidence are derived by the contract's rules (CONTRACT.md §6)
from the four dimension scores. A claim some evaluator left unscored on one dimension is left
without a verdict and stays neutral, which is what the contract allows.

Only `summary` (step 18) is still replayed. When a recording exists for the document's URL the
live claims are aligned with the recording's by span overlap, matched claims take the recorded
ids so the recorded summary's targets still resolve, and everything after `extract` replays
with events about unmatched recorded claims dropped and the recording's own version of every
stage that ran live left out. A verdict the replay does still emit — only where the verdict
stage did not run — has its likelihood and category re-derived from the live scores, the
recorded rationale kept. The log says all of this: `mode` is `live`, replayed stages carry a
`note`, and `debug.note` lines report the comparison against the golden reference, which is
each step's visual check. Without a recording there is no summary to replay, so the run stops
at `verdict` with a clear message and everything found so far still shown.
"""

from __future__ import annotations

import asyncio
import copy
import re
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from . import consistency as consistency_module
from . import extract as extract_module
from . import ingest
from . import language as language_module
from . import omissions as omissions_module
from . import substantiate as substantiate_module
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
from .ingest.anchor import AnchorStats, reanchor_payload
from .knowledge import KnowledgeError
from .llm import LlmError
from .store import Analysis
from .verdict import DIMENSIONS, derive_category, derive_likelihood

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
NOT_BUILT = "The document summary is not built yet (roadmap step 18), and the verdict layer runs inside the replay, so without a recording of this page there is nothing to argue each claim against. The claims, their language marks, their criteria and precedents, the evidence retrieved and recomputed for them, what the company says elsewhere and said before, and what the page leaves out are all shown as found; the analysis stops here."
CLAIM_STAGGER_SECONDS = 0.04

# The evaluator stages in the order the contract names them, so a replay can say which of them
# ran live and which the recording still supplies.
STAGE_ORDER = ("ingest", "extract", "language", "substantiate", "verify", "consistency", "omissions", "verdict", "summary")
NEXT_STEP = {
    "extract": "steps 12-17", "language": "steps 13-17", "substantiate": "steps 14-17",
    "verify": "steps 15-17", "consistency": "steps 16-17", "omissions": "step 17", "verdict": "step 18",
}

# The replay's marker for "run the live verdict stage here", put where the recording's own
# verdict stage would have started so the debate follows the evidence it argues from.
LIVE_VERDICT = "!verdict"


class StopReplay(Exception):
    """A stage running inside the replay has already emitted its own `analysis.failed`; the
    replay unwinds without emitting a second terminal event."""

# Called with every score and evidence item that exists by then; returns the verdicts it issued.
LiveVerdict = Callable[[list[dict[str, Any]], list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


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
    try:
        result = await extract_module.extract_claims(document)
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

    # -- language (step 12): every signal and score is emitted as Claude writes it
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

    # -- downstream: the recording, or a clear stop
    if recording is None:
        analysis.emit(STAGE_STARTED, {"stage": "verdict", "label": VERDICT_LABEL})
        analysis.emit(ANALYSIS_FAILED, {"error": NOT_BUILT, "stage": "verdict"})
        return

    # -- verdict (step 17): run inside the replay, after the stages it argues from. All four
    # dimensions are now live, so the debate reads nothing recorded; a claim that is somehow
    # short of one is judged on what exists and says so.
    async def live_verdict(scores: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        analysis.emit(STAGE_STARTED, {"stage": "verdict", "label": VERDICT_LABEL})
        ready, neutral = fully_scored(result.claims, scores)
        if neutral:
            # The contract wants all four dimensions before a verdict (§2, rule 3). Every
            # evaluator is live, so this means one of them placed no score at all for a claim;
            # it stays neutral rather than being decided on three dimensions.
            analysis.emit("debug.note", {"text": f"{len(neutral)} claims are not scored on every dimension and are left without a verdict: {', '.join(neutral[:10])}."})
        try:
            decided = await verdict_module.issue_verdicts(
                document, ready, scores, evidence, review.signals, emit=analysis.emit,
            )
        except LlmError as exc:
            # Every other stage says which stage failed; this one runs inside the replay, so it
            # has to stop the replay itself rather than return to `run_live`.
            analysis.emit(ANALYSIS_FAILED, {"error": f"The verdict layer failed: {exc}", "stage": "verdict"})
            raise StopReplay from exc
        for note in decided.notes:
            analysis.emit("debug.note", {"text": note})
        if recording is not None:
            against = verdict_module.compare_verdicts(decided.verdicts, recorded_verdicts(events))
            analysis.emit("debug.note", {"text": f"Against the recording {name!r} (the golden reference): {against.describe()}."})
        analysis.emit(STAGE_COMPLETED, {"stage": "verdict"})
        return decided.verdicts

    try:
        await replay_downstream(
            analysis, name, events, document, speed=speed, kept_claims=kept_recorded,
            live_claim_ids=[c["id"] for c in result.claims],
            live_scores=[*review.scores, *verification.scores, *against_itself.scores],
            live_stages=("language", "substantiate", "verify", "consistency", "omissions", "verdict"),
            live_signal_count=len(review.signals),
            live_evidence=[*substantiation.evidence, *verification.evidence, *against_itself.evidence, *missing.evidence],
            live_omissions=missing.omissions,
            live_verdict=live_verdict,
        )
    except StopReplay:
        return  # the failing stage already said so, with its own name on it


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


def recorded_omissions(events: list[Event]) -> list[dict[str, Any]]:
    return [e.payload["omission"] for e in events if e.type == "omission.found" and isinstance(e.payload.get("omission"), dict)]


def is_replaced(event: Event, live_stages: tuple[str, ...], live_dimensions: set[str]) -> str | None:
    """The stage whose live run replaces this recorded event, or None to replay it. A stage
    that ran live owns its own stage events, the entities it emits and the dimensions it
    scores; the recording's versions of those are left out."""
    if event.type in (STAGE_STARTED, STAGE_COMPLETED):
        stage = event.payload.get("stage")
        return stage if stage in live_stages else None
    if event.type == "language.signal":
        return "language" if "language" in live_stages else None
    if event.type == "evidence.added":
        stage = (event.payload.get("evidence") or {}).get("stage")
        return stage if stage in live_stages else None
    if event.type == "dimension.scored":
        dimension = (event.payload.get("score") or {}).get("dimension")
        if dimension in live_dimensions:
            return {"clarity": "language", "support": "verify", "materiality": "verify", "consistency": "consistency"}[dimension]
    if event.type in ("argument.made", "verdict.issued"):
        return "verdict" if "verdict" in live_stages else None
    if event.type == "omission.found":
        return "omissions" if "omissions" in live_stages else None
    return None


def rederive_verdict(verdict: dict[str, Any], scores: dict[str, dict[str, Any]], contradicted: set[str]) -> str | None:
    """Apply CONTRACT.md §6 to a recorded verdict whose clarity score is now live: likelihood is
    the weakest link, the category follows the rules, confidence stays within the bounds of the
    dimension confidences. The recorded rationale, tags, fix and rewrite are kept. Returns a
    note when the likelihood or category changed."""
    if any(d not in scores for d in DIMENSIONS):
        return None
    likelihood = derive_likelihood(scores)
    category = derive_category(scores, verdict["claim_id"] in contradicted)
    confidences = [scores[d]["confidence"] for d in DIMENSIONS]
    confidence = round(min(max(verdict["confidence"], max(0.0, min(confidences) - 0.1)), max(confidences)), 2)
    before = (verdict["likelihood"], verdict["category"])
    verdict["likelihood"], verdict["category"], verdict["confidence"] = likelihood, category, confidence
    if before != (likelihood, category):
        return f"{verdict['claim_id']} {before[1]} {before[0]} -> {category} {likelihood}"
    return None


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


async def replay_downstream(
    analysis: Analysis,
    name: str,
    events: list[Event],
    document: dict[str, Any],
    *,
    speed: float,
    kept_claims: set[str],
    live_claim_ids: list[str],
    live_scores: list[dict[str, Any]] | None = None,
    live_stages: tuple[str, ...] = (),
    live_signal_count: int = 0,
    live_evidence: list[dict[str, Any]] | None = None,
    live_omissions: list[dict[str, Any]] | None = None,
    live_verdict: LiveVerdict | None = None,
) -> None:
    """Replay a recording's events after its `extract` stage, spans re-anchored to `document`
    and everything about a recorded claim no live claim took over dropped. `live_stages` names
    the stages that have already run live: their stage events, their evidence and the
    dimensions they scored are left out of the replay, references to the evidence they replace
    are stripped from the recorded scores and verdicts, and every recorded verdict the replay
    still emits is re-derived (CONTRACT.md §6) from the live scores and whatever dimensions the
    recording supplies.

    `live_verdict` runs the verdict stage (step 17) where the recording's own verdict stage
    would have started, with every score and evidence item emitted up to that point, live or
    replayed. It replaces the recorded arguments and verdicts, so `live_stages` must name
    `verdict` for them to be left out."""
    old_text = recorded_text(events)
    live_scores = live_scores or []
    live_evidence = live_evidence or []
    live_omissions = live_omissions or []
    live_dimensions = {s["dimension"] for s in live_scores}
    # A recorded omission the live stage replaced is not a target any more, so the recorded
    # evidence gathered for it, and the summary lines that name it, go with it.
    replaced_omissions = {o["id"] for o in recorded_omissions(events)} if "omissions" in live_stages else set()
    start_index = next((i + 1 for i, e in enumerate(events) if e.type == STAGE_COMPLETED and e.payload.get("stage") == "extract"), None)
    if start_index is None or start_index >= len(events):
        # Everything up to `omissions` has already run live; the recording was only ever needed
        # for the summary, so that is the stage this fails at.
        analysis.emit(STAGE_STARTED, {"stage": "summary", "label": SUMMARY_LABEL})
        analysis.emit(ANALYSIS_FAILED, {"error": f"Recording {name!r} has nothing after its extract stage", "stage": "summary"})
        return
    stats = AnchorStats()
    targets = set(kept_claims)
    dropped_evidence: set[str] = set()
    counts: Counter[str] = Counter()
    prepared: list[tuple[int, str, dict[str, Any]]] = []
    scores: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for score in live_scores:
        scores[score["claim_id"]][score["dimension"]] = score
    contradicted = {l["target"] for e in live_evidence for l in e.get("links", []) if l.get("relation") == "contradicts"}
    changed: list[str] = []
    replaced: Counter[str] = Counter()
    for event in events[start_index:]:
        stage = is_replaced(event, live_stages, live_dimensions)
        if stage is not None:
            replaced[stage] += 1
            if event.type == "evidence.added":
                dropped_evidence.add(event.payload["evidence"]["id"])
            if stage == "verdict" and event.type == STAGE_STARTED and live_verdict is not None:
                prepared.append((event.t_ms, LIVE_VERDICT, {}))
            continue
        payload = filter_payload(event.type, event.payload, targets, dropped_evidence, document["text"], old_text, stats, replaced_omissions)
        if payload is None:
            continue
        if event.type == STAGE_STARTED:
            payload["note"] = f"Replayed from recording {name}; this stage is not built yet"
        if event.type == "omission.found":
            targets.add(payload["omission"]["id"])
        if event.type == "dimension.scored":
            scores[payload["score"]["claim_id"]][payload["score"]["dimension"]] = payload["score"]
        if event.type == "evidence.added":
            contradicted.update(l["target"] for l in payload["evidence"].get("links", []) if l.get("relation") == "contradicts")
        if event.type == "verdict.issued" and live_scores:
            note = rederive_verdict(payload["verdict"], scores.get(payload["verdict"]["claim_id"], {}), contradicted)
            if note:
                changed.append(note)
        counts[event.type] += 1
        prepared.append((event.t_ms, event.type, payload))
    sentinels = sum(1 for _, type_, _ in prepared if type_ == LIVE_VERDICT)
    dropped_total = (len(events) - start_index) - (len(prepared) - sentinels) - sum(replaced.values())
    last_live = max([*live_stages, "extract"], key=STAGE_ORDER.index)
    text = (
        f"Stages after {last_live} are replayed from recording {name!r}, pending roadmap {NEXT_STEP[last_live]}. "
        f"{stats.describe()}; {dropped_total} recorded events about claims the live extraction did not find were dropped"
    )
    if replaced:
        parts = [f"{n} {stage}-stage" for stage, n in sorted(replaced.items(), key=lambda kv: STAGE_ORDER.index(kv[0]))]
        text += f"; the recording's {english_list(parts)} events are replaced by the live ones"
    if live_scores and live_verdict is None:
        # With the verdict stage live there are no recorded verdicts left to re-derive.
        dimensions = english_list([d for d in DIMENSIONS if d in live_dimensions])
        text += f". Verdicts re-derived from the live {dimensions} scores (contract §6): {len(changed)} changed" + (": " + "; ".join(changed[:8]) if changed else "")
    analysis.emit("debug.note", {"text": text + "."})
    loop = asyncio.get_running_loop()
    origin = loop.time()
    t0 = events[start_index - 1].t_ms
    # What the verdict stage argues from: everything live, plus everything the replay has
    # emitted by the time it runs. The recorded consistency scores are in here.
    so_far_scores, so_far_evidence = list(live_scores), list(live_evidence)
    decided: list[dict[str, Any]] = []
    for t_ms, type_, payload in prepared:
        delay = origin + (t_ms - t0) / 1000 / speed - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        if type_ == LIVE_VERDICT:
            decided = await live_verdict(so_far_scores, so_far_evidence)  # type: ignore[misc]
            continue
        if type_ == "dimension.scored":
            so_far_scores.append(payload["score"])
        if type_ == "evidence.added":
            so_far_evidence.append(payload["evidence"])
        if type_ == "summary.updated":
            payload = fix_summary(payload, live_claim_ids, prepared, live_scores, decided, live_omissions)
        if type_ == ANALYSIS_COMPLETED:
            payload = dict(payload)
            payload.pop("duration_ms", None)
            payload["counts"] = {
                "claims": len(live_claim_ids),
                "signals": counts["language.signal"] + live_signal_count,
                "evidence": counts["evidence.added"] + len(live_evidence),
                "omissions": counts["omission.found"] + len(live_omissions),
            }
        analysis.emit(type_, payload)


def english_list(parts: list[str]) -> str:
    """"a", "a and b", "a, b and c"."""
    if len(parts) < 3:
        return " and ".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def filter_payload(
    type_: str,
    payload: dict[str, Any],
    targets: set[str],
    dropped_evidence: set[str],
    text: str,
    old_text: str | None,
    stats: AnchorStats,
    replaced_omissions: set[str],
) -> dict[str, Any] | None:
    """A copy of a recorded payload with references to dropped claims and evidence removed, or
    None when the event is about a dropped claim. `targets` holds the ids that exist so far;
    `replaced_omissions` the recorded omissions a live stage has taken over."""
    if type_ == "claim.extracted":
        return None
    if type_ == "language.signal":
        payload = reanchor_payload(payload, text, old_text, stats)
        signal = payload["signal"]
        claim_ids = [c for c in signal.get("claim_ids", []) if c in targets]
        if signal.get("claim_ids") and not claim_ids:
            return None
        signal["claim_ids"] = claim_ids
        return payload
    payload = copy.deepcopy(payload)
    if type_ == "evidence.added":
        item = payload["evidence"]
        # Omissions come later than the evaluators, so a link to an omission the live stage has
        # not replaced stays, even though that omission does not exist yet.
        links = [
            l for l in item.get("links", [])
            if l["target"] not in replaced_omissions and (l["target"] in targets or not l["target"].startswith("C"))
        ]
        if not links:
            dropped_evidence.add(item["id"])
            return None
        item["links"] = links
        item["derived_from"] = [d for d in item.get("derived_from", []) if d not in dropped_evidence] or None
        if item["derived_from"] is None:
            item.pop("derived_from")
        return payload
    if type_ == "dimension.scored":
        score = payload["score"]
        if score.get("claim_id") not in targets:
            return None
        _strip_evidence(score, dropped_evidence)
        return payload
    if type_ in ("argument.made", "verdict.issued"):
        entity = payload.get("argument") or payload.get("verdict")
        if entity.get("claim_id") not in targets:
            return None
        _strip_evidence(entity, dropped_evidence)
        return payload
    if type_ == "omission.found":
        _strip_evidence(payload["omission"], dropped_evidence)
        return payload
    if type_ == "summary.updated":
        summary = payload["summary"]
        summary["top_issues"] = [dict(x, rank=i + 1) for i, x in enumerate(x for x in summary.get("top_issues", []) if x["target"] in targets)]
        summary["credit"] = [x for x in summary.get("credit", []) if x["target"] in targets]
        return payload
    return payload


def _strip_evidence(entity: dict[str, Any], dropped: set[str]) -> None:
    if "evidence_ids" in entity:
        entity["evidence_ids"] = [e for e in entity["evidence_ids"] if e not in dropped]


def fix_summary(
    payload: dict[str, Any],
    live_claim_ids: list[str],
    prepared: list[tuple[int, str, dict[str, Any]]],
    live_scores: list[dict[str, Any]] | None = None,
    live_verdicts: list[dict[str, Any]] | None = None,
    live_omissions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The recording's summary with its counts made true for this run: claims as extracted
    live, the verdict distribution as decided live or replayed and re-derived, and every
    dimension that was scored live as the mean of those scores (step 18 owns the real
    aggregation)."""
    payload = copy.deepcopy(payload)
    summary = payload["summary"]
    distribution: Counter[str] = Counter()
    if live_verdicts:
        distribution.update(v["category"] for v in live_verdicts)
    for _, type_, p in prepared:
        if type_ == "verdict.issued" and not live_verdicts:
            distribution[p["verdict"]["category"]] += 1
    summary["verdict_distribution"] = {k: distribution.get(k, 0) for k in summary.get("verdict_distribution", {})} or dict(distribution)
    summary["claim_count"] = len(live_claim_ids)
    summary["omission_count"] = sum(1 for _, t, _ in prepared if t == "omission.found") + len(live_omissions or [])
    by_dimension: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for score in live_scores or []:
        by_dimension[score["dimension"]].append(score)
    dimensions = summary.get("dimensions")
    if isinstance(dimensions, dict):
        for dimension, scores in by_dimension.items():
            if dimension in dimensions and scores:
                dimensions[dimension] = {
                    "score": round(sum(s["score"] for s in scores) / len(scores), 2),
                    "confidence": round(sum(s["confidence"] for s in scores) / len(scores), 2),
                }
    return payload
