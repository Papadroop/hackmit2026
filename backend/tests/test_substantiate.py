"""The substantiation evaluator: matches become evidence items with the right links, scores
follow with their citations, everything streams in contract order, and the comparison with
the golden reference measures the result. No test calls the model."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO, golden_substantiation

from auditor.knowledge import CriteriaIndex, Knowledge, PrecedentIndex, StoreEntry, load_knowledge
from auditor.language import reanchored_claims
from auditor.llm import LlmError, Usage
from auditor.substantiate import (
    PLACEHOLDER_BASIS,
    Assessment,
    Assessments,
    Match,
    Matches,
    apply_substantiation,
    compare_links,
    compare_support,
    match_prompt,
    score_prompt,
    substantiate,
)


def document(text: str = "We are carbon neutral. Our target is net zero by 2050.", url: str | None = "https://acme.example/climate") -> dict:
    return {"id": "d", "title": "Climate", "company": {"name": "Acme"}, "text_type": "policy", "source": {"url": url, "retrieved": "2026-09-20"}, "text": text, "word_count": 11, "regions": []}


def claim(cid: str, text: str, words: str, type_: str = "factual") -> dict:
    start = text.index(words)
    return {"id": cid, "spans": [{"text": words, "start": start, "end": start + len(words)}], "type": type_, "scope": "company", "attribute": words, "paragraph": "P1", "prominence": 1.0}


def small_knowledge() -> Knowledge:
    criteria = [
        StoreEntry(id="rule-neutral", kind="standard", tier=1, source={"name": "Neutral rule"}, url="https://reg.example/neutral", quote="say offsets", verified=True, verification="fetched_exact", retrieved="2026-09-20", note="A note.", index=CriteriaIndex(jurisdiction="UK", terms=["carbon neutral"], applies_to=["certification"], rule="Say whether offsets are used.")),
        StoreEntry(id="rule-targets", kind="law", tier=1, source={"name": "Targets rule"}, url="https://reg.example/targets", quote="show a plan", verified=True, verification="fetched_exact", retrieved="2026-09-20", index=CriteriaIndex(jurisdiction="EU", terms=["net zero by"], applies_to=["commitment"], rule="Show a plan.")),
    ]
    precedents = [
        StoreEntry(id="ruling-neutral", kind="ruling", tier=1, source={"name": "Neutral ruling"}, url="https://court.example/neutral", quote="misleading", verified=True, verification="fetched_exact", retrieved="2026-09-20", index=PrecedentIndex(jurisdiction="DE", body="Court", company="Other", claim_text="carbon neutral watch", outcome="upheld", reasoning="offsets short", terms=["carbon neutral"])),
        StoreEntry(id="ruling-acme", kind="ruling", tier=1, source={"name": "Acme ruling"}, url="https://acme.example/climate", verified=False, verification="unverified", retrieved="2026-09-20", index=PrecedentIndex(jurisdiction="UK", body="ASA", company="Acme", claim_text="net zero by 2050", outcome="upheld", reasoning="no plan", adjudicated_urls=["https://acme.example/climate"])),
    ]
    return Knowledge(criteria, precedents)


def emitted():
    events: list[tuple[str, dict]] = []
    return events, lambda type_, payload: events.append((type_, payload))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def two_claims():
    doc = document()
    text = doc["text"]
    return doc, [claim("C1", text, "We are carbon neutral", "certification"), claim("C2", text, "Our target is net zero by 2050", "commitment")]


def test_matches_become_evidence_with_criteria_and_precedent_links_and_scores_cite_them():
    doc, claims = two_claims()
    events, emit = emitted()
    matches = Matches(matches=[
        Match(evidence_id="K1", claim_ids=["C1"], note="neutral wording"),
        Match(evidence_id="P1", claim_ids=["C1", "C9", "C1"], note="same claim family"),
        Match(evidence_id="K9", claim_ids=["C1"], note="unknown id"),
        Match(evidence_id="K2", claim_ids=["C9"], note="only unknown claims"),
        Match(evidence_id="K1", claim_ids=["C2"], note="repeated item"),
    ])
    assessments = Assessments(assessments=[
        Assessment(claim_id="C1", criteria_ids=["K1"], precedent_ids=["P1"], score=0.65, confidence=0.7, basis="No offset disclosure.", gap="Say offsets are used."),
        Assessment(claim_id="C2", criteria_ids=["K2", "K2"], score=0.5, confidence=0.4, basis="No plan shown."),
        Assessment(claim_id="C1", score=0.1, confidence=0.9, basis="repeat"),
    ])
    result = apply_substantiation(matches, assessments, doc, claims, small_knowledge(), emit)
    types = [t for t, _ in events]
    assert types == ["evidence.added", "evidence.added", "dimension.scored", "evidence.added", "dimension.scored"]
    k1, p1, k2 = events[0][1]["evidence"], events[1][1]["evidence"], events[3][1]["evidence"]
    assert k1["id"] == "K1" and k1["links"] == [{"target": "C1", "relation": "criteria"}] and k1["quote"] == "say offsets" and k1["note"] == "A note."
    assert k1["ext"] == {"store": "criteria", "store_id": "rule-neutral", "jurisdiction": "UK", "match_note": "neutral wording"}
    assert p1["id"] == "P1" and p1["links"] == [{"target": "C1", "relation": "precedent"}], "unknown and repeated claim ids are dropped"
    assert p1["ext"]["outcome"] == "upheld" and p1["ext"]["company"] == "Other"
    assert k2["id"] == "K2" and k2["links"] == [{"target": "C2", "relation": "criteria"}] and "match_note" not in k2["ext"], "cited by the scorer only: emitted then, linked to that claim"
    c1, c2 = events[2][1]["score"], events[4][1]["score"]
    assert c1 == {"claim_id": "C1", "dimension": "support", "score": 0.65, "confidence": 0.7, "basis": "No offset disclosure.", "stage": "substantiate", "evidence_ids": ["K1", "P1"], "ext": {"gap": "Say offsets are used."}}
    assert c2["evidence_ids"] == ["K2"] and "ext" not in c2
    assert [s["claim_id"] for s in result.scores] == ["C1", "C2"] and result.placeholders == []
    assert result.notes[0].startswith("3 store items cited (2 criteria, 1 precedents) for 2 of 2 claims; 1 cited by the scorer only; 2 repeated matches or scores ignored; 1 unknown store ids ignored; 2 unknown claim ids ignored")


def test_a_precedent_on_the_document_itself_is_held_out_and_unscored_claims_get_placeholders():
    doc, claims = two_claims()
    events, emit = emitted()
    matches = Matches(matches=[Match(evidence_id="P2", claim_ids=["C2"], note="same company, same page")])
    result = apply_substantiation(matches, Assessments(assessments=[]), doc, claims, small_knowledge(), emit)
    assert result.held_out == ["ruling-acme"]
    assert [t for t, _ in events] == ["dimension.scored", "dimension.scored"], "P2 no longer exists, so the match is ignored"
    assert result.placeholders == ["C1", "C2"]
    scores = [p["score"] for _, p in events]
    assert all(s["score"] == 0.5 and s["confidence"] == 0.2 and s["basis"] == PLACEHOLDER_BASIS for s in scores)
    assert any("Held out: ruling-acme" in n for n in result.notes) and any("Placeholder support score for 2 claims" in n for n in result.notes)
    other = apply_substantiation(matches, Assessments(assessments=[]), document(url="https://other.example/"), claims, small_knowledge(), score=False)
    assert other.held_out == [] and [e["id"] for e in other.evidence] == ["P2"] and other.scores == [] and other.placeholders == []
    assert "quote" not in other.evidence[0], "an unverified store entry is listed without its quote"


def test_the_prompts_carry_the_claims_and_the_store_index():
    doc, claims = two_claims()
    knowledge = small_knowledge()
    prompt = match_prompt(claims, knowledge)
    assert "C1 | certification | company | P1 | prominence 1.0 | \"We are carbon neutral\"" in prompt
    assert "K1 [criterion; UK; tier 1] Neutral rule" in prompt and "Rule: Say whether offsets are used. Terms: carbon neutral. Claim types: certification." in prompt
    assert "P1 [precedent; DE; tier 1] Neutral ruling" in prompt and "Wording ruled on: \"carbon neutral watch\". Outcome: upheld." in prompt
    assert "<review>" not in score_prompt(claims, knowledge, batch=claims)
    partial = score_prompt(claims, knowledge, batch=claims[:1])
    assert "In this call, score only these claims: C1." in partial and "C2 | commitment" in partial


class StreamingLlm:
    """A stand-in for auditor.llm.Llm.extract_streaming: the matching call hands over its
    matches one by one (some, so the catch-up path is exercised) and each scoring call the
    assessments for the claims it was asked about, then returns the whole."""

    def __init__(self, matches: Matches, assessments: Assessments, hand_over: int = 1, *, fail_matcher: bool = False) -> None:
        self.matches = matches
        self.assessments = assessments
        self.hand_over = hand_over
        self.fail_matcher = fail_matcher
        self.calls: list[dict] = []

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if output is Matches:
            if self.fail_matcher:
                raise LlmError("the model's stream went quiet")
            await asyncio.sleep(0.01)  # the scorer is faster: its scores must wait for these
            for match in self.matches.matches[: self.hand_over]:
                await on_element("matches", match.model_dump())
            await on_element("other", {"ignored": True})
            return self.matches, usage()
        wanted = [line.split(" | ")[0] for line in prompt.split("<review>")[-1].split("\n") if False]  # noqa: F841 - ids come from the review line
        ids = set()
        if "<review>" in prompt:
            ids = {x.strip().rstrip(".") for x in prompt.split("score only these claims: ")[1].split("\n")[0].split(",")}
        else:
            ids = {a.claim_id for a in self.assessments.assessments}
        mine = [a for a in self.assessments.assessments if a.claim_id in ids]
        for item in mine[: self.hand_over]:
            await on_element("assessments", item.model_dump())
        await on_element("assessments", {"claim_id": "C1", "score": "not a number"})
        return Assessments(assessments=mine), usage()


def test_substantiate_streams_evidence_before_scores_and_catches_up_the_rest(monkeypatch):
    doc, claims = two_claims()
    matches = Matches(matches=[Match(evidence_id="K1", claim_ids=["C1"], note="n"), Match(evidence_id="K2", claim_ids=["C2"], note="n")])
    assessments = Assessments(assessments=[
        Assessment(claim_id="C1", criteria_ids=["K1"], precedent_ids=["P1"], score=0.6, confidence=0.7, basis="a"),
        Assessment(claim_id="C2", criteria_ids=["K2"], score=0.5, confidence=0.4, basis="b"),
    ])
    llm = StreamingLlm(matches, assessments, hand_over=1)
    events, emit = emitted()
    result = asyncio.run(substantiate(doc, claims, emit=emit, llm=llm, knowledge=small_knowledge()))
    types = [t for t, _ in events]
    assert types.index("dimension.scored") > max(i for i, t in enumerate(types) if t == "evidence.added" and events[i][1]["evidence"]["id"] in ("K1", "K2"))
    assert [e["evidence"]["id"] for t, e in events if t == "evidence.added"] == ["K1", "K2", "P1"], "the matcher's items, then the scorer's extra citation"
    assert sorted(e["score"]["claim_id"] for t, e in events if t == "dimension.scored") == ["C1", "C2"]
    assert result.usage is not None and result.usage.input_tokens == 20, "two calls (one matcher, one scoring batch)"
    assert "The model matched 2 store items in one call (first item after" in result.notes[0] and "scored 2 claims over 1 parallel calls of up to 9 claims, 1 malformed" in result.notes[0]
    matcher = next(c for c in llm.calls if c["output"] is Matches)
    assert matcher["effort"] == "low" and matcher["cache"] is True and matcher["system"].startswith("You are")
    scorer = next(c for c in llm.calls if c["output"] is Assessments)
    assert scorer["effort"] == "medium"


def test_scoring_runs_in_parallel_batches_and_can_be_switched_off(monkeypatch):
    from auditor import substantiate as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims = two_claims()
    matches = Matches(matches=[Match(evidence_id="K1", claim_ids=["C1"], note="n")])
    assessments = Assessments(assessments=[
        Assessment(claim_id="C1", criteria_ids=["K1"], score=0.6, confidence=0.7, basis="a"),
        Assessment(claim_id="C2", score=0.5, confidence=0.4, basis="b"),
    ])
    llm = StreamingLlm(matches, assessments, hand_over=5)
    events, emit = emitted()
    result = asyncio.run(substantiate(doc, claims, emit=emit, llm=llm, knowledge=small_knowledge()))
    assert len(llm.calls) == 3 and "over 2 parallel calls of up to 1 claims" in result.notes[0]
    assert [e["score"]["claim_id"] for t, e in events if t == "dimension.scored"] in (["C1", "C2"], ["C2", "C1"])
    llm = StreamingLlm(matches, assessments, hand_over=5)
    events, emit = emitted()
    result = asyncio.run(substantiate(doc, claims, emit=emit, llm=llm, knowledge=small_knowledge(), score=False))
    assert len(llm.calls) == 1 and [t for t, _ in events] == ["evidence.added"] and result.scores == []
    assert "Support is not scored here, because external verification (step 14) scores it" in result.notes[0]
    assert asyncio.run(substantiate(doc, [], emit=emit, llm=llm, knowledge=small_knowledge())).notes == ["No claims to substantiate."]


def test_a_failing_matcher_fails_the_stage_with_a_plain_error():
    doc, claims = two_claims()
    llm = StreamingLlm(Matches(matches=[]), Assessments(assessments=[Assessment(claim_id="C1", score=0.5, confidence=0.5, basis="x")]), fail_matcher=True)
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(substantiate(doc, claims, llm=llm, knowledge=small_knowledge()))


def test_the_golden_matches_place_the_reference_links_and_scores():
    """The fixture's substantiate-stage evidence maps onto the repository stores by URL, so a
    perfect evaluator reproduces the reference's criteria and precedent links and scores."""
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    doc = analysis["document"]
    claims = reanchored_claims(analysis["claims"], doc["text"], doc["text"])
    matches, assessments = golden_substantiation()
    assert len(matches.matches) == 6, "E8, E8b, E8c, E9, E11, E12 all have a store entry with the same URL"
    result = apply_substantiation(matches, assessments, doc, claims, load_knowledge())
    links = compare_links(result.evidence, analysis["evidence"])
    assert links.same_source == links.reference == links.any_source and links.missed == []
    support = compare_support(result.scores, analysis["scores"])
    assert support.mean_abs_error == 0 and support.wrong_band() == [] and support.unscored == []
    assert "6 of 6 reference" not in links.describe() and links.describe().startswith(f"{links.reference} of {links.reference} reference criteria and precedent links found ({links.reference} from the same source)")


def test_the_comparison_counts_missed_links_and_scores_on_the_other_side():
    reference_evidence = [
        {"id": "E11", "stage": "substantiate", "url": "https://a.example/code", "links": [{"target": "C3", "relation": "criteria"}, {"target": "O1", "relation": "criteria"}]},
        {"id": "E9", "stage": "substantiate", "url": "https://b.example/ruling", "links": [{"target": "C1", "relation": "precedent"}]},
        {"id": "E5", "stage": "verify", "url": "https://c.example", "links": [{"target": "C1", "relation": "supports"}]},
    ]
    live = [
        {"id": "K1", "stage": "substantiate", "url": "https://a.example/code/", "links": [{"target": "C3", "relation": "criteria"}]},
        {"id": "P4", "stage": "substantiate", "url": "https://other.example", "links": [{"target": "C1", "relation": "precedent"}, {"target": "C2", "relation": "precedent"}]},
    ]
    links = compare_links(live, reference_evidence)
    assert (links.reference, links.same_source, links.any_source, links.live_links, links.missed) == (2, 1, 2, 3, [])
    support = compare_support(
        [{"claim_id": "C1", "dimension": "support", "score": 0.7}, {"claim_id": "C3", "dimension": "support", "score": 0.5}, {"claim_id": "C3", "dimension": "clarity", "score": 0.9}],
        [{"claim_id": "C1", "dimension": "support", "score": 0.5}, {"claim_id": "C3", "dimension": "support", "score": 0.5}, {"claim_id": "C4", "dimension": "support", "score": 0.4}],
    )
    assert support.pairs == [("C1", 0.7, 0.5), ("C3", 0.5, 0.5)] and support.unscored == ["C4"]
    assert support.wrong_band() == ["C1"] and round(support.mean_abs_error, 2) == 0.1
    assert support.describe() == "support scored for 2 reference claims, mean absolute difference 0.10, 1 on the other side of 0.6, 1 reference claims unscored"
