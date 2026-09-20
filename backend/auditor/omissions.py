"""Omissions (roadmap step 16; design-doc D4 Q3 and D6 Completeness): what is material for the
company's industry and absent from the text — the "hidden trade-off", an airline talking about
recycled cups.

"Absent" means nothing on its own, so it is always absent *from a list*. The list is the
materiality reference (`auditor.materiality`, `knowledge/materiality.json`): one entry per
industry, an external standard naming the disclosure topics that industry is read against. The
document declares its industry in the contract's `Document.industry`; when it declares one the
store does not know, the model places it among the store's industries in a small call first, and
the choice is written to the log. Every document is also measured against the cross-industry
entry, so a page whose industry is unknown still has a list.

Then one call: the model reads the document (the cached prefix every stage sends), the claims,
the evidence the earlier evaluators have already put on the table, and the topic list, and
says for each topic whether the page addresses it, with a verbatim quote — either the words
that address it, or the nearest the page comes. Where it does not, it writes the margin card:
the topic, why it is material for this company, what the page would say if it were complete,
and how serious the omission is.

Two checks stand between that and a margin card, because "not mentioned" is a claim about the
text and has to be falsifiable (step 16's visual check is "a material topic that is truly
absent from the document"):

1. **Every quote is placed in the document.** A quote the model attributes to the page is located
   in it (`extract.locate`, the anchoring the claims use). One that is not there is dropped and
   the run says so; it never reaches a card.
2. **The reference's own words are looked for.** Each topic carries `terms`, the words that
   appear when a page does address it. A card whose topic has terms in the text and no nearest
   quote to explain them is marked and loses confidence; a card whose terms are all absent
   carries that in `ext.absence`, which is what makes it checkable by hand.

An omission cites the reference that makes its topic material (relation `criteria`, the
fixture's E16) and any evidence already retrieved that establishes the omitted fact. The
document-level Completeness score is returned, not emitted: the contract has no event for it
until the summary, and step 18 owns the aggregation.

    python -m auditor.omissions <file or url> [--golden fixtures/shell-climate.analysis.json] [--json]

With `--golden`, the reference's own claims and evidence are the input and the result is
compared with the reference's omissions.
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
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .extract import document_system, locate
from .knowledge import KnowledgeError
from .language import claims_listing, clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm
from .materiality import Match, Materiality, get_materiality, mentions

Emit = Callable[[str, dict[str, Any]], Any]


class Placement(BaseModel):
    sasb_code: str = Field(description="The SASB code of the industry from the list, or an empty string when none of them fits.")
    industry: str = Field(default="", description="The industry as you would name it, in three or four words.")
    confidence: float = Field(default=0.5, description="0 to 1: how sure you are that this company belongs to that industry.")
    basis: str = Field(default="", description="One sentence: what in the document places it there.")


class Coverage(BaseModel):
    topic_id: str = Field(description="A topic id from the list (M2.3).")
    addressed: Literal["yes", "partly", "no"] = Field(description="Whether the document addresses this topic.")
    nearest: str = Field(default="", description="Words copied from the document, character for character: what addresses the topic, or the nearest the page comes to it. Empty only when the page says nothing on the subject at all.")
    topic: str = Field(default="", description="The margin card's title when the topic is not addressed: what is not mentioned, in a few words.")
    why_material: str = Field(default="", description="Why this topic decides whether this company's environmental story is honest, in one or two sentences naming what the page does instead.")
    complete_text: str = Field(default="", description="One sentence the document would contain if it addressed the topic, written as the company would write it.")
    evidence_ids: list[str] = Field(default_factory=list, description="Ids from the evidence list that establish the omitted fact; empty when none of it does.")
    score: float = Field(default=0.0, description="0 to 1, from the bands in the task: how serious the omission is.")
    confidence: float = Field(default=0.0, description="0 to 1: how sure you are that the topic is material here and the page does not address it.")


class Coverages(BaseModel):
    coverage: list[Coverage] = Field(description="Exactly one entry per topic in the list, in the list's order.")


PLACE_TASK = """Place this company in one of the industries below (the audit needs to know which industry's material impacts to measure the document against).

Each line is a SASB industry code, the industry, and words associated with it. Choose by what the company mainly does, not by what this document is about: a company that makes devices is technology hardware even when the document is about its forests.

Return the code of the industry that fits, your confidence, and one sentence saying what in the document places it there. If none of them fits, return an empty code: the document will be measured against the cross-industry topics alone, which is better than the wrong industry."""

COVERAGE_TASK = """Decide, topic by topic, what this document leaves out (the audit's question D4 Q3: which impacts are material for this company's industry and unaddressed in the text, the "hidden trade-off" — an airline talking about recycled cups).

Below are the claims found in the document, the evidence the earlier evaluators have already gathered, and the material topics for this company's industry, taken from an external reference. Read the whole document, footnotes and cautionary notes included.

For each topic in the list, in order, return one entry saying whether the document addresses it:
- `yes`: the page gives what the topic expects, or enough of it that a reader could see the picture. Copy the words that do so into `nearest`.
- `partly`: the page touches the subject but not in the way the topic expects — a target that covers part of it, a word in a list of other things, a figure without the basis that would make it mean anything. Copy the nearest words into `nearest` and write the card: what is still missing.
- `no`: the page says nothing that bears on the topic. Copy into `nearest` the closest the page comes, if there is anything at all, and write the card.

`nearest` must be copied from the document character for character, from one continuous passage. It is checked against the text and dropped if it is not there, so never paraphrase, never join two parts of a sentence, and leave it empty rather than guess.

For a topic the page does not address, write the margin card:
- `topic`: what is not mentioned, in a few words, as a reader would say it ("Capital allocation", "The absolute size of total emissions"). Not a sentence.
- `why_material`: one or two sentences on why it decides whether this company's story is honest, naming what the page does instead. Be specific to this company and this page, not to the industry in general.
- `complete_text`: one sentence the document would contain if it addressed the topic, in the company's own voice, with the figures where you know them from the evidence below. This is what the interface shows as "what the page would say".
- `evidence_ids`: ids from the evidence list that establish the omitted fact. Cite only what is there; leave empty when nothing does.

`score` is how serious the omission is, 0 to 1:
- 0.75 to 0.9: the topic is where most of this company's impact sits, and the page is an account of its environmental performance that never mentions it.
- 0.6 to 0.75: a topic the reference names first for this industry, absent, and the page's framing invites the reader to think it is covered.
- 0.4 to 0.55: material and absent, but the page's stated subject is narrower than the topic.
- 0.2 to 0.35: material for the industry, marginal for what this page claims.
- Below 0.2: do not write a card. Return `addressed` as `yes` or `partly` and leave the card fields empty.

`confidence` is how sure you are, 0 to 1: 0.8 to 0.9 when the reference names the topic for exactly this industry and nothing in the page touches it; 0.5 to 0.7 when the page touches the subject in passing; below 0.5 when it is arguable whether the topic belongs to this company at all.

Rules:
- An omission is about the text, not about the company. "The page does not say X" has to be true of the page in front of you; before writing a card, look for the words again.
- Credit a page that addresses a topic plainly, even briefly. A list where every topic is missing was read badly, and a page that covers its material impacts should come back with few cards or none.
- Do not repeat a claim's weakness as an omission. That a claim is vague or unsupported is scored elsewhere; here the question is what subject the page does not raise at all.
- Judge the document as what it is. A press release about one product is not a sustainability report, but the impacts of the business it belongs to are still what its environmental claims are read against."""

PLACE_MAX_OUTPUT_TOKENS = 2000
COVERAGE_MAX_OUTPUT_TOKENS = 16000

PLACE_EFFORT = os.environ.get("AUDITOR_OMISSIONS_PLACE_EFFORT", "low")
COVERAGE_EFFORT = os.environ.get("AUDITOR_OMISSIONS_EFFORT", "medium")

# Below this the model was told not to write a card; a card that arrives anyway is dropped.
MIN_SCORE = 0.2

# What a card loses when the reference's own words are in the text and the model did not say
# where: the absence is not disproved, but it is no longer corroborated.
UNEXPLAINED_PENALTY = 0.8


# ----------------------------------------------------------------------------- what the model sees


def evidence_listing(items: list[dict[str, Any]]) -> str:
    """The evidence already on the table, so an omission can cite what establishes the fact the
    document leaves out. Quotes are shown only where the item carries one (D5)."""
    lines = []
    for item in items:
        source = item.get("source") or {}
        head = f"{item['id']} [tier {item.get('tier', '?')}; {item.get('kind', 'other')}] {source.get('name', '')}"
        quote = item.get("quote")
        if quote:
            head += f"\n  \"{quote[:300]}\""
        elif item.get("computation"):
            head += f"\n  {item['computation'].get('result', '')[:300]}"
        elif item.get("note"):
            head += f"\n  {item['note'][:200]}"
        lines.append(head)
    return "\n".join(lines) or "(no evidence gathered yet)"


def place_prompt(store: Materiality) -> str:
    return f"{PLACE_TASK}\n\n<industries>\n{store.industries_listing()}\n</industries>"


def coverage_prompt(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], store: Materiality, matches: list[Match]) -> str:
    return (
        f"{COVERAGE_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>"
        f"\n\n<evidence>\n{evidence_listing(evidence)}\n</evidence>"
        f"\n\n<topics>\n{store.topics_listing(matches)}\n</topics>"
    )


# ----------------------------------------------------------------------------- assembly


@dataclass
class OmissionsResult:
    omissions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    completeness: dict[str, Any]
    matches: list[Match] = field(default_factory=list)
    addressed: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


class Assembler:
    """Turns what the model returns into contract entities: the omissions first, then the
    evidence items that make their topics material, then the omissions themselves, because an
    evidence item must exist before an omission cites it and its links may name omissions that
    come after (contract §2 rule 3, as the fixture emits E16)."""

    def __init__(
        self,
        document: dict[str, Any],
        store: Materiality,
        matches: list[Match],
        prior_evidence: list[dict[str, Any]] | None = None,
        emit: Emit | None = None,
        *,
        first_number: int = 1,
    ) -> None:
        self.text: str = document["text"]
        self.store = store
        self.matches = matches
        self.topics = store.topics(matches)
        self.known_evidence = {item["id"] for item in prior_evidence or []}
        self.emit = emit
        self.next_number = first_number
        self.omissions: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.by_topic: dict[str, dict[str, Any]] = {}
        self.addressed: list[str] = []
        self.unknown_topics = 0
        self.repeated = 0
        self.low_score = 0
        self.lost_quotes: list[str] = []
        self.unknown_evidence = 0
        self.unexplained: list[str] = []
        self.missing: list[str] = []

    def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.emit is not None:
            self.emit(type_, payload)

    def add(self, item: Coverage) -> dict[str, Any] | None:
        """One topic's answer. Returns the omission built from it, or None when the topic is
        addressed, unknown, or the card does not survive the checks."""
        topic_id = item.topic_id.strip()
        found = self.topics.get(topic_id)
        if found is None:
            self.unknown_topics += 1
            return None
        match, topic = found
        if topic_id in self.by_topic or topic_id in self.addressed:
            self.repeated += 1
            return None
        nearest = self._place_quote(topic_id, item.nearest)
        if item.addressed == "yes" or (item.addressed != "no" and item.score < MIN_SCORE):
            self.addressed.append(topic_id)
            return None
        if item.score < MIN_SCORE or not (item.topic.strip() or topic.name):
            self.low_score += 1
            self.addressed.append(topic_id)
            return None
        seen = mentions(self.text, topic.terms)
        confidence = clamp01(item.confidence)
        if seen and not nearest:
            # The reference's own words are on the page and the model did not say where: the
            # card stands, the certainty does not.
            confidence = clamp01(confidence * UNEXPLAINED_PENALTY)
            self.unexplained.append(topic_id)
        omission_id = f"O{self.next_number}"
        self.next_number += 1
        cited = [eid for eid in dict.fromkeys(item.evidence_ids) if eid in self.known_evidence]
        self.unknown_evidence += len(set(item.evidence_ids)) - len(cited)
        omission: dict[str, Any] = {
            "id": omission_id,
            "topic": item.topic.strip() or topic.name,
            "why_material": item.why_material.strip() or topic.why_material,
            "materiality_reference": f"{match.entry.index.reference}" + (f" {topic.code}" if topic.code else "") + f": {topic.name}",
            "score": clamp01(item.score),
            "confidence": confidence,
        }
        if item.complete_text.strip():
            omission["complete_text"] = item.complete_text.strip()
        ext: dict[str, Any] = {
            "topic_id": topic_id,
            "topic": topic.name,
            "industry": match.entry.index.industry,
            "addressed": item.addressed,
            "absence": f"none of the reference's words for this topic appear in the text ({', '.join(topic.terms[:6])})" if not seen
            else f"the text does use: {', '.join(seen[:6])}",
        }
        if nearest is not None:
            ext["nearest"] = nearest
        omission["ext"] = ext
        self.by_topic[topic_id] = omission
        self.omissions.append(omission)
        if cited:
            omission["evidence_ids"] = cited
        return omission

    def _place_quote(self, topic_id: str, quote: str) -> str | None:
        """A quote the model attributes to the document, placed in it. One that is not there is
        dropped: nothing reaches a card that the page does not say."""
        quote = quote.strip()
        if not quote:
            return None
        placed = locate(self.text, quote)
        if placed is None:
            self.lost_quotes.append(topic_id)
            return None
        return placed.text

    def finish(self) -> OmissionsResult:
        """Emit the reference evidence, then the omissions, and score Completeness."""
        for topic_id in self.topics:
            if topic_id not in self.by_topic and topic_id not in self.addressed:
                self.missing.append(topic_id)
        for match in self.matches:
            targets = [o["id"] for o in self.omissions if o["ext"]["topic_id"].startswith(f"{match.evidence_id}.")]
            if not targets:
                continue
            item = match.entry.as_evidence(match.evidence_id, [{"target": t, "relation": "criteria"} for t in targets])
            self.evidence.append(item)
            self._emit("evidence.added", {"evidence": item})
        for omission in self.omissions:
            # `evidence_ids` are all older than this event: the reference above, and items the
            # earlier evaluators emitted.
            omission.setdefault("evidence_ids", []).insert(0, self._reference_for(omission))
            self._emit("omission.found", {"omission": omission})
        result = OmissionsResult(self.omissions, self.evidence, self.completeness(), self.matches, self.addressed)
        result.notes.append(self.describe())
        return result

    def _reference_for(self, omission: dict[str, Any]) -> str:
        return omission["ext"]["topic_id"].split(".")[0]

    def completeness(self) -> dict[str, Any]:
        """D6 Completeness, document level: the weakest link, as claim likelihood is (contract
        §6). Step 18 folds it into the summary; nothing in the contract carries it before that."""
        if not self.omissions:
            covered = len(self.addressed)
            return {
                "score": 0.15,
                "confidence": 0.6 if covered >= max(1, len(self.topics) - 1) else 0.4,
                "basis": f"The page addresses {covered} of the {len(self.topics)} topics its industry's reference names; no material topic was found missing.",
            }
        worst = max(self.omissions, key=lambda o: o["score"])
        confidences = [o["confidence"] for o in self.omissions]
        return {
            "score": worst["score"],
            "confidence": round(sum(confidences) / len(confidences), 2),
            "basis": f"{len(self.omissions)} of the {len(self.topics)} material topics are unaddressed; the most serious is {worst['topic'].lower()}.",
        }

    def describe(self) -> str:
        industries = ", ".join(f"{m.entry.index.industry} ({m.evidence_id})" for m in self.matches)
        text = f"{len(self.omissions)} omissions from {len(self.topics)} material topics ({industries}); {len(self.addressed)} topics addressed by the page"
        if self.unexplained:
            text += f"; {len(self.unexplained)} cards whose topic words are in the text with no nearest passage given, confidence reduced ({', '.join(self.unexplained[:6])})"
        if self.lost_quotes:
            text += f"; {len(self.lost_quotes)} quotes were not in the document and were dropped ({', '.join(self.lost_quotes[:6])})"
        if self.missing:
            text += f"; {len(self.missing)} topics the model did not answer for ({', '.join(self.missing[:6])})"
        if self.low_score:
            text += f"; {self.low_score} cards below the {MIN_SCORE} bar dropped"
        if self.unknown_topics:
            text += f"; {self.unknown_topics} unknown topic ids ignored"
        if self.repeated:
            text += f"; {self.repeated} repeated topics ignored"
        if self.unknown_evidence:
            text += f"; {self.unknown_evidence} citations of evidence that does not exist dropped"
        return text


def apply_omissions(
    coverages: Coverages,
    document: dict[str, Any],
    store: Materiality,
    matches: list[Match],
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    *,
    first_number: int = 1,
) -> OmissionsResult:
    """The batch path: a whole result at once (tests and fakes)."""
    assembler = Assembler(document, store, matches, prior_evidence, emit, first_number=first_number)
    for item in coverages.coverage:
        assembler.add(item)
    return assembler.finish()


async def choose_industry(document: dict[str, Any], store: Materiality, llm: Llm) -> tuple[Match | None, Placement | None, Usage | None]:
    """Place a document whose industry the store does not know. Returns the match, what the model
    answered, and what the call cost. An empty or unknown code leaves the document with the
    cross-industry topics alone."""
    if not store.industries_listing().strip():
        return None, None, None
    placement, usage = await llm.extract(
        place_prompt(store), Placement, system=document_system(document), cache=True,
        max_tokens=PLACE_MAX_OUTPUT_TOKENS, effort=PLACE_EFFORT,
    )
    return store.by_code(placement.sasb_code), placement, usage


async def find_omissions(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    llm: Llm | None = None,
    store: Materiality | None = None,
    first_number: int = 1,
) -> OmissionsResult:
    """Run the stage on an ingested document, its claims and the evidence gathered so far.
    Raises LlmError when the model cannot answer and KnowledgeError when the store cannot be read."""
    store = store or get_materiality()
    llm = llm or get_llm()
    prior_evidence = prior_evidence or []
    started = time.perf_counter()
    usages: list[Usage] = []
    notes: list[str] = []

    matches = store.for_document(document)
    industry = (document.get("industry") or {}).get("label") or "not stated"
    if all(m.entry.index.sasb_code == "*" for m in matches):
        match, placement, usage = await choose_industry(document, store, llm)
        if usage is not None:
            usages.append(usage)
        if match is not None and placement is not None:
            matches.insert(0, Match(match.evidence_id, match.entry, f"The model placed it in {match.entry.index.industry} (confidence {placement.confidence:.2f}): {placement.basis}"))
            notes.append(f"The document declares industry {industry!r}, which the materiality store does not know; the model placed it in {match.entry.index.industry} ({match.entry.index.sasb_code}), confidence {placement.confidence:.2f}: {placement.basis}")
        elif placement is not None:
            notes.append(f"The document declares industry {industry!r} and the model matched it to no industry in the store ({placement.basis or 'no basis given'}); the cross-industry topics alone are used.")
    else:
        notes.append(f"Industry {industry!r} -> " + "; ".join(f"{m.evidence_id} {m.entry.index.industry} ({m.how})" for m in matches))

    assembler = Assembler(document, store, matches, prior_evidence, emit, first_number=first_number)
    returned = {"coverage": 0, "invalid": 0}
    handed: set[str] = set()

    async def on_element(key: str, item: dict[str, Any]) -> None:
        if key != "coverage":
            return
        try:
            coverage = Coverage.model_validate(item)
        except ValidationError:
            returned["invalid"] += 1
            return
        handed.add(coverage.topic_id)
        assembler.add(coverage)

    result_model, usage = await llm.extract_streaming(
        coverage_prompt(claims, prior_evidence, store, matches), Coverages, on_element=on_element,
        system=document_system(document), cache=True, max_tokens=COVERAGE_MAX_OUTPUT_TOKENS, effort=COVERAGE_EFFORT,
    )
    # Anything the incremental pass did not hand over, by topic, so a second answer for a topic
    # that did stream is not counted as a repeat.
    for item in result_model.coverage:
        if item.topic_id not in handed:
            assembler.add(item)
    returned["coverage"] += len(result_model.coverage)
    usages.append(usage)

    result = assembler.finish()
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = f"The model read {returned['coverage']} topics in one call"
    if returned["invalid"]:
        note += f", {returned['invalid']} malformed"
    result.notes[:0] = [note + f" ({result.usage.describe()})", *notes]
    result.notes.append(f"Completeness {result.completeness['score']} (confidence {result.completeness['confidence']}): {result.completeness['basis']}")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class OmissionComparison:
    """The live omissions against a reference's, paired by the words of their topics, since
    two runs will not name a card identically."""

    pairs: list[tuple[str, str, float, float]]
    missed: list[str]
    extra: list[str]
    reference: int

    def describe(self) -> str:
        text = f"{len(self.pairs)} of {self.reference} reference omissions found"
        if self.pairs:
            error = sum(abs(a - b) for _, _, a, b in self.pairs) / len(self.pairs)
            text += f", mean absolute difference in materiality {error:.2f}"
        if self.missed:
            text += f"; missed {', '.join(self.missed)}"
        if self.extra:
            text += f"; {len(self.extra)} not in the reference ({', '.join(self.extra[:4])})"
        return text


STOP_WORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "its", "their", "for", "to", "s", "at", "by", "with", "that"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS and len(w) > 2}


def compare_omissions(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> OmissionComparison:
    """Pair each reference omission with the live one whose topic and card share the most
    words, above a low bar. Every live omission is used at most once."""
    taken: set[str] = set()
    pairs, missed = [], []
    for ref in reference:
        wanted = _words(f"{ref['topic']} {ref.get('why_material', '')} {ref.get('complete_text', '')}")
        best: tuple[float, dict[str, Any]] | None = None
        for got in live:
            if got["id"] in taken:
                continue
            words = _words(f"{got['topic']} {got.get('why_material', '')} {got.get('complete_text', '')}")
            overlap = len(wanted & words) / max(1, min(len(wanted), len(words)))
            if overlap >= 0.25 and (best is None or overlap > best[0]):
                best = (overlap, got)
        if best is None:
            missed.append(f"{ref['id']} {ref['topic'][:40]}")
        else:
            taken.add(best[1]["id"])
            pairs.append((best[1]["id"], ref["id"], float(best[1]["score"]), float(ref["score"])))
    extra = [f"{o['id']} {o['topic'][:40]}" for o in live if o["id"] not in taken]
    return OmissionComparison(pairs, missed, extra, len(reference))


# ----------------------------------------------------------------------------- command line


def _print_omission(omission: dict[str, Any]) -> None:
    print(f"{omission['id']:>4}  {omission['score']:<5} confidence {omission['confidence']:<5} {omission['topic']}")
    print(f"      {omission['why_material']}")
    if omission.get("complete_text"):
        print(f"      would say: {omission['complete_text']}")
    print(f"      {omission['materiality_reference']}")
    print(f"      absence: {omission['ext']['absence']}" + (f"; nearest: \"{omission['ext']['nearest'][:90]}\"" if omission["ext"].get("nearest") else ""))


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
    print(f"{document['title']} — {document['word_count']} words, industry {document.get('industry', {}).get('label')}", file=sys.stderr)
    analysis = json.loads(Path(args.golden).read_text(encoding="utf-8")) if args.golden else None
    try:
        if analysis is not None:
            claims = reanchored_claims(analysis["claims"], document["text"], analysis["document"]["text"])
            evidence = [e for e in analysis["evidence"] if e.get("stage") in ("substantiate", "verify", "consistency")]
            print(f"using the reference's {len(claims)} claims and {len(evidence)} evidence items as input", file=sys.stderr)
        else:
            extracted = await extract_claims(document)
            for note in extracted.notes:
                print(f"note: {note}", file=sys.stderr)
            claims, evidence = extracted.claims, []

        def emit(type_: str, payload: dict[str, Any]) -> None:
            if args.json or type_ != "omission.found":
                return
            _print_omission(payload["omission"])

        result = await find_omissions(document, claims, prior_evidence=evidence, emit=emit)
    except (LlmError, KnowledgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps({"omissions": result.omissions, "evidence": result.evidence, "completeness": result.completeness}, ensure_ascii=False, indent=2))
    if analysis is not None and analysis.get("omissions"):
        comparison = compare_omissions(result.omissions, analysis["omissions"])
        print(f"\nagainst {Path(args.golden).name}: {comparison.describe()}")
        for live_id, ref_id, live, ref in comparison.pairs:
            print(f"  {live_id:>4} matches {ref_id:<4} live {live:<5} reference {ref:<5} diff {live - ref:+.2f}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.omissions", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims and evidence are the input and its omissions the reference")
    parser.add_argument("--json", action="store_true", help="print the omissions as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
