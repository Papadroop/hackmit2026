"""Calibration (roadmap step 19; design-doc D5 "Rigour guarantees"): run the pipeline on the
precedent set, leave-one-out, and report precision, recall and a calibration curve.

The precedent store is the only ground truth this project has: 24 rulings on environmental
claims, each with the wording that was ruled on and what the regulator decided. A ruling that
was **upheld** says the wording misled; **not upheld** or **dismissed** says it did not. So each
precedent is a labelled test case, and the audit can be scored on them — as long as the ruling
under test is taken out of the store first, which is what `Knowledge.without` is for
(demo-documents.md §6, and the leave-one-out rule in D5).

**What is calibrated, and what cannot be.** A precedent gives a claim's wording and nothing
else: no company report, no filings, no page around it. Clarity is read from wording, and
Support from the criteria and the precedents, so both can run and both are exactly what this
set is ground truth for. Materiality and Consistency need a document and a company's own
record, which a bare wording does not have, so they are not scored and the likelihood is the
weakest link of the two that are (CONTRACT.md §6 over the dimensions present). Nor is external
verification run: searching the web for the wording of a famous ruling finds the ruling, which
is the leak the hold-out exists to prevent. The verdict layer's debate is not run either —
likelihood and category are derived, not judged, so the debate cannot move the number being
measured and would only cost calls.

**What the numbers mean.** `upheld` and `upheld_in_part` are the positive class, `not_upheld`
and `dismissed` the negative. `settled` is neither: a company that settles admits nothing and a
regulator that settles has found nothing, so those cases are predicted and shown but kept out
of precision and recall unless `--settled-positive` says otherwise. The set is small and badly
balanced — 17 positive against 3 negative — so recall is easy and precision is nearly
meaningless on so few negatives. The report says so in as many words rather than quoting a
number that flatters. The calibration curve is the honest one: it asks whether claims the audit
scores 0.7 really do turn out misleading about 70% of the time.

    python -m auditor.calibration run --out data/calibration.json    # calls Claude, ~2 per case
    python -m auditor.calibration report data/calibration.json       # metrics only, no model

`run` saves every case's scores with its label, so the metrics can be recomputed, the thresholds
moved and the curve redrawn without paying for the run again.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .knowledge import Knowledge, PrecedentIndex, StoreEntry, get_knowledge
from .language import reanchored_claims  # noqa: F401  (kept for the CLI's --analysis path)
from .llm import Llm, LlmError, Usage, get_llm

# What a regulator's outcome says about the wording. `settled` is deliberately absent: it is a
# bargain, not a finding, and counting it either way would be inventing ground truth.
POSITIVE = ("upheld", "upheld_in_part")
NEGATIVE = ("not_upheld", "dismissed")
UNLABELLED = ("settled",)

# A claim is called misleading above this likelihood. The contract's category rule turns on 0.5
# too (above it a claim is at best `misleading_by_framing`), so the two agree by construction.
THRESHOLD = float(os.environ.get("AUDITOR_CALIBRATION_THRESHOLD", "0.5"))

# The curve's buckets. Five over [0, 1]: fewer than the eye wants, more than 24 cases support.
BINS = int(os.environ.get("AUDITOR_CALIBRATION_BINS", "5"))

# How many cases run at once. Each is two calls on a one-sentence document, so this is about
# not opening 24 connections at once rather than about tokens.
CONCURRENCY = int(os.environ.get("AUDITOR_CALIBRATION_CONCURRENCY", "4"))

DIMENSIONS_RUN = ("clarity", "support")


def label_of(outcome: str | None, *, settled_positive: bool = False) -> int | None:
    """1 misleading, 0 not, None not adjudicated either way."""
    if outcome in POSITIVE:
        return 1
    if outcome in NEGATIVE:
        return 0
    if outcome in UNLABELLED:
        return 1 if settled_positive else None
    return None


@dataclass
class Case:
    """One precedent as a test case: its wording, what the regulator decided, and what the
    audit predicted for it with that ruling taken out of the store."""

    store_id: str
    claim_text: str
    outcome: str
    company: str = ""
    industry: str = ""
    body: str = ""
    claim_type: str = "factual"
    label: int | None = None
    likelihood: float | None = None
    category: str = ""
    scores: dict[str, dict[str, float]] = field(default_factory=dict)
    cited: list[str] = field(default_factory=list)
    held_out: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def predicted(self) -> int | None:
        return None if self.likelihood is None else int(self.likelihood > THRESHOLD)


def cases_from(knowledge: Knowledge, *, settled_positive: bool = False) -> list[Case]:
    """Every precedent that names the wording it ruled on, as a test case."""
    out = []
    for entry in knowledge.precedents:
        index = entry.index
        if not isinstance(index, PrecedentIndex) or not (index.claim_text or "").strip():
            continue
        out.append(Case(
            store_id=entry.id,
            claim_text=" ".join(index.claim_text.split()),
            outcome=index.outcome or "",
            company=index.company or "",
            industry=index.industry or "",
            body=index.body or "",
            claim_type=(index.applies_to or ["factual"])[0],
            label=label_of(index.outcome, settled_positive=settled_positive),
        ))
    return out


def case_document(case: Case) -> dict[str, Any]:
    """The wording as a one-claim document, so the evaluators see what they always see. There
    is no url: a precedent's wording is an advert or a page that no longer exists, and giving
    one would only invite a fetch."""
    text = case.claim_text
    return {
        "id": f"cal-{case.store_id}",
        "title": f"Claim ruled on by {case.body or 'a regulator'}",
        "company": {"name": case.company or "the advertiser"},
        "text_type": "claim",
        "source": {"retrieved": "", "url": None},
        "text": text,
        "word_count": len(text.split()),
        "regions": [],
    }


def case_claim(case: Case) -> dict[str, Any]:
    """The whole wording is the claim; there is nothing else on the page to extract from."""
    return {
        "id": "C1",
        "spans": [{"text": case.claim_text, "start": 0, "end": len(case.claim_text)}],
        "type": case.claim_type if case.claim_type in ("factual", "commitment", "comparative", "vague_attribute", "certification") else "factual",
        "scope": "company",
        "attribute": case.claim_text[:60],
        "paragraph": "P1",
        "prominence": 1.0,
    }


# ----------------------------------------------------------------------------- running a case


async def run_case(case: Case, knowledge: Knowledge, *, llm: Llm | None = None) -> Case:
    """Score one wording with its own ruling taken out of the store, and derive the verdict the
    contract's rules give. Clarity and Support only; the module docstring says why."""
    from . import language as language_module
    from . import substantiate as substantiate_module
    from .verdict import derive_category, derive_likelihood

    held = knowledge.without({case.store_id})
    case.held_out = list(held.held_out)
    document, claim = case_document(case), case_claim(case)
    try:
        review = await language_module.review_language(document, [claim], llm=llm)
        substantiation = await substantiate_module.substantiate(document, [claim], llm=llm, knowledge=held, score=True)
    except LlmError as exc:
        case.error = str(exc)
        return case
    scores = {s["dimension"]: s for s in [*review.scores, *substantiation.scores] if s["claim_id"] == "C1"}
    case.scores = {d: {"score": float(s["score"]), "confidence": float(s["confidence"])} for d, s in scores.items() if d in DIMENSIONS_RUN}
    if not case.scores:
        case.error = "no dimension was scored"
        return case
    present = {d: scores[d] for d in DIMENSIONS_RUN if d in scores}
    case.likelihood = derive_likelihood(present)
    # No evidence item contradicts a bare wording, so `contradicted` is out of reach here; the
    # rule still decides between the other three.
    case.category = derive_category(present, False)
    case.cited = sorted({e for s in present.values() for e in s.get("evidence_ids", [])})
    return case


async def run_calibration(
    *,
    knowledge: Knowledge | None = None,
    limit: int | None = None,
    settled_positive: bool = False,
    llm: Llm | None = None,
    concurrency: int = CONCURRENCY,
    on_case: Any = None,
) -> tuple[list[Case], Usage | None]:
    """Every precedent, leave-one-out, a few at a time."""
    from .language import combine_usage

    store = knowledge or get_knowledge()
    cases = cases_from(store, settled_positive=settled_positive)[: limit or None]
    llm = llm or get_llm()
    started = time.perf_counter()
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(case: Case) -> None:
        async with gate:
            await run_case(case, store, llm=llm)
            if on_case is not None:
                on_case(case)

    await asyncio.gather(*(one(case) for case in cases))
    return cases, combine_usage([], time.perf_counter() - started)


# ----------------------------------------------------------------------------- the metrics


@dataclass
class Bin:
    low: float
    high: float
    count: int
    predicted: float          # the mean likelihood the audit gave in this bucket
    observed: float           # the share of them a regulator actually upheld

    def gap(self) -> float:
        return self.predicted - self.observed


@dataclass
class Metrics:
    """What the precedent set can and cannot say about the audit."""

    scored: int
    labelled: int
    positives: int
    negatives: int
    unlabelled: int
    failed: int
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    brier: float | None
    bins: list[Bin] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        called = self.true_positive + self.false_positive
        return self.true_positive / called if called else None

    @property
    def recall(self) -> float | None:
        actual = self.true_positive + self.false_negative
        return self.true_positive / actual if actual else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r and (p + r) else None

    @property
    def accuracy(self) -> float | None:
        return (self.true_positive + self.true_negative) / self.labelled if self.labelled else None

    def caveat(self) -> str:
        """The honest sentence that has to go beside the numbers."""
        if self.negatives < 5:
            return (
                f"Only {self.negatives} of the {self.labelled} adjudicated cases were decided in the advertiser's favour, "
                "so recall is easy to score well on and precision rests on too few negatives to mean much. "
                "The calibration curve is the number to read."
            )
        return f"{self.positives} positive and {self.negatives} negative cases."

    def describe(self) -> str:
        def pct(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.0%}"
        return (
            f"{self.scored} of {self.scored + self.failed} cases scored, {self.labelled} adjudicated "
            f"({self.positives} upheld, {self.negatives} not) and {self.unlabelled} settled and left out; "
            f"at a threshold of {self.threshold:g}: precision {pct(self.precision)}, recall {pct(self.recall)}, "
            f"F1 {pct(self.f1)}, accuracy {pct(self.accuracy)}"
            + (f", Brier {self.brier:.3f}" if self.brier is not None else "")
        )


def calibration_bins(rows: list[tuple[float, int]], bins: int = BINS) -> list[Bin]:
    """The curve: bucket the cases by what the audit predicted, and see how many of each bucket
    a regulator actually upheld. A well-calibrated audit has predicted close to observed."""
    out: list[Bin] = []
    for i in range(bins):
        low, high = i / bins, (i + 1) / bins
        inside = [(p, y) for p, y in rows if (low <= p < high) or (i == bins - 1 and p == 1.0)]
        if not inside:
            continue
        out.append(Bin(
            low=round(low, 3), high=round(high, 3), count=len(inside),
            predicted=round(sum(p for p, _ in inside) / len(inside), 3),
            observed=round(sum(y for _, y in inside) / len(inside), 3),
        ))
    return out


def measure(cases: list[Case], *, threshold: float = THRESHOLD, bins: int = BINS) -> Metrics:
    scored = [c for c in cases if c.likelihood is not None]
    labelled = [(c.likelihood, c.label) for c in scored if c.label is not None]
    counts = Counter()
    for likelihood, label in labelled:
        predicted = int(likelihood > threshold)
        counts[(label, predicted)] += 1
    brier = (sum((p - y) ** 2 for p, y in labelled) / len(labelled)) if labelled else None
    return Metrics(
        scored=len(scored),
        labelled=len(labelled),
        positives=sum(1 for _, y in labelled if y == 1),
        negatives=sum(1 for _, y in labelled if y == 0),
        unlabelled=sum(1 for c in scored if c.label is None),
        failed=sum(1 for c in cases if c.likelihood is None),
        threshold=threshold,
        true_positive=counts[(1, 1)],
        false_positive=counts[(0, 1)],
        true_negative=counts[(0, 0)],
        false_negative=counts[(1, 0)],
        brier=round(brier, 4) if brier is not None else None,
        bins=calibration_bins(labelled, bins),
    )


def sweep(cases: list[Case], thresholds: tuple[float, ...] = (0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85)) -> list[dict[str, Any]]:
    """Precision and recall at every operating point. Choosing where to call a claim misleading
    is a decision, not a fact, and this is what it costs either way: the roadmap's "if
    calibration is poor, adjust the combination" starts here, before anything is re-scored."""
    out = []
    for threshold in thresholds:
        m = measure(cases, threshold=threshold)
        out.append({
            "threshold": threshold, "precision": m.precision, "recall": m.recall,
            "accuracy": m.accuracy, "true_positive": m.true_positive, "false_positive": m.false_positive,
            "true_negative": m.true_negative, "false_negative": m.false_negative,
        })
    return out


def report(cases: list[Case], metrics: Metrics) -> dict[str, Any]:
    """The artifact the app reads: every case with its score and label, and the metrics."""
    return {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "leave-one-out over the precedent store; Clarity and Support only (see auditor/calibration.py)",
        "dimensions": list(DIMENSIONS_RUN),
        "metrics": {
            **{k: v for k, v in asdict(metrics).items() if k != "bins"},
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
            "accuracy": metrics.accuracy,
            "caveat": metrics.caveat(),
            "bins": [asdict(b) for b in metrics.bins],
            "sweep": sweep(cases),
        },
        "cases": [asdict(c) for c in cases],
    }


def load_report(path: Path) -> tuple[list[Case], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {f for f in Case.__dataclass_fields__}
    return [Case(**{k: v for k, v in row.items() if k in fields}) for row in raw.get("cases", [])], raw


# ----------------------------------------------------------------------------- command line


def _curve(metrics: Metrics, width: int = 34) -> list[str]:
    """The calibration curve as text, so it can be read without the app."""
    lines = ["", "  calibration curve — predicted (o) against what regulators decided (x)"]
    for b in metrics.bins:
        row = [" "] * (width + 1)
        for value, mark in ((b.predicted, "o"), (b.observed, "x")):
            row[min(width, max(0, round(value * width)))] = mark
        lines.append(f"  {b.low:.1f}-{b.high:.1f} |{''.join(row)}| n={b.count:<3} predicted {b.predicted:.2f} observed {b.observed:.2f}")
    lines.append(f"           {'0':<{width // 2}}{'0.5':^{width // 2}}1")
    return lines


def _print(cases: list[Case], metrics: Metrics) -> None:
    for case in sorted(cases, key=lambda c: (c.likelihood is None, -(c.likelihood or 0))):
        if case.error:
            print(f"  {case.store_id[:38]:<40} FAILED  {case.error[:60]}")
            continue
        mark = {None: " ", True: "ok ", False: "MISS"}[None if case.label is None else case.predicted == case.label]
        parts = " ".join(f"{d[:3]} {case.scores[d]['score']:.2f}" for d in DIMENSIONS_RUN if d in case.scores)
        print(f"  {case.store_id[:38]:<40} {case.outcome:<14} likelihood {case.likelihood:<5} {case.category:<22} {parts}  {mark}")
    print()
    print(metrics.describe())
    print(f"  confusion: {metrics.true_positive} true positive, {metrics.false_positive} false positive, "
          f"{metrics.true_negative} true negative, {metrics.false_negative} false negative")
    print("\n".join(_curve(metrics)))
    print("\n  where to draw the line")
    print(f"  {'threshold':>9} {'precision':>9} {'recall':>7} {'accuracy':>8}   TP  FP  TN  FN")
    for row in sweep(cases):
        def pct(v):
            return "n/a" if v is None else f"{v:.0%}"
        print(f"  {row['threshold']:>9g} {pct(row['precision']):>9} {pct(row['recall']):>7} {pct(row['accuracy']):>8}   "
              f"{row['true_positive']:>2}  {row['false_positive']:>2}  {row['true_negative']:>2}  {row['false_negative']:>2}")
    print(f"\n  {metrics.caveat()}")


async def _run(args: argparse.Namespace) -> int:
    store = get_knowledge()
    done: list[str] = []

    def tick(case: Case) -> None:
        done.append(case.store_id)
        print(f"  [{len(done)}] {case.store_id[:44]:<46} {'failed' if case.error else f'likelihood {case.likelihood}'}", file=sys.stderr)

    try:
        cases, usage = await run_calibration(
            knowledge=store, limit=args.limit, settled_positive=args.settled_positive,
            concurrency=args.concurrency, on_case=tick,
        )
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    metrics = measure(cases, threshold=args.threshold, bins=args.bins)
    payload = report(cases, metrics)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"note: written to {path}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print(cases, metrics)
    return 0


def _report(args: argparse.Namespace) -> int:
    cases, raw = load_report(Path(args.report))
    for case in cases:
        case.label = label_of(case.outcome, settled_positive=args.settled_positive)
    metrics = measure(cases, threshold=args.threshold, bins=args.bins)
    if args.json:
        print(json.dumps(report(cases, metrics), ensure_ascii=False, indent=2))
    else:
        print(f"{raw.get('generated', '?')}: {raw.get('method', '')}\n")
        _print(cases, metrics)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.calibration", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"a claim is called misleading above this likelihood (default {THRESHOLD:g})")
    parser.add_argument("--bins", type=int, default=BINS, help=f"buckets in the calibration curve (default {BINS})")
    parser.add_argument("--settled-positive", action="store_true", help="count settled cases as misleading instead of leaving them out")
    parser.add_argument("--json", action="store_true", help="print the whole report as JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="score every precedent leave-one-out; calls Claude")
    run.add_argument("--out", help="write the report here (e.g. data/calibration.json)")
    run.add_argument("--limit", type=int, help="only the first N precedents")
    run.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"cases at once (default {CONCURRENCY})")
    read = sub.add_parser("report", help="recompute the metrics from a saved run; calls no model")
    read.add_argument("report", help="a calibration.json written by `run`")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args)) if args.command == "run" else _report(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
