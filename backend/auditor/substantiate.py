"""Substantiation evaluator (roadmap step 13; design-doc D5 "Substantiation" and D6 Support):
does each claim meet the criteria for its term, and has similar wording been ruled on?

Two curated stores (`knowledge/`, loaded by `auditor.knowledge`) supply the evidence: the
substantiation criteria drawn from regulator guidance and law, and the precedents, past
rulings on environmental claims. Claude reads the document (the cached prefix every stage
sends), the claims, and the index of both stores, and does two things in parallel:

1. Matching, one call at low effort: which criteria each claim is measured against and which
   rulings concern similar wording or the same company. Every match is emitted the moment it
   closes in the stream as an `evidence.added` item with relation `criteria` or `precedent`,
   so the claim panel fills with rules and rulings while the scoring is still thinking.
2. Scoring, in parallel batches at medium effort: a Support score per claim from the criteria
   and precedents alone, with the evidence it relied on and the gap the text would have to
   close. Scores are emitted as they close, after the matching call has finished, so every
   evidence item exists before a score cites it (contract §2, rule 3). An item the scorer
   cites that the matcher did not is emitted then, linked to that claim.

Support here is a problem score on what the text shows against what its criteria require, and
it is capped accordingly: only evidence about the facts can go higher. In the pipeline the
scoring is off (`score=False`) and external verification (step 14) scores Support once, from
these criteria and precedents and the facts it retrieves together, because the contract allows
one score per claim per dimension and that is the dimension's definition (D6). The scoring
here stays for `--no-score`'s opposite: measuring what the stores alone can settle. A claim
the model skips gets a neutral placeholder at low confidence. A precedent that adjudicated the
very page under analysis is held out (demo-documents.md §6).

    python -m auditor.substantiate <file or url> [--golden fixtures/shell-climate.analysis.json] [--no-score] [--json]

With `--golden`, the reference's own claims are the input and the result is compared with the
reference's support scores and its criteria and precedent links.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .documents import normalise_url
from .extract import document_system
from .knowledge import Knowledge, StoreEntry, get_knowledge
from .language import claims_listing, clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm


class Match(BaseModel):
    evidence_id: str = Field(description="An id from the index (K3, P5).")
    claim_ids: list[str] = Field(description="The claims this rule or ruling bears on, by id from the list.")
    note: str = Field(description="One sentence: what in these claims' wording or type the rule or ruling speaks to.")


class Matches(BaseModel):
    matches: list[Match] = Field(description="One entry per store item that bears on at least one claim, in the index's order; nothing for items that bear on none.")


class Assessment(BaseModel):
    claim_id: str
    criteria_ids: list[str] = Field(default_factory=list, description="The criteria (K ids) the score rests on.")
    precedent_ids: list[str] = Field(default_factory=list, description="The precedents (P ids) the score rests on.")
    score: float = Field(description="The Support problem score, 0 to 1, from the bands in the task.")
    confidence: float = Field(description="0 to 1: how far the criteria and precedents settle the question.")
    basis: str = Field(description="One sentence: what the claim shows against what its criteria require, naming the rule or ruling that decides it.")
    gap: str = Field(default="", description="What the text would have to show for the claim to meet its criteria, in one sentence; empty when it already does.")


class Assessments(BaseModel):
    assessments: list[Assessment] = Field(description="Exactly one entry per claim under review, in the list's order.")


MATCH_TASK = """Match each claim to the substantiation criteria it is measured against and to the precedents on similar wording (the audit's question: does the claim meet the criteria for its term, and has similar wording been ruled on?).

Below are the claims found in the document, each with its id, type, scope, paragraph, prominence and words, and then the index of the two knowledge stores: criteria (rules from regulators and standards, id K1, K2, ...) and precedents (rulings on environmental claims, id P1, P2, ...).

A criterion applies to a claim when the claim uses a term the rule governs (the rule's terms list, or a close variant) or is of a claim type the rule governs and the rule's substance is what a regulator would test the claim against. Claim types route the choice: a commitment is measured against the rules for targets and future performance; a comparative against the comparison rules; a certification, label, award or validation against the label and certification rules; a vague attribute against the generic-term rules; a factual claim against the rule for its subject (offsets, renewable electricity, recycled content, scope) when there is one.

A precedent applies to a claim when the wording ruled on is the same claim family as the claim's wording: an offset-based neutrality claim, a net-zero target with or without a plan, a generic term, a comparative with no baseline, a 'sustainable' absolute, a recyclable or recycled-content figure, a transition message from a fossil-fuel company. A ruling against the same company on any environmental claim applies to that company's claims of the same kind. Do not cite a precedent merely because the industry matches; the wording must resemble.

Return `matches`: one entry per store item that bears on at least one claim, with the claims it bears on and one sentence saying what in their wording it speaks to. Most claims have one to three criteria and none to two precedents; a store item may be cited for many claims. Cite only ids from the index and only claim ids from the list. Leave out an item that bears on no claim."""

SCORE_TASK = """Score each claim's Support from the substantiation criteria and the precedents alone (the audit's Support dimension, at the substantiation stage: no other evidence is available yet; external verification of the facts comes later).

Below are the claims to score, each with its id, type, scope, paragraph, prominence and words, and then the index of the two knowledge stores: criteria (rules from regulators and standards, id K1, K2, ...) and precedents (rulings on environmental claims, id P1, P2, ...). Read the whole document: what a claim shows may sit in a footnote, a definition or a neighbouring sentence.

For each claim, decide what its criteria require it to show (a baseline and scope for a reduction; a plan, interim milestones and what is in scope for a target; the basis for a comparison; the scheme and its independence for a label; whether offsets are used and which for a neutrality claim; the mechanism and boundary for renewable electricity) and whether the text shows it. Then ask whether a precedent found the same form of claim misleading, or cleared it.

Support is a problem score, 0 to 1. Bands:
- 0.1 to 0.2: the text gives what the criteria require, or the claim is a plain description of a practice or a definition that a rule does not test, and no precedent counts against it.
- 0.3 to 0.4: the claim meets its criteria in substance with a gap a reader could close from the page (a baseline stated in a nearby sentence, a term defined in a note, a scheme named elsewhere on the page).
- 0.4 to 0.6, with confidence below 0.6: the criteria require substantiation the text does not give and the stores cannot settle it either way; nothing found. Most unquantified factual claims and most commitments with no plan shown land here.
- 0.6 to 0.7: the claim's form is one the criteria say must carry a disclosure the text omits (an offset-based neutrality claim that does not say offsets are used, a generic term with no explanation, a net-zero target with no plan or milestone, a comparative with no baseline) and a precedent found that form misleading.
- 0.7 to 0.85, with confidence 0.6 or more: a ruling found the same wording misleading for the same company, or a criterion that applies bans the claim's form outright and the claim is of that kind.
Never score above 0.85 from criteria and precedents alone: only evidence about the facts can go higher.

Confidence, 0 to 1, is how far the stores settle the question: 0.3 to 0.5 when they are silent on the claim's substance; 0.6 to 0.8 when a rule or ruling speaks to the wording directly; 0.9 only for the same wording and the same company.

Return `assessments`: one entry per claim in the list, none twice, in the list's order, each with the criteria and precedent ids it rests on (only ids from the index; one to three criteria, none to two precedents), the score, the confidence, a one-sentence basis naming the rule or ruling that decides it, and `gap`: one sentence on what the text would have to show to meet its criteria, empty when it already does.

Rules:
- Judge substantiation, not wording and not truth. How clear the words are is scored elsewhere; whether the numbers are right is checked later. Here the question is whether the text shows what a claim of this kind must show.
- A precedent against the same company on the same kind of claim weighs heavily; one against another company shows what regulators test, no more.
- A cleared precedent (not upheld, dismissed) counts in a claim's favour when the claim has the feature that got the other one cleared (the investment split stated, the scope limited to one project).
- Credit where due: a figure with its baseline, scope and date, a named standard, a disclosed offset scheme, a validated target, all score low. A page with only high scores was read badly."""

MATCH_MAX_OUTPUT_TOKENS = 12000
SCORE_MAX_OUTPUT_TOKENS = 16000

# Claims per scoring call; the matcher reads all claims in one call.
BATCH_SIZE = int(os.environ.get("AUDITOR_SUBSTANTIATE_BATCH", "9"))

# Matching is a lookup with judgment, so it runs at low effort and answers first; scoring
# reasons over the rules and runs at medium, like the other per-claim stages.
MATCH_EFFORT = os.environ.get("AUDITOR_SUBSTANTIATE_MATCH_EFFORT", "low")
SCORE_EFFORT = os.environ.get("AUDITOR_SUBSTANTIATE_EFFORT", "medium")

PLACEHOLDER_BASIS = "Not assessed by the substantiation evaluator; neutral placeholder."

Emit = Callable[[str, dict[str, Any]], Any]


# ----------------------------------------------------------------------------- what the model sees


def match_prompt(claims: list[dict[str, Any]], knowledge: Knowledge) -> str:
    return f"{MATCH_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<knowledge>\n{knowledge.listing()}\n</knowledge>"


def score_prompt(claims: list[dict[str, Any]], knowledge: Knowledge, batch: list[dict[str, Any]] | None = None) -> str:
    listing = claims_listing(claims)
    review = ""
    if batch is not None and len(batch) < len(claims):
        ids = ", ".join(c["id"] for c in batch)
        review = f"\n\n<review>\nIn this call, score only these claims: {ids}. The other claims are listed for context; return no assessment for them.\n</review>"
    return f"{SCORE_TASK}\n\n<claims>\n{listing}\n</claims>\n\n<knowledge>\n{knowledge.listing()}\n</knowledge>{review}"


# ----------------------------------------------------------------------------- assembly


@dataclass
class SubstantiationResult:
    evidence: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    held_out: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


class Assembler:
    """Turns matches and assessments into contract entities one at a time, emitting each as it
    is built, so the stream and the batch path share one code path."""

    def __init__(self, claims: list[dict[str, Any]], knowledge: Knowledge, emit: Emit | None = None, *, emit_scores: bool = True) -> None:
        self.claims = {c["id"]: c for c in claims}
        self.order = [c["id"] for c in claims]
        self.knowledge = knowledge
        self.ids: dict[str, StoreEntry] = knowledge.ids()
        self.emit = emit
        self.emit_scores = emit_scores
        self.evidence: list[dict[str, Any]] = []
        self.emitted: dict[str, dict[str, Any]] = {}
        self.scores: list[dict[str, Any]] = []
        self.scored: set[str] = set()
        self.unknown_ids = 0
        self.unknown_claims = 0
        self.repeated = 0
        self.late: list[str] = []
        self.placeholders: list[str] = []

    @staticmethod
    def relation_for(entry: StoreEntry) -> str:
        return "criteria" if entry.store == "criteria" else "precedent"

    def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.emit is not None:
            self.emit(type_, payload)

    def _emit_evidence(self, evidence_id: str, claim_ids: list[str], note: str | None = None) -> dict[str, Any]:
        entry = self.ids[evidence_id]
        links = [{"target": cid, "relation": self.relation_for(entry)} for cid in claim_ids]
        item = entry.as_evidence(evidence_id, links)
        if note:
            item["ext"]["match_note"] = note
        self.emitted[evidence_id] = item
        self.evidence.append(item)
        self._emit("evidence.added", {"evidence": item})
        return item

    def add_match(self, match: Match) -> dict[str, Any] | None:
        if match.evidence_id not in self.ids:
            self.unknown_ids += 1
            return None
        claim_ids: list[str] = []
        for cid in match.claim_ids:
            if cid in self.claims and cid not in claim_ids:
                claim_ids.append(cid)
            elif cid not in self.claims:
                self.unknown_claims += 1
        if not claim_ids:
            return None
        if match.evidence_id in self.emitted:
            # The contract allows one event per evidence id; a second match for the same item
            # cannot add links. The scorer's citations still reach the panel as "cited".
            self.repeated += 1
            return None
        return self._emit_evidence(match.evidence_id, claim_ids, match.note.strip() or None)

    def add_assessment(self, item: Assessment) -> dict[str, Any] | None:
        if item.claim_id not in self.claims:
            self.unknown_claims += 1
            return None
        if item.claim_id in self.scored:
            self.repeated += 1
            return None
        cited: list[str] = []
        for eid in [*item.criteria_ids, *item.precedent_ids]:
            if eid not in self.ids:
                self.unknown_ids += 1
            elif eid not in cited:
                cited.append(eid)
        for eid in cited:
            if eid not in self.emitted:
                # Cited by the scorer only: it exists from here on, linked to this claim.
                self.late.append(eid)
                self._emit_evidence(eid, [item.claim_id])
        score: dict[str, Any] = {
            "claim_id": item.claim_id,
            "dimension": "support",
            "score": clamp01(item.score),
            "confidence": clamp01(item.confidence),
            "basis": item.basis.strip() or "No basis given.",
            "stage": "substantiate",
        }
        if cited:
            score["evidence_ids"] = cited
        if item.gap.strip():
            score["ext"] = {"gap": item.gap.strip()}
        self.scored.add(item.claim_id)
        self.scores.append(score)
        if self.emit_scores:
            self._emit("dimension.scored", {"score": score})
        return score

    def finish(self) -> SubstantiationResult:
        if self.emit_scores:
            for cid in self.order:
                if cid not in self.scored:
                    self.placeholders.append(cid)
                    self.add_assessment(Assessment(claim_id=cid, score=0.5, confidence=0.2, basis=PLACEHOLDER_BASIS))
        result = SubstantiationResult(self.evidence, self.scores, list(self.knowledge.held_out), self.placeholders)
        criteria = sum(1 for e in self.evidence if e["ext"]["store"] == "criteria")
        linked = {l["target"] for e in self.evidence for l in e["links"]}
        result.notes.append(
            f"{len(self.evidence)} store items cited ({criteria} criteria, {len(self.evidence) - criteria} precedents) for {len(linked)} of {len(self.order)} claims"
            + (f"; {len(self.late)} cited by the scorer only" if self.late else "")
            + (f"; {self.repeated} repeated matches or scores ignored" if self.repeated else "")
            + (f"; {self.unknown_ids} unknown store ids ignored" if self.unknown_ids else "")
            + (f"; {self.unknown_claims} unknown claim ids ignored" if self.unknown_claims else "")
        )
        if self.emit_scores and self.placeholders:
            result.notes.append(f"Placeholder support score for {len(self.placeholders)} claims the model did not assess: {', '.join(self.placeholders[:10])}")
        if self.knowledge.held_out:
            result.notes.append(f"Held out: {', '.join(self.knowledge.held_out)} (adjudicated this very document)")
        return result


def apply_substantiation(
    matches: Matches,
    assessments: Assessments,
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    knowledge: Knowledge | None = None,
    emit: Emit | None = None,
    *,
    score: bool = True,
) -> SubstantiationResult:
    """The batch path: whole results at once (tests and fakes), matches first, then scores."""
    knowledge = (knowledge or get_knowledge()).for_document((document.get("source") or {}).get("url"))
    assembler = Assembler(claims, knowledge, emit, emit_scores=score)
    for match in matches.matches:
        assembler.add_match(match)
    if score:
        for item in assessments.assessments:
            assembler.add_assessment(item)
    return assembler.finish()


async def substantiate(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    emit: Emit | None = None,
    llm: Llm | None = None,
    knowledge: Knowledge | None = None,
    score: bool = True,
) -> SubstantiationResult:
    """Run the evaluator on an ingested document and its claims, emitting each evidence item
    and score as it arrives. With `score=False` only the matching runs, which is what the
    pipeline asks for now that external verification (step 14) scores Support from the rules
    and the facts together. Raises LlmError when Claude cannot answer."""
    knowledge = (knowledge or get_knowledge()).for_document((document.get("source") or {}).get("url"))
    if not claims:
        return SubstantiationResult([], [], list(knowledge.held_out), notes=["No claims to substantiate."])
    llm = llm or get_llm()
    assembler = Assembler(claims, knowledge, emit, emit_scores=score)
    system = document_system(document)
    size = max(1, BATCH_SIZE)
    batches = [claims[i : i + size] for i in range(0, len(claims), size)] if score else []
    started = time.perf_counter()
    usages: list[Usage] = []
    returned = {"matches": 0, "assessments": 0, "invalid": 0, "out_of_batch": 0}
    matched = asyncio.Event()
    first: list[float] = []

    async def run_matcher() -> None:
        handed = 0

        async def on_element(key: str, item: dict[str, Any]) -> None:
            nonlocal handed
            if key != "matches":
                return
            handed += 1
            try:
                if assembler.add_match(Match.model_validate(item)) and not first:
                    first.append(time.perf_counter() - started)
            except ValidationError:
                returned["invalid"] += 1

        try:
            result, usage = await llm.extract_streaming(
                match_prompt(claims, knowledge), Matches, on_element=on_element,
                system=system, cache=True, max_tokens=MATCH_MAX_OUTPUT_TOKENS, effort=MATCH_EFFORT,
            )
            for match in result.matches[handed:]:
                assembler.add_match(match)
            returned["matches"] += len(result.matches)
            usages.append(usage)
        finally:
            matched.set()

    async def run_batch(batch: list[dict[str, Any]]) -> None:
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
                returned["invalid"] += 1
                return
            if assessment.claim_id not in ids:
                returned["out_of_batch"] += 1
                return
            await matched.wait()  # every evidence item exists before a score cites it
            assembler.add_assessment(assessment)

        result, usage = await llm.extract_streaming(
            score_prompt(claims, knowledge, batch=batch), Assessments, on_element=on_element,
            system=system, cache=True, max_tokens=SCORE_MAX_OUTPUT_TOKENS, effort=SCORE_EFFORT,
        )
        await matched.wait()
        for assessment in result.assessments[handed:]:
            if assessment.claim_id in ids:
                assembler.add_assessment(assessment)
        returned["assessments"] += len(result.assessments)
        usages.append(usage)

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(run_matcher())
            for batch in batches:
                group.create_task(run_batch(batch))
    except* LlmError as errors:
        raise errors.exceptions[0]
    result = assembler.finish()
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = f"Claude matched {returned['matches']} store items in one call"
    if first:
        note += f" (first item after {first[0]:.1f} s)"
    if score:
        note += f" and scored {returned['assessments']} claims over {len(batches)} parallel calls of up to {size} claims"
    else:
        note += "; Support is not scored here, because external verification (step 14) scores it from the rules and the facts together"
    if returned["invalid"]:
        note += f", {returned['invalid']} malformed"
    if returned["out_of_batch"]:
        note += f", {returned['out_of_batch']} assessments for claims outside their call ignored"
    result.notes.insert(0, note + f" ({result.usage.describe()})")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class SupportComparison:
    pairs: list[tuple[str, float, float]]
    unscored: list[str]

    @property
    def mean_abs_error(self) -> float:
        return sum(abs(a - b) for _, a, b in self.pairs) / len(self.pairs) if self.pairs else 0.0

    def wrong_band(self) -> list[str]:
        """Claims where live and reference disagree on whether Support is above 0.6 (the
        line above which a claim's form counts against it)."""
        return [cid for cid, live, ref in self.pairs if (live > 0.6) != (ref > 0.6)]

    def describe(self) -> str:
        text = f"support scored for {len(self.pairs)} reference claims, mean absolute difference {self.mean_abs_error:.2f}, {len(self.wrong_band())} on the other side of 0.6"
        if self.unscored:
            text += f", {len(self.unscored)} reference claims unscored"
        return text


def compare_support(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> SupportComparison:
    """Live support scores against a reference's, by claim id."""
    live_by = {s["claim_id"]: s for s in live if s.get("dimension") == "support"}
    pairs, unscored = [], []
    for ref in reference:
        if ref.get("dimension") != "support":
            continue
        got = live_by.get(ref["claim_id"])
        if got is None:
            unscored.append(ref["claim_id"])
        else:
            pairs.append((ref["claim_id"], float(got["score"]), float(ref["score"])))
    return SupportComparison(pairs, unscored)


@dataclass
class LinkComparison:
    """For each (claim, relation) the reference's substantiate-stage evidence links, whether
    the live run linked the same source, or any source, with that relation."""

    reference: int
    same_source: int
    any_source: int
    live_links: int
    missed: list[str]

    def describe(self) -> str:
        return (
            f"{self.any_source} of {self.reference} reference criteria and precedent links found ({self.same_source} from the same source); "
            f"{self.live_links} live links in all"
        )


def compare_links(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> LinkComparison:
    def links_of(items: list[dict[str, Any]], relations: set[str]) -> dict[tuple[str, str], set[str]]:
        out: dict[tuple[str, str], set[str]] = {}
        for item in items:
            if item.get("stage") not in (None, "substantiate"):
                continue
            url = normalise_url(item["url"]) if item.get("url") else ""
            for link in item.get("links", []):
                if link["relation"] in relations and link["target"].startswith("C"):
                    out.setdefault((link["target"], link["relation"]), set()).add(url)
        return out

    relations = {"criteria", "precedent"}
    ref = links_of(reference, relations)
    got = links_of(live, relations)
    same = sum(1 for key, urls in ref.items() if key in got and urls & got[key])
    any_ = sum(1 for key in ref if key in got)
    missed = sorted(f"{cid} {rel}" for (cid, rel) in ref if (cid, rel) not in got)
    live_links = sum(len(item.get("links", [])) for item in live)
    return LinkComparison(len(ref), same, any_, live_links, missed)


# ----------------------------------------------------------------------------- command line


def _print_evidence(item: dict[str, Any]) -> None:
    targets = ",".join(l["target"] for l in item["links"])
    print(f"{item['id']:>4}  {item['links'][0]['relation']:<9} tier {item['tier']} {targets:<24} {item['source']['name'][:80]}")


async def _main(args: argparse.Namespace) -> int:
    from .extract import extract_claims
    from .ingest import IngestError, ingest_file, ingest_url
    from .language import reanchored_claims

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
            for note in extracted.notes:
                print(f"note: {note}", file=sys.stderr)
            claims = extracted.claims

        def emit(type_: str, payload: dict[str, Any]) -> None:
            if args.json:
                return
            if type_ == "evidence.added":
                _print_evidence(payload["evidence"])
            else:
                s = payload["score"]
                gap = (s.get("ext") or {}).get("gap", "")
                print(f"{s['claim_id']:>4}  support {s['score']:<5} confidence {s['confidence']:<5} [{','.join(s.get('evidence_ids', []))}] {s['basis'][:110]}" + (f"\n      gap: {gap[:120]}" if gap else ""))

        result = await substantiate(document, claims, emit=emit, score=not args.no_score)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps({"evidence": result.evidence, "scores": result.scores}, ensure_ascii=False, indent=2))
    if analysis is not None:
        links = compare_links(result.evidence, analysis["evidence"])
        print(f"\nagainst {Path(args.golden).name}: {links.describe()}")
        for miss in links.missed:
            print(f"  missed {miss}")
        if result.scores:
            support = compare_support(result.scores, analysis["scores"])
            print(support.describe())
            for cid, live, ref in support.pairs:
                flag = "  <-- other side of 0.6" if (live > 0.6) != (ref > 0.6) else ""
                print(f"  {cid:>4} live {live:<5} reference {ref:<5} diff {live - ref:+.2f}{flag}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.substantiate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims are the input and its support scores and links the reference")
    parser.add_argument("--no-score", action="store_true", help="only match criteria and precedents; do not score Support")
    parser.add_argument("--json", action="store_true", help="print the evidence and scores as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
