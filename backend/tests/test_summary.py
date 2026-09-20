"""Document aggregation: every number in the header is arithmetic over the claims beneath it
and says which ones it came from, a page cannot bury a bad headline under true trivia, and the
model is asked for the words only. No test calls Claude."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO

from auditor.llm import LlmError, Usage
from auditor.summary import (
    CATEGORIES,
    POWER,
    DEFAULT_PROMINENCE,
    PROFILE,
    Header,
    Row,
    Title,
    aggregate,
    build_summary,
    compare_summaries,
    explain,
    summarise,
    aggregate_rows,
    contributions,
    write_prompt,
)


DOC = {"id": "d", "title": "T", "company": {"name": "Acme"}, "text": "A page.", "word_count": 2, "regions": []}


def claim(cid: str, words: str = "a claim", prominence: float | None = 1.0) -> dict:
    out = {"id": cid, "spans": [{"text": words, "start": 0, "end": len(words)}], "type": "factual", "scope": "company"}
    if prominence is not None:
        out["prominence"] = prominence
    return out


def score(cid: str, dimension: str, value: float, confidence: float = 0.8) -> dict:
    return {"claim_id": cid, "dimension": dimension, "score": value, "confidence": confidence, "basis": "b.", "stage": "verify"}


def verdict(cid: str, likelihood: float, category: str = "misleading_by_framing", confidence: float = 0.8) -> dict:
    return {"claim_id": cid, "likelihood": likelihood, "confidence": confidence, "category": category, "tags": [], "rationale": f"{cid}."}


def omission(oid: str, value: float = 0.7, confidence: float = 0.9) -> dict:
    return {"id": oid, "topic": f"Topic {oid}", "why_material": "It is material.", "complete_text": "It would say this.", "score": value, "confidence": confidence}


def full(cid: str, value: float, prominence: float = 1.0, confidence: float = 0.8) -> tuple[dict, list[dict], dict]:
    """A claim scored the same on all four dimensions, with the matching verdict."""
    return (
        claim(cid, f"claim {cid}", prominence),
        [score(cid, d, value, confidence) for d in ("clarity", "support", "materiality", "consistency")],
        verdict(cid, value, "supported" if value <= 0.5 else "misleading_by_framing", confidence),
    )


def page(*rows):
    claims, scores, verdicts = [], [], []
    for c, ss, v in rows:
        claims.append(c); scores.extend(ss); verdicts.append(v)
    return claims, scores, verdicts


def golden() -> dict:
    return json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


# ----------------------------------------------------------------------------- the arithmetic


def test_the_mean_leans_to_the_worst_without_leaving_the_range():
    rows = [Row("A", 0.9, 1.0, 1.0), Row("B", 0.1, 1.0, 1.0), Row("C", 0.1, 1.0, 1.0)]
    got = aggregate_rows(rows)
    plain = (0.9 + 0.1 + 0.1) / 3
    assert plain < got.score <= 0.9, "above the plain mean, never above the worst claim"
    assert got.drivers[0] == "A", "and it says which claim put it there"
    assert aggregate_rows([]).score == 0.0
    assert aggregate_rows([Row("A", 0.4, 0.9, 1.0)]).score == 0.4, "one claim is its own mean"


def test_a_page_with_nothing_wrong_reads_zero_and_still_reports_its_confidence():
    rows = [Row("A", 0.0, 0.9, 1.0), Row("B", 0.0, 0.7, 1.0)]
    got = aggregate_rows(rows)
    assert got.score == 0.0 and got.drivers == []
    assert got.confidence == round((0.9 * 0.9 + 0.7 * 0.7) / (0.9 + 0.7), 2), "still weighted by how sure each reading is"


def test_contributions_say_how_much_of_the_number_each_claim_is():
    rows = [Row("A", 0.9, 1.0, 1.0), Row("B", 0.1, 1.0, 1.0)]
    shares = contributions(rows)
    assert [t for t, _ in shares] == ["A", "B"]
    assert round(sum(share for _, share in shares), 6) == 1.0
    assert shares[0][1] > 0.95, f"a claim {0.9 / 0.1:.0f}x worse dominates at power {POWER}"


def test_prominence_and_confidence_are_the_weights():
    loud = Row("loud", 0.8, 0.9, 1.0)
    quiet = Row("quiet", 0.8, 0.9, 0.3)
    assert loud.weight > quiet.weight and loud.severity > quiet.severity
    unsure = Row("unsure", 0.8, 0.2, 1.0)
    assert unsure.weight < loud.weight, "a reading nobody is sure of has less say"


def test_a_true_footnote_cannot_bury_a_false_headline():
    """The document-level form of weakest-link (D6): the page is judged by what it says
    loudest, not by how many harmless sentences surround it. This is the property the whole
    aggregation is chosen for, so it is worth stating twice as loudly as the rest."""
    hero = full("C1", 0.9, prominence=1.0)
    trivia = [full(f"C{i}", 0.05, prominence=0.3) for i in range(2, 22)]
    claims, scores, verdicts = page(hero, *trivia)
    summary, _ = aggregate(claims, scores, verdicts, [])
    assert summary["headline"]["score"] >= 0.8, "twenty true footnotes do not dilute one false headline"
    mean = sum(v["likelihood"] for v in verdicts) / len(verdicts)
    assert mean < 0.2, "the plain mean would have called this page clean"
    doubled = page(hero, *trivia, *[full(f"D{i}", 0.05, prominence=0.3) for i in range(40)])
    assert aggregate(*doubled, [])[0]["headline"]["score"] >= 0.8, "and forty more do not either"


def test_every_number_says_which_claims_it_came_from():
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1), full("C3", 0.1))
    summary, parts = aggregate(claims, scores, verdicts, [omission("O1", 0.8)])
    assert summary["ext"]["drivers"]["headline"][0] == "C1", "the worst claim drove the headline"
    assert summary["ext"]["drivers"]["completeness"] == ["O1"]
    assert set(summary["ext"]["drivers"]) == {*PROFILE, "headline"}
    lines = explain(summary, parts)
    assert any(line.startswith("headline") and "C1" in line for line in lines)
    assert all("driven by" in line for line in lines)


def test_the_distribution_and_the_counts_are_what_the_contract_checks():
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1), full("C3", 0.1))
    summary, _ = aggregate(claims, scores, verdicts, [omission("O1"), omission("O2")])
    assert summary["verdict_distribution"] == {"supported": 2, "unsubstantiated": 0, "misleading_by_framing": 1, "contradicted": 0}
    assert sum(summary["verdict_distribution"].values()) == len(verdicts)
    assert set(summary["verdict_distribution"]) == set(CATEGORIES)
    assert summary["claim_count"] == 3 and summary["omission_count"] == 2
    assert [t["rank"] for t in summary["top_issues"]] == list(range(1, len(summary["top_issues"]) + 1))


def test_completeness_comes_from_the_omissions_and_is_empty_without_them():
    claims, scores, verdicts = page(full("C1", 0.4))
    summary, _ = aggregate(claims, scores, verdicts, [omission("O1", 0.9), omission("O2", 0.1), omission("O3", 0.1)])
    assert summary["dimensions"]["completeness"]["score"] >= 0.85, "the biggest gap sets it"
    bare, _ = aggregate(claims, scores, verdicts, [])
    assert bare["dimensions"]["completeness"] == {"score": 0.0, "confidence": 0.0}, "nothing found is not a problem found"
    assert set(bare["dimensions"]) == set(PROFILE)


def test_credit_is_the_best_supported_claims_and_never_anything_else():
    """The contract's validator warns about a credit whose verdict is not `supported`."""
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1), full("C3", 0.3), full("C4", 0.2))
    summary, _ = aggregate(claims, scores, verdicts, [])
    assert [t["target"] for t in summary["credit"]] == ["C2", "C4", "C3"], "lowest likelihood first"
    assert all(next(v for v in verdicts if v["claim_id"] == t["target"])["category"] == "supported" for t in summary["credit"])


def test_a_claim_with_no_prominence_is_treated_as_body_text():
    unmarked = (claim("C1", "a claim", prominence=None), [score("C1", d, 0.5) for d in ("clarity", "support", "materiality", "consistency")], verdict("C1", 0.5))
    claims, scores, verdicts = page(unmarked)
    summary, parts = aggregate(claims, scores, verdicts, [])
    assert summary["headline"]["score"] == 0.5, "it still counts"
    assert 0 < DEFAULT_PROMINENCE < 1


def test_the_aggregation_lands_close_to_the_golden_references_hand_written_header():
    """The reference's header was a judgment; this is arithmetic. They should agree on the
    headline and on the shape of the profile, and the ranking should find the same claims."""
    analysis = golden()
    summary, _ = aggregate(analysis["claims"], analysis["scores"], analysis["verdicts"], analysis["omissions"])
    comparison = compare_summaries(summary, analysis["summary"])
    assert comparison.mean_abs_error <= 0.09
    headline = next(p for p in comparison.pairs if p[0] == "headline")
    # The analyst read the page at 0.80 and this reads it at 0.70. A statistic that matched the
    # hand number more closely was tried and rejected: it let twenty true footnotes bury one
    # false headline, which is the failure this aggregation exists to prevent.
    assert abs(headline[1] - headline[2]) <= 0.12
    assert summary["verdict_distribution"] == analysis["summary"]["verdict_distribution"]
    assert len(set(comparison.issues[0]) & set(comparison.issues[1])) >= 3
    assert len(set(comparison.credit[0]) & set(comparison.credit[1])) >= 3


def test_the_golden_header_still_satisfies_the_contracts_own_checks():
    """A live header has to pass what the fixture passes: `check_analysis` on the folded
    analysis with the computed summary swapped in for the hand-written one."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("contract_tool", REPO / "contract" / "tools" / "contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    analysis = golden()
    result = build_summary(analysis["document"], analysis["claims"], analysis["scores"], analysis["verdicts"], analysis["omissions"])
    report = module.Report()
    module.check_analysis({**analysis, "summary": result.summary}, report, strict_summary=True)
    assert not report.errors, report.errors
    assert not [w for w in report.warnings if "credit" in w], report.warnings


# ----------------------------------------------------------------------------- the words


def test_the_model_writes_the_titles_and_changes_no_number():
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1))
    before, _ = aggregate(claims, scores, verdicts, [omission("O1")])
    header = Header(
        issues=[Title(target="C1", title="  The figure has no baseline.  "), Title(target="O1", title="Not mentioned: the capital split")],
        credit=[Title(target="C2", title="Assured and dated")],
        narrative="  The page leans on one\n number.  ",
    )
    result = build_summary({}, claims, scores, verdicts, [omission("O1")], header)
    assert result.summary["headline"] == before["headline"], "the arithmetic is settled before the writing"
    titles = {t["target"]: t["title"] for t in result.summary["top_issues"]}
    assert titles["C1"] == "The figure has no baseline", "whitespace collapsed, full stop dropped"
    assert titles["O1"] == "Not mentioned: the capital split"
    assert result.summary["credit"][0]["title"] == "Assured and dated"
    assert result.summary["narrative"] == "The page leans on one number."
    assert result.untitled == []


def test_a_target_the_writer_skipped_falls_back_to_its_own_words():
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1))
    result = build_summary({}, claims, scores, verdicts, [omission("O1")], Header(issues=[Title(target="C9", title="not a target here")]))
    titles = {t["target"]: t["title"] for t in [*result.summary["top_issues"], *result.summary["credit"]]}
    assert titles["C1"] == "claim C1" and titles["O1"] == "Not mentioned: Topic O1"
    assert sorted(result.untitled) == ["C1", "C2", "O1"]
    assert "3 targets the writer did not name" in result.notes[-1]
    assert all(t["title"] for t in result.summary["top_issues"]), "every link still has something to show"


def test_the_writing_prompt_shows_the_finding_not_just_the_claim():
    analysis = golden()
    summary, _ = aggregate(analysis["claims"], analysis["scores"], analysis["verdicts"], analysis["omissions"])
    prompt = write_prompt(
        summary, {c["id"]: c for c in analysis["claims"]},
        {v["claim_id"]: v for v in analysis["verdicts"]}, {o["id"]: o for o in analysis["omissions"]},
    )
    assert "<issues>" in prompt and "<credit>" in prompt
    assert "The judge:" in prompt and "Why it is material:" in prompt
    assert 'its title begins "Not mentioned: "' in prompt
    assert "O2 | omission |" in prompt


class FakeWriter:
    def __init__(self, header: Header | None = None, error: Exception | None = None) -> None:
        self.header = header or Header()
        self.error = error
        self.calls: list[dict] = []

    async def extract(self, prompt, output, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if self.error is not None:
            raise self.error
        return self.header, usage()


def test_the_stage_emits_one_final_summary_and_asks_for_the_words_once():
    claims, scores, verdicts = page(full("C1", 0.9), full("C2", 0.1))
    events: list[tuple[str, dict]] = []
    llm = FakeWriter(Header(issues=[Title(target="C1", title="No baseline")], narrative="A page."))
    result = asyncio.run(summarise(DOC, claims, scores, verdicts, [], emit=lambda t, p: events.append((t, p)), llm=llm))
    assert [t for t, _ in events] == ["summary.updated"]
    assert events[0][1]["final"] is True and events[0][1]["summary"] is result.summary
    assert len(llm.calls) == 1 and llm.calls[0]["cache"] is True and llm.calls[0]["effort"] == "medium"
    assert result.usage is not None and result.usage.input_tokens == 10
    assert result.notes[0].startswith("Headline 0.89") and "leaning to the worst" in result.notes[0]
    assert any(line.startswith("clarity") for line in result.notes)


def test_a_page_with_nothing_to_rank_needs_no_call_at_all():
    result = asyncio.run(summarise(DOC, [], [], [], [], llm=FakeWriter(error=LlmError("should not be called"))))
    assert result.summary["claim_count"] == 0 and result.summary["top_issues"] == [] and result.summary["credit"] == []
    assert result.summary["headline"] == {"score": 0.0, "confidence": 0.0} and result.usage is not None


def test_a_failing_writer_fails_the_stage_with_a_plain_error():
    claims, scores, verdicts = page(full("C1", 0.9))
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(summarise(DOC, claims, scores, verdicts, [], llm=FakeWriter(error=LlmError("Claude's stream went quiet"))))


def test_the_comparison_reports_what_moved():
    live = {"headline": {"score": 0.8, "confidence": 0.9}, "dimensions": {n: {"score": 0.5, "confidence": 0.8} for n in PROFILE},
            "top_issues": [{"rank": 1, "target": "C1", "title": "x"}], "credit": [{"target": "C2", "title": "y"}]}
    reference = {"headline": {"score": 0.7, "confidence": 0.9}, "dimensions": {n: {"score": 0.5, "confidence": 0.8} for n in PROFILE},
                 "top_issues": [{"rank": 1, "target": "C1", "title": "x"}, {"rank": 2, "target": "C3", "title": "z"}], "credit": [{"target": "C9", "title": "y"}]}
    comparison = compare_summaries(live, reference)
    assert round(comparison.mean_abs_error, 3) == round(0.1 / 6, 3)
    assert "headline +0.10" in comparison.describe()
    assert "1 of 2 top issues and 0 of 1 credits the same" in comparison.describe()
