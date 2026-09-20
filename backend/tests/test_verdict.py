"""The verdict layer: the debate streams before the verdict it decides, the likelihood and the
category are derived by the contract's rules rather than judged, the confidence formula is the
one the module documents, and the whole thing reproduces the golden reference's verdicts from
the reference's own scores. No test calls the model."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO

from auditor.llm import LlmError, Usage
from auditor.verdict import (
    DERIVED_RATIONALE,
    DIMENSIONS,
    HUMILITY,
    NO_EVIDENCE_CAP,
    TIER_CAP,
    Case,
    Cases,
    Judgment,
    Judgments,
    apply_verdicts,
    calibrate,
    calibration_report,
    check_derivation,
    claim_dossier,
    compare_verdicts,
    deciding_dimension,
    derive_category,
    derive_likelihood,
    index_evidence,
    index_scores,
    index_signals,
    issue_verdicts,
    judge_prompt,
    propose_tags,
    verdict_confidence,
)


def document(text: str = "We are carbon neutral. Our target is net zero by 2050.") -> dict:
    return {"id": "d", "title": "Climate", "company": {"name": "Acme"}, "text_type": "policy", "source": {"url": "https://acme.example/climate"}, "text": text, "word_count": 11, "regions": []}


def claim(cid: str, words: str, type_: str = "factual") -> dict:
    text = document()["text"]
    start = text.index(words)
    return {"id": cid, "spans": [{"text": words, "start": start, "end": start + len(words)}], "type": type_, "scope": "company", "attribute": words, "paragraph": "P1", "prominence": 1.0}


def scored(cid: str, clarity=0.2, support=0.2, materiality=0.2, consistency=0.2, confidence=0.8) -> list[dict]:
    values = {"clarity": clarity, "support": support, "materiality": materiality, "consistency": consistency}
    out = []
    for dimension, value in values.items():
        score, conf = value if isinstance(value, tuple) else (value, confidence)
        out.append({"claim_id": cid, "dimension": dimension, "score": score, "confidence": conf, "basis": f"{dimension} basis.", "stage": "verify"})
    return out


def evidence(eid: str, target: str, relation: str, tier: int = 2, **kw) -> dict:
    item = {"id": eid, "kind": "filing", "tier": tier, "source": {"name": f"Source {eid}"}, "quote": "A quoted sentence.", "verified": True, "verification": "fetched_exact", "retrieved": "2026-09-20", "stage": "verify", "links": [{"target": target, "relation": relation}]}
    return {**item, **kw}


def dimensions(**kw) -> dict:
    """The four dimensions as verdict_confidence and derive_category read them."""
    out = {}
    for dimension in DIMENSIONS:
        value = kw.get(dimension, 0.2)
        score, conf = value if isinstance(value, tuple) else (value, 0.8)
        out[dimension] = {"score": score, "confidence": conf}
    return out


def emitted():
    events: list[tuple[str, dict]] = []
    return events, lambda type_, payload: events.append((type_, payload))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def golden() -> dict:
    return json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- the arithmetic (CONTRACT.md §6)


def test_likelihood_is_the_weakest_link_not_an_average():
    assert derive_likelihood(dimensions(clarity=0.1, support=0.9, materiality=0.1, consistency=0.1)) == 0.9
    assert derive_likelihood(dimensions(clarity=0.4, support=0.4, materiality=0.4, consistency=0.4)) == 0.4
    assert derive_likelihood({}) == 0.5, "nothing scored: the middle, and the confidence formula says so"


def test_the_category_rules_are_the_contract_in_order():
    contradicting = dimensions(support=(0.8, 0.7))
    assert derive_category(contradicting, True) == "contradicted"
    assert derive_category(contradicting, False) == "misleading_by_framing", "a contradicted claim needs an item that contradicts it"
    assert derive_category(dimensions(consistency=(0.8, 0.7)), True) == "contradicted", "consistency reaches it too"
    assert derive_category(dimensions(support=(0.8, 0.5)), True) == "misleading_by_framing", "not at confidence 0.5"
    assert derive_category(dimensions(clarity=0.7, support=0.1), False) == "unsubstantiated", "too vague to verify"
    assert derive_category(dimensions(support=(0.5, 0.5)), False) == "unsubstantiated", "nothing found either way"
    assert derive_category(dimensions(support=(0.5, 0.7)), False) == "supported", "found, and it is fine"
    assert derive_category(dimensions(materiality=0.6), False) == "misleading_by_framing"
    assert derive_category(dimensions(), False) == "supported"


def test_the_two_consequences_the_contract_calls_out():
    """CONTRACT.md §6: materiality alone at 0.5 stays supported and carries the caveat; an item
    that contradicts only the framing does not make a claim contradicted."""
    assert derive_category(dimensions(materiality=0.5), False) == "supported"
    assert derive_likelihood(dimensions(materiality=0.5)) == 0.5, "and the 0.5 is visible on the verdict"
    framing_only = dimensions(consistency=(0.8, 0.9))
    assert derive_category(framing_only, False) == "misleading_by_framing"


def test_the_deciding_dimension_is_the_least_confident_of_the_tied_weakest_links():
    assert deciding_dimension(dimensions(support=0.9)) == "support"
    assert deciding_dimension(dimensions(clarity=(0.5, 0.9), materiality=(0.5, 0.6))) == "materiality"
    assert deciding_dimension(dimensions(clarity=(0.5, 0.8), materiality=(0.5, 0.8))) == "clarity", "then the contract's order"
    assert deciding_dimension({}) is None


# ----------------------------------------------------------------------------- the confidence formula


def test_confidence_starts_at_the_deciding_dimension_and_pays_the_humility():
    scores = dimensions(support=(0.9, 0.8))
    value, basis = verdict_confidence(scores, [evidence("E1", "C1", "supports", tier=1)], "C1")
    assert value == round(0.8 - HUMILITY, 2)
    assert basis.startswith("Support decides it at confidence 0.80")


def test_no_evidence_caps_confidence_because_nothing_found_is_not_proof():
    scores = dimensions(clarity=(0.5, 0.8), support=(0.45, 0.4), materiality=(0.5, 0.8), consistency=(0.2, 0.5))
    value, basis = verdict_confidence(scores, [], "C1")
    assert value == round(NO_EVIDENCE_CAP - HUMILITY, 2) == 0.5
    assert "no evidence was found for it" in basis


def test_the_evidence_tier_caps_a_verdict_that_rests_on_evidence_but_not_one_read_from_the_text():
    company_material = [evidence("E1", "C1", "contradicts_framing", tier=5)]
    resting_on_evidence = dimensions(materiality=(0.9, 0.9), clarity=(0.1, 0.4), support=(0.1, 0.4), consistency=(0.1, 0.4))
    value, basis = verdict_confidence(resting_on_evidence, company_material, "C1")
    assert value == round(TIER_CAP[5] - HUMILITY, 2) == 0.6 and "best evidence is tier 5" in basis
    read_from_the_text = dimensions(clarity=(0.9, 0.9), support=(0.1, 0.4), materiality=(0.1, 0.4), consistency=(0.1, 0.4))
    value, basis = verdict_confidence(read_from_the_text, company_material, "C1")
    assert value == round(0.9 - HUMILITY, 2), "no tier makes a vagueness reading surer or less sure"
    assert "tier" not in basis


def test_criteria_and_precedents_set_the_standard_and_only_grade_the_tier_when_nothing_decisive_was_found():
    scores = dimensions(support=(0.9, 0.9), clarity=(0.1, 0.4), materiality=(0.1, 0.4), consistency=(0.1, 0.4))
    rule_only = [evidence("K1", "C1", "criteria", tier=1)]
    assert verdict_confidence(scores, rule_only, "C1")[0] == round(0.9 - HUMILITY, 2), "a tier-1 rule caps nothing"
    with_a_weak_fact = [*rule_only, evidence("E1", "C1", "supports", tier=4)]
    assert verdict_confidence(scores, with_a_weak_fact, "C1")[0] == round(TIER_CAP[4] - HUMILITY, 2), "the fact decides, not the rule"


def test_evidence_that_both_supports_and_contradicts_is_evaluator_disagreement():
    scores = dimensions(support=(0.6, 0.9))
    conflicting = [evidence("E1", "C1", "supports", tier=1), evidence("E2", "C1", "contradicts", tier=1)]
    value, basis = verdict_confidence(scores, conflicting, "C1")
    assert value == round(0.9 - HUMILITY - 0.10, 2) and "both supports and contradicts" in basis


def test_a_dissenting_or_unstable_judge_lowers_confidence():
    scores = dimensions(support=(0.6, 0.9))
    items = [evidence("E1", "C1", "supports", tier=1)]
    agreed, _ = verdict_confidence(scores, items, "C1", judge_agreement=1.0)
    dissented, basis = verdict_confidence(scores, items, "C1", judge_agreement=0.0)
    assert dissented == round(agreed - 0.10, 2) and "the judge did not reach the same category" in basis
    unstable, basis = verdict_confidence(scores, items, "C1", judge_agreement=0.5, judge_stability=0.5)
    assert unstable == round(agreed - 0.05 - 0.05, 2) and "repeated judges disagreed" in basis


def test_confidence_is_held_inside_the_bounds_the_contract_sets():
    """CONTRACT.md §6: never above the highest dimension confidence, never more than 0.1 below
    the lowest. Four evaluators that are all sure hold the verdict up even where the formula
    would go lower, and the contract wins."""
    all_sure = dimensions(clarity=(0.5, 0.95), support=(0.5, 0.95), materiality=(0.5, 0.95), consistency=(0.5, 0.95))
    value, basis = verdict_confidence(all_sure, [], "C1")
    assert value == 0.85 == round(0.95 - 0.1, 2) and "held inside the range" in basis
    assert value <= max(s["confidence"] for s in all_sure.values())
    assert verdict_confidence(all_sure, [], "C1", judge_agreement=0.0)[0] == 0.85, "the floor absorbs the penalties"


def test_a_missing_dimension_is_said_and_capped():
    partial = {d: {"score": 0.3, "confidence": 0.9} for d in ("clarity", "support", "materiality")}
    value, basis = verdict_confidence(partial, [evidence("E1", "C1", "supports", tier=1)], "C1")
    assert value == 0.45 and "consistency was not scored" in basis
    assert derive_likelihood(partial) == 0.3, "the weakest link of what exists"


def test_the_formula_reproduces_the_golden_references_hand_assigned_confidences():
    """The calibration the module docstring quotes. It guards the constants: change one and
    this says by how much the reference moves."""
    rows = calibrate(golden())
    errors = [formula - reference for _, reference, formula, _ in rows]
    assert len(rows) == 25
    assert sum(abs(e) for e in errors) / len(errors) <= 0.05
    assert abs(sum(errors) / len(errors)) <= 0.03, "and it is not systematically over- or under-confident"
    assert sum(1 for e in errors if abs(e) <= 0.1) >= 23
    assert "mean absolute error 0.040" in calibration_report(rows)


def test_the_derivation_reproduces_every_verdict_in_the_golden_reference():
    """The likelihood and the category are rules, not judgments: run them over the reference's
    own scores and evidence and all 25 verdicts come back unchanged."""
    assert check_derivation(golden()) == []


# ----------------------------------------------------------------------------- the tags


def test_tags_are_read_off_the_analysis_as_candidates_for_the_judge():
    vague = claim("C1", "We are carbon neutral", "vague_attribute")
    assert "vagueness" in propose_tags(vague, dimensions(clarity=0.8), [], [evidence("E1", "C1", "supports")])
    assert "no_proof" in propose_tags(vague, dimensions(), [], []), "nothing to check at all"
    assert "no_proof" in propose_tags(vague, dimensions(support=0.7), [], [evidence("E1", "C1", "context")])
    assert "no_proof" not in propose_tags(vague, dimensions(support=0.7), [], [evidence("E1", "C1", "supports")])
    framing = [evidence("E1", "C1", "contradicts_framing")]
    assert "hidden_trade_off" in propose_tags(vague, dimensions(), [], framing)
    assert "greenrinsing" in propose_tags(vague, dimensions(consistency=0.7), [], framing), "a target weakened before it was met"
    false_label = claim("C1", "We are carbon neutral", "certification")
    assert "false_labels" in propose_tags(false_label, dimensions(support=0.6), [], framing)


def test_the_tag_rules_recover_most_of_the_golden_references_tags_before_any_judge_runs():
    analysis = golden()
    scores, signals, items = index_scores(analysis["scores"]), index_signals(analysis["signals"]), index_evidence(analysis["evidence"])
    claims = {c["id"]: c for c in analysis["claims"]}
    shared = reference_only = 0
    for verdict in analysis["verdicts"]:
        cid = verdict["claim_id"]
        proposed = set(propose_tags(claims[cid], scores.get(cid, {}), signals.get(cid, []), items.get(cid, [])))
        shared += len(proposed & set(verdict["tags"]))
        reference_only += len(set(verdict["tags"]) - proposed)
    assert shared >= 17 and reference_only <= 2, "the judge prunes the rest; it should rarely have to invent one"


# ----------------------------------------------------------------------------- the stage


def two_claims() -> tuple[dict, list[dict], list[dict], list[dict]]:
    claims = [claim("C1", "We are carbon neutral", "certification"), claim("C2", "Our target is net zero by 2050", "commitment")]
    scores = [*scored("C1", clarity=(0.8, 0.9), support=(0.6, 0.5), materiality=(0.2, 0.5), consistency=(0.2, 0.5)), *scored("C2", materiality=0.3)]
    items = [evidence("E1", "C1", "contradicts", tier=1), evidence("E2", "C2", "supports", tier=2)]
    return document(), claims, scores, items


def judgment(cid: str, category: str = "unsubstantiated", **kw) -> Judgment:
    return Judgment(**{
        "claim_id": cid, "rationale": f"{cid} rationale.", "tags": ["vagueness"], "fix": "State the offsets.",
        "rewrite": f"{cid} rewritten.", "evidence_ids": ["E1"], "own_category": category, "own_likelihood": 0.7, **kw,
    })


def test_both_sides_are_argued_before_the_verdict_and_the_verdict_is_derived_not_judged():
    doc, claims, scores, items = two_claims()
    events, emit = emitted()
    result = apply_verdicts(
        Cases(cases=[Case(claim_id="C1", text="The case against.", evidence_ids=["E1"])]),
        Cases(cases=[Case(claim_id="C1", text="The case for.", evidence_ids=["E1"])]),
        Judgments(judgments=[judgment("C1"), judgment("C2", category="supported", tags=[], evidence_ids=["E2"])]),
        claims, scores, items, emit=emit,
    )
    types = [t for t, _ in events]
    assert types == ["argument.made", "argument.made", "verdict.issued", "verdict.issued"]
    assert [e["argument"]["role"] for t, e in events if t == "argument.made"] == ["prosecutor", "defence"]
    first = result.verdicts[0]
    assert first["likelihood"] == 0.8 == max(s["score"] for s in scores if s["claim_id"] == "C1"), "the weakest link"
    assert first["category"] == "unsubstantiated", "clarity 0.8, not whatever the judge felt"
    assert first["rationale"] == "C1 rationale." and first["fix"] and first["rewrite"] and first["tags"] == ["vagueness"]
    assert first["ext"]["judge"]["own_category"] == "unsubstantiated" and first["ext"]["confidence_basis"]
    assert result.notes[0].startswith("2 verdicts (1 supported, 1 unsubstantiated), 2 arguments")


def test_a_judge_that_dissents_from_the_rule_is_recorded_and_costs_confidence():
    doc, claims, scores, items = two_claims()
    agreed = apply_verdicts(Cases(cases=[]), Cases(cases=[]), Judgments(judgments=[judgment("C1")]), claims, scores, items)
    dissenting = apply_verdicts(
        Cases(cases=[]), Cases(cases=[]),
        Judgments(judgments=[judgment("C1", category="supported", dissent="The wording is defined two lines below.")]),
        claims, scores, items,
    )
    before = next(v for v in agreed.verdicts if v["claim_id"] == "C1")
    after = next(v for v in dissenting.verdicts if v["claim_id"] == "C1")
    assert after["category"] == before["category"] == "unsubstantiated", "the rule still decides"
    assert after["confidence"] == round(before["confidence"] - 0.10, 2)
    assert after["ext"]["judge"]["dissent"].startswith("The wording is defined")
    assert dissenting.dissents == ["C1 rule unsubstantiated / judge supported"]
    assert "The judge dissented from the derived category on 1 claims" in dissenting.notes[1]


def test_repeated_judges_that_disagree_with_each_other_cost_more_confidence():
    doc, claims, scores, items = two_claims()
    result = apply_verdicts(
        Cases(cases=[]), Cases(cases=[]),
        Judgments(judgments=[judgment("C1"), judgment("C1", category="supported"), judgment("C1")]),
        claims, scores, items,
    )
    verdict = next(v for v in result.verdicts if v["claim_id"] == "C1")
    assert verdict["ext"]["judge"]["samples"] == 3
    assert verdict["ext"]["judge"]["agreement"] == 0.67 and verdict["ext"]["judge"]["stability"] == 0.67
    assert "repeated judges disagreed" in verdict["ext"]["confidence_basis"]


def test_a_claim_the_judge_skips_still_gets_a_derived_verdict():
    doc, claims, scores, items = two_claims()
    result = apply_verdicts(Cases(cases=[]), Cases(cases=[]), Judgments(judgments=[judgment("C1")]), claims, scores, items)
    skipped = next(v for v in result.verdicts if v["claim_id"] == "C2")
    assert skipped["rationale"] == DERIVED_RATIONALE and skipped["tags"] == [] and "judge" not in skipped["ext"]
    assert skipped["likelihood"] == 0.3 and skipped["category"] == "supported"
    assert result.placeholders == ["C2"] and "1 derived without a judge: C2" in result.notes[0]
    assert len(result.verdicts) == len(claims), "exactly one verdict per claim (contract §2, rule 4)"


def test_citations_of_evidence_that_is_not_the_claims_are_dropped_and_unknown_claims_ignored():
    doc, claims, scores, items = two_claims()
    result = apply_verdicts(
        Cases(cases=[Case(claim_id="C9", text="About a claim that does not exist."), Case(claim_id="C1", text="Fine.", evidence_ids=["E2", "E1", "E1", "E404"])]),
        Cases(cases=[]),
        Judgments(judgments=[judgment("C1", evidence_ids=["E1", "E2"])]),
        claims, scores, items,
    )
    assert [a["claim_id"] for a in result.arguments] == ["C1"]
    assert result.arguments[0]["evidence_ids"] == ["E1"], "E2 belongs to C2, E404 to nothing"
    assert next(v for v in result.verdicts if v["claim_id"] == "C1")["evidence_ids"] == ["E1"]
    assert "1 unknown claim ids ignored" in result.notes[0] and "3 citations of evidence not linked to the claim dropped" in result.notes[0]


def test_the_dossier_shows_the_scores_the_marks_and_only_verified_quotes():
    doc, claims, scores, items = two_claims()
    unverified = evidence("E3", "C1", "supports", verified=False, verification="unverified", note="A report nobody could open.")
    signals = [{"id": "L1", "level": "claim", "kind": "vague_term", "polarity": "flag", "spans": [{"text": "carbon neutral", "start": 7, "end": 21}], "claim_ids": ["C1"]}]
    text = claim_dossier(
        claims[0], index_scores(scores)["C1"], signals, [*index_evidence([*items, unverified])["C1"]],
        tags=["vagueness"], derived=(0.8, "unsubstantiated"), arguments={"prosecutor": "Against.", "defence": "For."},
    )
    assert "clarity      0.80  confidence 0.90  clarity basis." in text
    assert 'Language marks: vague_term "carbon neutral"' in text
    assert "E1 [tier 1 filing] Source E1 — contradicts" in text and "A quoted sentence." in text
    assert "(quote not verified, so not shown) A report nobody could open." in text and "A quoted sentence.\n     A quoted" not in text
    assert "Suggested tags: vagueness" in text
    assert "Derived verdict: likelihood 0.80 (weakest link: clarity), category unsubstantiated" in text
    assert "Prosecutor: Against." in text and "Defence: For." in text


def test_the_judge_reads_both_arguments_and_the_advocates_read_neither():
    from auditor.verdict import argue_prompt

    doc, claims, scores, items = two_claims()
    by_claim = (index_scores(scores), index_signals([]), index_evidence(items))
    against = argue_prompt("prosecutor", claims[:1], *by_claim, claims)
    assert "You are the prosecutor" in against and "Derived verdict" not in against and "Defence:" not in against
    assert "The other claims found on the page, for context only; argue only the ones above." in against and "C2 | commitment" in against
    for_it = argue_prompt("defence", claims, *by_claim, claims)
    assert "You are the defence" in for_it and "<page>" not in for_it, "nothing left over when the batch is the page"
    bench = judge_prompt(claims[:1], *by_claim, {"C1": ["vagueness"]}, {"C1": (0.8, "unsubstantiated")}, {"C1": {"prosecutor": "Against.", "defence": "For."}}, claims)
    assert "You are the judge" in bench and "Prosecutor: Against." in bench and "Defence: For." in bench
    assert "Derived verdict: likelihood 0.80" in bench and "greenrinsing — a target quietly weakened" in bench


# ----------------------------------------------------------------------------- the live path


class StreamingLlm:
    """A stand-in for auditor.llm.Llm: each argue call hands over its cases one by one, the
    judge call its judgments, then returns the whole. It records what each call was asked."""

    def __init__(self, *, hand_over: int = 1, fail_defence: bool = False) -> None:
        self.hand_over = hand_over
        self.fail_defence = fail_defence
        self.calls: list[dict] = []
        self.order: list[str] = []

    def _role(self, prompt: str) -> str:
        return "prosecutor" if "You are the prosecutor" in prompt else "defence" if "You are the defence" in prompt else "judge"

    def _ids(self, prompt: str) -> list[str]:
        return [line.split(" | ")[0].removeprefix("=== ") for line in prompt.split("\n") if line.startswith("=== ")]

    async def _answer(self, prompt, output, on_element=None, **kwargs):
        role = self._role(prompt)
        self.calls.append(dict(kwargs, role=role, prompt=prompt, output=output, ids=self._ids(prompt)))
        self.order.append(role)
        if role == "defence":
            if self.fail_defence:
                raise LlmError("the model's stream went quiet")
            await asyncio.sleep(0.01)  # the prosecutor answers first; the judge waits for both
        if output is Cases:
            items = [Case(claim_id=cid, text=f"{role} on {cid}.", evidence_ids=["E1"]) for cid in self._ids(prompt)]
            key, whole = "cases", Cases(cases=items)
        else:
            items = [judgment(cid, category="supported" if cid == "C2" else "unsubstantiated") for cid in self._ids(prompt)]
            key, whole = "judgments", Judgments(judgments=items)
        if on_element is not None:
            for item in items[: self.hand_over]:
                await on_element(key, item.model_dump())
            await on_element("other", {"ignored": True})
            await on_element(key, {"claim_id": "C1", "rationale": 17})
        return whole, usage()

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        return await self._answer(prompt, output, on_element, **kwargs)

    async def extract(self, prompt, output, **kwargs):
        return await self._answer(prompt, output, **kwargs)


def test_the_two_advocates_run_in_parallel_and_the_judge_runs_after_both():
    doc, claims, scores, items = two_claims()
    llm = StreamingLlm()
    events, emit = emitted()
    result = asyncio.run(issue_verdicts(doc, claims, scores, items, emit=emit, llm=llm))
    assert llm.order == ["prosecutor", "defence", "judge"], "the judge cannot read a debate that has not happened"
    types = [t for t, _ in events]
    assert types.index("verdict.issued") > max(i for i, t in enumerate(types) if t == "argument.made")
    assert sorted(a["claim_id"] + a["role"][0] for a in result.arguments) == ["C1d", "C1p", "C2d", "C2p"]
    assert [v["claim_id"] for v in result.verdicts] == ["C1", "C2"] and result.placeholders == []
    assert result.usage is not None and result.usage.input_tokens == 30, "three calls"
    assert "The model argued 4 cases and judged 2 claims over 1 batches of up to 6 claims" in result.notes[0]
    assert "3 malformed" in result.notes[0], "one per streaming call, and none reaches a verdict"
    judge_call = next(c for c in llm.calls if c["role"] == "judge")
    assert judge_call["effort"] == "high" and "Prosecutor: prosecutor on C1." in judge_call["prompt"]
    assert next(c for c in llm.calls if c["role"] == "prosecutor")["effort"] == "medium"
    assert all(c["cache"] is True and c["system"].startswith("You are") for c in llm.calls)


def test_claims_are_batched_and_every_batch_holds_its_own_debate(monkeypatch):
    from auditor import verdict as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims, scores, items = two_claims()
    llm = StreamingLlm(hand_over=5)
    result = asyncio.run(issue_verdicts(doc, claims, scores, items, llm=llm))
    assert len(llm.calls) == 6 and "over 2 batches of up to 1 claims" in result.notes[0]
    assert all(len(c["ids"]) == 1 for c in llm.calls)
    assert len(result.verdicts) == 2 and result.placeholders == []


def test_repeated_judges_are_asked_for_and_counted(monkeypatch):
    doc, claims, scores, items = two_claims()
    llm = StreamingLlm(hand_over=5)
    result = asyncio.run(issue_verdicts(doc, claims, scores, items, llm=llm, samples=3))
    assert sum(1 for c in llm.calls if c["role"] == "judge") == 3
    assert "each judged 3 times" in result.notes[0]
    assert all(v["ext"]["judge"]["samples"] == 3 for v in result.verdicts)


def test_a_failing_advocate_fails_the_stage_with_a_plain_error():
    doc, claims, scores, items = two_claims()
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(issue_verdicts(doc, claims, scores, items, llm=StreamingLlm(fail_defence=True)))


def test_no_claims_is_no_calls():
    result = asyncio.run(issue_verdicts(document(), [], [], [], llm=StreamingLlm()))
    assert result.verdicts == [] and result.arguments == [] and result.usage is None


# ----------------------------------------------------------------------------- against the reference


def test_the_stage_reproduces_the_golden_reference_from_its_own_scores():
    """A judge that writes the reference's own words is still only writing words: the numbers
    and the categories come out of the reference's scores by rule, so all 25 verdicts match."""
    analysis = golden()
    judgments = Judgments(judgments=[
        Judgment(
            claim_id=v["claim_id"], rationale=v["rationale"], tags=v["tags"], fix=v.get("fix", ""),
            rewrite=v.get("rewrite", ""), evidence_ids=v.get("evidence_ids", []),
            own_category=v["category"], own_likelihood=v["likelihood"],
        )
        for v in analysis["verdicts"]
    ])
    result = apply_verdicts(
        Cases(cases=[Case(claim_id=a["claim_id"], text=a["text"], evidence_ids=a.get("evidence_ids", [])) for a in analysis["arguments"] if a["role"] == "prosecutor"]),
        Cases(cases=[Case(claim_id=a["claim_id"], text=a["text"], evidence_ids=a.get("evidence_ids", [])) for a in analysis["arguments"] if a["role"] == "defence"]),
        judgments, analysis["claims"], analysis["scores"], analysis["evidence"], analysis["signals"],
    )
    comparison = compare_verdicts(result.verdicts, analysis["verdicts"])
    assert len(comparison.same_category) == len(comparison.pairs) == 25 and comparison.missing == []
    assert comparison.likelihood_error == 0.0, "the weakest link is exact"
    assert comparison.confidence_error <= 0.05
    both, only_live, only_reference = comparison.tag_overlap()
    assert (only_live, only_reference) == (0, 0) and both == sum(len(v["tags"]) for v in analysis["verdicts"])
    assert len(result.arguments) == 8 and result.dissents == []


def test_the_comparison_reports_what_moved():
    live = [
        {"claim_id": "C1", "likelihood": 0.8, "confidence": 0.7, "category": "misleading_by_framing", "tags": ["vagueness"], "rationale": "x"},
        {"claim_id": "C2", "likelihood": 0.3, "confidence": 0.6, "category": "supported", "tags": [], "rationale": "y"},
    ]
    reference = [
        {"claim_id": "C1", "likelihood": 0.9, "confidence": 0.8, "category": "contradicted", "tags": ["vagueness", "no_proof"], "rationale": "x"},
        {"claim_id": "C2", "likelihood": 0.3, "confidence": 0.6, "category": "supported", "tags": [], "rationale": "y"},
        {"claim_id": "C3", "likelihood": 0.5, "confidence": 0.5, "category": "supported", "tags": [], "rationale": "z"},
    ]
    comparison = compare_verdicts(live, reference)
    assert comparison.same_category == ["C2"] and comparison.missing == ["C3"]
    assert round(comparison.likelihood_error, 2) == 0.05 and round(comparison.confidence_error, 2) == 0.05
    assert comparison.tag_overlap() == (1, 0, 1)
    assert comparison.describe() == (
        "1 of 2 categories agree, mean absolute likelihood difference 0.05, confidence 0.05, "
        "1 tags shared (0 only live, 1 only reference), 1 reference claims without a verdict"
    )


def test_every_argument_and_verdict_validates_against_the_contract():
    import jsonschema

    schema = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))
    doc, claims, scores, items = two_claims()
    events, emit = emitted()
    apply_verdicts(
        Cases(cases=[Case(claim_id="C1", text="Against.", evidence_ids=["E1"])]),
        Cases(cases=[Case(claim_id="C1", text="For.")]),
        Judgments(judgments=[judgment("C1"), judgment("C2", category="supported", tags=[], evidence_ids=[])]),
        claims, scores, items, emit=emit,
    )
    assert len(events) == 4
    for seq, (type_, payload) in enumerate(events, start=1):
        jsonschema.validate({"seq": seq, "t_ms": seq * 100, "type": type_, "payload": payload}, schema)


def test_a_supported_verdict_carries_no_pattern_tag():
    """A tag names a way of misleading, so it contradicts the verdict that the claim does not.
    The golden reference carries none on any of its ten supported claims."""
    doc, claims, scores, items = two_claims()
    result = apply_verdicts(
        Cases(cases=[]), Cases(cases=[]),
        Judgments(judgments=[judgment("C2", category="supported", tags=["hidden_trade_off", "vagueness"])]),
        claims, scores, items,
    )
    supported = next(v for v in result.verdicts if v["claim_id"] == "C2")
    assert supported["category"] == "supported" and supported["tags"] == []
    assert "C2 (hidden_trade_off, vagueness)" in result.notes[1] and "had their pattern tags dropped" in result.notes[1]
    assert supported["ext"]["judge"]["own_category"] == "supported", "the judge's own read is untouched"
    analysis = golden()
    assert all(v["tags"] == [] for v in analysis["verdicts"] if v["category"] == "supported")


def test_the_archive_marker_proposes_greenrinsing_where_the_score_alone_would_miss_it():
    """The self-consistency evaluator (step 15) marks the archived capture that shows a target
    weakened before it was met, saying in its own comment that step 17 assigns the tag. That
    marker is the exact signal; the Consistency score is the fallback."""
    commitment = claim("C1", "Our target is net zero by 2050", "commitment")
    weakened = evidence("A1", "C1", "contradicts_framing", kind="archive", ext={"axis": "archive", "change": "weakened", "greenrinsing": True})
    quiet = dimensions(consistency=0.4)
    assert "greenrinsing" not in propose_tags(commitment, quiet, [], [evidence("A2", "C1", "context", kind="archive", ext={"change": "unchanged"})])
    assert "greenrinsing" in propose_tags(commitment, quiet, [], [weakened]), "the marker is believed even at a low Consistency score"
    assert "greenrinsing" in propose_tags(commitment, dimensions(consistency=0.7), [], []), "and the score still stands alone"
