"""Claim extraction (roadmap step 11; design-doc D4 Q1): the document's atomic environmental
claims, each with a verbatim span, the type that routes its evaluation, its scope and what it
asserts.

The model reads the whole canonical text and returns claims as structured output. Nothing it
returns is trusted until its quote is found in the text: character for character first, then
after normalising quotation marks and dashes, then ignoring case. Offsets are computed here,
never by the model, and a claim whose quote cannot be placed is dropped and reported. Claims are
numbered in document order. `compare` measures a result against the golden reference by span
overlap, which is the roadmap's visual check for this step.

    python -m auditor.extract <file or url> [--golden fixtures/shell-climate.analysis.json] [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .ingest.anchor import anchor_span, find_all
from .llm import Llm, LlmError, Usage, get_llm

ClaimType = Literal["factual", "commitment", "comparative", "vague_attribute", "certification"]
ScopeKind = Literal["product", "packaging", "operations", "supply_chain", "company", "other"]


class ExtractedClaim(BaseModel):
    quote: str = Field(description="The claim, verbatim from the document: an exact substring, the shortest that carries the whole proposition, without the sentence's final full stop.")
    repeats: list[str] = Field(default_factory=list, description="Other verbatim passages of the document that restate this same claim, if any. Usually empty.")
    type: ClaimType
    scope: ScopeKind
    scope_note: str | None = Field(default=None, description="The precise subject and scope in a few words, e.g. 'operated upstream assets only' or 'Apple Watch models sold with a Sport Loop'.")
    attribute: str = Field(description="What is asserted, in a few words: 'net zero', 'Scope 1 and 2 down 36%', 'cleaner', 'validated by SBTi'.")
    quantity: str | None = Field(default=None, description="The number or range asserted, exactly as stated, if any.")
    baseline: str | None = Field(default=None, description="The baseline year or comparator, exactly as stated, if any.")
    timeframe: str | None = Field(default=None, description="The year or period the claim is about, exactly as stated, if any.")
    note: str | None = Field(default=None, description="One short sentence an analyst should know: a framing, an ambiguity, what heading it sits under. Optional.")


class Extraction(BaseModel):
    claims: list[ExtractedClaim] = Field(description="Every atomic environmental claim the company makes, in document order. Empty if there are none.")


SYSTEM_FRAME = (
    "You are the reading stage of a greenwashing audit. The document under audit is below, verbatim, "
    "between <document> tags. Whenever you quote it, quote it exactly, character for character."
)

TASK = """Decompose the document into its atomic environmental claims (the audit's question 1: what is claimed?).

A claim is one proposition the company makes about its own environmental performance, impact, targets, products, practices or credentials that a reasonable reader would take as true. Only the company's claims about itself count: not definitions, not general facts about the world or about other organisations, not descriptions of what a standard or a regulator does.

Include, as separate claims:
- statements of fact about past or present performance, practices or achievements, even when unquantified ("we are reducing emissions from our operations");
- commitments: targets, aims, plans, ambitions, intentions ("halve Scope 1 and 2 emissions by 2030");
- comparisons: relative performance against a baseline, benchmark, alternative or competitor ("36% below 2016", "less carbon-intensive than air transport");
- vague attributes: a claim carried by an unverifiable quality word ("cleaner energy", "low-carbon products", "high-quality carbon credits", "sustainable");
- certifications and credentials: a third-party label, validation, standard, ranking, score or award ("validated by the Science Based Targets initiative", "certified by SCS Global Services", "CDP A score").

Exclude: cautionary notes, disclaimers and forward-looking-statement boilerplate; footnotes that only define a term or a method; navigation, calls to action ("Find out more") and headings that only name a topic; product marketing with no environmental content; quotations from third parties about the company.

Granularity: one proposition per claim. A sentence that asserts different things about different subjects gives several claims, each with its own span; spans of different claims must not overlap. Keep together what belongs to one proposition: a measurement and the target it is compared with ("decreased by 9% and was within the target range"), two coordinated actions on the same subject ("improving efficiency and using more renewable electricity"), a value and its breakdown. A list of parallel items that each assert the same kind of fact (five yearly targets each marked "achieved") is one claim whose `quote` is the first item and whose `repeats` are the other items. A claim restated elsewhere in the document is one claim with the restatements in `repeats`. Slogans and vague promises count too ("more value with less emissions").

Spans: `quote` and each of `repeats` must be exact substrings of the document, copied character for character, including its quotation marks, apostrophes, dashes, numbers and spacing. Take the shortest span that carries the whole proposition, usually a clause. Do not include the sentence's final full stop. Never paraphrase, never join fragments from different places, never use an ellipsis.

Type, chosen by what verification would need: `factual` = says what is or was, verifiable in principle even if unquantified; a measured change against the company's own earlier baseline ("down 36% since 2016") is factual, not comparative; `commitment` = a future target, aim, plan or intention, including a hedged one ("we may choose to use carbon credits"); an activity already under way, described in the present tense ("we are growing our power sales", "we are developing CCS"), is `factual` even when it is listed as the way a target will be met: the target is the commitment, the activity is not; `comparative` = compares the company or its products with something outside them: an alternative, a competitor, an industry benchmark, an external goal or standard ("supports the goal of the Paris Agreement", "less carbon-intensive than air transport", "lower than the industry average"); a bare adjective like "cleaner" with nothing named to compare against is `vague_attribute`; `vague_attribute` = the claim rests on an unverifiable quality word or an unquantified comparative; `certification` = a third party's label, validation, ranking, score or award. When a claim is both a plan and vaguely worded, type it by its main proposition and put the vague word in `note`.

Scope, what the claim is about: `product` = products or services sold, including their use by customers; `packaging`; `operations` = the company's own sites and activities (Scope 1 and 2); `supply_chain` = suppliers and purchased goods; `company` = the whole company or its overall footprint; `other`. `scope_note` says the precise scope in words when the text narrows it (e.g. "operated assets only", "oil products only, gas and LNG excluded").

`quantity`, `baseline` and `timeframe` only as the text states them; leave them null otherwise. `attribute` is what is asserted, in a few words.

Example, for a text that said "We have cut our factories' water use by 30% since 2019 and aim to be water positive by 2030. Our bottles are made from plant-based plastic.":
- quote "cut our factories' water use by 30% since 2019", type comparative, scope operations, attribute "water use -30%", quantity "30%", baseline "2019";
- quote "aim to be water positive by 2030", type commitment, scope company, attribute "water positive", timeframe "2030";
- quote "Our bottles are made from plant-based plastic", type vague_attribute, scope packaging, attribute "plant-based plastic", note "Share of plant-based content not stated".

Return every claim, in document order."""

MAX_OUTPUT_TOKENS = 32000

# Effort for this stage. Measured on the Shell page on 2026-09-19 with Sonnet 5: medium found
# 24 of 25 golden claims at 80% precision with every type agreeing in 50 s; high found the same
# 24 at 83% precision in 143 s. After the present-tense rule was added to the prompt, medium found
# all 25 at 81% precision with 24 types agreeing in 50 s; runs vary by a claim or two. The team's
# global default (AUDITOR_EFFORT) stays high for the stages that reason; extraction is reading,
# and medium pays for itself in the demo.
EXTRACT_EFFORT = os.environ.get("AUDITOR_EXTRACT_EFFORT", "medium")

# One-to-one map so offsets into the normalised text are offsets into the original.
_NORMALISE = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"', "–": "-", "—": "-", "−": "-", "‐": "-", " ": " "})


def normalise(text: str) -> str:
    return text.translate(_NORMALISE)


def document_system(document: dict[str, Any]) -> str:
    """The stable, cacheable prefix every stage sends: the frame and the document itself."""
    title = document.get("title") or ""
    company = (document.get("company") or {}).get("name") or ""
    return f'{SYSTEM_FRAME}\n\n<document title="{title}" company="{company}">\n{document["text"]}\n</document>'


@dataclass
class Located:
    start: int
    end: int
    text: str
    occurrence: int | None = None

    def as_span(self) -> dict[str, Any]:
        span: dict[str, Any] = {"text": self.text, "start": self.start, "end": self.end}
        if self.occurrence is not None:
            span["occurrence"] = self.occurrence
        return span


def locate(text: str, quote: str, taken: list[tuple[int, int]] | None = None) -> Located | None:
    """Place a quote in the text: exactly, then with quotation marks and dashes normalised, then
    ignoring case; with a trailing full stop or surrounding quotation marks dropped if needed.
    Among several occurrences, the first not already taken by another span is preferred."""
    taken = taken or []
    quote = " ".join(quote.split())
    if not quote:
        return None
    # A sentence's final full stop is never part of a claim, so the stripped form is tried first.
    candidates: list[str] = []
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
            free = [h for h in hits if not any(h < t_end and h + len(needle) > t_start for t_start, t_end in taken)]
            start = (free or hits)[0]
            end = start + len(needle)
            exact = text[start:end]
            exact_hits = find_all(text, exact)
            occurrence = exact_hits.index(start) + 1 if len(exact_hits) > 1 and start in exact_hits else None
            return Located(start, end, exact, occurrence)
    return None


def paragraph_for(regions: list[dict[str, Any]], start: int, end: int) -> tuple[str | None, float | None]:
    """The innermost labelled paragraph region holding [start, end), and the prominence that
    applies there (the paragraph's, else its container's)."""
    best: dict[str, Any] | None = None
    prominence: float | None = None
    container: dict[str, Any] | None = None
    for r in regions:
        if not (r["start"] <= start and end <= r["end"]):
            continue
        if r["kind"] == "paragraph" and r.get("label"):
            if best is None or r["end"] - r["start"] < best["end"] - best["start"]:
                best = r
        elif r["kind"] in ("cautionary_note", "promo", "footnote", "quote"):
            if container is None or r["end"] - r["start"] < container["end"] - container["start"]:
                container = r
    if best is not None and best.get("prominence") is not None:
        prominence = best["prominence"]
    elif container is not None and container.get("prominence") is not None:
        prominence = container["prominence"]
    return (best["label"] if best else None), prominence


@dataclass
class ExtractResult:
    claims: list[dict[str, Any]]
    dropped: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


def assemble(extraction: Extraction, document: dict[str, Any], *, first_number: int = 1) -> ExtractResult:
    """Contract Claim objects from what the model returned, placed and numbered."""
    text = document["text"]
    regions = document.get("regions") or []
    taken: list[tuple[int, int]] = []
    built: list[dict[str, Any]] = []
    dropped: list[str] = []
    # Every primary span first, so that a repeat is never placed inside another claim's span
    # (the sentence "... by 15-20% by 2030" occurs in three claims; the repeat belongs to the one
    # that is nobody's primary).
    placed_primaries: list[tuple[ExtractedClaim, Located]] = []
    for item in extraction.claims:
        primary = locate(text, item.quote, taken)
        if primary is None:
            dropped.append(item.quote)
            continue
        taken.append((primary.start, primary.end))
        placed_primaries.append((item, primary))
    for item, primary in placed_primaries:
        spans = [primary]
        for repeat in item.repeats:
            placed = locate(text, repeat, taken)
            if placed is None or any(placed.start == s.start for s in spans):
                continue
            taken.append((placed.start, placed.end))
            spans.append(placed)
        claim: dict[str, Any] = {
            "id": "",
            "spans": [s.as_span() for s in spans],
            "type": item.type,
            "scope": item.scope,
            "attribute": (item.attribute or "").strip() or primary.text[:60],
        }
        for key in ("scope_note", "quantity", "baseline", "timeframe", "note"):
            value = getattr(item, key)
            if value and value.strip():
                claim[key] = value.strip()
        label, prominence = paragraph_for(regions, primary.start, primary.end)
        if label:
            claim["paragraph"] = label
        if prominence is not None:
            claim["prominence"] = prominence
        built.append(claim)
    built.sort(key=lambda c: (c["spans"][0]["start"], c["spans"][0]["end"]))
    for index, claim in enumerate(built):
        claim["id"] = f"C{first_number + index}"
    return ExtractResult(built, dropped)


async def extract_claims(
    document: dict[str, Any],
    llm: Llm | None = None,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> ExtractResult:
    """Run the extractor on an ingested document. Raises LlmError when the model cannot answer.

    `on_progress` is awaited with the running count as the model writes each claim. It is a
    heartbeat, not the live progression of D7: a claim's id follows its position in the
    document, which is only known once the whole list is in, so the claims themselves are still
    emitted together and in order by the caller. Without it the stage is silent for as long as
    the model takes, which on DeepSeek is over a minute of reasoning before the first word of
    the answer — long enough to read as a hang."""
    llm = llm or get_llm()
    found = 0

    async def on_element(key: str, item: dict[str, Any]) -> None:
        nonlocal found
        if key != "claims":
            return
        found += 1
        if on_progress is not None:
            await on_progress(found)

    extraction, usage = await llm.extract_streaming(
        TASK, Extraction, on_element=on_element, system=document_system(document), cache=True,
        max_tokens=MAX_OUTPUT_TOKENS, effort=EXTRACT_EFFORT,
    )
    result = assemble(extraction, document)
    result.usage = usage
    result.notes.append(f"The model returned {len(extraction.claims)} claims; {len(result.claims)} placed in the text" + (f", {len(result.dropped)} dropped because their quote is not in the document" if result.dropped else "") + f" ({usage.describe()})")
    for quote in result.dropped[:5]:
        result.notes.append(f"Dropped, not found verbatim: {quote[:120]!r}")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class Match:
    live_id: str
    reference_id: str
    overlap: float
    same_type: bool


@dataclass
class Comparison:
    matches: list[Match]
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
        agree = sum(1 for m in self.matches if m.same_type)
        text = (
            f"{len(self.matches)} of {self.reference_total} reference claims found (recall {self.recall:.0%}, precision {self.precision:.0%}); "
            f"type agrees on {agree} of {len(self.matches)}"
        )
        if self.missed:
            text += f"; missed {', '.join(self.missed)}"
        if self.extra:
            text += f"; new {', '.join(self.extra)}"
        return text


def _ranges(claim: dict[str, Any], text: str, old_text: str | None) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for span in claim.get("spans") or []:
        placed = anchor_span(text, span, old_text)
        if placed is not None:
            out.append((placed[0], placed[1]))
    return out


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    shorter = max(1, min(a[1] - a[0], b[1] - b[0]))
    return inter / shorter


def compare(live: list[dict[str, Any]], reference: list[dict[str, Any]], text: str, old_text: str | None = None, *, threshold: float = 0.5) -> Comparison:
    """Match live claims to reference claims by span overlap (share of the shorter span), one to
    one, best pairs first."""
    live_ranges = {c["id"]: _ranges(c, text, None) for c in live}
    ref_ranges = {c["id"]: _ranges(c, text, old_text) for c in reference}
    ref_types = {c["id"]: c.get("type") for c in reference}
    live_types = {c["id"]: c.get("type") for c in live}
    pairs: list[tuple[float, str, str]] = []
    for lid, lr in live_ranges.items():
        for rid, rr in ref_ranges.items():
            score = max((_overlap(a, b) for a in lr for b in rr), default=0.0)
            if score >= threshold:
                pairs.append((score, lid, rid))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    taken_live: set[str] = set()
    taken_ref: set[str] = set()
    matches: list[Match] = []
    for score, lid, rid in pairs:
        if lid in taken_live or rid in taken_ref:
            continue
        taken_live.add(lid)
        taken_ref.add(rid)
        matches.append(Match(lid, rid, round(score, 2), live_types[lid] == ref_types[rid]))
    matches.sort(key=lambda m: _claim_number(m.reference_id))
    return Comparison(
        matches=matches,
        missed=[c["id"] for c in reference if c["id"] not in taken_ref],
        extra=[c["id"] for c in live if c["id"] not in taken_live],
        reference_total=len(reference),
        live_total=len(live),
    )


def _claim_number(claim_id: str) -> int:
    digits = re.search(r"\d+", claim_id)
    return int(digits.group()) if digits else 0


# ----------------------------------------------------------------------------- CLI


def _print_claims(claims: list[dict[str, Any]]) -> None:
    for c in claims:
        primary = c["spans"][0]
        extra = f" (+{len(c['spans']) - 1} repeat{'s' if len(c['spans']) > 2 else ''})" if len(c["spans"]) > 1 else ""
        print(f"{c['id']:>4}  {c['type']:<16} {c['scope']:<12} {c.get('paragraph') or '':<4} {primary['text'][:110]!r}{extra}")
        details = ", ".join(f"{k} {c[k]}" for k in ("attribute", "quantity", "baseline", "timeframe", "scope_note") if c.get(k))
        if details:
            print(f"      {details}")


async def _main(args: argparse.Namespace) -> int:
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
    try:
        result = await extract_claims(document)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.claims, ensure_ascii=False, indent=2))
    else:
        _print_claims(result.claims)
    if args.golden:
        analysis = json.loads(Path(args.golden).read_text(encoding="utf-8"))
        comparison = compare(result.claims, analysis["claims"], document["text"], analysis["document"]["text"])
        print(f"\nagainst {Path(args.golden).name}: {comparison.describe()}")
        for m in comparison.matches:
            if not m.same_type:
                live = next(c for c in result.claims if c["id"] == m.live_id)
                ref = next(c for c in analysis["claims"] if c["id"] == m.reference_id)
                print(f"  type differs: {m.live_id} {live['type']} vs {m.reference_id} {ref['type']}: {live['spans'][0]['text'][:80]!r}")
        for rid in comparison.missed:
            ref = next(c for c in analysis["claims"] if c["id"] == rid)
            print(f"  missed {rid}: {ref['spans'][0]['text'][:100]!r}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.extract", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json to compare against")
    parser.add_argument("--json", action="store_true", help="print the claims as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
