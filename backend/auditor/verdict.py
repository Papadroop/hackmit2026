"""Verdict layer (roadmap step 17; design-doc D5 "Verdict layer" and D6): the debate, the
weakest-link combination, the confidence formula, the derived labels, the fix and the rewrite.

The four evaluators have scored every claim on Clarity, Support, Materiality and Consistency
and left behind the evidence they used. This stage turns that into the verdict the panel
shows. It is the one stage whose numbers are not a model's opinion:

1. **The debate (D5).** A prosecutor and a defence argue each claim from the same dossier —
   its words, its four scores with the one-sentence basis for each, its language marks, and
   every evidence item linked to it — in two calls that cannot see each other, so the case
   against a claim is not written by the same context that writes the case for it. Both are
   told to concede: a prosecutor with no case says so and cites nothing, a defence that cannot
   defend a claim gives the strongest point against it. Countering a detector's built-in bias
   toward accusation is the whole reason the debate exists.
2. **The arithmetic.** Likelihood is the maximum of the four dimension scores, exactly
   (weakest link, D6; CONTRACT.md §6): a claim that fails badly on one dimension is
   greenwashing whatever the others say. The category follows the contract's rules from the
   scores and the evidence relations. Neither is asked of the model.
3. **The judge.** It reads both arguments, the evidence and the derived verdict, and writes
   what the rule cannot: the rationale, the pattern tags, the fix and the honest rewrite. It
   is also asked to reach the category itself, from the evidence rather than from the rule;
   when it dissents the dissent is kept and the confidence falls.
4. **Confidence**, the formula CONTRACT.md §6 left to this step. It answers "how sure are we
   of this verdict", never "how bad is the claim":

       confidence = min(base, evidence cap) - humility - conflict - dissent - instability

   *base* is the confidence of the deciding dimension, the weakest link whose score is the
   likelihood, because that is the reading the verdict rests on; ties go to the least
   confident of the tied dimensions. *evidence cap* is what the evidence is worth: no evidence
   linked to the claim at all caps confidence at 0.55 ("no evidence found" lowers confidence,
   D6; it is not proof of greenwashing), and when the deciding dimension is one that rests on
   evidence from outside the text, the best tier reached caps it — 1.00 for a regulator ruling
   or a law, 0.65 for the company's own material. Clarity is read from the text, so no tier
   makes a vagueness reading surer. *conflict* is evaluator disagreement: 0.10 when evidence
   both supports and contradicts the same claim. *dissent* and *instability* are judge
   consistency: up to 0.10 when the judge did not reach the derived category itself, and,
   with `AUDITOR_VERDICT_SAMPLES` above 1, up to 0.10 more when repeated judges disagree with
   each other. *humility* is a flat 0.05, because no single evaluator decides a verdict. The
   result is clamped into the contract's bounds: never above the highest dimension confidence,
   never more than 0.1 below the lowest.

   Against the hand-assigned confidences of the golden reference the formula's mean absolute
   error is 0.04, with 23 of its 25 claims inside 0.10. `--calibrate` prints that table and
   calls no model.

Pattern tags are computed, not judged separately (D6): rules read candidates off the scores,
the language marks and the evidence relations, the judge keeps the ones the evidence bears out
and may add from the closed taxonomy. A claim the judge skips still gets a verdict, derived
with a rationale that says so, because the contract requires exactly one verdict per claim.

    python -m auditor.verdict <file or url> [--golden fixtures/shell-climate.analysis.json] [--json]
    python -m auditor.verdict --calibrate fixtures/shell-climate.analysis.json

With `--golden`, the reference's own claims, scores, evidence and marks are the input — no
other stage runs — and the result is compared with the reference's verdicts: category
agreement, likelihood and confidence error, and tag overlap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .extract import document_system
from .language import claims_listing, clamp01, combine_usage
from .llm import Llm, LlmError, Usage, get_llm

# CONTRACT.md §6. The same four names the contract's validator and the replay path use.
DIMENSIONS = ("clarity", "support", "materiality", "consistency")

# The dimensions that rest on evidence gathered from outside the text. Clarity is read from the
# words themselves, so what tier the evidence reached says nothing about how sure it is.
EVIDENCE_DIMENSIONS = ("support", "materiality", "consistency")

CATEGORIES = ("supported", "unsubstantiated", "misleading_by_framing", "contradicted")

# The seven sins plus greenrinsing, as the contract closes the list.
TAGS = (
    "hidden_trade_off", "no_proof", "vagueness", "irrelevance",
    "lesser_of_two_evils", "fibbing", "false_labels", "greenrinsing",
)

# Relations that bear on whether the claim holds, as opposed to setting the standard it is
# measured against (`criteria`, `precedent`) or filling in background (`context`).
DECISIVE_RELATIONS = ("supports", "contradicts", "contradicts_framing")

# The confidence formula's constants (see the module docstring; calibrated with --calibrate).
TIER_CAP = {1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75, 5: 0.65}
NO_EVIDENCE_CAP = 0.55
MISSING_DIMENSION_CAP = 0.5
HUMILITY = 0.05
CONFLICT_PENALTY = 0.10
DISSENT_PENALTY = 0.10
INSTABILITY_PENALTY = 0.10

DERIVED_RATIONALE = "Not judged by the verdict layer; the likelihood and the category are derived from the dimension scores by the contract's rules."

Emit = Callable[[str, dict[str, Any]], Any]


# ----------------------------------------------------------------------------- what the model returns


class Case(BaseModel):
    claim_id: str
    text: str = Field(description="The argument, two to four sentences, from the dossier alone.")
    evidence_ids: list[str] = Field(default_factory=list, description="The evidence the argument rests on, by id from this claim's dossier; empty when the argument rests on the wording alone or concedes there is no case.")


class Cases(BaseModel):
    cases: list[Case] = Field(description="Exactly one entry per claim under argument, in the list's order.")


class Judgment(BaseModel):
    claim_id: str
    rationale: str = Field(description="One to three sentences deciding the claim, weighing both arguments and naming the evidence that settles it.")
    tags: list[Literal[TAGS]] = Field(default_factory=list, description="The pattern names the finding matches; empty when none fits.")  # type: ignore[valid-type]
    fix: str = Field(default="", description="What evidence or rewording would make the claim legitimate, in one or two sentences.")
    rewrite: str = Field(default="", description="The claim as the evidence would allow it to be stated.")
    evidence_ids: list[str] = Field(default_factory=list, description="The evidence the verdict rests on, by id from this claim's dossier.")
    own_category: Literal[CATEGORIES] = Field(description="The category you would reach yourself on the evidence, independently of the derived one.")  # type: ignore[valid-type]
    own_likelihood: float = Field(description="Your own 0-to-1 reading of how far the claim misleads, independently of the derived likelihood.")
    dissent: str = Field(default="", description="One sentence on why you differ from the derived verdict; empty when you agree.")


class Judgments(BaseModel):
    judgments: list[Judgment] = Field(description="Exactly one entry per claim under judgment, in the list's order.")


# ----------------------------------------------------------------------------- the tasks


DOSSIER_NOTE = """Below is a dossier for each claim: its words and where they sit on the page, the four dimension scores the evaluators gave it with the one-sentence basis for each, the language marks found in its wording, and every evidence item gathered for it. A score is a problem score: 0 means no greenwashing signal on that dimension, 1 means maximal. Clarity asks whether the claim is specific and checkable, Support whether evidence backs it, Materiality how much of the real impact it addresses, Consistency whether the company says the same elsewhere and said the same before.

Argue from the dossier and from nothing else. Do not assert a fact that is not in it, and do not reach for a general impression of the industry in place of a citation. An evidence item whose quote is not shown was not verified against its source, so its wording cannot be quoted or relied on (citation integrity); its existence may still be named."""

PROSECUTE_TASK = f"""You are the prosecutor in an audit of environmental claims. For each claim below, make the case that it misleads a reasonable reader.

{DOSSIER_NOTE}

The audit's subject is the gap between the impression a claim gives and what is true, so the strongest case is rarely that a sentence is false. It is that the sentence is literally true and the impression is not: what a reader takes away, what the page leaves out beside it, what the company's own filing says, what the wording carefully avoids committing to, what the figure is a share of.

Where the evidence gives you no case, say so in one sentence and cite nothing. A prosecutor who accuses every claim is worth nothing to the judge, and the audit gives credit where it is due.

Return `cases`: one entry per claim in the list, in the list's order, each two to four sentences, with the ids of the evidence items it rests on. Cite only ids that appear in that claim's own dossier."""

DEFEND_TASK = f"""You are the defence in an audit of environmental claims. For each claim below, make the case that it is a fair statement fairly made.

{DOSSIER_NOTE}

The strongest defence is usually specific: the figure the page does give, the baseline or scope it does state, the standard or scheme it names, the qualification a reader can see, the assurance behind a number, the part of the claim that is plainly true and checkable. Where a claim is about the future, a target is not a promise and a plan that does not yet reach it is not a lie; say so where it is true.

Where the claim cannot be defended, do not pretend. Concede the strongest point against it in one sentence and defend only what can be defended. A defence that defends everything is worth nothing to the judge.

Return `cases`: one entry per claim in the list, in the list's order, each two to four sentences, with the ids of the evidence items it rests on. Cite only ids that appear in that claim's own dossier."""

TAXONOMY = """    hidden_trade_off — true of one attribute while the larger impact goes unmentioned
    no_proof — nothing a reader or a regulator could check
    vagueness — so broad or undefined that it cannot be wrong
    irrelevance — true and checkable, and of no consequence
    lesser_of_two_evils — true within a category that is itself the problem
    fibbing — the literal statement is false
    false_labels — the impression of third-party endorsement that does not exist, or a label the company awarded itself
    greenrinsing — a target quietly weakened, delayed or dropped before it was met"""

JUDGE_TASK = f"""You are the judge in an audit of environmental claims. A prosecutor and a defence have argued each claim below; decide it.

{DOSSIER_NOTE}

The verdict's two numbers are already fixed and are not yours to set. `Likelihood` is the largest of the four dimension scores, because a claim that fails badly on any one dimension is greenwashing whatever the others say. `Category` follows from the scores and the evidence relations by a written rule. Both are shown in the dossier under "Derived verdict". Your job is everything the rule cannot write:

- `rationale`: one to three sentences saying why the claim lands where it does. Weigh both arguments, name the evidence that settles it, and say which side's strongest point you are rejecting and why. A rationale that only repeats the prosecutor has not judged anything, and a claim the evidence clears should be said to be clear.
- `tags`: the patterns the finding matches, from this closed list. The dossier shows candidates read off the scores, the marks and the evidence; keep the ones the evidence bears out, drop the ones it does not, add any other that clearly applies. An empty list is better than a tag that does not fit. A tag names a way of misleading, so a claim the evidence supports carries none: where you would tag one, the disagreement belongs in `own_category` and `dissent`, not in the tags.
{TAXONOMY}
- `fix`: what evidence or rewording would make the claim legitimate, in one or two sentences, taken from the substantiation criteria in the dossier where there are any. Name the figure, baseline, scope, scheme or disclosure that is missing. "Be more transparent" is not a fix. Where the claim is already fair, say what keeps it fair.
- `rewrite`: the claim as the evidence in the dossier would allow it to be stated — same subject, same page, same voice, with the figures and qualifications the evidence supports, and no figure the dossier does not contain. Where the claim is already fair, the rewrite may be the claim itself. Write what an honest communications team would have published, not a confession.
- `evidence_ids`: the items the verdict rests on, most important first. Only ids from that claim's dossier.

Then, separately from all of that, reach the verdict yourself. `own_category` is the category you would give on the evidence alone if no rule existed; `own_likelihood` is your own 0-to-1 reading of how far the claim misleads; `dissent` is one sentence on why you differ, empty when you agree. Do not adjust your own reading toward the derived one. When the rule and a careful reader disagree the audit needs to know: a claim whose judge dissents is reported at lower confidence, and the disagreement is what the calibration step measures.

Return `judgments`: one entry per claim in the list, none twice, in the list's order."""

ARGUE_MAX_OUTPUT_TOKENS = 12000
JUDGE_MAX_OUTPUT_TOKENS = 16000

# Claims per call. Three calls run per batch (prosecutor, defence, judge), the batches in
# parallel, so this trades latency against how much of the page each call holds at once.
BATCH_SIZE = int(os.environ.get("AUDITOR_VERDICT_BATCH", "6"))

# Repeated judges, for the judge-consistency term of the confidence formula. One by default:
# the demo cannot afford three judges per claim, and the judge's own read against the rule
# already measures most of what repetition would.
SAMPLES = max(1, int(os.environ.get("AUDITOR_VERDICT_SAMPLES", "1")))

ARGUE_EFFORT = os.environ.get("AUDITOR_VERDICT_ARGUE_EFFORT", "medium")
JUDGE_EFFORT = os.environ.get("AUDITOR_VERDICT_EFFORT", "high")


# ----------------------------------------------------------------------------- the derivation (CONTRACT.md §6)


def derive_likelihood(scores: dict[str, dict[str, Any]]) -> float:
    """The weakest link: the largest of the claim's dimension scores (D6). Exact."""
    present = [scores[d]["score"] for d in DIMENSIONS if d in scores]
    return round(max(present), 2) if present else 0.5


def derive_category(scores: dict[str, dict[str, Any]], has_contradicting_evidence: bool) -> str:
    """CONTRACT.md §6, category rule, in its order. The one implementation; the replay path in
    `pipeline` and the contract's own validator check against this."""
    if any(d not in scores for d in DIMENSIONS):
        scores = {**{d: {"score": 0.0, "confidence": 0.0} for d in DIMENSIONS}, **scores}
    support, clarity, consistency = scores["support"], scores["clarity"], scores["consistency"]
    if has_contradicting_evidence and (
        (support["score"] >= 0.7 and support["confidence"] >= 0.6)
        or (consistency["score"] >= 0.7 and consistency["confidence"] >= 0.6)
    ):
        return "contradicted"
    if clarity["score"] >= 0.7:
        return "unsubstantiated"
    if 0.4 <= support["score"] <= 0.6 and support["confidence"] < 0.6:
        return "unsubstantiated"
    if max(scores[d]["score"] for d in DIMENSIONS) > 0.5:
        return "misleading_by_framing"
    return "supported"


def deciding_dimension(scores: dict[str, dict[str, Any]]) -> str | None:
    """The weakest link: the dimension whose score is the likelihood. Ties go to the least
    confident of the tied dimensions, because that is the reading the verdict is least sure
    of; a remaining tie goes to the contract's order."""
    present = [d for d in DIMENSIONS if d in scores]
    if not present:
        return None
    best = max(scores[d]["score"] for d in present)
    tied = [d for d in present if abs(scores[d]["score"] - best) < 1e-9]
    lowest = min(scores[d]["confidence"] for d in tied)
    return next(d for d in tied if abs(scores[d]["confidence"] - lowest) < 1e-9)


def best_tier(evidence: list[dict[str, Any]], claim_id: str) -> int | None:
    """The best (lowest) tier among the evidence that bears on whether the claim holds. Criteria
    and precedents set the standard rather than settle the facts, so they count only when
    nothing decisive was found."""
    tiers: dict[bool, list[int]] = {True: [], False: []}
    for item in evidence:
        relations = {l["relation"] for l in item.get("links", []) if l.get("target") == claim_id}
        if not relations:
            continue
        tiers[bool(relations & set(DECISIVE_RELATIONS))].append(int(item.get("tier", 5)))
    pool = tiers[True] or tiers[False]
    return min(pool) if pool else None


def verdict_confidence(
    scores: dict[str, dict[str, Any]],
    evidence: list[dict[str, Any]],
    claim_id: str,
    *,
    judge_agreement: float = 1.0,
    judge_stability: float = 1.0,
) -> tuple[float, str]:
    """How sure the verdict is, and one sentence saying what set it. The formula CONTRACT.md §6
    left to this step; the module docstring explains each term, `--calibrate` measures it."""
    present = [d for d in DIMENSIONS if d in scores]
    deciding = deciding_dimension(scores)
    if deciding is None:
        return 0.1, "No dimension was scored, so the verdict is derived at minimal confidence."
    base = float(scores[deciding]["confidence"])
    reasons = [f"{deciding} decides it at confidence {base:.2f}"]

    linked = [e for e in evidence if any(l.get("target") == claim_id for l in e.get("links", []))]
    tier = best_tier(evidence, claim_id)
    cap, cap_reason = 1.0, ""
    if not linked:
        cap, cap_reason = NO_EVIDENCE_CAP, f"no evidence was found for it, capping confidence at {NO_EVIDENCE_CAP:.2f}"
    elif deciding in EVIDENCE_DIMENSIONS and tier is not None and TIER_CAP[tier] < 1.0:
        cap, cap_reason = TIER_CAP[tier], f"its best evidence is tier {tier}, capping confidence at {TIER_CAP[tier]:.2f}"
    if cap_reason:
        reasons.append(cap_reason)
    if len(present) < len(DIMENSIONS):
        cap = min(cap, MISSING_DIMENSION_CAP)
        reasons.append(f"{', '.join(d for d in DIMENSIONS if d not in scores)} was not scored")

    relations = {l["relation"] for e in linked for l in e["links"] if l.get("target") == claim_id}
    conflict = CONFLICT_PENALTY if {"supports", "contradicts"} <= relations else 0.0
    if conflict:
        reasons.append("the evidence both supports and contradicts it")
    dissent = DISSENT_PENALTY * (1.0 - max(0.0, min(1.0, judge_agreement)))
    if dissent:
        reasons.append("the judge did not reach the same category")
    instability = INSTABILITY_PENALTY * (1.0 - max(0.0, min(1.0, judge_stability)))
    if instability:
        reasons.append("repeated judges disagreed")

    value = min(base, cap) - HUMILITY - conflict - dissent - instability
    # CONTRACT.md §6's bounds. A dimension nobody scored counts as confidence 0, so a missing
    # evaluator cannot hold the verdict's confidence up.
    confidences = [scores[d]["confidence"] if d in scores else 0.0 for d in DIMENSIONS]
    bounded = min(max(value, min(confidences) - 0.1), max(confidences))
    if bounded != value:
        reasons.append(f"held inside the range of its dimension confidences [{min(confidences):.2f}, {max(confidences):.2f}]")
    return clamp01(bounded), "; ".join(reasons).capitalize() + "."


def first_of(judgments: list[Judgment]) -> Judgment | None:
    """The sample whose words the verdict carries; the rest only count toward its stability."""
    return judgments[0] if judgments else None


def judge_consistency(judgments: list[Judgment], derived_category: str) -> tuple[float, float]:
    """(agreement with the rule, agreement among repeated judges), both 0 to 1."""
    if not judgments:
        return 1.0, 1.0
    with_rule = sum(1 for j in judgments if j.own_category == derived_category) / len(judgments)
    modal = Counter(j.own_category for j in judgments).most_common(1)[0][1] / len(judgments)
    return round(with_rule, 2), round(modal, 2)


def propose_tags(
    claim: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    signals: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[str]:
    """Candidate pattern tags read off the analysis: the labels are computed from the
    dimensions, the marks and the evidence relations, not judged separately (D6). The judge
    starts from these, keeps what the evidence bears out and may add from the taxonomy.
    `evidence` is the items linked to this claim, so an evaluator that has already named a
    pattern in `ext` (the archive's `greenrinsing`) is believed over a score threshold."""
    def score(dimension: str) -> float:
        return float(scores[dimension]["score"]) if dimension in scores else 0.0

    kinds = {s.get("kind") for s in signals if s.get("polarity") != "credit"}
    relations = {l["relation"] for e in evidence for l in e.get("links", []) if l.get("target") == claim["id"]}
    kind = claim.get("type")
    tags: list[str] = []
    if score("clarity") >= 0.6:
        tags.append("vagueness")
    if not evidence or (score("support") >= 0.6 and "supports" not in relations):
        tags.append("no_proof")
    if score("materiality") >= 0.6 or "contradicts_framing" in relations or kinds & {"share_of_attention", "buried_admission"}:
        tags.append("hidden_trade_off")
    if score("materiality") >= 0.7 and score("support") <= 0.3:
        tags.append("irrelevance")
    if (kind == "comparative" and score("materiality") >= 0.6) or (score("materiality") >= 0.75 and "contradicts_framing" in relations):
        tags.append("lesser_of_two_evils")
    if kind in ("factual", "comparative") and "contradicts" in relations and score("support") >= 0.7:
        tags.append("fibbing")
    if kind == "certification" and score("support") >= 0.5:
        tags.append("false_labels")
    # Not a claim type: a target weakened before it was met shows up as a high Consistency
    # problem score whether the sentence reads as a commitment or as a fact about one. The
    # self-consistency evaluator (step 15) marks the archived capture that proves it, which is
    # the exact signal; the score is the fallback for a page with no capture to compare.
    if any((e.get("ext") or {}).get("greenrinsing") for e in evidence) or score("consistency") >= 0.6:
        tags.append("greenrinsing")
    return tags


# ----------------------------------------------------------------------------- what the model sees


def index_scores(scores: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_claim: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for score in scores:
        if score.get("dimension") in DIMENSIONS:
            by_claim[score["claim_id"]][score["dimension"]] = score
    return by_claim


def index_signals(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        for claim_id in signal.get("claim_ids") or []:
            by_claim[claim_id].append(signal)
    return by_claim


def index_evidence(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        # One item can link the same claim twice (supports the letter, contradicts the
        # framing); it is one card in the panel and one line in the dossier.
        for target in dict.fromkeys(l["target"] for l in item.get("links") or [] if l.get("target")):
            by_claim[target].append(item)
    return by_claim


def evidence_lines(items: list[dict[str, Any]], claim_id: str) -> list[str]:
    """One evidence item per two lines, with its relation to this claim. An unverified quote is
    never shown (D5 citation integrity); the item is still named."""
    lines = []
    for item in items:
        relations = ", ".join(sorted({l["relation"] for l in item.get("links", []) if l.get("target") == claim_id}))
        head = f"  {item['id']} [tier {item.get('tier', '?')} {item.get('kind', 'other')}] {item.get('source', {}).get('name', '')}"
        if item.get("source", {}).get("locator"):
            head += f" — {item['source']['locator']}"
        head += f" — {relations or 'linked'}"
        body = item.get("quote") or item.get("note") or ""
        if not item.get("verified", False) and item.get("kind") != "computation":
            body = "(quote not verified, so not shown) " + (item.get("note") or "")
        lines.append(head)
        if body.strip():
            lines.append(f"     {' '.join(body.split())[:600]}")
    return lines


def signal_line(signals: list[dict[str, Any]]) -> str:
    parts = []
    for signal in signals:
        words = (signal.get("spans") or [{}])[0].get("text", "")
        polarity = signal.get("polarity", "flag")
        mark = f"{signal.get('kind', '?')} {json.dumps(words, ensure_ascii=False)}" if words else str(signal.get("kind", "?"))
        parts.append(mark if polarity == "flag" else f"{mark} ({polarity})")
    return "; ".join(parts) or "none"


def claim_dossier(
    claim: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    signals: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    *,
    tags: list[str] | None = None,
    derived: tuple[float, str] | None = None,
    arguments: dict[str, str] | None = None,
) -> str:
    """One claim as every role reads it. The judge's copy adds the suggested tags, the derived
    verdict and both arguments; the two advocates see neither the derivation nor each other."""
    prominence = claim.get("prominence")
    head = " | ".join([
        claim["id"], str(claim.get("type", "?")), str(claim.get("scope", "?")),
        f"paragraph {claim.get('paragraph') or '?'}",
        f"prominence {prominence}" if prominence is not None else "prominence unknown",
    ])
    lines = [f"=== {head}", f'Words: {json.dumps(claim["spans"][0]["text"], ensure_ascii=False)}']
    if claim.get("note"):
        lines.append(f"Extractor's note: {claim['note']}")
    lines.append("Scores:")
    for dimension in DIMENSIONS:
        score = scores.get(dimension)
        if score is None:
            lines.append(f"  {dimension:<12} not scored")
        else:
            lines.append(f"  {dimension:<12} {score['score']:.2f}  confidence {score['confidence']:.2f}  {score.get('basis', '')}")
            gap = (score.get("ext") or {}).get("gap")
            if gap:
                lines.append(f"  {'':<12} gap: {gap}")
    lines.append(f"Language marks: {signal_line(signals)}")
    lines.append("Evidence:" if evidence else "Evidence: none was found for this claim.")
    lines.extend(evidence_lines(evidence, claim["id"]))
    if tags is not None:
        lines.append(f"Suggested tags: {', '.join(tags) or 'none'}")
    if derived is not None:
        likelihood, category = derived
        deciding = deciding_dimension(scores)
        lines.append(f"Derived verdict: likelihood {likelihood:.2f} (weakest link: {deciding}), category {category}")
    for role in ("prosecutor", "defence"):
        if arguments and arguments.get(role):
            lines.append(f"{role.capitalize()}: {arguments[role]}")
    return "\n".join(lines)


def dossiers(
    batch: list[dict[str, Any]],
    scores: dict[str, dict[str, dict[str, Any]]],
    signals: dict[str, list[dict[str, Any]]],
    evidence: dict[str, list[dict[str, Any]]],
    **kwargs: Any,
) -> str:
    return "\n\n".join(
        claim_dossier(claim, scores.get(claim["id"], {}), signals.get(claim["id"], []), evidence.get(claim["id"], []), **kwargs)
        for claim in batch
    ) or "(no claims)"


def rest_of_page(batch: list[dict[str, Any]], claims: list[dict[str, Any]], verb: str) -> str:
    """The claims this call is not responsible for, listed so a batch is not read as the whole
    page: a claim reads differently beside the five around it."""
    ids = {c["id"] for c in batch}
    rest = [c for c in claims if c["id"] not in ids]
    if not rest:
        return ""
    return f"\n\n<page>\nThe other claims found on the page, for context only; {verb} only the ones above.\n{claims_listing(rest)}\n</page>"


def argue_prompt(role: str, batch: list[dict[str, Any]], scores, signals, evidence, claims: list[dict[str, Any]]) -> str:
    task = PROSECUTE_TASK if role == "prosecutor" else DEFEND_TASK
    prompt = f"{task}\n\n<dossiers>\n{dossiers(batch, scores, signals, evidence)}\n</dossiers>"
    return prompt + rest_of_page(batch, claims, "argue")


def judge_prompt(batch: list[dict[str, Any]], scores, signals, evidence, tags, derived, arguments, claims: list[dict[str, Any]]) -> str:
    blocks = []
    for claim in batch:
        blocks.append(claim_dossier(
            claim, scores.get(claim["id"], {}), signals.get(claim["id"], []), evidence.get(claim["id"], []),
            tags=tags.get(claim["id"], []), derived=derived.get(claim["id"]), arguments=arguments.get(claim["id"], {}),
        ))
    body = "\n\n".join(blocks) if blocks else "(no claims)"
    return f"{JUDGE_TASK}\n\n<dossiers>\n{body}\n</dossiers>" + rest_of_page(batch, claims, "judge")


# ----------------------------------------------------------------------------- assembly


@dataclass
class VerdictResult:
    arguments: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    placeholders: list[str] = field(default_factory=list)
    dissents: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)


class Assembler:
    """Turns cases and judgments into contract entities one at a time, emitting each as it is
    built, so the streaming and the batch paths share one code path."""

    def __init__(
        self,
        claims: list[dict[str, Any]],
        scores: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        signals: list[dict[str, Any]] | None = None,
        emit: Emit | None = None,
    ) -> None:
        self.claims = {c["id"]: c for c in claims}
        self.order = [c["id"] for c in claims]
        self.scores = index_scores(scores)
        self.signals = index_signals(signals or [])
        self.evidence = index_evidence(evidence)
        self.all_evidence = evidence
        self.known_evidence = {e["id"] for e in evidence}
        self.emit = emit
        self.arguments: list[dict[str, Any]] = []
        self.verdicts: list[dict[str, Any]] = []
        self.argued: set[tuple[str, str]] = set()
        self.judged: set[str] = set()
        self.placeholders: list[str] = []
        self.dissents: list[str] = []
        self.untagged: list[str] = []
        self.unknown_claims = 0
        self.unknown_evidence = 0
        self.repeated = 0

    # -- the derivation, per claim

    def contradicted(self, claim_id: str) -> bool:
        return any(
            l.get("relation") == "contradicts"
            for item in self.evidence.get(claim_id, [])
            for l in item.get("links", [])
            if l.get("target") == claim_id
        )

    def derived(self, claim_id: str) -> tuple[float, str]:
        scores = self.scores.get(claim_id, {})
        return derive_likelihood(scores), derive_category(scores, self.contradicted(claim_id))

    def candidate_tags(self, claim_id: str) -> list[str]:
        claim = self.claims.get(claim_id)
        if claim is None:
            return []
        return propose_tags(claim, self.scores.get(claim_id, {}), self.signals.get(claim_id, []), self.evidence.get(claim_id, []))

    def _emit(self, type_: str, payload: dict[str, Any]) -> None:
        if self.emit is not None:
            self.emit(type_, payload)

    def _cited(self, claim_id: str, ids: list[str]) -> list[str]:
        """The evidence ids that exist and bear on this claim, deduplicated in the order given.
        Nothing is referenced before it exists (contract §2, rule 3), and a verdict cannot
        point the panel at an item that is not in the claim's own evidence."""
        linked = {item["id"] for item in self.evidence.get(claim_id, [])}
        out: list[str] = []
        for eid in ids:
            if eid in linked and eid not in out:
                out.append(eid)
            elif eid not in linked:
                self.unknown_evidence += 1
        return out

    # -- the two advocates

    def add_case(self, case: Case, role: str) -> dict[str, Any] | None:
        if case.claim_id not in self.claims:
            self.unknown_claims += 1
            return None
        if (case.claim_id, role) in self.argued:
            self.repeated += 1
            return None
        text = " ".join(case.text.split())
        if not text:
            return None
        argument: dict[str, Any] = {"claim_id": case.claim_id, "role": role, "text": text}
        cited = self._cited(case.claim_id, case.evidence_ids)
        if cited:
            argument["evidence_ids"] = cited
        self.argued.add((case.claim_id, role))
        self.arguments.append(argument)
        self._emit("argument.made", {"argument": argument})
        return argument

    # -- the judge

    def add_judgment(self, judgments: list[Judgment], claim_id: str) -> dict[str, Any] | None:
        """One verdict from however many judge samples the claim got. The likelihood and the
        category are derived; the judge supplies the words and, through its own read, part of
        the confidence."""
        if claim_id not in self.claims:
            self.unknown_claims += 1
            return None
        if claim_id in self.judged:
            self.repeated += 1
            return None
        first = first_of(judgments)
        likelihood, category = self.derived(claim_id)
        agreement, stability = judge_consistency(judgments, category)
        confidence, basis = verdict_confidence(
            self.scores.get(claim_id, {}), self.all_evidence, claim_id,
            judge_agreement=agreement, judge_stability=stability,
        )
        # A pattern tag names a way of misleading; a supported verdict says the claim does not
        # mislead. The two together read as a contradiction in the panel, and the golden
        # reference carries no tag on any of its ten supported claims.
        tags = [t for t in TAGS if first is not None and t in first.tags]
        if tags and category == "supported":
            self.untagged.append(f"{claim_id} ({', '.join(tags)})")
            tags = []
        verdict: dict[str, Any] = {
            "claim_id": claim_id,
            "likelihood": likelihood,
            "confidence": confidence,
            "category": category,
            "tags": tags,
            "rationale": " ".join(first.rationale.split()) if first and first.rationale.strip() else DERIVED_RATIONALE,
        }
        if first is not None:
            if first.fix.strip():
                verdict["fix"] = " ".join(first.fix.split())
            if first.rewrite.strip():
                verdict["rewrite"] = " ".join(first.rewrite.split())
            cited = self._cited(claim_id, first.evidence_ids)
            if cited:
                verdict["evidence_ids"] = cited
        ext: dict[str, Any] = {"confidence_basis": basis}
        if first is not None:
            ext["judge"] = {
                "own_category": first.own_category,
                "own_likelihood": clamp01(first.own_likelihood),
                "agreement": agreement,
            }
            if len(judgments) > 1:
                ext["judge"]["samples"] = len(judgments)
                ext["judge"]["stability"] = stability
            if first.dissent.strip():
                ext["judge"]["dissent"] = " ".join(first.dissent.split())
            if agreement < 1.0:
                self.dissents.append(f"{claim_id} rule {category} / judge {first.own_category}")
        else:
            self.placeholders.append(claim_id)
        verdict["ext"] = ext
        self.judged.add(claim_id)
        self.verdicts.append(verdict)
        self._emit("verdict.issued", {"verdict": verdict})
        return verdict

    def finish(self) -> VerdictResult:
        for claim_id in self.order:
            if claim_id not in self.judged:
                self.add_judgment([], claim_id)
        result = VerdictResult(self.arguments, self.verdicts, self.placeholders, self.dissents)
        distribution = Counter(v["category"] for v in self.verdicts)
        result.notes.append(
            f"{len(self.verdicts)} verdicts ("
            + ", ".join(f"{distribution[c]} {c}" for c in CATEGORIES if distribution[c])
            + f"), {len(self.arguments)} arguments"
            + (f"; {len(self.placeholders)} derived without a judge: {', '.join(self.placeholders[:10])}" if self.placeholders else "")
            + (f"; {self.repeated} repeated cases or judgments ignored" if self.repeated else "")
            + (f"; {self.unknown_claims} unknown claim ids ignored" if self.unknown_claims else "")
            + (f"; {self.unknown_evidence} citations of evidence not linked to the claim dropped" if self.unknown_evidence else "")
        )
        if self.untagged:
            result.notes.append(f"{len(self.untagged)} supported claims had their pattern tags dropped, because a supported verdict names no pattern: {'; '.join(self.untagged[:8])}")
        if self.dissents:
            result.notes.append(f"The judge dissented from the derived category on {len(self.dissents)} claims, which lowers their confidence: {'; '.join(self.dissents[:8])}")
        missing = [cid for cid in self.order if len(self.scores.get(cid, {})) < len(DIMENSIONS)]
        if missing:
            absent = sorted({d for cid in missing for d in DIMENSIONS if d not in self.scores.get(cid, {})})
            result.notes.append(f"{len(missing)} claims were judged without all four dimensions ({', '.join(absent)} missing); their likelihood is the weakest link of what exists and their confidence is capped at {MISSING_DIMENSION_CAP}")
        return result


def apply_verdicts(
    prosecution: Cases,
    defence: Cases,
    judgments: Judgments,
    claims: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    signals: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
) -> VerdictResult:
    """The batch path: whole results at once (tests and fakes), in contract order — both
    arguments for a claim, then its verdict."""
    assembler = Assembler(claims, scores, evidence, signals, emit)
    for case in prosecution.cases:
        assembler.add_case(case, "prosecutor")
    for case in defence.cases:
        assembler.add_case(case, "defence")
    by_claim: dict[str, list[Judgment]] = defaultdict(list)
    for judgment in judgments.judgments:
        by_claim[judgment.claim_id].append(judgment)
    for claim_id, group in by_claim.items():
        assembler.add_judgment(group, claim_id)
    return assembler.finish()


# ----------------------------------------------------------------------------- the stage


async def issue_verdicts(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    signals: list[dict[str, Any]] | None = None,
    *,
    emit: Emit | None = None,
    llm: Llm | None = None,
    samples: int | None = None,
) -> VerdictResult:
    """Debate and decide every claim, emitting each argument and verdict as it arrives. The
    prosecutor and the defence run in parallel and cannot see each other; the judge reads both.
    Raises LlmError when the model cannot answer."""
    assembler = Assembler(claims, scores, evidence, signals, emit)
    if not claims:
        return assembler.finish()
    llm = llm or get_llm()
    samples = max(1, samples if samples is not None else SAMPLES)
    system = document_system(document)
    size = max(1, BATCH_SIZE)
    batches = [claims[i : i + size] for i in range(0, len(claims), size)]
    started = time.perf_counter()
    usages: list[Usage] = []
    returned = {"cases": 0, "judgments": 0, "invalid": 0, "out_of_batch": 0}
    first: list[float] = []

    async def argue(role: str, batch: list[dict[str, Any]], into: dict[str, str]) -> None:
        ids = {c["id"] for c in batch}
        seen: set[str] = set()

        def hand(case: Case) -> None:
            seen.add(case.claim_id)
            if assembler.add_case(case, role) and not first:
                first.append(time.perf_counter() - started)
            into[case.claim_id] = " ".join(case.text.split())

        async def on_element(key: str, item: dict[str, Any]) -> None:
            if key != "cases":
                return
            try:
                case = Case.model_validate(item)
            except ValidationError:
                returned["invalid"] += 1
                return
            if case.claim_id not in ids:
                returned["out_of_batch"] += 1
            elif case.claim_id not in seen:
                hand(case)

        result, usage = await llm.extract_streaming(
            argue_prompt(role, batch, assembler.scores, assembler.signals, assembler.evidence, claims),
            Cases, on_element=on_element, system=system, cache=True,
            max_tokens=ARGUE_MAX_OUTPUT_TOKENS, effort=ARGUE_EFFORT,
        )
        # Whatever the stream did not hand over, by id rather than by position: a malformed
        # element must not shift the catch-up past a claim nobody argued.
        for case in result.cases:
            if case.claim_id in ids and case.claim_id not in seen:
                hand(case)
        returned["cases"] += len(result.cases)
        usages.append(usage)

    async def judge(batch: list[dict[str, Any]], arguments: dict[str, dict[str, str]]) -> None:
        ids = {c["id"] for c in batch}
        tags = {c["id"]: assembler.candidate_tags(c["id"]) for c in batch}
        derived = {c["id"]: assembler.derived(c["id"]) for c in batch}
        prompt = judge_prompt(batch, assembler.scores, assembler.signals, assembler.evidence, tags, derived, arguments, claims)
        collected: dict[str, list[Judgment]] = defaultdict(list)
        lock = asyncio.Lock()

        async def run_sample(streaming: bool) -> None:
            seen: set[str] = set()

            async def record(judgment: Judgment) -> None:
                seen.add(judgment.claim_id)
                async with lock:
                    collected[judgment.claim_id].append(judgment)
                    # The last sample to arrive decides the claim, so every judge is counted.
                    if len(collected[judgment.claim_id]) == samples:
                        assembler.add_judgment(collected[judgment.claim_id], judgment.claim_id)

            async def on_element(key: str, item: dict[str, Any]) -> None:
                if key != "judgments":
                    return
                try:
                    judgment = Judgment.model_validate(item)
                except ValidationError:
                    returned["invalid"] += 1
                    return
                if judgment.claim_id not in ids:
                    returned["out_of_batch"] += 1
                elif judgment.claim_id not in seen:
                    await record(judgment)

            call = llm.extract_streaming(prompt, Judgments, on_element=on_element, system=system, cache=True,
                                         max_tokens=JUDGE_MAX_OUTPUT_TOKENS, effort=JUDGE_EFFORT) if streaming else \
                llm.extract(prompt, Judgments, system=system, cache=True, max_tokens=JUDGE_MAX_OUTPUT_TOKENS, effort=JUDGE_EFFORT)
            result, usage = await call
            for judgment in result.judgments:
                if judgment.claim_id in ids and judgment.claim_id not in seen:
                    await record(judgment)
            returned["judgments"] += len(result.judgments)
            usages.append(usage)

        try:
            async with asyncio.TaskGroup() as group:
                for i in range(samples):
                    group.create_task(run_sample(streaming=i == 0))
        except* LlmError as errors:
            raise errors.exceptions[0]
        # A claim some samples skipped is decided on the samples it got, once they are all in.
        for claim_id, group_ in collected.items():
            if claim_id not in assembler.judged:
                assembler.add_judgment(group_, claim_id)

    async def run_batch(batch: list[dict[str, Any]]) -> None:
        arguments: dict[str, dict[str, str]] = defaultdict(dict)
        prosecution: dict[str, str] = {}
        defence: dict[str, str] = {}
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(argue("prosecutor", batch, prosecution))
                group.create_task(argue("defence", batch, defence))
        except* LlmError as errors:
            # Unwrap here so the stage's own handler sees an LlmError, not a group of groups.
            raise errors.exceptions[0]
        for claim_id, text in prosecution.items():
            arguments[claim_id]["prosecutor"] = text
        for claim_id, text in defence.items():
            arguments[claim_id]["defence"] = text
        await judge(batch, arguments)

    try:
        async with asyncio.TaskGroup() as group:
            for batch in batches:
                group.create_task(run_batch(batch))
    except* LlmError as errors:
        raise errors.exceptions[0]
    result = assembler.finish()
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = (
        f"The model argued {returned['cases']} cases and judged {returned['judgments']} claims over "
        f"{len(batches)} batches of up to {size} claims"
        + (f", each judged {samples} times" if samples > 1 else "")
    )
    if first:
        note += f" (first argument after {first[0]:.1f} s)"
    if returned["invalid"]:
        note += f", {returned['invalid']} malformed"
    if returned["out_of_batch"]:
        note += f", {returned['out_of_batch']} for claims outside their call ignored"
    result.notes.insert(0, note + f" ({result.usage.describe()})")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class VerdictComparison:
    pairs: list[tuple[str, dict[str, Any], dict[str, Any]]]
    missing: list[str]

    @property
    def same_category(self) -> list[str]:
        return [cid for cid, live, ref in self.pairs if live["category"] == ref["category"]]

    @property
    def likelihood_error(self) -> float:
        return sum(abs(live["likelihood"] - ref["likelihood"]) for _, live, ref in self.pairs) / len(self.pairs) if self.pairs else 0.0

    @property
    def confidence_error(self) -> float:
        return sum(abs(live["confidence"] - ref["confidence"]) for _, live, ref in self.pairs) / len(self.pairs) if self.pairs else 0.0

    def tag_overlap(self) -> tuple[int, int, int]:
        """(tags both gave, tags only the live run gave, tags only the reference gave)."""
        both = only_live = only_ref = 0
        for _, live, ref in self.pairs:
            a, b = set(live.get("tags", [])), set(ref.get("tags", []))
            both += len(a & b)
            only_live += len(a - b)
            only_ref += len(b - a)
        return both, only_live, only_ref

    def describe(self) -> str:
        if not self.pairs:
            return "no reference verdicts to compare"
        both, only_live, only_ref = self.tag_overlap()
        text = (
            f"{len(self.same_category)} of {len(self.pairs)} categories agree, "
            f"mean absolute likelihood difference {self.likelihood_error:.2f}, confidence {self.confidence_error:.2f}, "
            f"{both} tags shared ({only_live} only live, {only_ref} only reference)"
        )
        if self.missing:
            text += f", {len(self.missing)} reference claims without a verdict"
        return text


def compare_verdicts(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> VerdictComparison:
    """Live verdicts against a reference's, by claim id."""
    by_id = {v["claim_id"]: v for v in live}
    pairs, missing = [], []
    for ref in reference:
        got = by_id.get(ref["claim_id"])
        if got is None:
            missing.append(ref["claim_id"])
        else:
            pairs.append((ref["claim_id"], got, ref))
    return VerdictComparison(pairs, missing)


def calibrate(analysis: dict[str, Any]) -> list[tuple[str, float, float, str]]:
    """The confidence formula run on an analysis's own scores and evidence, against the
    confidences that analysis records: (claim id, reference, formula, deciding dimension).
    Calls no model, so it can be re-run after any change to the constants."""
    scores = index_scores(analysis.get("scores", []))
    evidence = analysis.get("evidence", [])
    rows = []
    for verdict in analysis.get("verdicts", []):
        claim_id = verdict["claim_id"]
        value, _ = verdict_confidence(scores.get(claim_id, {}), evidence, claim_id)
        rows.append((claim_id, float(verdict["confidence"]), value, deciding_dimension(scores.get(claim_id, {})) or "none"))
    return rows


def calibration_report(rows: list[tuple[str, float, float, str]]) -> str:
    if not rows:
        return "no verdicts to calibrate against"
    errors = [formula - reference for _, reference, formula, _ in rows]
    inside = sum(1 for e in errors if abs(e) <= 0.1)
    return (
        f"confidence formula against {len(rows)} reference verdicts: "
        f"mean absolute error {sum(abs(e) for e in errors) / len(errors):.3f}, "
        f"bias {sum(errors) / len(errors):+.3f}, worst {max(abs(e) for e in errors):.2f}, "
        f"{inside} of {len(rows)} inside 0.10"
    )


def check_derivation(analysis: dict[str, Any]) -> list[str]:
    """The likelihood and category rules re-derived from an analysis's own scores, against the
    verdicts it records. Empty when they agree; this is what the contract's validator checks."""
    scores = index_scores(analysis.get("scores", []))
    contradicted = {
        l["target"] for e in analysis.get("evidence", []) for l in e.get("links", []) if l.get("relation") == "contradicts"
    }
    problems = []
    for verdict in analysis.get("verdicts", []):
        claim_id = verdict["claim_id"]
        per_claim = scores.get(claim_id, {})
        likelihood = derive_likelihood(per_claim)
        category = derive_category(per_claim, claim_id in contradicted)
        if abs(likelihood - verdict["likelihood"]) > 1e-9:
            problems.append(f"{claim_id}: likelihood {verdict['likelihood']} but the rule derives {likelihood}")
        if category != verdict["category"]:
            problems.append(f"{claim_id}: category {verdict['category']} but the rule derives {category}")
    return problems


# ----------------------------------------------------------------------------- command line


def _print_argument(argument: dict[str, Any]) -> None:
    cited = ",".join(argument.get("evidence_ids", []))
    print(f"{argument['claim_id']:>4}  {argument['role']:<10} [{cited}] {argument['text'][:150]}")


def _print_verdict(verdict: dict[str, Any]) -> None:
    judge = (verdict.get("ext") or {}).get("judge") or {}
    dissent = f"  (judge said {judge['own_category']})" if judge.get("own_category") and judge["own_category"] != verdict["category"] else ""
    print(
        f"{verdict['claim_id']:>4}  {verdict['category']:<22} likelihood {verdict['likelihood']:<5} confidence {verdict['confidence']:<5}"
        f" [{','.join(verdict.get('tags', [])) or '-'}]{dissent}\n      {verdict['rationale'][:200]}"
    )
    if verdict.get("rewrite"):
        print(f"      rewrite: {verdict['rewrite'][:200]}")


async def _main(args: argparse.Namespace) -> int:
    from .ingest import IngestError, ingest_file, ingest_url
    from .language import reanchored_claims

    analysis = json.loads(Path(args.golden).read_text(encoding="utf-8")) if args.golden else None
    if args.calibrate:
        reference = analysis or json.loads(Path(args.calibrate).read_text(encoding="utf-8"))
        rows = calibrate(reference)
        print(f"{'claim':>6}  {'reference':>9}  {'formula':>7}  {'error':>6}  deciding")
        for claim_id, ref_value, value, deciding in rows:
            flag = "   <--" if abs(value - ref_value) > 0.1 else ""
            print(f"{claim_id:>6}  {ref_value:>9.2f}  {value:>7.2f}  {value - ref_value:>+6.2f}  {deciding}{flag}")
        print("\n" + calibration_report(rows))
        for problem in check_derivation(reference):
            print(f"derivation: {problem}")
        return 0

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
        if analysis is not None:
            claims = reanchored_claims(analysis["claims"], document["text"], analysis["document"]["text"])
            scores, evidence, signals = analysis["scores"], analysis["evidence"], analysis.get("signals", [])
            print(f"using the reference's {len(claims)} claims, {len(scores)} scores and {len(evidence)} evidence items as input", file=sys.stderr)
        else:
            claims, scores, evidence, signals = await _run_upstream(document)
    except (IngestError, LlmError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    def emit(type_: str, payload: dict[str, Any]) -> None:
        if args.json:
            return
        if type_ == "argument.made":
            _print_argument(payload["argument"])
        else:
            _print_verdict(payload["verdict"])

    try:
        result = await issue_verdicts(document, claims, scores, evidence, signals, emit=emit, samples=args.samples)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps({"arguments": result.arguments, "verdicts": result.verdicts}, ensure_ascii=False, indent=2))
    if analysis is not None:
        comparison = compare_verdicts(result.verdicts, analysis["verdicts"])
        print(f"\nagainst {Path(args.golden).name}: {comparison.describe()}")
        for claim_id, live, ref in comparison.pairs:
            if live["category"] != ref["category"] or abs(live["confidence"] - ref["confidence"]) > 0.15:
                print(f"  {claim_id:>4} live {live['category']:<22} {live['likelihood']:.2f}/{live['confidence']:.2f}   reference {ref['category']:<22} {ref['likelihood']:.2f}/{ref['confidence']:.2f}")
    return 0


async def _run_upstream(document: dict[str, Any]) -> tuple[list, list, list, list]:
    """Everything the verdict layer needs, from the stages that are built. Consistency (step 15)
    and omissions (step 16) are not among them yet, so the verdicts this path prints are the
    weakest link of the three dimensions that exist; `--golden` is the measured check."""
    from .extract import extract_claims
    from .language import review_language
    from .substantiate import substantiate
    from .verify import verify

    extracted = await extract_claims(document)
    claims = extracted.claims
    review = await review_language(document, claims)
    substantiation = await substantiate(document, claims, score=False)
    verification = await verify(document, claims, prior_evidence=substantiation.evidence)
    print(f"upstream: {len(claims)} claims, {len(review.signals)} marks, {len(substantiation.evidence) + len(verification.evidence)} evidence items", file=sys.stderr)
    print("upstream: consistency (step 15) has not been built, so it is missing from every claim", file=sys.stderr)
    return claims, [*review.scores, *verification.scores], [*substantiation.evidence, *verification.evidence], review.signals


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.verdict", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims, scores, evidence and marks are the input and its verdicts the reference")
    parser.add_argument("--calibrate", nargs="?", const="", help="print the confidence formula against an analysis.json's own confidences and call no model")
    parser.add_argument("--samples", type=int, help=f"judges per claim, for the judge-consistency term (default {SAMPLES})")
    parser.add_argument("--json", action="store_true", help="print the arguments and verdicts as JSON")
    args = parser.parse_args(argv)
    if args.calibrate == "":
        args.calibrate = args.golden
    if not args.calibrate and not args.source:
        parser.error("a source is required unless --calibrate names an analysis.json")
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
