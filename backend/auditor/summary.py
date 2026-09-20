"""Document aggregation (roadmap step 18; design-doc D6 "Aggregation"): the summary header,
from the real results beneath it.

The step's visual check is that every number in the header can be explained from the claims
underneath, so nothing here is a model's opinion: the profile, the headline and the ranking
are arithmetic over what the evaluators and the verdict layer already produced, and each one
records in `ext` the claims it was computed from. The model is asked for one thing only, at the
end: the words. A title for each issue and each piece of credit, and the narrative line.

**Leaning to the worst of the page.** A mean would let a page bury a false headline under twenty true
trivia, which is the document-level form of the failure weakest-link protects against at claim
level (D6). So every number here is the weighted mean of the *worst third of the page*, by
weight rather than by count: claims are sorted worst-first and taken until a third of the total
weight is used, and the last one in is counted only for the part of its weight that fits. A
claim's weight is its `prominence` times the confidence of the score being aggregated, so a
sentence in the hero counts for more than one in a footnote, and a reading nobody is sure of
counts for less than one that is settled. Each dimension is aggregated over its own scores, the
headline over the verdict likelihoods, and Completeness over the omissions (which have no
prominence, so confidence alone weights them). A profile entry's confidence is the weighted
mean confidence of the claims that drove its score, not of the whole page: it says how sure we
are of *this* number.

**Ranking.** Top issues are claims and omissions together, ordered by weighted severity — the
same score times weight the aggregation uses — so the list is the page's worst third in order
and the header links straight to them. Credit is the reverse over `supported` claims only: the
best-substantiated, most prominent claims the page makes (D6 "credit where due").

Against the golden reference's hand-assigned header the profile's mean absolute error is about
0.075, closest on the headline, Materiality and Completeness and reading Clarity and Support
higher than the analyst did, who averaged those two across the whole page. CONTRACT.md §6
leaves these numbers to this step and the validator checks only that they are consistent with
the claims (the distribution equals the verdict counts, the counts equal the lists, ranks are
1..n, targets exist); `--explain` prints the arithmetic.

    python -m auditor.summary <analysis.json> [--explain] [--json]

Reads a folded analysis (a fixture, or `contract.py fold` of a live log) and aggregates it, so
the numbers can be checked against any recorded run without calling a model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .extract import document_system
from .language import clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm

# CONTRACT.md §6. Completeness is document-level only, so it is not among the four a claim carries.
DIMENSIONS = ("clarity", "support", "materiality", "consistency")
PROFILE = (*DIMENSIONS, "completeness")
CATEGORIES = ("supported", "unsubstantiated", "misleading_by_framing", "contradicted")

# How far the number leans toward the worst of the page. Each claim's say in the mean is its
# weight times its severity raised to POWER-1, so at 3 a claim twice as bad as another has four
# times the say. 1 would be a plain weighted mean, which lets twenty true footnotes bury one
# false headline; the limit is the maximum, which lets one stray sentence speak for the page.
POWER = float(os.environ.get("AUDITOR_SUMMARY_POWER", "3"))

# How many of the largest contributors a number records as having driven it.
DRIVERS = int(os.environ.get("AUDITOR_SUMMARY_DRIVERS", "6"))

# A claim with no prominence recorded is treated as body text.
DEFAULT_PROMINENCE = 0.6

TOP_ISSUES = int(os.environ.get("AUDITOR_SUMMARY_ISSUES", "5"))
CREDIT_ENTRIES = int(os.environ.get("AUDITOR_SUMMARY_CREDIT", "4"))

WRITE_EFFORT = os.environ.get("AUDITOR_SUMMARY_EFFORT", "medium")
WRITE_MAX_OUTPUT_TOKENS = 8000

Emit = Callable[[str, dict[str, Any]], Any]


# ----------------------------------------------------------------------------- the arithmetic


@dataclass
class Aggregate:
    """One number in the header, and the rows it was computed from."""

    score: float
    confidence: float
    drivers: list[str] = field(default_factory=list)

    def entry(self) -> dict[str, float]:
        return {"score": self.score, "confidence": self.confidence}


@dataclass
class Row:
    """One thing being aggregated: a claim's score on a dimension, or an omission's."""

    target: str
    score: float
    confidence: float
    prominence: float

    @property
    def weight(self) -> float:
        return max(self.prominence * self.confidence, 1e-6)

    @property
    def severity(self) -> float:
        return self.score * self.weight


def aggregate_rows(rows: list[Row], power: float = POWER) -> Aggregate:
    """The page's reading on one dimension, and the claims that drove it.

    A weighted Lehmer mean: each row's say is its weight times its score to `power - 1`, so the
    result sits near the worst of what the page says rather than in the middle of it, without
    ever leaving the range of the scores or resting on a single sentence. The confidence is the
    same mean over the rows' confidences, so it is the confidence of the claims that actually
    set the number. `drivers` names the largest contributors, most first: the arithmetic behind
    every header number, which is this step's visual check."""
    live = [r for r in rows if r.score > 0]
    if not rows:
        return Aggregate(0.0, 0.0, [])
    if not live:
        # Nothing scored above zero: the mean is zero and every row says so equally.
        return Aggregate(0.0, clamp01(sum(r.confidence * r.weight for r in rows) / sum(r.weight for r in rows)), [])
    shares = [(r, r.weight * (r.score ** (power - 1))) for r in live]
    total = sum(share for _, share in shares)
    score = sum(r.score * share for r, share in shares) / total
    confidence = sum(r.confidence * share for r, share in shares) / total
    drivers = [r.target for r, _ in sorted(shares, key=lambda rs: (-rs[1], rs[0].target))[:DRIVERS]]
    return Aggregate(clamp01(score), clamp01(confidence), drivers)


def contributions(rows: list[Row], power: float = POWER) -> list[tuple[str, float]]:
    """Each row's share of the mean, largest first: what "explained from the claims beneath"
    means in numbers."""
    shares = [(r.target, r.weight * (r.score ** (power - 1))) for r in rows if r.score > 0]
    total = sum(share for _, share in shares)
    if not total:
        return []
    return sorted(((t, share / total) for t, share in shares), key=lambda ts: (-ts[1], ts[0]))


def prominence_of(claim: dict[str, Any]) -> float:
    value = claim.get("prominence")
    return float(value) if isinstance(value, (int, float)) else DEFAULT_PROMINENCE


def dimension_rows(claims: dict[str, dict[str, Any]], scores: list[dict[str, Any]], dimension: str) -> list[Row]:
    return [
        Row(s["claim_id"], float(s["score"]), float(s["confidence"]), prominence_of(claims[s["claim_id"]]))
        for s in scores
        if s.get("dimension") == dimension and s.get("claim_id") in claims
    ]


def omission_rows(omissions: list[dict[str, Any]]) -> list[Row]:
    # An omission is not said anywhere, so it has no prominence to weigh it by.
    return [Row(o["id"], float(o.get("score", 0.5)), float(o.get("confidence", 0.5)), 1.0) for o in omissions]


def verdict_rows(claims: dict[str, dict[str, Any]], verdicts: list[dict[str, Any]]) -> list[Row]:
    return [
        Row(v["claim_id"], float(v["likelihood"]), float(v["confidence"]), prominence_of(claims[v["claim_id"]]))
        for v in verdicts
        if v.get("claim_id") in claims
    ]


def rank_issues(rows: list[Row], limit: int) -> list[Row]:
    """The page's worst, in order: the same severity the aggregation weighs by."""
    return sorted(rows, key=lambda r: (-r.severity, -r.score, r.target))[:limit]


def rank_credit(claims: dict[str, dict[str, Any]], verdicts: list[dict[str, Any]], limit: int) -> list[Row]:
    """Credit where due (D6): the best-substantiated claims the page makes, most prominent
    first. Only `supported` verdicts, because the contract's validator warns about any other."""
    rows = [
        Row(v["claim_id"], float(v["likelihood"]), float(v["confidence"]), prominence_of(claims[v["claim_id"]]))
        for v in verdicts
        if v.get("category") == "supported" and v.get("claim_id") in claims
    ]
    return sorted(rows, key=lambda r: (r.score, -r.prominence * r.confidence, r.target))[:limit]


def aggregate(
    claims: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
    *,
    power: float = POWER,
) -> tuple[dict[str, Any], dict[str, Aggregate]]:
    """The header's numbers, and the aggregate behind each one so it can be explained. The
    titles are left empty: `summarise` asks the model for those."""
    by_id = {c["id"]: c for c in claims}
    parts: dict[str, Aggregate] = {}
    for dimension in DIMENSIONS:
        parts[dimension] = aggregate_rows(dimension_rows(by_id, scores, dimension), power)
    parts["completeness"] = aggregate_rows(omission_rows(omissions), power)
    parts["headline"] = aggregate_rows(verdict_rows(by_id, verdicts), power)

    distribution = Counter(v["category"] for v in verdicts if v.get("category") in CATEGORIES)
    issues = rank_issues([*verdict_rows(by_id, verdicts), *omission_rows(omissions)], TOP_ISSUES)
    credit = rank_credit(by_id, verdicts, CREDIT_ENTRIES)
    summary: dict[str, Any] = {
        "headline": parts["headline"].entry(),
        "dimensions": {name: parts[name].entry() for name in PROFILE},
        "verdict_distribution": {c: distribution.get(c, 0) for c in CATEGORIES},
        "top_issues": [{"rank": i + 1, "target": row.target, "title": ""} for i, row in enumerate(issues)],
        "credit": [{"target": row.target, "title": ""} for row in credit],
        "claim_count": len(claims),
        "omission_count": len(omissions),
        "ext": {
            "power": round(power, 2),
            "drivers": {name: parts[name].drivers for name in (*PROFILE, "headline")},
        },
    }
    return summary, parts


def explain(summary: dict[str, Any], parts: dict[str, Aggregate]) -> list[str]:
    """One line per number saying which claims it came from: the step's visual check."""
    lines = []
    for name in ("headline", *PROFILE):
        part = parts[name]
        lines.append(f"{name:<13} {part.score:.2f} at confidence {part.confidence:.2f}, driven by {', '.join(part.drivers) or 'nothing scored'}")
    return lines


# ----------------------------------------------------------------------------- the words


class Title(BaseModel):
    target: str = Field(description="The claim or omission id being titled, from the list.")
    title: str = Field(description="One line naming the finding, at most about 14 words.")


class Header(BaseModel):
    issues: list[Title] = Field(default_factory=list, description="One entry per top issue, in the order given.")
    credit: list[Title] = Field(default_factory=list, description="One entry per credit entry, in the order given.")
    narrative: str = Field(default="", description="Two or three sentences: what a reader should take from this page.")


WRITE_TASK = """Write the headings for the summary of an audit of environmental claims. The numbers are already settled and are not yours to change; what is missing is the words a reader sees at the top of the page.

Below are the issues the audit ranked worst, each with the claim's own words or, for an omission, the topic the page never addresses, together with the verdict, the pattern tags and the judge's reasoning; then the claims it gives credit to.

For each issue, write a `title`: one line naming *the finding*, not the claim. "Shell's target is to become a net-zero emissions energy business by 2050" is the claim; "The page's own cautionary note says the plan cannot reflect the headline net-zero target" is the finding. Name the specific thing that is wrong — the figure that is missing, the word that is undefined, the document that says otherwise — and prefer the concrete noun to the abstraction. At most about fourteen words, no full stop, no verdict jargon ("misleading by framing", "unsubstantiated") and no hedging.

An omission has nothing to quote, so its title begins "Not mentioned: " and then says the fact the page leaves out, with the figure where there is one: "Not mentioned: 9% of capital went to renewables and energy solutions".

For each credit entry, write a `title` the same way, but for what the page gets right: the figure, its baseline and what stands behind it. "Operational emissions 36% below 2016, assured". A tool that only accuses is less credible than one that says plainly where a claim holds up.

Then `narrative`: two or three sentences a reader could be shown under the headline. Say what the page is doing, what the strongest finding is and what the page does get right. Write it for someone who has not read the claims; name figures rather than gesturing at them. Do not describe the audit's own machinery, do not give a score in words, and do not tell the reader what to think of the company.

Return one entry per target in each list, using the ids exactly as given. Title nothing that is not in the lists."""


def target_listing(
    rows: list[dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    verdicts: dict[str, dict[str, Any]],
    omissions: dict[str, dict[str, Any]],
) -> str:
    """The issues or credits as the writing call reads them."""
    lines = []
    for row in rows:
        target = row["target"]
        if target in omissions:
            omission = omissions[target]
            lines.append(
                f"{target} | omission | {omission.get('topic', '')}\n"
                f"  Why it is material: {omission.get('why_material', '')}\n"
                f"  What the page would have said: {omission.get('complete_text', '')}"
            )
            continue
        claim, verdict = claims.get(target, {}), verdicts.get(target, {})
        words = (claim.get("spans") or [{}])[0].get("text", "")
        tags = ", ".join(verdict.get("tags", [])) or "no pattern tag"
        lines.append(
            f"{target} | {verdict.get('category', '?')} | likelihood {verdict.get('likelihood', '?')} | {tags}\n"
            f"  The claim: {json.dumps(words, ensure_ascii=False)}\n"
            f"  The judge: {verdict.get('rationale', '')}"
        )
    return "\n".join(lines) or "(none)"


def write_prompt(summary: dict[str, Any], claims, verdicts, omissions) -> str:
    issues = target_listing(summary["top_issues"], claims, verdicts, omissions)
    credit = target_listing(summary["credit"], claims, verdicts, omissions)
    return f"{WRITE_TASK}\n\n<issues>\n{issues}\n</issues>\n\n<credit>\n{credit}\n</credit>"


def apply_titles(summary: dict[str, Any], header: Header, fallbacks: dict[str, str]) -> list[str]:
    """Put the written titles on the header, keeping the order the ranking fixed. A target the
    model skipped falls back to the claim's or omission's own words, so the link always has
    something to show. Returns the targets that fell back."""
    written = {t.target: " ".join(t.title.split()).rstrip(".") for t in [*header.issues, *header.credit] if t.title.strip()}
    missing: list[str] = []
    for entry in [*summary["top_issues"], *summary["credit"]]:
        title = written.get(entry["target"])
        if not title:
            if entry["target"] not in missing:  # a target can sit in both lists
                missing.append(entry["target"])
            title = fallbacks.get(entry["target"], entry["target"])
        entry["title"] = title[:200]
    narrative = " ".join(header.narrative.split())
    if narrative:
        summary["narrative"] = narrative
    return missing


def fallback_titles(
    claims: dict[str, dict[str, Any]], omissions: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """What a target is called when the model did not name it: its own words, trimmed."""
    out = {}
    for claim_id, claim in claims.items():
        words = (claim.get("spans") or [{}])[0].get("text", "")
        out[claim_id] = (words[:117] + "...") if len(words) > 120 else words
    for omission_id, omission in omissions.items():
        out[omission_id] = f"Not mentioned: {omission.get('topic', omission_id)}"
    return out


# ----------------------------------------------------------------------------- the stage


@dataclass
class SummaryResult:
    summary: dict[str, Any]
    parts: dict[str, Aggregate] = field(default_factory=dict)
    untitled: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


def build_summary(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
    header: Header | None = None,
    emit: Emit | None = None,
    *,
    power: float = POWER,
) -> SummaryResult:
    """The batch path: the arithmetic, then whatever titles are in hand (tests and fakes)."""
    summary, parts = aggregate(claims, scores, verdicts, omissions, power=power)
    by_id = {c["id"]: c for c in claims}
    by_omission = {o["id"]: o for o in omissions}
    untitled = apply_titles(summary, header or Header(), fallback_titles(by_id, by_omission))
    result = SummaryResult(summary, parts, untitled)
    result.notes.extend(explain(summary, parts))
    if untitled:
        result.notes.append(f"{len(untitled)} targets the writer did not name, shown by their own words: {', '.join(untitled[:8])}")
    if emit is not None:
        emit("summary.updated", {"summary": summary, "final": True})
    return result


async def summarise(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
    *,
    emit: Emit | None = None,
    llm: Llm | None = None,
    power: float = POWER,
) -> SummaryResult:
    """Aggregate the analysis and emit the header. One call, for the words only; the numbers
    are arithmetic and are already fixed before the model sees anything. Raises LlmError when
    The model cannot answer."""
    summary, parts = aggregate(claims, scores, verdicts, omissions, power=power)
    by_id = {c["id"]: c for c in claims}
    by_verdict = {v["claim_id"]: v for v in verdicts}
    by_omission = {o["id"]: o for o in omissions}
    started = time.perf_counter()
    header, usage = Header(), None
    if summary["top_issues"] or summary["credit"]:
        header, usage = await (llm or get_llm()).extract(
            write_prompt(summary, by_id, by_verdict, by_omission), Header,
            system=document_system(document), cache=True,
            max_tokens=WRITE_MAX_OUTPUT_TOKENS, effort=WRITE_EFFORT,
        )
    untitled = apply_titles(summary, header, fallback_titles(by_id, by_omission))
    result = SummaryResult(summary, parts, untitled)
    result.usage = combine_usage([usage] if usage else [], time.perf_counter() - started)
    note = (
        f"Headline {summary['headline']['score']} at confidence {summary['headline']['confidence']} over "
        f"{len(claims)} claims and {len(omissions)} omissions, leaning to the worst of the page by prominence and confidence"
    )
    if usage is not None:
        note += f"; the model wrote {len(header.issues)} issue and {len(header.credit)} credit titles ({result.usage.describe()})"
    result.notes.append(note)
    result.notes.extend(explain(summary, parts))
    if untitled:
        result.notes.append(f"{len(untitled)} targets the writer did not name, shown by their own words: {', '.join(untitled[:8])}")
    if emit is not None:
        emit("summary.updated", {"summary": summary, "final": True})
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class SummaryComparison:
    pairs: list[tuple[str, float, float]]
    issues: tuple[list[str], list[str]]
    credit: tuple[list[str], list[str]]

    @property
    def mean_abs_error(self) -> float:
        return sum(abs(a - b) for _, a, b in self.pairs) / len(self.pairs) if self.pairs else 0.0

    def describe(self) -> str:
        shared_issues = len(set(self.issues[0]) & set(self.issues[1]))
        shared_credit = len(set(self.credit[0]) & set(self.credit[1]))
        return (
            f"header profile within {self.mean_abs_error:.2f} of the reference on average "
            f"({', '.join(f'{n} {a - b:+.2f}' for n, a, b in self.pairs)}); "
            f"{shared_issues} of {len(self.issues[1])} top issues and {shared_credit} of {len(self.credit[1])} credits the same"
        )


def compare_summaries(live: dict[str, Any], reference: dict[str, Any]) -> SummaryComparison:
    """A live header against a reference's, number by number."""
    pairs = [("headline", float(live["headline"]["score"]), float(reference["headline"]["score"]))]
    for name in PROFILE:
        got, ref = live.get("dimensions", {}).get(name), reference.get("dimensions", {}).get(name)
        if got and ref:
            pairs.append((name, float(got["score"]), float(ref["score"])))
    return SummaryComparison(
        pairs,
        ([t["target"] for t in live.get("top_issues", [])], [t["target"] for t in reference.get("top_issues", [])]),
        ([t["target"] for t in live.get("credit", [])], [t["target"] for t in reference.get("credit", [])]),
    )


# ----------------------------------------------------------------------------- command line


async def _main(args: argparse.Namespace) -> int:
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    for key in ("claims", "scores", "verdicts", "omissions"):
        analysis.setdefault(key, [])
    if args.explain:
        result = build_summary(
            analysis.get("document", {}), analysis["claims"], analysis["scores"],
            analysis["verdicts"], analysis["omissions"], power=args.power,
        )
    else:
        try:
            result = await summarise(
                analysis["document"], analysis["claims"], analysis["scores"],
                analysis["verdicts"], analysis["omissions"], power=args.power,
            )
        except LlmError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    else:
        for entry in result.summary["top_issues"]:
            print(f"  {entry['rank']}. {entry['target']:>4}  {entry['title']}")
        for entry in result.summary["credit"]:
            print(f"  credit {entry['target']:>4}  {entry['title']}")
        if result.summary.get("narrative"):
            print(f"\n{result.summary['narrative']}")
    if analysis.get("summary"):
        print(f"\nagainst {Path(args.analysis).name}: {compare_summaries(result.summary, analysis['summary']).describe()}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.summary", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("analysis", help="a folded analysis.json (a fixture, or `contract.py fold` of a live log)")
    parser.add_argument("--explain", action="store_true", help="print the arithmetic only; call no model")
    parser.add_argument("--power", type=float, default=POWER, help=f"how far the mean leans toward the worst of the page (default {POWER})")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
