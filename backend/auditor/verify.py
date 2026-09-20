"""External verification (roadmap step 14; design-doc D5 "External verification" and D6 Support
and Materiality): do independent data agree, do the numbers check out, and is every quote
really on the page it is attributed to?

Three things happen here, and the third is what makes the first two worth showing.

1. **Live retrieval.** Claude reads the document (the cached prefix every stage sends) and the
   claims, and searches the web for the evidence that would settle them: the company's audited
   or assured filings, government and intergovernmental data, independent datasets and
   standards, regulator rulings. The search and the fetch run on Anthropic's servers
   (`llm.web_tools`); what comes back is a source with a URL and a verbatim quote.
2. **Citation integrity.** Nothing Claude quotes is believed. Every URL is fetched from here
   (`knowledge.page_text`, the same reader the store check uses) and the quote looked for in
   the page with whitespace, quotation marks and dashes normalised and case ignored
   (`knowledge.quote_in`). Found: `verified`, `fetched_exact`, the quote is displayed. Not
   found, or the page cannot be read: the item is kept and listed by name, its quote dropped,
   and the run says so. **An unverified quote is never displayed** (D5).
3. **Numbers recomputed.** A second call turns the retrieved figures into the arithmetic the
   claims turn on: the share of the footprint a target covers, a capital expenditure split, a
   stated percentage checked against its inputs, the pace a target needs against the pace
   achieved. Claude writes the expression, the inputs and the number it makes them; this
   module evaluates the expression itself (plain arithmetic, no names but the inputs) and
   drops any computation whose arithmetic does not reproduce the number, or whose sentence
   does not state it. A computation is evidence (`kind: computation`), so "we recomputed this"
   is visible in the panel, and its tier is never better than its worst input.

Then Support and Materiality are scored per claim from everything now on the table: the
criteria and precedents the substantiation evaluator matched (step 13) and the facts retrieved
here. Support is scored once, in this stage, because that is the dimension's definition (D6:
"Substantiation and external verification"); Materiality is this evaluator's alone, and rests
on proportionality — what share of the real impact the claim addresses. A claim the model
skips gets a neutral placeholder at low confidence, so the verdict rules always have both.

    python -m auditor.verify <file or url> [--golden fixtures/shell-climate.analysis.json] [--json]
    python -m auditor.verify --check-quote <url> "<quote>"

The second form is the citation check on its own: it answers whether that quote is on that
page, which is what "open three evidence links by hand" and "feed in a fake quote" mean.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import operator
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
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
SourceKind = Literal["filing", "report", "dataset", "standard", "company_page", "press_release", "news", "archive", "law", "ruling", "other"]
Independence = Literal["regulator", "assured_filing", "government", "independent", "news", "company"]

# D5's reliability ladder, and the whole reason tier is not the model's to choose: the tier
# follows from who stands behind the source, not from how useful it is to the argument.
TIERS: dict[str, int] = {"regulator": 1, "assured_filing": 2, "government": 2, "independent": 3, "news": 4, "company": 5}


class Bearing(BaseModel):
    claim_id: str = Field(description="A claim id from the list.")
    relation: Relation = Field(description="From that claim's point of view: supports or contradicts the literal content, contradicts_framing when the content stands but the impression does not, context for background or scale.")


class Finding(BaseModel):
    kind: SourceKind = Field(description="What the source is.")
    independence: Independence = Field(description="Who stands behind it: regulator (a ruling, judgment or law), assured_filing (an audited or assured annual report, 20-F or GHG statement), government (a government or intergovernmental body's data), independent (a third-party dataset, standard or assessment), news, company (the company's own material, including its unassured reports and pages).")
    name: str = Field(description="The source, as a reader would cite it: the document and the part of it.")
    publisher: str = Field(default="", description="Who published it.")
    date: str = Field(default="", description="Publication or decision date, ISO where known.")
    locator: str = Field(default="", description="Page, paragraph, section or case reference.")
    url: str = Field(description="The page the quote is on. It will be fetched and the quote looked for.")
    quote: str = Field(description="One or two contiguous sentences, word for word from that page.")
    bears_on: list[Bearing] = Field(description="The claims this bears on, each with its own relation: one source can support one claim and contradict the framing of another.")
    note: str = Field(default="", description="One sentence: what this settles about the claims, or what it does not.")


class Findings(BaseModel):
    findings: list[Finding] = Field(description="The evidence found, most decisive first; nothing for a claim where nothing was found.")


class Computation(BaseModel):
    name: str = Field(description="What is being checked, as a title.")
    expression: str = Field(description="Plain arithmetic over the input names and numbers: + - * / ( ), for example '(y2021 - y2025) / y2021 * 100'. It is evaluated here and the result must equal `value`.")
    inputs: dict[str, float] = Field(description="Every name in the expression, with the number the evidence gives for it.")
    value: float = Field(description="What the expression comes to.")
    unit: str = Field(default="", description="The unit of the value: '%', 'Mt', 'points per year', or empty.")
    sentence: str = Field(description="One sentence stating the result, with the number in it, as the panel will show it.")
    derived_from: list[str] = Field(description="The evidence ids the inputs were read from; empty when every figure is printed in the document under analysis.")
    bears_on: list[Bearing] = Field(description="The claims this number bears on, each with its own relation.")
    stated: float | None = Field(default=None, description="The number the document itself states, when this checks one; leave out otherwise.")


class Computations(BaseModel):
    computations: list[Computation] = Field(description="The numbers worth recomputing, in the order they matter.")


class Assessment(BaseModel):
    claim_id: str
    support: float = Field(description="The Support problem score, 0 to 1, from the bands in the task.")
    support_confidence: float = Field(description="0 to 1: how far the evidence settles the question.")
    support_basis: str = Field(description="One sentence naming the evidence that decides it.")
    support_evidence_ids: list[str] = Field(default_factory=list, description="The evidence the Support score rests on.")
    materiality: float = Field(description="The Materiality problem score, 0 to 1, from the bands in the task.")
    materiality_confidence: float
    materiality_basis: str = Field(description="One sentence: what share of the real impact this claim addresses.")
    materiality_evidence_ids: list[str] = Field(default_factory=list)
    gap: str = Field(default="", description="What the text would have to show for the claim to stand as written, in one sentence; empty when it already does.")


class Assessments(BaseModel):
    assessments: list[Assessment] = Field(description="Exactly one entry per claim under review, in the list's order.")


# ----------------------------------------------------------------------------- the tasks

RETRIEVE_TASK = """Find the evidence that would settle these claims, and quote it word for word.

Below are the claims found in the document, each with its id, type, scope, paragraph, prominence and words. Search the web for the independent facts a careful auditor would look up, and open the pages you find.

What to look for, in this order:
- The company's audited or assured filings: the annual report, the 20-F or equivalent, the GHG statement and its assurance opinion. These carry the figures a claim on the page is measured against: totals, baselines, segment splits, the scope of a target, the assurance level.
- Government and intergovernmental data, and independent datasets, standards and assessments (Transition Pathway Initiative, CDP, the Science Based Targets initiative, sector standards, UNEP programmes) that rate or measure this company.
- Regulator rulings, judgments and law about this company's environmental claims, when a search turns them up.
- The company's own material last, and only for what it admits: a page or unassured report of its own can give context or contradict the company, but it can never substantiate the company's own claim.

What makes a finding useful here: a number that lets a figure on the page be checked, a scope the page leaves out, a total the page's share can be measured against, an independent assessment of the same target, a plan the page says exists. A general statement that the company takes climate change seriously settles nothing; do not return it.

Rules about quotes, which decide whether a finding can be shown at all:
- The quote must be one or two contiguous sentences copied word for word from the page at the URL you give. Every quote is fetched from that URL and looked for in the page after this call. A quote that is not found is not displayed, so the finding is wasted.
- Do not paraphrase, do not stitch two passages together with an ellipsis, do not tidy the punctuation, and do not write a quote from memory: open the page and copy it.
- Give the URL of the page the quote is actually on, not a landing page or a search result.
- Quote from something whose text can be read: an HTML page or a PDF. A spreadsheet, an image, a video or a download that needs a login cannot be checked from here, so a quote from one is thrown away however good it is. Where a filing is published both as a data file and as a readable document, give the readable one.
- A number in a table is often not a sentence. Quote the sentence around it where there is one; where there is not, quote the row as the page prints it.
- Do not cite a regulator's ruling on this very document; rulings on this page are held out of the analysis deliberately.

Return `findings`: one entry per source and quote, with `bears_on` naming the claims it bears on and the relation to each of them separately — one filing can support one claim and contradict the framing of another. Say what the source is (`kind`) and who stands behind it (`independence`); the reliability tier is derived from `independence` here, not chosen by you. Aim for the two or three findings that decide each claim, not a reading list; one source may bear on several claims. Return nothing for a claim where the search found nothing, and do not fill the gap with the company's marketing."""

COMPUTE_TASK = """Recompute the numbers these claims turn on.

Below are the claims, then the evidence gathered so far with its ids: the criteria and precedents matched to each claim, and the sources retrieved for them with their quotes. The document itself is above.

The arithmetic worth doing, where the evidence supports it:
- **Proportionality**: what share of the company's reported footprint does the claim's scope cover? A target on operations (Scope 1 and 2) against total reported emissions including Scope 3 is the classic one, and it is what Materiality turns on.
- **Absolute versus intensity**: an intensity figure falling while the absolute number rises, or a percentage that is true only per unit. Compute both where both are available.
- **Checking a stated figure**: the page says "around 70%", "18%", "a third". Recompute it from the inputs in the evidence and say whether it holds. Put the page's own number in `stated`.
- **Pace against a target**: what has been delivered per year so far, and what is needed per year for the rest. A target that needs twice the pace ever achieved is worth the two lines it takes to show it.
- **Composition**: the split of capital expenditure, sales or production between the parts of the business the claim is about and the parts it is not.

Rules, which decide whether a computation can be shown at all:
- `expression` is plain arithmetic over the names in `inputs` — `+ - * / ( )` and numbers, nothing else. It is evaluated here after this call, and a computation whose expression does not come to `value` is dropped, as is one whose `sentence` does not state that number. Do the arithmetic before you write the number down.
- Every input must be a figure that appears in the evidence listed below or in the document under analysis. `derived_from` names the evidence ids the figures came from — the ids in the evidence listing, `V`, `N`, `K` and `P` as printed there. A paragraph label in the claims list (`P4`, `P7`) is not an evidence id. A computation whose figures are all printed in the document under analysis names nothing in `derived_from`, and is worth doing: the page's own numbers are exactly what proportionality and pace are computed from. It simply carries the document's own reliability rather than a filing's.
- Say the result in one plain sentence with the number and its unit in it, as a reader will see it: "Scope 1 and 2 (53 Mt) are 4.7% of total reported emissions (1,118 Mt)."
- Do not compute what the page already states and the evidence confirms outright, unless the point is that the page's number is wrong.

Return `computations`: the handful that change how a claim reads. Six to twelve for a page with figures on it; fewer where the page has none."""

SCORE_TASK = """Score each claim's Support and Materiality from all the evidence now on the table.

Below are the claims to score, then the evidence with its ids: the criteria the substantiation evaluator matched (K ids, the rules a claim of this kind is measured against), the precedents it matched (P ids, rulings on similar wording), the sources retrieved for this document (V ids, with whether the quote was verified on the page) and the numbers recomputed from them (N ids). Read the document too: what a claim shows may sit in a footnote or a neighbouring sentence.

**Support** is a problem score on whether the evidence backs the claim, 0 to 1. Bands:
- 0.05 to 0.2: independent or assured evidence confirms the claim as stated, with its scope and baseline, and no rule or ruling counts against it.
- 0.3 to 0.4: the substance holds with a gap a reader could close from the page or the filings.
- 0.4 to 0.6, with confidence below 0.6: the criteria require substantiation nothing found gives, either way. Nothing found is not proof; it lowers confidence.
- 0.6 to 0.7: the claim's form needs a disclosure the text omits and a precedent found that form misleading, or the retrieved facts leave the claim standing only on a reading the page does not offer.
- 0.7 to 0.85: independent evidence contradicts the impression the claim gives, or a ruling found the same wording misleading for this company.
- 0.85 to 1.0: tier 1 to 3 evidence contradicts what the claim literally says. Only evidence about the facts can reach this band, and only when it is verified.

**Materiality** is a problem score on how much of the real environmental impact the claim addresses, 0 to 1. This dimension is proportionality, so lean on the recomputed numbers. Bands:
- 0.1 to 0.2: the claim covers the dominant share of the company's footprint, or names the lever that actually decides its impact.
- 0.3 to 0.4: a real but partial lever, with the rest of the footprint addressed elsewhere on the page.
- 0.5 to 0.6: a small share of the footprint; or an intensity measure where the absolute number is what matters; or progress that came substantially from divestment or a sale rather than from abatement.
- 0.7 to 0.85: a trivial share of the impact presented as the company's environmental story, while the material part goes unmentioned. This is the hidden trade-off.
- Confidence is high when a computation puts a figure on the share, low when nothing found gives one.

Rules:
- Weigh evidence by reliability: a regulator ruling or a law (tier 1) over an assured filing or government data (tier 2) over an independent dataset or standard (tier 3) over news (tier 4) over the company's own material (tier 5). **A company's own material cannot substantiate its own claim**; it can only contradict it or give context. A Support score in the low bands must rest on something the company did not publish about itself, or on an assured part of its filings.
- An item marked "quote not verified" was retrieved but its quote could not be found on the page. Do not let it decide a score; if it is all there is for a claim, that claim's confidence is low.
- Judge the facts, not the wording. How clear the words are is scored elsewhere.
- Credit where due: a figure with its baseline, scope and date, confirmed in an assured filing, scores low on Support. A page with only high scores was read badly.

Return `assessments`: one entry per claim in the list, none twice, in the list's order, each with both scores, both confidences, a one-sentence basis for each naming the evidence that decides it, the evidence ids each rests on (only ids from the listing), and `gap`: one sentence on what the text would have to show for the claim to stand as written, empty when it already does."""

RETRIEVE_MAX_OUTPUT_TOKENS = 16000
COMPUTE_MAX_OUTPUT_TOKENS = 16000
SCORE_MAX_OUTPUT_TOKENS = 16000

# Claims per retrieval call and per scoring call. Retrieval is the slow one: every call runs
# its own searches and fetches, so the batches are small and go out together.
BATCH_SIZE = int(os.environ.get("AUDITOR_VERIFY_BATCH", "6"))
SCORE_BATCH_SIZE = int(os.environ.get("AUDITOR_VERIFY_SCORE_BATCH", "9"))
MAX_SEARCHES = int(os.environ.get("AUDITOR_VERIFY_SEARCHES", "6"))
MAX_FETCHES = int(os.environ.get("AUDITOR_VERIFY_FETCHES", "6"))

RETRIEVE_EFFORT = os.environ.get("AUDITOR_VERIFY_RETRIEVE_EFFORT", "medium")
COMPUTE_EFFORT = os.environ.get("AUDITOR_VERIFY_COMPUTE_EFFORT", "medium")
SCORE_EFFORT = os.environ.get("AUDITOR_VERIFY_EFFORT", "medium")

SOURCE_PREFIX = "V"
COMPUTATION_PREFIX = "N"
COMPUTED_BY = "Recomputed by the External verification evaluator"
PLACEHOLDER_BASIS = "Not assessed by the external verification evaluator; neutral placeholder."

Emit = Callable[[str, dict[str, Any]], Any]
FetchText = Callable[[str], str]


def today() -> str:
    return date.today().isoformat()


# ----------------------------------------------------------------------------- citation integrity


@dataclass
class Page:
    """What came back from fetching a URL, so one bad link never stops the stage."""

    url: str
    text: str | None = None
    error: str | None = None


NO_LINK = "not an http(s) address"


def is_web_url(url: str) -> bool:
    """A link a reader could open and this module could fetch. A model that writes a bare
    domain or a made-up scheme gets an item with no link rather than a broken one."""
    return bool(re.match(r"^https?://[^\s/]+", url.strip()))


def load_page(url: str, fetch_text: FetchText | None = None) -> Page:
    """Fetch a page for the quote check. Never raises: a page that cannot be read is a Page
    with an error, and its quote goes undisplayed like any other unverified one."""
    if not is_web_url(url):
        return Page(url, error=NO_LINK)
    reader = fetch_text or page_text
    try:
        return Page(url, text=reader(url))
    except Exception as exc:  # noqa: BLE001 - reported on the evidence item, never raised
        detail = str(exc).strip() or type(exc).__name__
        return Page(url, error=detail[:160])


# Why a quote is not shown. The two are not the same thing and the run says which: a quote the
# page does not contain is a citation rejected, a page that will not open is a gap this machine
# could not close. Only the first is a finding about the evidence.
ABSENT = "absent"
UNREADABLE = "unreadable"


def check_quote(page: Page, quote: str) -> tuple[bool, str, str]:
    """(verified, why, reason) for one quote against one page, by the contract's `fetched_exact`
    bar. `reason` is "" when verified, else ABSENT or UNREADABLE."""
    if page.error == NO_LINK:
        return False, f"Quote not verified: {page.url!r} is not a link that can be opened, so nothing could be checked.", UNREADABLE
    if page.error is not None:
        return False, f"Quote not verified: {page.url} could not be read from here ({page.error}). Open the link by hand.", UNREADABLE
    if page.text is None:
        return False, f"Quote not verified: {page.url} was not fetched.", UNREADABLE
    if quote_in(page.text, quote):
        return True, "", ""
    return False, f"Quote not found on {page.url} when it was fetched on {today()}, so it is not shown (citation integrity, design-doc D5).", ABSENT


# ----------------------------------------------------------------------------- recomputation


class ComputationError(ValueError):
    """An expression is not plain arithmetic, or does not come to what was claimed."""


_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluate(expression: str, inputs: dict[str, float]) -> float:
    """Evaluate plain arithmetic over named inputs. Anything else — a call, an attribute, a
    name with no input — raises, because a number nobody can reproduce is not evidence."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ComputationError(f"{expression!r} does not parse as arithmetic") from exc

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in inputs:
                raise ComputationError(f"no input named {node.id!r}")
            return float(inputs[node.id])
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](walk(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ComputationError("division by zero")
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ComputationError("exponent out of range")
            return _OPERATORS[type(node.op)](left, right)
        raise ComputationError(f"{expression!r} is not plain arithmetic")

    result = walk(tree)
    if result != result or result in (float("inf"), float("-inf")):  # NaN or overflow
        raise ComputationError("the expression has no finite value")
    return float(result)


def close_enough(computed: float, claimed: float) -> bool:
    """The model's number against ours: a rounding apart is fine, a different number is not."""
    return abs(computed - claimed) <= max(0.05, abs(computed) * 0.005)


def states_value(sentence: str, value: float) -> bool:
    """Whether the sentence actually states the number we computed, to any sane rounding. The
    result a reader sees has to be the result we checked. The number must stand on its own:
    "2" is not stated by "12%" or "2025", which is most of what makes this check worth
    anything."""
    plain = sentence.replace(",", "")
    for number in (value, abs(value)):
        for places in (0, 1, 2):
            text = f"{number:.{places}f}"
            for candidate in (text, text[:-2] if text.endswith(".0") else text):
                if re.search(rf"(?<![\d.]){re.escape(candidate)}(?!\d)", plain):
                    return True
    return False


# ----------------------------------------------------------------------------- assembly


@dataclass
class VerificationResult:
    evidence: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    absent: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    usage: Usage | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def unverified(self) -> list[str]:
        """Every source whose quote is not shown, for whichever of the two reasons."""
        return [*self.absent, *self.unreadable]

    @property
    def sources(self) -> list[dict[str, Any]]:
        return [e for e in self.evidence if e["kind"] != "computation"]

    @property
    def computations(self) -> list[dict[str, Any]]:
        return [e for e in self.evidence if e["kind"] == "computation"]


class Assembler:
    """Turns findings, computations and assessments into contract entities one at a time,
    emitting each as it is built, so the stream and the batch path share one code path."""

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
        self.seen: set[tuple[str, str]] = set()  # (url, quote): two calls that found the same passage make one row
        self.scores: list[dict[str, Any]] = []
        self.scored: set[str] = set()
        self.absent: list[str] = []      # the page opened; the quote was not in it
        self.unreadable: list[str] = []  # the page would not open from here
        self.rejected: list[str] = []
        self.placeholders: list[str] = []
        self.duplicates = 0
        self.unknown_claims = 0
        self.unknown_ids = 0
        self.repeated = 0
        self.downgraded = 0

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

    # -- findings

    def add_finding(self, finding: Finding, page: Page) -> dict[str, Any] | None:
        """One retrieved source, its quote checked against the page it names."""
        links = self._links(finding.bears_on)
        if not links:
            return None
        key = (normalise_url(finding.url), " ".join(finding.quote.split()).lower())
        if key in self.seen:
            self.duplicates += 1
            return None
        self.seen.add(key)
        verified, why, reason = check_quote(page, finding.quote)
        tier = TIERS[finding.independence]
        note = finding.note.strip()
        if tier == 5 and any(l["relation"] == "supports" for l in links):
            # D5: a company cannot substantiate its own claim. The item stays; the link
            # becomes what it honestly is.
            for link in links:
                if link["relation"] == "supports":
                    link["relation"] = "context"
                    self.downgraded += 1
            note = (note + " " if note else "") + "The company's own material, so it is context, not substantiation (design-doc D5)."
        if not verified:
            (self.absent if reason == ABSENT else self.unreadable).append(finding.url)
            note = (note + " " if note else "") + why
        source = {"name": finding.name.strip() or finding.url}
        for key_, value in (("publisher", finding.publisher), ("date", finding.date), ("locator", finding.locator)):
            if value.strip():
                source[key_] = value.strip()
        item: dict[str, Any] = {
            "id": self._next_id(SOURCE_PREFIX),
            "kind": finding.kind,
            "tier": tier,
            "source": source,
            "verified": verified,
            "verification": "fetched_exact" if verified else "unverified",
            "retrieved": today(),
            "stage": "verify",
            "links": links,
            "ext": {"independence": finding.independence, "retrieval": "live"},
        }
        if is_web_url(finding.url):
            item["url"] = finding.url.strip()
        if verified:
            item["quote"] = finding.quote.strip()
        if note:
            item["note"] = note
        return self._add_evidence(item)

    # -- computations

    def add_computation(self, item: Computation) -> dict[str, Any] | None:
        """One recomputed number, evaluated here before anyone sees it."""
        links = self._links(item.bears_on)
        if not links:
            return None
        known = [e for e in dict.fromkeys(item.derived_from) if e in self.by_id or e in self.prior]
        unknown = [e for e in dict.fromkeys(item.derived_from) if e not in known]
        self.unknown_ids += len(unknown)
        if unknown and not known:
            # Every id named is one we do not have: the model was pointing at something else
            # (a paragraph label, say), so we cannot say where the figures came from.
            self.rejected.append(f"{item.name}: derived from evidence that does not exist ({', '.join(unknown)})")
            return None
        try:
            value = evaluate(item.expression, item.inputs)
        except ComputationError as exc:
            self.rejected.append(f"{item.name}: {exc}")
            return None
        if not close_enough(value, item.value):
            self.rejected.append(f"{item.name}: {item.expression} = {value:.4g}, not {item.value:.4g} as claimed")
            return None
        if not states_value(item.sentence, value):
            self.rejected.append(f"{item.name}: the sentence does not state {value:.4g} ({item.sentence[:60]!r})")
            return None
        # A computation is no better than what it was computed from (contract §4); with no
        # evidence under it the figures came off the document itself, which is tier 5.
        tier = max((self.by_id.get(e, self.prior.get(e, {})).get("tier", 5) for e in known), default=5)
        ext: dict[str, Any] = {"recomputed": round(value, 4)}
        if item.unit.strip():
            ext["unit"] = item.unit.strip()
        if item.stated is not None:
            # Both numbers, and the gap between them: what "18%" on the page turned out to be.
            ext["stated"] = item.stated
            ext["difference"] = round(value - item.stated, 4)
        computed: dict[str, Any] = {
            "id": self._next_id(COMPUTATION_PREFIX),
            "kind": "computation",
            "tier": tier,
            "source": {"name": item.name.strip() or "Recomputed number", "publisher": COMPUTED_BY, "date": today()},
            "quote": item.sentence.strip(),
            "verified": True,
            "verification": "computed",
            "retrieved": today(),
            "stage": "verify",
            "links": links,
            "computation": {"formula": item.expression.strip(), "inputs": dict(item.inputs), "result": item.sentence.strip()},
            "derived_from": known,
            "ext": ext,
        }
        return self._add_evidence(computed)

    # -- scores

    def _score(self, claim_id: str, dimension: str, score: float, confidence: float, basis: str, evidence_ids: list[str], gap: str = "") -> dict[str, Any]:
        cited = [e for e in dict.fromkeys(evidence_ids) if e in self.by_id or e in self.prior]
        self.unknown_ids += len(set(evidence_ids)) - len(cited)
        out: dict[str, Any] = {
            "claim_id": claim_id,
            "dimension": dimension,
            "score": clamp01(score),
            "confidence": clamp01(confidence),
            "basis": basis.strip() or "No basis given.",
            "stage": "verify",
        }
        if cited:
            out["evidence_ids"] = cited
        if gap.strip():
            out["ext"] = {"gap": gap.strip()}
        self.scores.append(out)
        self._emit("dimension.scored", {"score": out})
        return out

    def add_assessment(self, item: Assessment) -> bool:
        if item.claim_id not in self.claims:
            self.unknown_claims += 1
            return False
        if item.claim_id in self.scored:
            self.repeated += 1
            return False
        self.scored.add(item.claim_id)
        self._score(item.claim_id, "support", item.support, item.support_confidence, item.support_basis, item.support_evidence_ids, item.gap)
        self._score(item.claim_id, "materiality", item.materiality, item.materiality_confidence, item.materiality_basis, item.materiality_evidence_ids)
        return True

    def finish(self) -> VerificationResult:
        for cid in self.order:
            if cid not in self.scored:
                self.placeholders.append(cid)
                self.add_assessment(Assessment(
                    claim_id=cid, support=0.5, support_confidence=0.2, support_basis=PLACEHOLDER_BASIS,
                    materiality=0.5, materiality_confidence=0.2, materiality_basis=PLACEHOLDER_BASIS,
                ))
        result = VerificationResult(self.evidence, self.scores, list(self.absent), list(self.unreadable), list(self.rejected), list(self.placeholders))
        sources, computations = result.sources, result.computations
        linked = {l["target"] for e in self.evidence for l in e["links"]}
        result.notes.append(
            f"{len(sources)} sources retrieved for {len(linked)} of {len(self.order)} claims, "
            f"{len(sources) - len(self.absent) - len(self.unreadable)} with a quote found on the page, "
            f"{len(self.absent)} whose quote was not on the page, {len(self.unreadable)} whose page could not be read from here; "
            f"{len(computations)} numbers recomputed"
            + (f", {len(self.rejected)} rejected" if self.rejected else "")
            + (f"; {self.downgraded} tier-5 'supports' links made 'context'" if self.downgraded else "")
            + (f"; {self.duplicates} duplicate findings ignored" if self.duplicates else "")
            + (f"; {self.unknown_ids} unknown evidence ids ignored" if self.unknown_ids else "")
            + (f"; {self.unknown_claims} unknown claim ids ignored" if self.unknown_claims else "")
            + (f"; {self.repeated} repeated assessments ignored" if self.repeated else "")
        )
        for line in self.rejected[:8]:
            result.notes.append(f"Rejected: {line}")
        if self.absent:
            result.notes.append(f"Quote not on the page, so the citation is rejected and the quote not displayed: {', '.join(dict.fromkeys(self.absent))[:400]}")
        if self.unreadable:
            result.notes.append(f"Page could not be read from here, so the quote stays unverified and undisplayed: {', '.join(dict.fromkeys(self.unreadable))[:400]}")
        if self.placeholders:
            result.notes.append(f"Placeholder support and materiality for {len(self.placeholders)} claims the model did not assess: {', '.join(self.placeholders[:10])}")
        return result


# ----------------------------------------------------------------------------- what the model sees


def evidence_listing(items: list[dict[str, Any]]) -> str:
    """The evidence so far, as the compute and score calls read it."""
    lines = []
    for item in items:
        links = ", ".join(f"{l['target']} ({l['relation']})" for l in item.get("links", []))
        head = f"{item['id']} [tier {item['tier']}; {item['kind']}] {item['source']['name']}"
        if item.get("source", {}).get("locator"):
            head += f" — {item['source']['locator']}"
        body = item.get("quote") or item.get("note") or ""
        if not item.get("verified", False) and item["kind"] != "computation":
            body = "(quote not verified, so not shown) " + (item.get("note") or "")
        lines.append(f"{head}\n  Bears on: {links or 'nothing'}.\n  {' '.join(body.split())[:600]}")
    return "\n".join(lines) or "(no evidence gathered)"


def retrieve_prompt(claims: list[dict[str, Any]], batch: list[dict[str, Any]] | None = None) -> str:
    listing = claims_listing(claims)
    review = ""
    if batch is not None and len(batch) < len(claims):
        ids = ", ".join(c["id"] for c in batch)
        review = f"\n\n<review>\nIn this call, look for evidence on these claims only: {ids}. The other claims are listed for context; another call is looking for theirs.\n</review>"
    return f"{RETRIEVE_TASK}\n\n<claims>\n{listing}\n</claims>{review}"


def compute_prompt(claims: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    return f"{COMPUTE_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<evidence>\n{evidence_listing(evidence)}\n</evidence>"


def score_prompt(claims: list[dict[str, Any]], evidence: list[dict[str, Any]], batch: list[dict[str, Any]] | None = None) -> str:
    review = ""
    if batch is not None and len(batch) < len(claims):
        ids = ", ".join(c["id"] for c in batch)
        review = f"\n\n<review>\nIn this call, score only these claims: {ids}. The other claims are listed for context; return no assessment for them.\n</review>"
    return f"{SCORE_TASK}\n\n<claims>\n{claims_listing(claims)}\n</claims>\n\n<evidence>\n{evidence_listing(evidence)}\n</evidence>{review}"


# ----------------------------------------------------------------------------- the stage


def apply_verification(
    findings: Findings,
    computations: Computations,
    assessments: Assessments,
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    *,
    fetch_text: FetchText | None = None,
) -> VerificationResult:
    """The batch path: whole results at once (tests and fakes), in contract order — sources,
    then the numbers computed from them, then the scores that cite both."""
    assembler = Assembler(claims, prior_evidence, emit)
    pages: dict[str, Page] = {}
    for finding in findings.findings:
        if finding.url not in pages:
            pages[finding.url] = load_page(finding.url, fetch_text)
        assembler.add_finding(finding, pages[finding.url])
    for computation in computations.computations:
        assembler.add_computation(computation)
    for assessment in assessments.assessments:
        assembler.add_assessment(assessment)
    return assembler.finish()


async def verify(
    document: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    prior_evidence: list[dict[str, Any]] | None = None,
    emit: Emit | None = None,
    llm: Llm | None = None,
    fetch_text: FetchText | None = None,
) -> VerificationResult:
    """Run external verification on an ingested document and its claims: retrieval in parallel
    batches with the web tools, every quote checked against its page as it arrives, then the
    numbers recomputed, then Support and Materiality scored. A retrieval batch that fails is
    reported and the stage carries on with what the others found; a failure to score raises
    LlmError, because the stage owes the verdict two dimensions."""
    if not claims:
        return VerificationResult([], [], notes=["No claims to verify."])
    llm = llm or get_llm()
    assembler = Assembler(claims, prior_evidence, emit)
    system = document_system(document)
    tools = web_tools(searches=MAX_SEARCHES, fetches=MAX_FETCHES)
    batches = [claims[i : i + max(1, BATCH_SIZE)] for i in range(0, len(claims), max(1, BATCH_SIZE))]
    started = time.perf_counter()
    usages: list[Usage] = []
    counts = {"findings": 0, "computations": 0, "assessments": 0, "invalid": 0, "out_of_batch": 0}
    failures: list[str] = []
    fetching: dict[str, asyncio.Task[Page]] = {}
    first: list[float] = []

    async def page_for(url: str) -> Page:
        """One fetch per URL per run, however many findings quote it, and the second caller
        waits for the first one's fetch rather than seeing a half-filled entry."""
        if url not in fetching:
            fetching[url] = asyncio.create_task(asyncio.to_thread(load_page, url, fetch_text))
        return await fetching[url]

    async def place(finding: Finding) -> None:
        page = await page_for(finding.url)
        if assembler.add_finding(finding, page) is not None and not first:
            first.append(time.perf_counter() - started)

    async def run_retrieval(batch: list[dict[str, Any]]) -> None:
        ids = {c["id"] for c in batch}
        handed: list[Finding] = []
        placing: list[asyncio.Task[None]] = []

        async def on_element(key: str, item: dict[str, Any]) -> None:
            if key != "findings":
                return
            try:
                finding = Finding.model_validate(item)
            except ValidationError:
                counts["invalid"] += 1
                return
            if not ({b.claim_id for b in finding.bears_on} & ids):
                counts["out_of_batch"] += 1
                return
            handed.append(finding)
            placing.append(asyncio.create_task(place(finding)))

        try:
            result, usage = await llm.extract_streaming(
                retrieve_prompt(claims, batch=batch), Findings, on_element=on_element,
                system=system, cache=True, tools=tools, max_tokens=RETRIEVE_MAX_OUTPUT_TOKENS, effort=RETRIEVE_EFFORT,
            )
        except LlmError as exc:
            # One search that fails must not lose the other batches' evidence.
            failures.append(f"{', '.join(sorted(ids))}: {exc}")
            if placing:
                await asyncio.gather(*placing)
            return
        usages.append(usage)
        counts["findings"] += len(result.findings)
        seen = {(f.url, f.quote) for f in handed}
        for finding in result.findings:
            if (finding.url, finding.quote) not in seen and {b.claim_id for b in finding.bears_on} & ids:
                placing.append(asyncio.create_task(place(finding)))
        if placing:
            await asyncio.gather(*placing)

    async with asyncio.TaskGroup() as group:
        for batch in batches:
            group.create_task(run_retrieval(batch))

    # -- the numbers, from everything retrieved (one call: a computation may cross batches)
    if assembler.evidence or prior_evidence:
        handed = 0

        async def on_computation(key: str, item: dict[str, Any]) -> None:
            nonlocal handed
            if key != "computations":
                return
            handed += 1
            try:
                assembler.add_computation(Computation.model_validate(item))
            except ValidationError:
                counts["invalid"] += 1

        try:
            result, usage = await llm.extract_streaming(
                compute_prompt(claims, [*(prior_evidence or []), *assembler.evidence]), Computations,
                on_element=on_computation, system=system, cache=True,
                max_tokens=COMPUTE_MAX_OUTPUT_TOKENS, effort=COMPUTE_EFFORT,
            )
            for computation in result.computations[handed:]:
                assembler.add_computation(computation)
            usages.append(usage)
            counts["computations"] = len(result.computations)
        except LlmError as exc:
            failures.append(f"numbers: {exc}")

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

    result = assembler.finish()
    result.usage = combine_usage(usages, time.perf_counter() - started)
    note = (
        f"Claude searched for evidence on {len(claims)} claims over {len(batches)} parallel calls of up to {BATCH_SIZE}"
        + (f" (first source after {first[0]:.1f} s)" if first else "")
        + f", returned {counts['findings']} findings and {counts['computations']} computations, and scored {counts['assessments']} claims over {len(score_batches)} calls"
    )
    if counts["invalid"]:
        note += f", {counts['invalid']} malformed"
    if counts["out_of_batch"]:
        note += f", {counts['out_of_batch']} for claims outside their call ignored"
    result.notes.insert(0, note + f" ({result.usage.describe()})")
    for failure in failures:
        result.notes.insert(1, f"Retrieval failed for {failure}")
    return result


# ----------------------------------------------------------------------------- comparison with a reference


@dataclass
class ScoreComparison:
    dimension: str
    pairs: list[tuple[str, float, float]]
    unscored: list[str]

    @property
    def mean_abs_error(self) -> float:
        return sum(abs(a - b) for _, a, b in self.pairs) / len(self.pairs) if self.pairs else 0.0

    def wrong_band(self) -> list[str]:
        return [cid for cid, live, ref in self.pairs if (live > 0.6) != (ref > 0.6)]

    def describe(self) -> str:
        text = f"{self.dimension} scored for {len(self.pairs)} reference claims, mean absolute difference {self.mean_abs_error:.2f}, {len(self.wrong_band())} on the other side of 0.6"
        if self.unscored:
            text += f", {len(self.unscored)} reference claims unscored"
        return text


def compare_scores(live: list[dict[str, Any]], reference: list[dict[str, Any]], dimension: str) -> ScoreComparison:
    """Live scores for one dimension against a reference's, by claim id."""
    live_by = {s["claim_id"]: s for s in live if s.get("dimension") == dimension}
    pairs, unscored = [], []
    for ref in reference:
        if ref.get("dimension") != dimension:
            continue
        got = live_by.get(ref["claim_id"])
        if got is None:
            unscored.append(ref["claim_id"])
        else:
            pairs.append((ref["claim_id"], float(got["score"]), float(ref["score"])))
    return ScoreComparison(dimension, pairs, unscored)


@dataclass
class SourceComparison:
    """The reference's verify-stage sources against the live run's, by host: hand-curated URLs
    and a live search rarely land on the same page, but they should land on the same bodies."""

    reference_hosts: list[str]
    found_hosts: list[str]
    live_sources: int
    verified: int

    def describe(self) -> str:
        return (
            f"{len(self.found_hosts)} of {len(self.reference_hosts)} reference sources matched by host "
            f"({', '.join(sorted(self.found_hosts)) or 'none'}); {self.live_sources} live sources, {self.verified} with the quote found on the page"
        )


def host_of(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).netloc.lower().removeprefix("www.")


def compare_sources(live: list[dict[str, Any]], reference: list[dict[str, Any]]) -> SourceComparison:
    live_sources = [e for e in live if e["kind"] != "computation" and e.get("url")]
    live_hosts = {host_of(e["url"]) for e in live_sources}
    reference_hosts = sorted({host_of(e["url"]) for e in reference if e.get("stage") == "verify" and e.get("url")})
    return SourceComparison(
        reference_hosts,
        sorted(h for h in reference_hosts if h in live_hosts),
        len(live_sources),
        sum(1 for e in live_sources if e["verified"]),
    )


# ----------------------------------------------------------------------------- command line


def _print_evidence(item: dict[str, Any]) -> None:
    targets = ",".join(l["target"] for l in item["links"])
    mark = "ok  " if item["verified"] else "FAIL"
    print(f"{mark} {item['id']:>4}  {item['links'][0]['relation']:<20} tier {item['tier']} {targets:<20} {item['source']['name'][:70]}")
    if item.get("quote"):
        print(f"          “{' '.join(item['quote'].split())[:150]}”")
    if item.get("url"):
        print(f"          {item['url']}")
    if item.get("note") and not item["verified"]:
        print(f"          {item['note'][:150]}")


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
            for note in matched.notes:
                print(f"note: {note}", file=sys.stderr)
            prior = matched.evidence

        def emit(type_: str, payload: dict[str, Any]) -> None:
            if args.json:
                return
            if type_ == "evidence.added":
                _print_evidence(payload["evidence"])
            else:
                s = payload["score"]
                print(f"     {s['claim_id']:>4}  {s['dimension']:<12} {s['score']:<5} confidence {s['confidence']:<5} [{','.join(s.get('evidence_ids', []))}] {s['basis'][:100]}")

        result = await verify(document, claims, prior_evidence=prior, emit=emit)
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps({"evidence": result.evidence, "scores": result.scores}, ensure_ascii=False, indent=2))
    if analysis is not None:
        sources = compare_sources(result.evidence, analysis["evidence"])
        print(f"\nagainst {Path(args.golden).name}: {sources.describe()}")
        for dimension in ("support", "materiality"):
            comparison = compare_scores(result.scores, analysis["scores"], dimension)
            print(comparison.describe())
            for cid, live, ref in comparison.pairs:
                flag = "  <-- other side of 0.6" if (live > 0.6) != (ref > 0.6) else ""
                print(f"  {cid:>4} live {live:<5} reference {ref:<5} diff {live - ref:+.2f}{flag}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.verify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    parser.add_argument("--golden", help="an analysis.json: its claims are the input and its support and materiality scores the reference")
    parser.add_argument("--no-knowledge", action="store_true", help="skip the substantiation matching that usually precedes this stage")
    parser.add_argument("--json", action="store_true", help="print the evidence and scores as JSON")
    parser.add_argument("--check-quote", nargs=2, metavar=("URL", "QUOTE"), help="only run the citation check: is that quote on that page?")
    args = parser.parse_args(argv)
    if args.check_quote:
        url, quote = args.check_quote
        page = load_page(url)
        verified, why = check_quote(page, quote)
        print(f"{'ok  ' if verified else 'FAIL'} {url}\n     {why or 'quote found on the page (fetched_exact)'}")
        return 0 if verified else 1
    if not args.source:
        parser.error("a source is required unless --check-quote is given")
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
