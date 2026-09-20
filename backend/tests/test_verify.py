"""External verification: retrieved sources become evidence with the tier their independence
earns, every quote is checked against the page it names and never displayed unless it is
found, numbers are recomputed here before anyone sees them, and Support and Materiality are
scored from all of it. No test calls the model and no test touches the network."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO, golden_verification

from auditor.language import reanchored_claims
from auditor.llm import LlmError, Usage
from auditor.verify import (
    PLACEHOLDER_BASIS,
    Assessment,
    Assessments,
    Bearing,
    Computation,
    ComputationError,
    Computations,
    Finding,
    Findings,
    Page,
    apply_verification,
    check_quote,
    compare_scores,
    compare_sources,
    evaluate,
    load_page,
    states_value,
    verify,
)

SEC = "https://www.sec.gov/Archives/edgar/data/1306965/filing.htm"
PAGES = {
    SEC: "Scope 1 and 2 emissions were 53 million tonnes CO2e (2024: 58). Total cash capital expenditure 20,915.",
    "https://acme.example/climate": "We are proud of our progress on climate.",
    "https://tpi.example/acme": "Carbon Performance: 2028 Not Aligned.",
}


def document(text: str = "We are carbon neutral. Our target is net zero by 2050.") -> dict:
    return {"id": "d", "title": "Climate", "company": {"name": "Acme"}, "text_type": "policy", "source": {"url": "https://acme.example/climate-page", "retrieved": "2026-09-20"}, "text": text, "word_count": 11, "regions": []}


def claim(cid: str, text: str, words: str) -> dict:
    start = text.index(words)
    return {"id": cid, "spans": [{"text": words, "start": start, "end": start + len(words)}], "type": "factual", "scope": "company", "attribute": words, "paragraph": "P1", "prominence": 1.0}


def two_claims():
    doc = document()
    text = doc["text"]
    return doc, [claim("C1", text, "We are carbon neutral"), claim("C2", text, "Our target is net zero by 2050")]


def fetch(url: str) -> str:
    if url not in PAGES:
        raise ValueError(f"{url} answered HTTP 404")
    return PAGES[url]


def emitted():
    events: list[tuple[str, dict]] = []
    return events, lambda type_, payload: events.append((type_, payload))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def finding(**kwargs) -> Finding:
    base = dict(
        kind="filing", independence="assured_filing", name="Acme Annual Report 2025", publisher="Acme plc",
        date="2026-03", locator="p. 7", url=SEC, quote="Scope 1 and 2 emissions were 53 million tonnes CO2e (2024: 58).",
        bears_on=[Bearing(claim_id="C1", relation="supports")], note="",
    )
    return Finding(**{**base, **kwargs})


def computation(**kwargs) -> Computation:
    base = dict(
        name="Share of the footprint the target covers", expression="scope12 / (scope12 + scope3) * 100",
        inputs={"scope12": 53.0, "scope3": 1065.0}, value=4.7406, unit="%",
        sentence="Scope 1 and 2 (53 Mt) are 4.7% of total reported emissions.",
        derived_from=["V1"], bears_on=[Bearing(claim_id="C1", relation="context")],
    )
    return Computation(**{**base, **kwargs})


# ----------------------------------------------------------------------------- citation integrity


def test_a_quote_on_the_page_is_verified_and_a_fake_one_is_rejected():
    doc, claims = two_claims()
    events, emit = emitted()
    findings = Findings(findings=[
        finding(),
        finding(quote="Shell is a world leader in renewable energy investment.", name="Acme Annual Report 2025, invented",
                bears_on=[Bearing(claim_id="C2", relation="supports")]),
    ])
    result = apply_verification(findings, Computations(computations=[]), Assessments(assessments=[]), doc, claims, emit=emit, fetch_text=fetch)
    real, fake = result.sources
    assert real["id"] == "V1" and real["verified"] is True and real["verification"] == "fetched_exact"
    assert real["quote"].startswith("Scope 1 and 2 emissions were 53") and real["tier"] == 2 and real["stage"] == "verify"
    assert real["source"] == {"name": "Acme Annual Report 2025", "publisher": "Acme plc", "date": "2026-03", "locator": "p. 7"}
    assert real["links"] == [{"target": "C1", "relation": "supports"}] and real["ext"]["independence"] == "assured_filing"
    assert fake["verified"] is False and fake["verification"] == "unverified"
    assert "quote" not in fake, "an unverified quote is never displayed (D5)"
    assert "Quote not found on" in fake["note"] and fake["url"] == SEC, "the item is still listed by name, with the reason"
    assert result.absent == [SEC] and result.unreadable == [] and result.unverified == [SEC]
    assert [t for t, _ in events][:2] == ["evidence.added", "evidence.added"]
    assert any("1 with a quote found on the page, 1 whose quote was not on the page, 0 whose page could not be read" in n for n in result.notes)
    assert any(n.startswith("Quote not on the page, so the citation is rejected") for n in result.notes)


def test_a_page_that_cannot_be_read_leaves_the_quote_undisplayed_with_the_reason():
    doc, claims = two_claims()
    findings = Findings(findings=[
        finding(url="https://nowhere.example/report", quote="Anything at all."),
        finding(url="example.com/story", quote="Anything else.", bears_on=[Bearing(claim_id="C2", relation="context")]),
    ])
    result = apply_verification(findings, Computations(computations=[]), Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    unread, unlinkable = result.sources
    assert unread["verified"] is False and "quote" not in unread
    assert "could not be read from here" in unread["note"] and "Open the link by hand" in unread["note"]
    assert "url" not in unlinkable, "a bare domain is not a link a reader can open, so none is shown"
    assert "is not a link that can be opened" in unlinkable["note"]
    assert result.absent == [] and len(result.unreadable) == 2, "neither is a rejected citation: the pages never opened"
    assert any(n.startswith("Page could not be read from here") for n in result.notes)


def test_the_check_normalises_the_way_the_store_check_does():
    page = Page("https://x.example", text="Shell — the company’s  “net-zero” target")
    assert check_quote(page, "the company's \"net-zero\" target")[:2] == (True, ""), "dashes, curly quotes, runs of spaces and case"
    assert check_quote(page, "the company's net zero target")[::2] == (False, "absent")
    assert check_quote(Page("https://x.example", error="HTTP 403"), "anything")[::2] == (False, "unreadable")


def test_load_page_never_raises(monkeypatch):
    def boom(url: str) -> str:
        raise RuntimeError("the site hung up")

    page = load_page("https://x.example", boom)
    assert page.text is None and page.error == "the site hung up"


def test_a_tier_five_source_cannot_substantiate_its_own_company_and_a_duplicate_is_ignored():
    doc, claims = two_claims()
    findings = Findings(findings=[
        finding(kind="company_page", independence="company", url="https://acme.example/climate",
                quote="We are proud of our progress on climate.", name="Acme, our climate page",
                bears_on=[Bearing(claim_id="C1", relation="supports"), Bearing(claim_id="C2", relation="contradicts_framing")]),
        finding(kind="company_page", independence="company", url="https://acme.example/climate",
                quote="We are proud of our progress on climate.", name="the same page and quote again",
                bears_on=[Bearing(claim_id="C2", relation="context")]),
        finding(bears_on=[Bearing(claim_id="C9", relation="supports")]),
    ])
    result = apply_verification(findings, Computations(computations=[]), Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    assert len(result.sources) == 1, "the duplicate is dropped; the finding about an unknown claim has no links left"
    item = result.sources[0]
    assert item["tier"] == 5
    assert item["links"] == [{"target": "C1", "relation": "context"}, {"target": "C2", "relation": "contradicts_framing"}]
    assert "context, not substantiation" in item["note"]
    assert any("1 tier-5 'supports' links made 'context'" in n and "1 duplicate findings ignored" in n and "1 unknown claim ids ignored" in n for n in result.notes)


def test_tier_follows_independence_not_the_argument():
    doc, claims = two_claims()
    kinds = [("regulator", 1), ("assured_filing", 2), ("government", 2), ("independent", 3), ("news", 4), ("company", 5)]
    findings = Findings(findings=[
        finding(independence=independence, quote=f"Scope 1 and 2 emissions were 53 million tonnes CO2e (2024: 58). {independence}")
        for independence, _ in kinds
    ])
    result = apply_verification(findings, Computations(computations=[]), Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    assert [e["tier"] for e in result.sources] == [tier for _, tier in kinds]


# ----------------------------------------------------------------------------- recomputation


def test_the_arithmetic_is_evaluated_here():
    assert evaluate("(a - b) / a * 100", {"a": 569, "b": 467}) == pytest.approx(17.926, abs=0.001)
    assert evaluate("-(2 + 3) * 4", {}) == -20
    for expression, inputs in [("a / b", {"a": 1, "b": 0}), ("a + c", {"a": 1}), ("len(a)", {"a": 1}), ("a ** 99", {"a": 10}), ("a +", {"a": 1}), ("__import__('os')", {})]:
        with pytest.raises(ComputationError):
            evaluate(expression, inputs)


def test_states_value_accepts_any_sane_rounding():
    assert states_value("Emissions fell 1.8% in 2025.", 1.753) is True
    assert states_value("That is 72%, consistent with 'around 70%'.", 72.0) is True
    assert states_value("Upstream took 67.0% of capital expenditure.", 66.96) is True
    assert states_value("It is 20,915 million dollars.", 20915) is True
    assert states_value("Emissions fell 12% in 2025.", 1.753) is False, "'2' is not stated by '12%' or '2025'"
    assert states_value("It is 4.74% of the footprint.", 4.7406) is True


def test_a_computation_is_shown_only_when_its_arithmetic_and_its_sentence_agree():
    doc, claims = two_claims()
    events, emit = emitted()
    computations = Computations(computations=[
        computation(),
        computation(name="wrong arithmetic", value=40.0, sentence="It is 40% of the footprint."),
        computation(name="sentence says something else", sentence="It is about a twentieth of the footprint."),
        computation(name="not arithmetic", expression="share(scope12, scope3)"),
        computation(name="derived from a paragraph label, not evidence", derived_from=["P7"]),
        computation(name="about a claim that does not exist", bears_on=[Bearing(claim_id="C9", relation="context")]),
    ])
    result = apply_verification(Findings(findings=[finding()]), computations, Assessments(assessments=[]), doc, claims, emit=emit, fetch_text=fetch)
    assert len(result.computations) == 1
    item = result.computations[0]
    assert item["id"] == "N1" and item["kind"] == "computation" and item["verification"] == "computed" and item["verified"] is True
    assert item["tier"] == 2, "no better than its worst input"
    assert item["derived_from"] == ["V1"] and item["links"] == [{"target": "C1", "relation": "context"}]
    assert item["computation"] == {"formula": "scope12 / (scope12 + scope3) * 100", "inputs": {"scope12": 53.0, "scope3": 1065.0}, "result": "Scope 1 and 2 (53 Mt) are 4.7% of total reported emissions."}
    assert item["quote"] == item["computation"]["result"] and item["ext"] == {"recomputed": 4.7406, "unit": "%"}
    assert item["source"]["publisher"] == "Recomputed by the External verification evaluator"
    reasons = " ".join(result.rejected)
    assert "= 4.741, not 40 as claimed" in reasons and "does not state 4.741" in reasons
    assert "not plain arithmetic" in reasons and "derived from evidence that does not exist (P7)" in reasons
    assert len(result.rejected) == 4, "the one about an unknown claim is dropped before the arithmetic"
    assert any("1 numbers recomputed, 4 rejected" in n for n in result.notes)


def test_a_computation_over_the_documents_own_figures_names_no_evidence_and_is_tier_five():
    """The page prints both numbers, so there is nothing to derive from and nothing better to
    claim than the page's own reliability (contract §4: no better than its worst input)."""
    doc, claims = two_claims()
    computations = Computations(computations=[computation(
        name="Pace needed against pace achieved", expression="(target - achieved) / years_left",
        inputs={"target": 20.0, "achieved": 9.0, "years_left": 5.0}, value=2.2, unit="points per year",
        sentence="2.2 points a year are needed to 2030, against the 1.0 achieved since 2016.",
        derived_from=[],
    )])
    result = apply_verification(Findings(findings=[finding()]), computations, Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    item = result.computations[0]
    assert item["tier"] == 5 and item["derived_from"] == [] and result.rejected == []
    assert item["ext"]["recomputed"] == 2.2


def test_a_computation_checking_a_stated_number_keeps_both_numbers_and_the_gap():
    doc, claims = two_claims()
    computations = Computations(computations=[
        computation(stated=5.0),
        computation(name="the page says a fifth", stated=20.0, bears_on=[Bearing(claim_id="C2", relation="contradicts")]),
    ])
    result = apply_verification(Findings(findings=[finding()]), computations, Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    close, far = result.computations
    assert close["ext"] == {"recomputed": 4.7406, "unit": "%", "stated": 5.0, "difference": -0.2594}
    assert far["ext"]["difference"] == -15.2594, "the page says a fifth; it is a twentieth"


def test_a_computation_is_never_better_than_its_worst_input():
    doc, claims = two_claims()
    findings = Findings(findings=[
        finding(),
        finding(kind="company_page", independence="company", url="https://acme.example/climate", quote="We are proud of our progress on climate."),
    ])
    computations = Computations(computations=[computation(derived_from=["V1", "V2"])])
    result = apply_verification(findings, computations, Assessments(assessments=[]), doc, claims, fetch_text=fetch)
    assert result.computations[0]["tier"] == 5


# ----------------------------------------------------------------------------- scoring


def test_both_dimensions_are_scored_after_the_evidence_and_skipped_claims_get_placeholders():
    doc, claims = two_claims()
    events, emit = emitted()
    assessments = Assessments(assessments=[
        Assessment(claim_id="C1", support=0.75, support_confidence=0.8, support_basis="The filing contradicts the impression.",
                   support_evidence_ids=["V1", "N1", "V9", "K1"], materiality=0.6, materiality_confidence=0.9,
                   materiality_basis="Operations only.", materiality_evidence_ids=["N1"], gap="Give the scope."),
        Assessment(claim_id="C1", support=0.1, support_confidence=0.1, support_basis="repeat", materiality=0.1, materiality_confidence=0.1, materiality_basis="repeat"),
    ])
    prior = [{"id": "K1", "kind": "standard", "tier": 1, "source": {"name": "A rule"}, "verified": False, "verification": "unverified", "retrieved": "2026-09-20", "stage": "substantiate", "links": [{"target": "C1", "relation": "criteria"}]}]
    result = apply_verification(Findings(findings=[finding()]), Computations(computations=[computation()]), assessments, doc, claims, prior, emit, fetch_text=fetch)
    types = [t for t, _ in events]
    assert types == ["evidence.added", "evidence.added", "dimension.scored", "dimension.scored", "dimension.scored", "dimension.scored"]
    support, materiality = events[2][1]["score"], events[3][1]["score"]
    assert support == {"claim_id": "C1", "dimension": "support", "score": 0.75, "confidence": 0.8, "basis": "The filing contradicts the impression.", "stage": "verify", "evidence_ids": ["V1", "N1", "K1"], "ext": {"gap": "Give the scope."}}
    assert materiality["dimension"] == "materiality" and materiality["evidence_ids"] == ["N1"] and "ext" not in materiality
    placeholder_support, placeholder_materiality = events[4][1]["score"], events[5][1]["score"]
    assert placeholder_support["claim_id"] == "C2" and placeholder_support["score"] == 0.5 and placeholder_support["confidence"] == 0.2
    assert placeholder_support["basis"] == PLACEHOLDER_BASIS and placeholder_materiality["basis"] == PLACEHOLDER_BASIS
    assert result.placeholders == ["C2"]
    assert any("1 unknown evidence ids ignored" in n and "1 repeated assessments ignored" in n for n in result.notes)
    assert any("Placeholder support and materiality for 1 claims" in n for n in result.notes)


# ----------------------------------------------------------------------------- the live stage


class StreamingLlm:
    """A stand-in for auditor.llm.Llm.extract_streaming: hands over some of each call's items
    one by one (so the catch-up path is exercised too) and returns the whole."""

    def __init__(self, findings: Findings, computations: Computations, assessments: Assessments, hand_over: int = 1, *, fail: type | None = None) -> None:
        self.results = {Findings: findings, Computations: computations, Assessments: assessments}
        self.keys = {Findings: "findings", Computations: "computations", Assessments: "assessments"}
        self.hand_over = hand_over
        self.fail = fail
        self.calls: list[dict] = []

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if self.fail is output:
            raise LlmError("the model's stream went quiet")
        whole = self.results[output]
        items = list(getattr(whole, self.keys[output]))
        if "<review>" in prompt:
            wanted = {x.strip() for x in prompt.split("these claims")[-1].split(":")[1].split(".")[0].split(",")}
            def mine(item):
                ids = {b.claim_id for b in item.bears_on} if hasattr(item, "bears_on") else {item.claim_id}
                return bool(ids & wanted)
            items = [i for i in items if mine(i)]
        for item in items[: self.hand_over]:
            await on_element(self.keys[output], item.model_dump())
        await on_element("something_else", {"ignored": True})
        return type(whole)(**{self.keys[output]: items}), usage()


def test_verify_retrieves_then_recomputes_then_scores_and_reports_what_it_cost(monkeypatch):
    from auditor import verify as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims = two_claims()
    findings = Findings(findings=[finding(), finding(url="https://tpi.example/acme", independence="independent", kind="dataset",
                                                     name="TPI assessment", quote="Carbon Performance: 2028 Not Aligned.",
                                                     bears_on=[Bearing(claim_id="C2", relation="contradicts_framing")])])
    assessments = Assessments(assessments=[
        Assessment(claim_id="C1", support=0.6, support_confidence=0.7, support_basis="a", support_evidence_ids=["V1"], materiality=0.4, materiality_confidence=0.6, materiality_basis="b"),
        Assessment(claim_id="C2", support=0.3, support_confidence=0.6, support_basis="c", materiality=0.5, materiality_confidence=0.5, materiality_basis="d"),
    ])
    llm = StreamingLlm(findings, Computations(computations=[computation()]), assessments, hand_over=1)
    events, emit = emitted()
    result = asyncio.run(verify(doc, claims, emit=emit, llm=llm, fetch_text=fetch))
    types = [t for t, _ in events]
    assert types.count("evidence.added") == 3 and types.count("dimension.scored") == 4
    assert max(i for i, t in enumerate(types) if t == "evidence.added") < min(i for i, t in enumerate(types) if t == "dimension.scored"), \
        "every item exists before a score can cite it (contract §2, rule 3)"
    assert [e["evidence"]["id"] for t, e in events if t == "evidence.added"][-1] == "N1", "the numbers come after the sources they derive from"
    retrieval = [c for c in llm.calls if c["output"] is Findings]
    assert len(retrieval) == 2, "one call per claim at BATCH_SIZE 1, in parallel"
    assert retrieval[0]["effort"] == "medium" and retrieval[0]["cache"] is True and retrieval[0]["system"].startswith("You are")
    assert [t["name"] for t in retrieval[0]["tools"]] == ["web_search", "web_fetch"], "the search runs on Anthropic's servers"
    assert "tools" not in [c for c in llm.calls if c["output"] is Computations][0], "no searching once the evidence is in"
    assert "tools" not in [c for c in llm.calls if c["output"] is Assessments][0]
    assert result.usage is not None and result.usage.input_tokens == 40, "two retrieval calls, one for the numbers, one for the scores"
    assert "searched for evidence on 2 claims over 2 parallel calls" in result.notes[0] and "scored 2 claims over 1 calls" in result.notes[0]


def test_one_failed_search_does_not_lose_the_other_batches(monkeypatch):
    from auditor import verify as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims = two_claims()
    llm = StreamingLlm(Findings(findings=[]), Computations(computations=[]), Assessments(assessments=[]), fail=Findings)
    result = asyncio.run(verify(doc, claims, llm=llm, fetch_text=fetch))
    assert [s["dimension"] for s in result.scores] == ["support", "materiality", "support", "materiality"], "the stage still owes the verdict its dimensions"
    assert result.placeholders == ["C1", "C2"]
    assert sum(n.startswith("Retrieval failed for") for n in result.notes) == 2


def test_a_failed_scoring_call_fails_the_stage():
    doc, claims = two_claims()
    llm = StreamingLlm(Findings(findings=[finding()]), Computations(computations=[]), Assessments(assessments=[]), fail=Assessments)
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(verify(doc, claims, llm=llm, fetch_text=fetch))
    assert asyncio.run(verify(doc, [], llm=llm, fetch_text=fetch)).notes == ["No claims to verify."]


# ----------------------------------------------------------------------------- against the reference


def test_the_golden_verification_reproduces_the_reference_scores_and_sources():
    """The fixture's verify-stage sources and its support and materiality scores, run through
    the real assembly: a perfect evaluator reproduces the reference exactly, and every quote
    the hand analysis recorded is found on the page it was recorded from."""
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    doc = analysis["document"]
    claims = reanchored_claims(analysis["claims"], doc["text"], doc["text"])
    findings, computations, assessments, mapping, pages = golden_verification()
    result = apply_verification(findings, computations, assessments, doc, claims, fetch_text=lambda url: pages[url])
    assert len(result.sources) == 10 and all(e["verified"] for e in result.sources)
    assert len(result.computations) == 5 and result.rejected == []
    for dimension in ("support", "materiality"):
        comparison = compare_scores(result.scores, analysis["scores"], dimension)
        assert comparison.mean_abs_error == 0 and comparison.wrong_band() == [] and comparison.unscored == []
    sources = compare_sources(result.evidence, analysis["evidence"])
    assert sources.found_hosts == sources.reference_hosts == ["ogmpartnership.org", "sec.gov", "transitionpathwayinitiative.org"]
    assert sources.describe().startswith("3 of 3 reference sources matched by host")
    assert mapping["E5"] in {e["id"] for e in result.sources}


def test_the_comparison_counts_scores_on_the_other_side_and_sources_not_found():
    comparison = compare_scores(
        [{"claim_id": "C1", "dimension": "materiality", "score": 0.7}, {"claim_id": "C3", "dimension": "materiality", "score": 0.5}],
        [{"claim_id": "C1", "dimension": "materiality", "score": 0.5}, {"claim_id": "C3", "dimension": "materiality", "score": 0.5}, {"claim_id": "C4", "dimension": "materiality", "score": 0.4}],
        "materiality",
    )
    assert comparison.pairs == [("C1", 0.7, 0.5), ("C3", 0.5, 0.5)] and comparison.unscored == ["C4"]
    assert comparison.wrong_band() == ["C1"] and round(comparison.mean_abs_error, 2) == 0.1
    assert comparison.describe() == "materiality scored for 2 reference claims, mean absolute difference 0.10, 1 on the other side of 0.6, 1 reference claims unscored"
    sources = compare_sources(
        [{"id": "V1", "kind": "filing", "url": "https://www.sec.gov/other/filing.htm", "verified": True},
         {"id": "N1", "kind": "computation", "verified": True}],
        [{"id": "E1", "stage": "verify", "url": "https://www.sec.gov/Archives/x.htm"}, {"id": "E2", "stage": "verify", "url": "https://cdp.net/acme"}, {"id": "E3", "stage": "consistency", "url": "https://acme.example"}],
    )
    assert sources.reference_hosts == ["cdp.net", "sec.gov"] and sources.found_hosts == ["sec.gov"]
    assert sources.live_sources == 1 and sources.verified == 1, "a computation is not a source with a link to open"
