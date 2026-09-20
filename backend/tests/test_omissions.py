"""Omissions (step 16): the materiality store loads and places a document in its industry, a
margin card is only written for a topic the text really does not address, the reference that
makes it material is emitted before the card that cites it, and everything validates against
the contract. No test calls Claude."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO

from auditor.knowledge import KnowledgeError
from auditor.llm import LlmError, Usage
from auditor.materiality import (
    Materiality,
    MaterialityEntry,
    MaterialityIndex,
    Topic,
    load_materiality,
    mentions,
)
from auditor.omissions import (
    MIN_SCORE,
    Coverage,
    Coverages,
    Placement,
    apply_omissions,
    compare_omissions,
    coverage_prompt,
    find_omissions,
)

TEXT = (
    "# Our climate plan\n\n"
    "We have cut the carbon intensity of our energy by 12% since 2016 and we eliminated routine "
    "flaring from our upstream operations in 2025.\n\n"
    "We are making investments in low carbon projects while sustaining our liquids production."
)


def document(text: str = TEXT, *, label: str = "Oil & Gas – Integrated", codes: list[str] | None = None) -> dict:
    return {
        "id": "d",
        "title": "Our climate plan",
        "company": {"name": "Acme Energy"},
        "industry": {"label": label, "sasb_codes": ["EM-EP"] if codes is None else codes},
        "text_type": "policy",
        "source": {"url": "https://acme.example/climate", "retrieved": "2026-09-20"},
        "text": text,
        "word_count": len(text.split()),
        "regions": [],
    }


def claim(cid: str, words: str, text: str = TEXT) -> dict:
    start = text.index(words)
    return {"id": cid, "spans": [{"text": words, "start": start, "end": start + len(words)}], "type": "factual", "scope": "company", "attribute": words, "paragraph": "P1", "prominence": 1.0}


def small_store() -> Materiality:
    """Two industries: one with three topics, and the cross-industry entry with one."""
    entry = MaterialityEntry(
        id="ref-oil-and-gas", kind="standard", tier=3, source={"name": "Sector Standard, Oil and Gas"},
        url="https://ref.example/oil-and-gas", quote="likely material topics", verified=True, verification="fetched_exact",
        retrieved="2026-09-20", note="A note.",
        index=MaterialityIndex(
            industry="Oil & Gas", reference="REF EM-EP", sasb_code="EM-EP", also_codes=["EM-RM"], aliases=["Oil and Gas", "Petroleum"], keywords=["oil", "gas"],
            topics=[
                Topic(code="11.1", name="Absolute emissions", why_material="Intensity can fall while the total rises.", expects="The total in tonnes.", terms=["absolute emissions", "total emissions", "million tonnes"]),
                Topic(code="11.2", name="Production plans", why_material="Volumes decide emissions.", expects="Planned volumes.", terms=["barrels", "production", "output"]),
                Topic(code="11.3", name="Methane and flaring", why_material="The fastest-acting impact.", expects="Methane intensity.", terms=["methane", "flaring"]),
            ],
        ),
    )
    general = MaterialityEntry(
        id="ref-any-industry", kind="law", tier=1, source={"name": "Disclosure regulation"},
        url="https://ref.example/any", verified=False, verification="unverified", retrieved="2026-09-20",
        index=MaterialityIndex(
            industry="Any company", reference="REG E1", sasb_code="*",
            topics=[Topic(code="E1-1", name="Where the money goes", why_material="Capital allocation decides a transition claim.", expects="The capex split.", terms=["capital expenditure", "capex"])],
        ),
    )
    return Materiality([entry, general])


def emitted():
    events: list[tuple[str, dict]] = []
    return events, lambda type_, payload: events.append((type_, payload))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def card(topic_id: str, **kwargs) -> Coverage:
    fields = {
        "topic_id": topic_id, "addressed": "no", "topic": "Absolute emissions",
        "why_material": "The page gives an intensity figure and no total.",
        "complete_text": "Our total emissions were 1,118 million tonnes.", "score": 0.7, "confidence": 0.8,
    }
    fields.update(kwargs)
    return Coverage(**fields)


# ----------------------------------------------------------------------------- the store


def test_the_repository_store_loads_and_covers_the_demo_industries():
    store = load_materiality()
    assert store.directory == REPO / "knowledge"
    assert len(store.entries) >= 8
    codes = {e.index.sasb_code for e in store.entries}
    assert {"*", "EM-EP", "TC-HW", "IF-EU"} <= codes, "the three demo documents' industries, and the cross-industry entry"
    for entry in store.entries:
        assert entry.index.topics, entry.id
        for topic in entry.index.topics:
            assert topic.terms, f"{entry.id}: {topic.name} has no terms, so its absence cannot be checked"
    assert store.general() is not None
    verified = [e for e in store.entries if e.verified]
    assert verified and all(e.quote and e.verification != "unverified" for e in verified)
    assert all(e.quote is None for e in store.entries if not e.verified), "an unverified quote is never displayed"


def test_every_reference_becomes_a_valid_contract_evidence_item():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator({"$ref": "#/definitions/EvidenceItem", "definitions": schema["definitions"]})
    store = load_materiality()
    for evidence_id, entry in store.ids().items():
        item = entry.as_evidence(evidence_id, [{"target": "O1", "relation": "criteria"}])
        assert not list(validator.iter_errors(item)), (entry.id, [e.message for e in validator.iter_errors(item)])
        assert item["stage"] == "omissions" and item["ext"]["store"] == "materiality" and item["ext"]["sasb_code"] == entry.index.sasb_code
        assert ("quote" in item) == entry.verified


def test_a_document_is_placed_by_code_then_by_label_and_always_gets_the_cross_industry_entry():
    store = small_store()
    by_code = store.for_document(document())
    assert [m.evidence_id for m in by_code] == ["M1", "M2"] and by_code[0].how == "SASB code EM-EP"
    neighbour = store.for_document(document(codes=["EM-RM"]))
    assert neighbour[0].evidence_id == "M1" and "covered by EM-EP" in neighbour[0].how
    by_label = store.for_document(document(label="Petroleum", codes=[]))
    assert by_label[0].evidence_id == "M1" and "matched" in by_label[0].how
    unknown = store.for_document(document(label="Not identified", codes=[]))
    assert [m.evidence_id for m in unknown] == ["M2"], "only the cross-industry entry; the evaluator then asks Claude"
    assert store.by_code("TC-HW") is None


def test_a_second_entry_for_the_same_industry_is_refused(tmp_path):
    entry = small_store().entries[0].model_dump(exclude_none=True)
    (tmp_path / "materiality.json").write_text(json.dumps([entry, {**entry, "id": "other"}]), encoding="utf-8")
    with pytest.raises(KnowledgeError, match="a second entry for industry EM-EP"):
        load_materiality(tmp_path)
    (tmp_path / "materiality.json").write_text("[]", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="the store is empty"):
        load_materiality(tmp_path)
    with pytest.raises(KnowledgeError, match="is missing"):
        load_materiality(tmp_path / "nowhere")


def test_mentions_matches_whole_words_only():
    assert mentions("We ended routine flaring in 2025.", ["flaring", "methane"]) == ["flaring"]
    assert mentions("Our gasoline business", ["gas"]) == [], "a word inside another word is not a mention"
    assert mentions("Capital  expenditure was $20bn", ["capital expenditure"]) == ["capital expenditure"], "whitespace between words is not significant"
    assert mentions("CAPEX rose", ["capex"]) == ["capex"]


# ----------------------------------------------------------------------------- assembly


def test_the_reference_is_emitted_before_the_cards_that_cite_it_and_links_to_all_of_them():
    store = small_store()
    doc = document()
    events, emit = emitted()
    coverages = Coverages(coverage=[
        card("M1.1", nearest="carbon intensity of our energy by 12%"),
        card("M1.2", topic="Production plans", why_material="Only 'sustaining our liquids production'.", nearest="sustaining our liquids production", score=0.6, confidence=0.7),
        Coverage(topic_id="M1.3", addressed="yes", nearest="eliminated routine flaring"),
        card("M2.1", topic="Capital allocation", why_material="No split is given.", score=0.65, confidence=0.75),
    ])
    result = apply_omissions(coverages, doc, store, store.for_document(doc), emit=emit)
    assert [t for t, _ in events] == ["evidence.added", "evidence.added", "omission.found", "omission.found", "omission.found"]
    first, second = events[0][1]["evidence"], events[1][1]["evidence"]
    assert first["id"] == "M1" and [l["target"] for l in first["links"]] == ["O1", "O2"] and all(l["relation"] == "criteria" for l in first["links"])
    assert first["stage"] == "omissions" and first["quote"] == "likely material topics" and first["ext"]["industry"] == "Oil & Gas"
    assert second["id"] == "M2" and [l["target"] for l in second["links"]] == ["O3"] and "quote" not in second
    ids = [e["omission"]["id"] for t, e in events if t == "omission.found"]
    assert ids == ["O1", "O2", "O3"]
    o1 = events[2][1]["omission"]
    assert o1["topic"] == "Absolute emissions" and o1["evidence_ids"] == ["M1"]
    assert o1["materiality_reference"] == "REF EM-EP 11.1: Absolute emissions"
    assert o1["ext"]["nearest"] == "carbon intensity of our energy by 12%" and o1["ext"]["topic_id"] == "M1.1"
    assert result.addressed == ["M1.3"] and len(result.omissions) == 3
    assert result.completeness["score"] == 0.7 and result.completeness["confidence"] == 0.75
    assert "3 of the 4 material topics are unaddressed" in result.completeness["basis"]


def test_a_topic_the_page_does_not_touch_records_that_its_words_are_absent():
    store = small_store()
    doc = document()
    result = apply_omissions(Coverages(coverage=[card("M2.1", topic="Capital allocation")]), doc, store, store.for_document(doc))
    absence = result.omissions[0]["ext"]["absence"]
    assert absence.startswith("none of the reference's words for this topic appear in the text")
    assert "capital expenditure" in absence


def test_a_card_whose_words_are_in_the_text_with_no_passage_given_loses_confidence():
    store = small_store()
    doc = document()
    result = apply_omissions(Coverages(coverage=[card("M1.3", topic="Methane and flaring", nearest="", confidence=0.9)]), doc, store, store.for_document(doc))
    omission = result.omissions[0]
    assert omission["confidence"] == 0.72, "0.9 penalised: the text says 'flaring' and the card did not say where"
    assert omission["ext"]["absence"] == "the text does use: flaring"
    assert "1 cards whose topic words are in the text with no nearest passage given" in result.notes[0]


def test_a_quote_that_is_not_in_the_document_is_dropped_and_reported():
    store = small_store()
    doc = document()
    result = apply_omissions(Coverages(coverage=[card("M1.1", nearest="we halved our absolute emissions last year")]), doc, store, store.for_document(doc))
    assert "nearest" not in result.omissions[0]["ext"], "a quote the page does not contain never reaches a card"
    assert "1 quotes were not in the document and were dropped (M1.1)" in result.notes[0]


def test_unknown_repeated_low_and_unanswered_topics_are_left_out():
    store = small_store()
    doc = document()
    coverages = Coverages(coverage=[
        card("M1.1"),
        card("M1.1", topic="Repeat"),
        card("M9.9", topic="Unknown reference"),
        card("M1.2", topic="Barely material", score=MIN_SCORE - 0.05),
        Coverage(topic_id="M1.3", addressed="partly", nearest="eliminated routine flaring", score=0.1),
    ])
    result = apply_omissions(coverages, doc, store, store.for_document(doc))
    assert [o["id"] for o in result.omissions] == ["O1"]
    note = result.notes[0]
    assert "1 topics the model did not answer for (M2.1)" in note
    assert "1 cards below the 0.2 bar dropped" in note and "1 unknown topic ids ignored" in note and "1 repeated topics ignored" in note
    assert result.addressed == ["M1.2", "M1.3"], "a topic below the bar counts as addressed, not as a card"


def test_an_omission_cites_the_evidence_that_establishes_the_fact_and_nothing_else():
    store = small_store()
    doc = document()
    prior = [{"id": "E4", "kind": "filing", "tier": 2, "source": {"name": "Annual report"}, "quote": "1,118 million tonnes", "links": []}]
    coverages = Coverages(coverage=[card("M1.1", evidence_ids=["E4", "E4", "E9"])])
    result = apply_omissions(coverages, doc, store, store.for_document(doc), prior_evidence=prior)
    assert result.omissions[0]["evidence_ids"] == ["M1", "E4"], "the reference first, then what establishes the fact"
    assert "1 citations of evidence that does not exist dropped" in result.notes[0]


def test_every_omission_validates_against_the_contract():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator({"$ref": "#/definitions/Omission", "definitions": schema["definitions"]})
    store = small_store()
    doc = document()
    result = apply_omissions(Coverages(coverage=[card("M1.1"), card("M2.1", topic="Capital allocation")]), doc, store, store.for_document(doc))
    for omission in result.omissions:
        assert not list(validator.iter_errors(omission)), [e.message for e in validator.iter_errors(omission)]


def test_completeness_is_low_when_the_page_addresses_everything():
    store = small_store()
    doc = document()
    coverages = Coverages(coverage=[Coverage(topic_id=t, addressed="yes") for t in ("M1.1", "M1.2", "M1.3", "M2.1")])
    result = apply_omissions(coverages, doc, store, store.for_document(doc))
    assert result.omissions == [] and result.evidence == []
    assert result.completeness["score"] == 0.15 and result.completeness["confidence"] == 0.6
    assert "no material topic was found missing" in result.completeness["basis"]


# ----------------------------------------------------------------------------- the call


class StreamingLlm:
    """A stand-in for auditor.llm.Llm: hands over some coverage entries while the reply
    streams, then returns the whole, and answers the industry call with `placement`."""

    def __init__(self, coverages: Coverages, placement: Placement | None = None, hand_over: int = 1, *, fail: bool = False) -> None:
        self.coverages = coverages
        self.placement = placement
        self.hand_over = hand_over
        self.fail = fail
        self.calls: list[dict] = []

    async def extract(self, prompt, output, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        assert self.placement is not None
        return self.placement, usage()

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if self.fail:
            raise LlmError("Claude's stream went quiet")
        for item in self.coverages.coverage[: self.hand_over]:
            await on_element("coverage", item.model_dump())
        await on_element("coverage", {"topic_id": "M1.1", "score": "not a number"})
        await on_element("other", {"ignored": True})
        return self.coverages, usage()


def test_the_stage_streams_what_it_can_and_catches_up_the_rest():
    store = small_store()
    doc = document()
    coverages = Coverages(coverage=[card("M1.1"), card("M2.1", topic="Capital allocation", score=0.65, confidence=0.75)])
    llm = StreamingLlm(coverages, hand_over=1)
    events, emit = emitted()
    result = asyncio.run(find_omissions(doc, [claim("C1", "cut the carbon intensity of our energy by 12% since 2016")], emit=emit, llm=llm, store=store))
    assert [o["id"] for o in result.omissions] == ["O1", "O2"]
    assert [t for t, _ in events][:2] == ["evidence.added", "evidence.added"], "both references, then the cards"
    assert "Claude read 2 topics in one call, 1 malformed" in result.notes[0]
    assert result.notes[1].startswith("Industry 'Oil & Gas – Integrated' -> M1 Oil & Gas (SASB code EM-EP)")
    assert result.notes[-1].startswith("Completeness 0.7")
    call = llm.calls[0]
    assert call["effort"] == "medium" and call["cache"] is True and call["system"].startswith("You are")
    assert "<topics>" in call["prompt"] and "M1.1 [11.1] Absolute emissions" in call["prompt"] and "C1 | factual" in call["prompt"]
    assert result.usage is not None and result.usage.input_tokens == 10


def test_an_unknown_industry_is_placed_by_claude_and_the_choice_is_in_the_log():
    store = small_store()
    doc = document(label="Not identified", codes=[])
    llm = StreamingLlm(Coverages(coverage=[card("M1.1")]), Placement(sasb_code="EM-EP", industry="Oil and gas", confidence=0.8, basis="It talks about upstream operations."))
    result = asyncio.run(find_omissions(doc, [], llm=llm, store=store))
    assert [c["output"] for c in llm.calls] == [Placement, Coverages]
    assert llm.calls[0]["effort"] == "low"
    assert "Claude placed it in Oil & Gas (EM-EP), confidence 0.80: It talks about upstream operations." in result.notes[1]
    assert [m.evidence_id for m in result.matches] == ["M1", "M2"]
    assert result.omissions[0]["evidence_ids"] == ["M1"]


def test_an_industry_claude_cannot_place_leaves_the_cross_industry_topics():
    store = small_store()
    doc = document(label="Something else", codes=[])
    llm = StreamingLlm(Coverages(coverage=[card("M2.1", topic="Capital allocation")]), Placement(sasb_code="", basis="No industry in the list fits."))
    result = asyncio.run(find_omissions(doc, [], llm=llm, store=store))
    assert [m.evidence_id for m in result.matches] == ["M2"]
    assert "matched it to no industry in the store" in result.notes[1]
    assert result.omissions[0]["evidence_ids"] == ["M2"]


def test_a_failing_call_fails_the_stage_with_a_plain_error():
    store = small_store()
    llm = StreamingLlm(Coverages(coverage=[]), fail=True)
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(find_omissions(document(), [], llm=llm, store=store))


def test_the_prompt_shows_the_evidence_with_quotes_only_where_they_are_verified():
    store = small_store()
    doc = document()
    prior = [
        {"id": "E4", "kind": "filing", "tier": 2, "source": {"name": "Annual report"}, "quote": "1,118 million tonnes", "links": []},
        {"id": "E9", "kind": "ruling", "tier": 1, "source": {"name": "A ruling"}, "note": "Listed by name.", "links": []},
    ]
    prompt = coverage_prompt([], prior, store, store.for_document(doc))
    assert 'E4 [tier 2; filing] Annual report\n  "1,118 million tonnes"' in prompt
    assert "E9 [tier 1; ruling] A ruling\n  Listed by name." in prompt
    assert coverage_prompt([], [], store, store.for_document(doc)).count("(no evidence gathered yet)") == 1


# ----------------------------------------------------------------------------- against the golden reference


def test_the_comparison_pairs_cards_with_the_reference_by_their_words():
    reference = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))["omissions"]
    live = [
        {"id": "O1", "topic": "Capital allocation", "why_material": "The page never says what share of investment goes to renewables and energy solutions against upstream and gas.", "complete_text": "In 2025 we invested $1.9 billion of $20.9 billion in renewables.", "score": 0.7},
        {"id": "O2", "topic": "Something else entirely", "why_material": "Nothing to do with the reference at all.", "complete_text": "", "score": 0.4},
    ]
    comparison = compare_omissions(live, reference)
    assert [(a, b) for a, b, _, _ in comparison.pairs] == [("O1", "O2")]
    assert comparison.extra == ["O2 Something else entirely"] and len(comparison.missed) == 3
    assert "1 of 4 reference omissions found, mean absolute difference in materiality 0.05" in comparison.describe()


# ----------------------------------------------------------------------------- through the pipeline


def test_the_stage_runs_live_in_a_pipeline_run_and_replaces_the_recorded_cards(
    client, shell_pages, real_shell, fake_extract, fake_language, fake_substantiate, fake_verify, fake_consistency, fake_verdict, fake_omissions
):
    """A live analysis of the Shell page with a perfect omissions stage: the reference is
    emitted before the cards that cite it, the recording's own omissions and the evidence
    gathered for them are gone, and the whole log still passes the contract's checks."""
    from conftest import SHELL_URL, golden_debate, golden_extraction, golden_omissions, golden_review, golden_substantiation, golden_verification, read_sse
    from test_pipeline import check_contract, types_of

    fake_extract.extraction = golden_extraction()
    fake_language.review = golden_review()
    fake_substantiate.matches, fake_substantiate.assessments = golden_substantiation()
    fake_verify.findings, fake_verify.computations, fake_verify.assessments, _, _ = golden_verification()
    fake_verdict.prosecution, fake_verdict.defence, fake_verdict.judgments = golden_debate()
    fake_omissions.coverages = golden_omissions()

    summary = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6}).json()
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[-1] == "analysis.completed"

    stage = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "omissions")
    assert "note" not in stage["payload"] and stage["payload"]["label"] == "Looking for what the page leaves out"
    cards = [env["payload"]["omission"] for _, env in received if env["type"] == "omission.found"]
    assert [o["id"] for o in cards] == ["O1", "O2", "O3", "O4"], "four cards, none of them replayed from the recording"
    assert {o["topic"] for o in cards} == {
        "The absolute size and trend of Shell's total emissions", "Capital allocation",
        "Production and sales volume plans", "The history of the targets",
    }
    references = [env["payload"]["evidence"] for _, env in received if env["type"] == "evidence.added" and env["payload"]["evidence"]["stage"] == "omissions"]
    assert [e["id"] for e in references] == ["M2", "M1"], "the industry's own reference, then the cross-industry one"
    assert {l["target"] for e in references for l in e["links"]} == {"O1", "O2", "O3", "O4"}
    last_reference = max(i for i, (_, env) in enumerate(received) if env["type"] == "evidence.added" and env["payload"]["evidence"]["stage"] == "omissions")
    assert last_reference < types.index("omission.found"), "the reference exists before the cards cite it"
    for card in cards:
        assert card["evidence_ids"][0] in ("M1", "M2") and card["materiality_reference"]
        assert card["ext"]["industry"] in ("Oil & Gas – Exploration, Production, Refining & Marketing", "Any company making environmental claims")
    industries = {o["ext"]["industry"] for o in cards}
    assert len(industries) == 2, "three cards come from the industry's reference, the fourth from the cross-industry one"
    nearest = {o["topic"]: o["ext"].get("nearest") for o in cards}
    assert nearest["Production and sales volume plans"] == "while sustaining our liquids production", "placed in the live text"
    assert nearest["The history of the targets"] is None, "the page comes nowhere near it"
    assert all(o["evidence_ids"] == [o["evidence_ids"][0]] for o in cards), (
        "the golden cards cite the fixture's own evidence ids, which a live run does not have: they are dropped, "
        "and only the reference is left"
    )

    assert {o["id"] for o in cards} == {"O1", "O2", "O3", "O4"}, "the recording's O1-O4 are replaced, not added to"
    folded = check_contract(received)
    assert len(folded["omissions"]) == 4
    assert next(env["payload"]["summary"] for _, env in received if env["type"] == "summary.updated")["omission_count"] == 4
    completed = received[-1][1]["payload"]
    assert completed["counts"]["omissions"] == 4
    notes = [env["payload"]["text"] for _, env in received if env["type"] == "debug.note"]
    assert any("4 of 4 reference omissions found" in n for n in notes), "the visual check against the golden reference"
    assert any("citations of evidence that does not exist dropped" in n for n in notes)
    assert not any(e["id"] == "E16" for _, env in received if env["type"] == "evidence.added" for e in [env["payload"]["evidence"]]), \
        "the recording's own materiality reference is replaced by the live one"
