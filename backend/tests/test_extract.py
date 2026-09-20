"""Claim extraction (roadmap step 11): placing the model's quotes, numbering, comparison with
the golden reference. The model itself is faked; the placement and comparison code is real."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO, golden_extraction, shell_fixture_document

from auditor.extract import ExtractedClaim, Extraction, assemble, compare, document_system, extract_claims, locate, paragraph_for
from auditor.llm import Usage

GOLDEN = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))


def test_locate_exact_then_normalised_then_case_insensitive():
    text = "Shell’s target – “net zero” by 2050. Shell’s target – “net zero” by 2050 again."
    exact = locate(text, "Shell’s target – “net zero” by 2050")
    assert exact is not None and (exact.start, exact.end, exact.occurrence) == (0, 35, 1)
    straight = locate(text, 'Shell\'s target - "net zero" by 2050')
    assert straight is not None and straight.text == "Shell’s target – “net zero” by 2050", "quotes and dashes normalised, original text kept"
    lower = locate(text, "NET ZERO")
    assert lower is not None and lower.text == "net zero" and lower.occurrence == 1
    second = locate(text, "net zero", taken=[(lower.start, lower.end)])
    assert second is not None and second.occurrence == 2, "an occurrence already taken is skipped"
    assert locate(text, "by 2050.") is not None, "a trailing full stop is forgiven"
    assert locate(text, "“net zero”").text == "“net zero”"
    assert locate(text, "carbon neutral") is None
    assert locate(text, "   ") is None


def test_paragraph_for_uses_the_innermost_labelled_region():
    document = shell_fixture_document()
    assert paragraph_for(document["regions"], 9, 77) == ("P1", 1.0)
    label, prominence = paragraph_for(document["regions"], 4775, 4800)
    assert label == "P11" and prominence == 0.3
    assert paragraph_for(document["regions"], 0, 7) == (None, None), "the title is in no paragraph"


def test_assemble_places_numbers_and_labels_claims():
    document = shell_fixture_document()
    extraction = Extraction(
        claims=[
            ExtractedClaim(quote="helping our customers transition to cleaner energy solutions.", type="vague_attribute", scope="product", attribute="cleaner"),
            ExtractedClaim(quote="Our target is to become a net-zero emissions energy business by 2050", repeats=["We have a target to become a net-zero emissions energy business by 2050"], type="commitment", scope="company", attribute="net zero", timeframe="2050", scope_note=" whole company "),
            ExtractedClaim(quote="This sentence is not in the document", type="factual", scope="other", attribute="x"),
            ExtractedClaim(quote="Shell's net carbon intensity is the average intensity", type="factual", scope="product", attribute=""),
        ]
    )
    result = assemble(extraction, document)
    assert result.dropped == ["This sentence is not in the document"]
    assert [c["id"] for c in result.claims] == ["C1", "C2", "C3"], "numbered in document order"
    first = result.claims[0]
    assert first["spans"][0] == {"text": "Our target is to become a net-zero emissions energy business by 2050", "start": 9, "end": 77}
    assert first["spans"][1]["text"].startswith("We have a target") and first["spans"][1]["occurrence"] == 1, "a repeated phrase records which occurrence"
    assert first["paragraph"] == "P1" and first["prominence"] == 1.0 and first["scope_note"] == "whole company" and first["timeframe"] == "2050"
    second = result.claims[1]
    assert second["spans"][0]["text"] == "helping our customers transition to cleaner energy solutions" and second["paragraph"] == "P1"
    third = result.claims[2]
    assert third["spans"][0]["text"] == "Shell’s net carbon intensity is the average intensity", "curly apostrophe restored"
    assert third["attribute"] == third["spans"][0]["text"][:60], "an empty attribute falls back to the quote"
    assert third["paragraph"] == "P11" and third["prominence"] == 0.3
    for claim in result.claims:
        for span in claim["spans"]:
            assert document["text"][span["start"] : span["end"]] == span["text"]


def test_a_perfect_extraction_reproduces_the_golden_claims():
    document = shell_fixture_document()
    result = assemble(golden_extraction(), document)
    assert len(result.claims) == 25 and not result.dropped
    starts = [c["spans"][0]["start"] for c in result.claims]
    assert starts == sorted(starts) and [c["id"] for c in result.claims] == [f"C{i}" for i in range(1, 26)], "numbered in document order"
    by_primary = {c["spans"][0]["text"]: c for c in result.claims}
    for golden in GOLDEN["claims"]:
        live = by_primary[golden["spans"][0]["text"]]
        assert [(s["text"], s["start"], s["end"]) for s in live["spans"]] == [(s["text"], s["start"], s["end"]) for s in golden["spans"]]
        assert live["type"] == golden["type"] and live["scope"] == golden["scope"] and live["paragraph"] == golden["paragraph"]
    comparison = compare(result.claims, GOLDEN["claims"], document["text"])
    assert comparison.recall == 1.0 and comparison.precision == 1.0 and not comparison.missed and not comparison.extra
    assert all(m.same_type for m in comparison.matches)


def test_compare_matches_by_overlap_one_to_one():
    document = shell_fixture_document()
    text = document["text"]
    def span(quote: str) -> dict:
        start = text.index(quote)
        return {"text": quote, "start": start, "end": start + len(quote)}

    live = [
        {"id": "C1", "spans": [span("net-zero emissions energy business by 2050")], "type": "commitment"},  # inside golden C1
        {"id": "C2", "spans": [span("we are reducing emissions from our operations, and helping our customers")], "type": "factual"},  # covers C2, touches C3
        {"id": "C3", "spans": [span("Find out more about how we are working to achieve this target")], "type": "factual"},  # no golden claim
    ]
    comparison = compare(live, GOLDEN["claims"], text)
    pairs = {(m.live_id, m.reference_id) for m in comparison.matches}
    assert ("C1", "C1") in pairs and ("C2", "C2") in pairs
    assert "C3" in comparison.extra
    assert "C3" in comparison.missed or ("C2", "C3") not in pairs, "one live claim matches at most one reference claim"
    assert comparison.reference_total == 25 and comparison.live_total == 3
    assert "recall" in comparison.describe() and "missed" in comparison.describe()


def test_extract_claims_sends_the_document_as_the_cached_system_prefix():
    document = shell_fixture_document()

    class FakeLlm:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def extract(self, prompt, output, **kwargs):
            self.calls.append({"prompt": prompt, "output": output, **kwargs})
            return golden_extraction(), Usage("claude-sonnet-5", 5000, 900, 0, 5000, "end_turn", "req", 3.0)

    llm = FakeLlm()
    result = asyncio.run(extract_claims(document, llm))  # type: ignore[arg-type]
    assert len(result.claims) == 25 and result.usage is not None and result.usage.output_tokens == 900
    [call] = llm.calls
    assert call["output"] is Extraction and call["cache"] is True and call["effort"] == "medium"
    assert call["system"] == document_system(document)
    assert call["system"].startswith("You are the reading stage") and "<document title=\"Climate | Shell Global\" company=\"Shell plc\">" in call["system"]
    assert document["text"] in call["system"]
    assert "atomic environmental claims" in call["prompt"]
    assert any("25 placed" in note for note in result.notes)
