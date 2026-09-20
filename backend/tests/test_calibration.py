"""Calibration: the ruling under test is taken out of the store before its own wording is
scored, the label mapping refuses to invent ground truth out of a settlement, and the metrics
say plainly what a set of 17 positives and 3 negatives can and cannot support. Only the
end-to-end test touches a (fake) model."""

from __future__ import annotations

import asyncio
import json

import pytest

from auditor.calibration import (
    DIMENSIONS_RUN,
    NEGATIVE,
    POSITIVE,
    Case,
    calibration_bins,
    case_claim,
    case_document,
    cases_from,
    label_of,
    load_report,
    measure,
    report,
    run_calibration,
    run_case,
)
from auditor.knowledge import Knowledge, PrecedentIndex, StoreEntry, get_knowledge
from auditor.llm import LlmError


def precedent(store_id: str, outcome: str, claim_text: str = "carbon neutral by 2030", company: str = "Acme") -> StoreEntry:
    return StoreEntry(
        id=store_id, kind="ruling", tier=1, source={"name": f"Ruling {store_id}"}, url=f"https://reg.example/{store_id}",
        quote="misleading", verified=True, verification="fetched_exact", retrieved="2026-09-20",
        index=PrecedentIndex(jurisdiction="UK", body="ASA", company=company, claim_text=claim_text,
                             outcome=outcome, reasoning="because.", terms=["carbon neutral"], applies_to=["vague_attribute"]),
    )


def store(*entries: StoreEntry) -> Knowledge:
    return Knowledge([], list(entries))


def case(likelihood: float | None, label: int | None, store_id: str = "p") -> Case:
    return Case(store_id=store_id, claim_text="t", outcome="upheld" if label else "not_upheld", label=label, likelihood=likelihood)


# ----------------------------------------------------------------------------- labels


def test_a_settlement_is_not_a_finding_either_way():
    assert label_of("upheld") == 1 and label_of("upheld_in_part") == 1
    assert label_of("not_upheld") == 0 and label_of("dismissed") == 0
    assert label_of("settled") is None, "a company that settles admits nothing"
    assert label_of("settled", settled_positive=True) == 1, "unless the run is told to count it"
    assert label_of(None) is None and label_of("something else") is None
    assert not set(POSITIVE) & set(NEGATIVE)


def test_the_real_precedent_store_is_a_small_and_lopsided_test_set():
    """Worth stating in a test: the shape of this set is why the report leads with a caveat."""
    cases = cases_from(get_knowledge())
    assert len(cases) >= 20 and all(c.claim_text and c.outcome for c in cases)
    assert sum(1 for c in cases if c.label == 1) > 10
    assert sum(1 for c in cases if c.label == 0) < 5, "too few negatives for precision to mean much"
    assert len({c.store_id for c in cases}) == len(cases)


# ----------------------------------------------------------------------------- the case document


def test_a_wording_becomes_a_one_claim_document_with_no_url_to_fetch():
    row = Case(store_id="p1", claim_text="We are  carbon neutral", outcome="upheld", company="Acme", body="ASA", claim_type="vague_attribute")
    document, claim = case_document(row), case_claim(row)
    assert document["text"] == "We are  carbon neutral" and document["company"]["name"] == "Acme"
    assert document["source"]["url"] is None, "nothing to fetch, so nothing can leak in"
    assert document["text_type"] == "claim" and "ASA" in document["title"]
    assert claim["spans"][0] == {"text": row.claim_text, "start": 0, "end": len(row.claim_text)}
    assert document["text"][claim["spans"][0]["start"]:claim["spans"][0]["end"]] == claim["spans"][0]["text"]
    assert claim["type"] == "vague_attribute" and claim["prominence"] == 1.0
    assert case_claim(Case(store_id="p", claim_text="x", outcome="upheld", claim_type="nonsense"))["type"] == "factual"


# ----------------------------------------------------------------------------- metrics


def test_precision_recall_and_the_confusion_matrix():
    cases = [case(0.9, 1), case(0.8, 1), case(0.2, 1), case(0.9, 0), case(0.1, 0), case(0.7, None)]
    m = measure(cases)
    assert (m.true_positive, m.false_negative, m.false_positive, m.true_negative) == (2, 1, 1, 1)
    assert m.precision == 2 / 3 and m.recall == 2 / 3 and round(m.f1, 4) == round(2 / 3, 4)
    assert m.accuracy == 3 / 5 and m.labelled == 5 and m.unlabelled == 1 and m.failed == 0
    assert "precision 67%, recall 67%" in m.describe()


def test_the_threshold_moves_the_line_and_nothing_else():
    cases = [case(0.6, 1), case(0.4, 0)]
    assert measure(cases, threshold=0.5).true_positive == 1
    assert measure(cases, threshold=0.7).true_positive == 0 and measure(cases, threshold=0.7).false_negative == 1
    assert measure(cases, threshold=0.3).false_positive == 1


def test_a_case_that_failed_to_score_is_counted_as_failed_not_as_wrong():
    m = measure([case(None, 1), case(0.9, 1)])
    assert m.failed == 1 and m.scored == 1 and m.labelled == 1
    assert m.recall == 1.0, "a case that never ran is not a miss"


def test_the_brier_score_rewards_being_right_and_being_sure():
    assert measure([case(1.0, 1), case(0.0, 0)]).brier == 0.0
    assert measure([case(0.0, 1), case(1.0, 0)]).brier == 1.0
    assert measure([case(0.5, 1), case(0.5, 0)]).brier == 0.25


def test_the_curve_buckets_by_what_was_predicted_and_reports_what_happened():
    rows = [(0.1, 0), (0.15, 0), (0.85, 1), (0.95, 1), (0.9, 0)]
    bins = calibration_bins(rows, bins=5)
    assert [b.count for b in bins] == [2, 3], "empty buckets are left out"
    low, high = bins
    assert (low.low, low.high) == (0.0, 0.2) and low.observed == 0.0 and low.predicted == 0.125
    assert round(high.observed, 2) == round(2 / 3, 2) and high.gap() > 0, "over-confident in the top bucket"
    assert calibration_bins([(1.0, 1)], bins=5)[0].count == 1, "a likelihood of exactly 1 lands in the last bucket"
    assert calibration_bins([], bins=5) == []


def test_the_report_leads_with_what_the_set_cannot_support():
    m = measure([case(0.9, 1) for _ in range(17)] + [case(0.1, 0) for _ in range(3)])
    assert "Only 3 of the 20 adjudicated cases" in m.caveat() and "precision rests on too few negatives" in m.caveat()
    assert "calibration curve is the number to read" in m.caveat()
    plenty = measure([case(0.9, 1) for _ in range(10)] + [case(0.1, 0) for _ in range(10)])
    assert plenty.caveat() == "10 positive and 10 negative cases."


def test_a_report_round_trips_so_the_thresholds_can_move_without_paying_again(tmp_path):
    cases = [case(0.9, 1, "a"), case(0.2, 0, "b")]
    m = measure(cases)
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(report(cases, m)), encoding="utf-8")
    back, raw = load_report(path)
    assert [c.store_id for c in back] == ["a", "b"] and [c.likelihood for c in back] == [0.9, 0.2]
    assert raw["metrics"]["precision"] == 1.0 and raw["metrics"]["caveat"]
    assert raw["dimensions"] == list(DIMENSIONS_RUN) and "leave-one-out" in raw["method"]
    assert measure(back).describe() == m.describe()


# ----------------------------------------------------------------------------- running


class FakeStages:
    """Stands in for the language and substantiation evaluators, recording the store each case
    was given so the hold-out can be checked."""

    def __init__(self, clarity: float = 0.8, support: float = 0.6, error: Exception | None = None) -> None:
        self.clarity, self.support, self.error = clarity, support, error
        self.seen: list[tuple[str, list[str]]] = []

    async def review_language(self, document, claims, *, emit=None, llm=None):
        from auditor.language import LanguageResult

        if self.error is not None:
            raise self.error
        return LanguageResult([], [{"claim_id": "C1", "dimension": "clarity", "score": self.clarity, "confidence": 0.9, "basis": "b."}])

    async def substantiate(self, document, claims, *, emit=None, llm=None, knowledge=None, score=True):
        from auditor.substantiate import SubstantiationResult

        self.seen.append((document["id"], [e.id for e in knowledge.precedents]))
        assert score is True, "calibration needs the support score, so it must ask for it"
        return SubstantiationResult([], [{"claim_id": "C1", "dimension": "support", "score": self.support, "confidence": 0.7, "basis": "b.", "evidence_ids": ["P1"]}])


@pytest.fixture
def stages(monkeypatch) -> FakeStages:
    from auditor import language as language_module
    from auditor import substantiate as substantiate_module

    fake = FakeStages()
    monkeypatch.setattr(language_module, "review_language", fake.review_language)
    monkeypatch.setattr(substantiate_module, "substantiate", fake.substantiate)
    return fake


def test_the_ruling_under_test_is_taken_out_of_the_store_before_its_wording_is_scored(stages):
    knowledge = store(precedent("p1", "upheld"), precedent("p2", "not_upheld"), precedent("p3", "upheld"))
    row = cases_from(knowledge)[0]
    done = asyncio.run(run_case(row, knowledge))
    assert done.held_out == ["p1"], "its own ruling"
    assert stages.seen == [("cal-p1", ["p2", "p3"])], "and the other two stay in"
    assert done.likelihood == 0.8 == max(stages.clarity, stages.support), "the weakest link of what was scored"
    assert done.category == "unsubstantiated" and set(done.scores) == set(DIMENSIONS_RUN)
    assert done.predicted == 1 and done.label == 1


def test_every_case_is_run_against_a_store_without_itself(stages):
    knowledge = store(precedent("p1", "upheld"), precedent("p2", "not_upheld"), precedent("p3", "settled"))
    cases, usage = asyncio.run(run_calibration(knowledge=knowledge, concurrency=1))
    assert [c.store_id for c in cases] == ["p1", "p2", "p3"]
    assert [c.held_out for c in cases] == [["p1"], ["p2"], ["p3"]]
    assert all(sorted(seen) == sorted({"p1", "p2", "p3"} - {doc.removeprefix("cal-")}) for doc, seen in stages.seen)
    assert [c.label for c in cases] == [1, 0, None]
    assert usage is not None


def test_a_case_that_the_model_cannot_score_is_recorded_and_the_run_carries_on(stages, monkeypatch):
    from auditor import language as language_module

    failing = FakeStages(error=LlmError("the model's stream went quiet"))
    monkeypatch.setattr(language_module, "review_language", failing.review_language)
    knowledge = store(precedent("p1", "upheld"))
    cases, _ = asyncio.run(run_calibration(knowledge=knowledge))
    assert cases[0].likelihood is None and "went quiet" in cases[0].error
    assert measure(cases).failed == 1


def test_the_limit_shrinks_the_set_rather_than_the_method(stages):
    """The roadmap's fallback if time is short is to shrink the set, not to cut the step."""
    knowledge = store(precedent("p1", "upheld"), precedent("p2", "upheld"), precedent("p3", "upheld"))
    cases, _ = asyncio.run(run_calibration(knowledge=knowledge, limit=2))
    assert [c.store_id for c in cases] == ["p1", "p2"]
    assert all(c.held_out == [c.store_id] for c in cases), "still leave-one-out"
