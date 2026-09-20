"""Linguistic evaluator (roadmap step 12; design-doc D4 Q2 and D6 Clarity): how each claim is
worded, marked at word level, and a Clarity score for every claim.

The model reads the document (the same cached prefix extraction sent) and the claims found in it,
and returns language signals and clarity scores as structured output. The claims go out in
parallel batches (`BATCH_SIZE` each; one more call reads the page as a whole for the
document-level signals), because one call over every claim thinks for minutes before it writes
a word, and the point of this stage is that marks appear while it works. Each signal is handed
over the moment it is complete in its stream, placed in the text and emitted, so the Language
layer fills in while the model is still writing; clarity scores follow the same way. Nothing
The model returns is trusted until its words are found in the text: exactly, then with
quotation marks and dashes normalised, then ignoring case; inside the claim's own spans first,
then its paragraph, then anywhere. A claim-level signal whose words cannot be placed is dropped
and reported. Every claim ends up with exactly one clarity score: a claim the model skipped
gets a neutral placeholder at low confidence, so the verdict rules always have the dimension.

    python -m auditor.language <file or url> [--golden fixtures/shell-climate.analysis.json] [--json]

With `--golden`, the reference's own claims are the input, so the evaluator is measured on the
hand-analysed claims rather than on whatever extraction found.
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
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .extract import Located, document_system, normalise
from .ingest.anchor import anchor_span, find_all
from .ingest.canonical import word_count
from .llm import Llm, LlmError, Usage, get_llm

SignalKind = Literal[
    "hedge", "vague_term", "undefined_term", "comparative_without_baseline", "weak_verb",
    "qualifier_present", "qualifier_absent", "scope_mismatch", "responsibility_diffusion",
    "framing", "ratio_language", "intensifier", "approximation", "buried_admission",
    "prominence", "share_of_attention", "emotive", "register",
]
Polarity = Literal["flag", "benign", "credit"]
Level = Literal["claim", "document"]

# Kinds that make sense with no words to point at.
DOCUMENT_KINDS = {"prominence", "share_of_attention", "emotive", "register", "buried_admission"}

KIND_LABELS = {
    "hedge": "Hedge", "vague_term": "Vague term", "undefined_term": "Undefined term",
    "comparative_without_baseline": "Comparative without a baseline", "weak_verb": "Weak verb",
    "qualifier_present": "Qualifier present", "qualifier_absent": "Qualifier absent",
    "scope_mismatch": "Scope mismatch", "responsibility_diffusion": "Responsibility diffusion",
    "framing": "Framing", "ratio_language": "Ratio language", "intensifier": "Intensifier",
    "approximation": "Approximation", "buried_admission": "Buried admission", "prominence": "Prominence",
    "share_of_attention": "Share of attention", "emotive": "Emotive language", "register": "Register",
}


class FoundSignal(BaseModel):
    level: Level
    kind: SignalKind
    polarity: Polarity
    quotes: list[str] = Field(default_factory=list, description="Claim level: the exact words that carry the signal, verbatim from the document, as short as the observation allows (a word or a phrase, not the whole sentence). Several entries when the signal rests on more than one phrase. Empty for a document-level signal.")
    claim_ids: list[str] = Field(default_factory=list, description="The claims this wording belongs to, by id from the list. Required for a claim-level signal; for a document-level one, the claims it concerns, if any.")
    note: str = Field(description="One sentence for the analyst: what the wording does to the reader and against what it fails (a regulator's principle, arithmetic, the document's own words). Do not restate the kind.")
    strength: float = Field(description="0 to 1: how far this wording alone could mislead a reasonable reader. 0.1 for benign marks; 0.8 or more when the wording carries the claim's whole impression.")


class ClarityScore(BaseModel):
    claim_id: str
    score: float = Field(description="The Clarity problem score, 0 to 1, from the bands in the task.")
    confidence: float = Field(description="0 to 1: how sure the score is from the text alone.")
    basis: str = Field(description="One sentence naming the words or the missing element that set the score.")


class LanguageReview(BaseModel):
    signals: list[FoundSignal] = Field(description="Every claim-level language signal for the claims under review, in document order.")
    clarity: list[ClarityScore] = Field(description="Exactly one entry per claim under review, in the list's order.")


class DocumentSignals(BaseModel):
    signals: list[FoundSignal] = Field(description="The document-level signals, and nothing else.")


TASK = """Assess how the claims are worded (the audit's question 2: how is it portrayed?) and score each claim's Clarity.

Below the task are the claims found in the document, each with its id, type, scope, paragraph, prominence (1.0 is the top of the page; lower is further down or in small print) and its words, and then the page's structure (headings, paragraphs with word counts, notes and footnotes). Read the whole document: the words around a claim, the heading above it and where on the page it sits are all part of how it is portrayed.

Return two lists.

1. `signals`: claim-level language signals, each one specific observation about wording: the exact words that carry it, quoted verbatim from the document and as short as the observation allows (a word or a phrase, not the whole sentence), attached to the claims they belong to, in document order. Observations about the page as a whole (prominence, share of attention, register, emotive language, admissions buried in notes) are asked for in a separate call: return none of those here.

Kinds (use only these):
- hedge: words that soften a claim or turn it into an opinion or an option: "aim to", "we believe", "may", "up to", "where possible". Agency hedges ("helping", "supporting", "contributing to") leave the company's own part unspecified.
- vague_term: a term with no fixed meaning, no definition and no measure: "sustainable", "eco-friendly", "energy system of the future", "high-quality".
- undefined_term: a term of art the document uses without defining it, or defines only elsewhere: "net-zero business", "carbon neutral" with no standard named.
- comparative_without_baseline: "cleaner", "lower-carbon", "less", "more efficient" with nothing named to compare against.
- weak_verb: a verb chosen to say less than the reader will hear: "supports the goal" for "is aligned with", "working towards", "exploring".
- qualifier_present: a limiting condition that is stated: "on a net basis", "operated assets only", "including those of renewable power". Polarity credit when it makes the claim more honest; flag when the qualifier itself shows that the headline overstates.
- qualifier_absent: a condition an informed reader expects and the text leaves out: a target with no baseline year, a reduction with no scope, "carbon neutral" without saying offsets are used.
- scope_mismatch: the words imply a wider scope than the claim has: "our operations" when only operated assets count, "our products" when one line is meant.
- responsibility_diffusion: the outcome is conditioned on others: "requires action by customers and governments", "as society transitions".
- framing: a heading, a juxtaposition or a list that lends environmental meaning to something with none of its own: a bullet about selling more gas under a decarbonisation heading.
- ratio_language: intensities, proportions and percentages where the absolute quantities would tell a different story.
- intensifier: "well below", "significantly", "dramatically", "leading". Benign when the number bears it out.
- approximation: "around", "about", "nearly". Benign when the arithmetic checks.
- buried_admission: a fact that undercuts the impression, placed where it will not be read: inside a list of good news, in a footnote, in a cautionary note. Claim level when it sits in a claim's words; document level when it is about the page.
- prominence: where a claim sits relative to what qualifies it. Claim level for one claim ("achieved" ticks with no target history); document level for the page (the qualifying note is at the bottom, in small print).
- share_of_attention: document level; what the page gives words to and what it does not.
- emotive: document level; nature imagery, feelings and identity language doing the work of evidence.
- register: document level; the overall voice, in one line. Benign when the text is plain and numerate.

Polarity: `flag` when the wording could mislead; `benign` when the wording looks like a signal but the facts on the page bear it out, so the reader sees that not everything is flagged; `credit` when the wording makes the claim more honest than it needed to be (a stated qualifier, a precise figure with its baseline). Use benign and credit where they apply: a page with only flags is a page read badly.

Strength, 0 to 1: how far this wording alone could mislead. 0.1 for benign marks; 0.3 to 0.5 for a hedge or a technical qualifier; 0.6 to 0.7 for an undefined or vague key term; 0.8 or more when the wording carries the claim's whole impression (a comparative with no baseline, a heading that supplies the meaning, ratios that hide growth).

2. `clarity`: one score per claim, every claim in the list, none twice. Clarity is a problem score: 0 means specific and checkable, 1 means nothing to check. Bands:
- 0.1 to 0.2: a specific figure with its baseline, scope and date; an explicit scope statement; a plain statement of what the company does with no degree asserted ("we recycle the water we use").
- 0.3 to 0.45: specific, but with a technical qualifier a lay reader will not parse, a term defined only elsewhere, or a scope worded wider than it is.
- 0.5 to 0.6: an improvement or direction asserted without a quantity ("we are improving the efficiency of our fleet"); a hedged or opinion-framed claim; a percentage or intensity with no absolute; an "achieved" with no history.
- 0.7 to 0.85: the claim rests on an undefined or vague term, a comparative with no baseline, a slogan, or a double hedge; as worded there is nothing to verify.
- above 0.85: only a pure slogan with no proposition at all.
At 0.7 and above the audit treats a claim as too vague to verify, so cross that line only when you could not say what evidence would settle it.
Confidence, 0 to 1, is how sure the score is from the text alone: 0.8 to 0.9 for most; lower when it depends on a definition that may exist off the page.
The basis is one sentence naming the words or the missing element that set the score.

Rules:
- Quote exactly. A quote is an exact substring of the document, character for character, with the quotation marks and dashes the document uses. When the same words recur and the signal applies each time, give the quote once: every occurrence inside the claims named is marked.
- Attach signals only to ids from the list. A signal can belong to several claims.
- Judge the wording, not the truth. Whether a claim is true is another evaluator's job; here the question is whether the words say what the reader will hear. A false claim can be perfectly clear.
- Do not flag every adjective. Most claims deserve one signal or none; only a claim whose wording fails in two different ways gets two. A specific, dated, scoped figure gets credit or nothing: at most one credit mark per claim, for a qualifier that limits it. Aim for the signals an experienced analyst would put in a memo; every one must earn its place.
- The same words repeated on the page are one signal, not two.
- The yardstick is regulators' guidance: the UK CMA Green Claims Code and the US FTC Green Guides hold that vague general terms, comparatives with no basis, and a small part presented as the whole mislead. Naming the principle in a note helps the analyst; never invent a citation."""

DOCUMENT_TASK = """Assess how the page as a whole portrays the claims (the audit's question 2, at document level).

Below are the claims found in the document, each with its id, type, scope, paragraph, prominence (1.0 is the top of the page; lower is further down or in small print) and its words, and then the page's structure (headings, paragraphs with word counts, notes and footnotes).

Return `signals`: document-level observations only, each with level "document", no quotes, the claims it concerns in `claim_ids` (empty when it is about the page in general), one sentence of note, a polarity and a strength. Use only these kinds, at most two of each, and only where there is something to say:
- prominence: where the claims sit relative to what qualifies them (a headline target above a note that undercuts it; the qualifying note in small print at the bottom). Name the paragraphs or notes by their labels.
- buried_admission: a fact that undercuts the impression, placed where it will not be read (a cautionary note, a footnote, the tail of a list of good news). Say what it is and where.
- share_of_attention: what the page gives words to and what it does not, in an analyst's terms: the absolute size of the footprint, growth plans, capital allocation, the fossil share of the business.
- emotive: nature imagery, feelings and identity language doing the work of evidence. Benign when there is little of it.
- register: the overall voice, in one line: plain and numerate, or lyrical. Usually benign.
Polarity: `flag` when the page's arrangement could mislead, `benign` when it does not. Strength, 0 to 1, is how far the arrangement alone could mislead; benign marks sit at 0.1 to 0.2.
Rules: judge the arrangement, not the truth of the claims; do not repeat a word-level observation about a single claim; every signal must earn its place."""

MAX_OUTPUT_TOKENS = 32000
DOCUMENT_MAX_OUTPUT_TOKENS = 8000

# Claims per call. Smaller batches think less before the first mark and run in parallel; larger
# ones see more of the page at once. Measured on the Shell page (25 claims): see README.
BATCH_SIZE = int(os.environ.get("AUDITOR_LANGUAGE_BATCH", "9"))

# Effort for this stage. Measured on the Shell page (25 golden claims, batches of 9) with Sonnet 5
# on 2026-09-20: medium found 17 of 24 golden signals at 36% precision, clarity within 0.13 of
# the reference on average with 1 claim on the wrong side of the 0.7 line, first mark after
# 12 s, done in 38 s; high found the same 17 with clarity within 0.11 and 1 on the wrong side,
# first mark after 24 s, done in 63 s. One call over all 25 claims took 175-223 s with the
# first mark after 2-3 minutes, which is why the batches exist. The team's global default
# (AUDITOR_EFFORT) stays high for the stages that reason over evidence.
LANGUAGE_EFFORT = os.environ.get("AUDITOR_LANGUAGE_EFFORT", "medium")

PLACEHOLDER_BASIS = "Not assessed by the linguistic evaluator; neutral placeholder."


# ----------------------------------------------------------------------------- what the model sees


def claims_listing(claims: list[dict[str, Any]]) -> str:
    lines = []
    for c in claims:
        primary = c["spans"][0]["text"]
        prominence = f"prominence {c['prominence']}" if c.get("prominence") is not None else "prominence unknown"
        lines.append(f"{c['id']} | {c.get('type', '?')} | {c.get('scope', '?')} | {c.get('paragraph') or '?'} | {prominence} | {json.dumps(primary, ensure_ascii=False)}")
    return "\n".join(lines) or "(no claims)"


def structure_summary(document: dict[str, Any]) -> str:
    """Headings, paragraphs with word counts and prominence, notes and footnotes, in page order."""
    text = document["text"]
    lines = []
    for r in document.get("regions") or []:
        if r["kind"] in ("list_item", "caption"):
            continue
        words = word_count(text[r["start"]:r["end"]])
        label = r.get("label") or r["kind"]
        if r["kind"] in ("title", "heading"):
            lines.append(label)
        elif r["kind"] == "paragraph":
            lines.append(f"{label}: {words} words" + (f", prominence {r['prominence']}" if r.get("prominence") is not None else ""))
        else:
            lines.append(f"{r['kind']} {label}: {words} words" + (f", prominence {r['prominence']}" if r.get("prominence") is not None else ""))
    return "\n".join(lines) or f"(no structure; {document.get('word_count', word_count(text))} words)"


def task_prompt(claims: list[dict[str, Any]], document: dict[str, Any], batch: list[dict[str, Any]] | None = None) -> str:
    """The claim-level task: all claims for context, the batch's ids to mark and score."""
    prompt = f"{TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<structure>\n{structure_summary(document)}\n</structure>"
    if batch is not None:
        ids = ", ".join(c["id"] for c in batch)
        prompt += (
            f"\n\n<review>\nIn this call, mark and score only these claims: {ids}. The other claims are listed for context and are "
            "covered by other calls; a separate call covers the page as a whole.\n</review>"
        )
    return prompt


def document_prompt(claims: list[dict[str, Any]], document: dict[str, Any]) -> str:
    return f"{DOCUMENT_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<structure>\n{structure_summary(document)}\n</structure>"


# ----------------------------------------------------------------------------- placement


def occurrences(text: str, quote: str) -> list[Located]:
    """Every occurrence of a quote in the text, from the first tier that matches: exactly, then
    with quotation marks and dashes normalised, then ignoring case; with surrounding quotation
    marks or a trailing full stop dropped if that is what it takes."""
    quote = " ".join(quote.split())
    if not quote:
        return []
    candidates: list[str] = []
    # A mark never ends in a sentence's full stop, so the stripped form is tried first (as for claims).
    for candidate in (quote.rstrip(".;:,"), quote, quote.strip("\"'“”‘’").rstrip(".;:,"), quote.strip("\"'“”‘’")):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    normal_text = normalise(text)
    lower_text = normal_text.lower()
    for candidate in candidates:
        for hay, needle in ((text, candidate), (normal_text, normalise(candidate)), (lower_text, normalise(candidate).lower())):
            hits = find_all(hay, needle)
            if not hits:
                continue
            out: list[Located] = []
            for start in hits:
                end = start + len(needle)
                exact = text[start:end]
                exact_hits = find_all(text, exact)
                occurrence = exact_hits.index(start) + 1 if len(exact_hits) > 1 and start in exact_hits else None
                out.append(Located(start, end, exact, occurrence))
            return out
    return []


def _inside(hit: Located, windows: list[tuple[int, int]]) -> bool:
    return any(w0 <= hit.start and hit.end <= w1 for w0, w1 in windows)


def choose_hits(hits: list[Located], claim_windows: list[tuple[int, int]], paragraph_windows: list[tuple[int, int]]) -> list[Located]:
    """The occurrences a signal marks: every one inside the named claims' spans; else the first
    inside their paragraphs; else the first in the document."""
    if not hits:
        return []
    inside = [h for h in hits if _inside(h, claim_windows)]
    if inside:
        return inside
    nearby = [h for h in hits if _inside(h, paragraph_windows)]
    return nearby[:1] if nearby else hits[:1]


def _paragraph_windows(regions: list[dict[str, Any]], windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for r in regions:
        if r["kind"] not in ("paragraph", "cautionary_note", "footnote", "promo", "quote"):
            continue
        if any(r["start"] <= s and e <= r["end"] for s, e in windows):
            out.append((r["start"], r["end"]))
    return out


def clamp01(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 2)


# ----------------------------------------------------------------------------- assembly


Emit = Callable[[str, dict[str, Any]], Any]


@dataclass
class LanguageResult:
    signals: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    dropped: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


class Assembler:
    """Turns what the model returns into contract entities, one at a time, emitting each as it
    is built (`emit(type, payload)`), so the stream and the batch path share one code path."""

    def __init__(self, document: dict[str, Any], claims: list[dict[str, Any]], emit: Emit | None = None, *, first_number: int = 1) -> None:
        self.text: str = document["text"]
        self.regions: list[dict[str, Any]] = document.get("regions") or []
        self.claims = {c["id"]: c for c in claims}
        self.order = [c["id"] for c in claims]
        self.emit = emit
        self.signals: list[dict[str, Any]] = []
        self.scores: list[dict[str, Any]] = []
        self.scored: set[str] = set()
        self.dropped: list[str] = []
        self.placeholders: list[str] = []
        self.unknown_ids = 0
        self.duplicates = 0
        self.folded = 0
        self._seen: set[tuple[str, tuple[int, ...]]] = set()
        self._number = first_number

    def _windows(self, claim_ids: list[str]) -> list[tuple[int, int]]:
        return [(s["start"], s["end"]) for cid in claim_ids for s in self.claims[cid].get("spans", [])]

    def add_signal(self, found: FoundSignal) -> dict[str, Any] | None:
        claim_ids: list[str] = []
        for cid in found.claim_ids:
            if cid in self.claims and cid not in claim_ids:
                claim_ids.append(cid)
            elif cid not in self.claims:
                self.unknown_ids += 1
        windows = self._windows(claim_ids)
        paragraphs = _paragraph_windows(self.regions, windows)
        placed: dict[int, Located] = {}
        for quote in found.quotes:
            for hit in choose_hits(occurrences(self.text, quote), windows, paragraphs):
                placed.setdefault(hit.start, hit)
        spans = [placed[k] for k in sorted(placed)]
        level = found.level
        if level == "claim" and not spans:
            if found.kind in DOCUMENT_KINDS:
                level = "document"
            else:
                self.dropped.append(f"{found.kind}: {' / '.join(found.quotes)[:100]}")
                return None
        if level == "claim" and not claim_ids:
            first = spans[0]
            for cid in self.order:
                if _inside(first, self._windows([cid])):
                    claim_ids = [cid]
                    break
        if spans:
            key = (found.kind, tuple(s.start for s in spans))
            if key in self._seen:
                self.folded += 1  # the same observation on the same words, from a repeat or another batch
                return None
            self._seen.add(key)
        signal = {
            "id": f"L{self._number}",
            "level": level,
            "kind": found.kind,
            "polarity": found.polarity,
            "spans": [s.as_span() for s in spans],
            "note": " ".join(found.note.split()) or KIND_LABELS[found.kind],
            "claim_ids": claim_ids,
            "strength": clamp01(found.strength),
        }
        self._number += 1
        self.signals.append(signal)
        if self.emit is not None:
            self.emit("language.signal", {"signal": signal})
        return signal

    def add_clarity(self, item: ClarityScore) -> dict[str, Any] | None:
        if item.claim_id not in self.claims:
            self.unknown_ids += 1
            return None
        if item.claim_id in self.scored:
            self.duplicates += 1
            return None
        score = {
            "claim_id": item.claim_id,
            "dimension": "clarity",
            "score": clamp01(item.score),
            "confidence": clamp01(item.confidence),
            "basis": " ".join(item.basis.split()) or "No basis given.",
            "stage": "language",
        }
        self.scored.add(item.claim_id)
        self.scores.append(score)
        if self.emit is not None:
            self.emit("dimension.scored", {"score": score})
        return score

    def finish(self) -> LanguageResult:
        for cid in self.order:
            if cid not in self.scored:
                self.placeholders.append(cid)
                self.add_clarity(ClarityScore(claim_id=cid, score=0.5, confidence=0.3, basis=PLACEHOLDER_BASIS))
        polarity = {p: sum(1 for s in self.signals if s["polarity"] == p) for p in ("flag", "benign", "credit")}
        levels = {lv: sum(1 for s in self.signals if s["level"] == lv) for lv in ("claim", "document")}
        note = (
            f"{len(self.signals)} language signals placed ({polarity['flag']} flagged, {polarity['benign']} benign, {polarity['credit']} credit; "
            f"{levels['claim']} claim-level, {levels['document']} document-level)"
        )
        if self.dropped:
            note += f"; {len(self.dropped)} dropped because their words are not in the document"
        note += f"; clarity scored for {len(self.scored)} of {len(self.order)} claims"
        if self.placeholders:
            note += f", {len(self.placeholders)} with a neutral placeholder ({', '.join(self.placeholders[:8])})"
        if self.unknown_ids or self.duplicates:
            note += f"; ignored {self.unknown_ids} unknown claim ids and {self.duplicates} duplicate scores"
        if self.folded:
            note += f"; {self.folded} repeated marks folded"
        result = LanguageResult(self.signals, self.scores, self.dropped, self.placeholders, notes=[note])
        for item in self.dropped[:5]:
            result.notes.append(f"Dropped, words not found verbatim: {item!r}")
        return result


def apply_review(review: LanguageReview, document: dict[str, Any], claims: list[dict[str, Any]], emit: Emit | None = None) -> LanguageResult:
    """The batch path: a whole review at once (tests and fakes)."""
    assembler = Assembler(document, claims, emit)
    for found in review.signals:
        assembler.add_signal(found)
    for item in review.clarity:
        assembler.add_clarity(item)
    return assembler.finish()


def combine_usage(usages: list[Usage], seconds: float) -> Usage:
    """Token totals over parallel calls, with the wall time they took together."""
    return Usage(
        model=usages[0].model if usages else "",
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        cache_read_tokens=sum(u.cache_read_tokens for u in usages),
        cache_write_tokens=sum(u.cache_write_tokens for u in usages),
        stop_reason=None,
        request_id=None,
        seconds=seconds,
    )


async def review_language(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    emit: Emit | None = None,
    llm: Llm | None = None,
) -> LanguageResult:
    """Run the evaluator on an ingested document and its claims, emitting each signal and score
    as it arrives: the claims in parallel batches of `BATCH_SIZE`, plus one call for the page as
    a whole. Raises LlmError when the model cannot answer."""
    if not claims:
        return LanguageResult([], [], notes=["No claims to review; the language stage has nothing to mark."])
    llm = llm or get_llm()
    assembler = Assembler(document, claims, emit)
    system = document_system(document)
    size = max(1, BATCH_SIZE)
    batches = [claims[i : i + size] for i in range(0, len(claims), size)]
    started = time.perf_counter()
    usages: list[Usage] = []
    returned = {"signals": 0, "clarity": 0, "invalid": 0, "out_of_batch": 0}

    async def run_batch(batch: list[dict[str, Any]]) -> None:
        ids = {c["id"] for c in batch}
        handed = {"signals": 0, "clarity": 0}

        async def on_element(key: str, item: dict[str, Any]) -> None:
            if key not in handed:
                return
            handed[key] += 1
            try:
                if key == "signals":
                    assembler.add_signal(FoundSignal.model_validate(item))
                else:
                    score = ClarityScore.model_validate(item)
                    if score.claim_id in ids:
                        assembler.add_clarity(score)
                    else:
                        returned["out_of_batch"] += 1
            except ValidationError:
                returned["invalid"] += 1

        review, usage = await llm.extract_streaming(
            task_prompt(claims, document, batch=batch), LanguageReview, on_element=on_element,
            system=system, cache=True, max_tokens=MAX_OUTPUT_TOKENS, effort=LANGUAGE_EFFORT,
        )
        # The incremental pass hands over everything; this catches anything it did not.
        for found in review.signals[handed["signals"]:]:
            assembler.add_signal(found)
        for item in review.clarity[handed["clarity"]:]:
            if item.claim_id in ids:
                assembler.add_clarity(item)
        returned["signals"] += len(review.signals)
        returned["clarity"] += len(review.clarity)
        usages.append(usage)

    async def run_document() -> None:
        handed = 0

        def as_document(found: FoundSignal) -> FoundSignal:
            return found.model_copy(update={"level": "document", "quotes": []})

        async def on_element(key: str, item: dict[str, Any]) -> None:
            nonlocal handed
            if key != "signals":
                return
            handed += 1
            try:
                assembler.add_signal(as_document(FoundSignal.model_validate(item)))
            except ValidationError:
                returned["invalid"] += 1

        review, usage = await llm.extract_streaming(
            document_prompt(claims, document), DocumentSignals, on_element=on_element,
            system=system, cache=True, max_tokens=DOCUMENT_MAX_OUTPUT_TOKENS, effort=LANGUAGE_EFFORT,
        )
        for found in review.signals[handed:]:
            assembler.add_signal(as_document(found))
        returned["signals"] += len(review.signals)
        usages.append(usage)

    try:
        async with asyncio.TaskGroup() as group:
            for batch in batches:
                group.create_task(run_batch(batch))
            group.create_task(run_document())
    except* LlmError as errors:
        raise errors.exceptions[0]
    result = assembler.finish()
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = f"The model returned {returned['signals']} signals and {returned['clarity']} clarity scores over {len(batches) + 1} parallel calls ({len(batches)} of up to {size} claims each, 1 for the page)"
    if returned["invalid"]:
        note += f", {returned['invalid']} malformed"
    if returned["out_of_batch"]:
        note += f", {returned['out_of_batch']} scores for claims outside their call ignored"
    result.notes.insert(0, note + f" ({result.usage.describe()})")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    shorter = max(1, min(a[1] - a[0], b[1] - b[0]))
    return inter / shorter


def _signal_ranges(signal: dict[str, Any], text: str, old_text: str | None) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for span in signal.get("spans") or []:
        placed = anchor_span(text, span, old_text)
        if placed is not None:
            out.append((placed[0], placed[1]))
    return out


@dataclass
class SignalMatch:
    live_id: str
    reference_id: str
    how: str  # "span" (same kind, overlapping words) or "claim" (same kind, same claim)


@dataclass
class SignalComparison:
    matches: list[SignalMatch]
    missed: list[str]
    extra: list[str]
    reference_total: int
    live_total: int

    @property
    def recall(self) -> float:
        return len(self.matches) / self.reference_total if self.reference_total else 0.0

    @property
    def precision(self) -> float:
        return len(self.matches) / self.live_total if self.live_total else 0.0

    def describe(self) -> str:
        by_span = sum(1 for m in self.matches if m.how == "span")
        text = (
            f"{len(self.matches)} of {self.reference_total} reference signals found (recall {self.recall:.0%}, precision {self.precision:.0%}; "
            f"{by_span} on the same words, {len(self.matches) - by_span} on the same claim)"
        )
        if self.missed:
            text += f"; missed {', '.join(self.missed)}"
        if self.extra:
            text += f"; new {', '.join(self.extra)}"
        return text


def compare_signals(live: list[dict[str, Any]], reference: list[dict[str, Any]], text: str, old_text: str | None = None, *, threshold: float = 0.5) -> SignalComparison:
    """Match live signals to reference signals of the same kind: by overlapping words first,
    then by a shared claim; document-level ones by kind alone. One to one, best first."""
    live_ranges = {s["id"]: _signal_ranges(s, text, None) for s in live}
    ref_ranges = {s["id"]: _signal_ranges(s, text, old_text) for s in reference}
    pairs: list[tuple[int, float, str, str, str]] = []
    for ls in live:
        for rs in reference:
            if ls["kind"] != rs["kind"]:
                continue
            overlap = max((_overlap(a, b) for a in live_ranges[ls["id"]] for b in ref_ranges[rs["id"]]), default=0.0)
            if overlap >= threshold:
                pairs.append((0, overlap, ls["id"], rs["id"], "span"))
            elif ls["level"] == rs["level"] == "document":
                pairs.append((1, 0.0, ls["id"], rs["id"], "claim"))
            elif set(ls.get("claim_ids", [])) & set(rs.get("claim_ids", [])):
                pairs.append((1, 0.0, ls["id"], rs["id"], "claim"))
    pairs.sort(key=lambda p: (p[0], -p[1], _number(p[2]), _number(p[3])))
    taken_live: set[str] = set()
    taken_ref: set[str] = set()
    matches: list[SignalMatch] = []
    for _, _, lid, rid, how in pairs:
        if lid in taken_live or rid in taken_ref:
            continue
        taken_live.add(lid)
        taken_ref.add(rid)
        matches.append(SignalMatch(lid, rid, how))
    matches.sort(key=lambda m: _number(m.reference_id))
    return SignalComparison(
        matches=matches,
        missed=[s["id"] for s in reference if s["id"] not in taken_ref],
        extra=[s["id"] for s in live if s["id"] not in taken_live],
        reference_total=len(reference),
        live_total=len(live),
    )


@dataclass
class ClarityComparison:
    pairs: list[tuple[str, float, float]]  # claim id, live score, reference score
    unscored: list[str]

    @property
    def mean_abs_error(self) -> float:
        return sum(abs(l - r) for _, l, r in self.pairs) / len(self.pairs) if self.pairs else 0.0

    @property
    def wrong_side(self) -> list[str]:
        """Claims the two put on different sides of the 0.7 line (contract §6: too vague to verify)."""
        return [cid for cid, l, r in self.pairs if (l >= 0.7) != (r >= 0.7)]

    def describe(self) -> str:
        text = f"clarity compared on {len(self.pairs)} claims: mean absolute difference {self.mean_abs_error:.2f}"
        text += f"; {len(self.wrong_side)} on the other side of the 0.7 line" + (f" ({', '.join(self.wrong_side)})" if self.wrong_side else "")
        if self.unscored:
            text += f"; reference claims without a live score: {', '.join(self.unscored)}"
        return text


def compare_clarity(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> ClarityComparison:
    live_by = {s["claim_id"]: s["score"] for s in live if s.get("dimension") == "clarity"}
    pairs = []
    unscored = []
    for s in reference:
        if s.get("dimension") != "clarity":
            continue
        if s["claim_id"] in live_by:
            pairs.append((s["claim_id"], live_by[s["claim_id"]], s["score"]))
        else:
            unscored.append(s["claim_id"])
    return ClarityComparison(pairs, unscored)


def _number(entity_id: str) -> int:
    digits = "".join(ch for ch in entity_id if ch.isdigit())
    return int(digits) if digits else 0


def reanchored_claims(reference: list[dict[str, Any]], text: str, old_text: str | None) -> list[dict[str, Any]]:
    """The reference's claims with their spans placed in this text (for `--golden`)."""
    out = []
    for c in reference:
        spans = []
        for span in c.get("spans", []):
            placed = anchor_span(text, span, old_text)  # (start, end, how it was anchored)
            if placed is not None:
                spans.append({"text": text[placed[0] : placed[1]], "start": placed[0], "end": placed[1]})
        if spans:
            out.append(dict(c, spans=spans))
    return out


# ----------------------------------------------------------------------------- CLI


def _print_signal(signal: dict[str, Any]) -> None:
    words = "; ".join(f"{s['text'][:50]!r}@{s['start']}" for s in signal["spans"]) or "(document)"
    print(f"{signal['id']:>4}  {signal['level']:<8} {signal['kind']:<29} {signal['polarity']:<7} {signal['strength']:<4} {','.join(signal['claim_ids']) or '-':<8} {words}")
    print(f"      {signal['note']}")


async def _main(args: argparse.Namespace) -> int:
    from .extract import extract_claims
    from .ingest import IngestError, ingest_file, ingest_url

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
        started = time.perf_counter()
        first: list[float] = []

        def emit(type_: str, payload: dict[str, Any]) -> None:
            if not first:
                first.append(time.perf_counter() - started)
            if args.json:
                return
            if type_ == "language.signal":
                _print_signal(payload["signal"])
            else:
                s = payload["score"]
                print(f"{s['claim_id']:>4}  clarity {s['score']:<5} confidence {s['confidence']:<5} {s['basis'][:100]}")

        result = await review_language(document, claims, emit=emit)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if first:
        print(f"note: first mark after {first[0]:.1f} s", file=sys.stderr)
    if args.json:
        print(json.dumps({"signals": result.signals, "scores": result.scores}, ensure_ascii=False, indent=2))
    if analysis is not None:
        signals = compare_signals(result.signals, analysis["signals"], document["text"], analysis["document"]["text"])
        print(f"\nagainst {Path(args.golden).name}: {signals.describe()}")
        for rid in signals.missed:
            ref = next(s for s in analysis["signals"] if s["id"] == rid)
            words = "; ".join(sp["text"][:40] for sp in ref["spans"]) or "(document)"
            print(f"  missed {rid} {ref['kind']} [{','.join(ref['claim_ids'])}]: {words}")
        clarity = compare_clarity(result.scores, analysis["scores"])
        print(clarity.describe())
        for cid, live, ref in clarity.pairs:
            flag = "  <-- other side of 0.7" if (live >= 0.7) != (ref >= 0.7) else ""
            print(f"  {cid:>4} live {live:<5} reference {ref:<5} diff {live - ref:+.2f}{flag}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.language", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims are the input and its signals and clarity scores the reference")
    parser.add_argument("--json", action="store_true", help="print the signals and scores as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
