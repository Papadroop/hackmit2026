"""The linguistic evaluator (step 12): placement of word-level marks, clarity bookkeeping,
streaming assembly and the comparison with the golden reference. No test calls Claude."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from conftest import REPO, golden_review, shell_fixture_document

from auditor.extract import locate
from auditor.ingest import ingest_text
from auditor import language as language_module
from auditor.language import (
    PLACEHOLDER_BASIS,
    Assembler,
    ClarityScore,
    DocumentSignals,
    FoundSignal,
    LanguageReview,
    LanguageResult,
    apply_review,
    claims_listing,
    compare_clarity,
    compare_signals,
    document_prompt,
    occurrences,
    review_language,
    structure_summary,
    task_prompt,
)
from auditor.llm import Usage

TEXT = (
    "# Climate\n\n"
    "Our target is to become a net-zero business by 2050. We are helping our customers to use cleaner energy, and helping suppliers too.\n\n"
    "## Progress\n\n"
    "Emissions were around 70% lower than in 2016; well below the target. We achieved this by helping customers."
)


def document():
    return ingest_text(TEXT, title="Climate").document


def claim(cid: str, text: str, quote: str, **extra) -> dict:
    placed = locate(text, quote)
    assert placed is not None, quote
    return {"id": cid, "spans": [placed.as_span()], "type": "factual", "scope": "company", "attribute": quote[:20], **extra}


def emitted():
    events: list[tuple[str, dict]] = []
    return events, (lambda type_, payload: events.append((type_, payload)))


def test_occurrences_tiers_and_numbering():
    text = document()["text"]
    hits = occurrences(text, "helping")
    assert [h.occurrence for h in hits] == [1, 2, 3]
    assert occurrences(text, "Helping")[0].text == "helping", "case-insensitive is the last tier"
    assert occurrences(text, "net-zero business by 2050.")[0].text == "net-zero business by 2050", "a trailing full stop is dropped"
    assert occurrences(text, "not in the text") == []


def test_a_signal_is_placed_inside_its_claim_before_anywhere_else():
    doc = document()
    text = doc["text"]
    c1 = claim("C1", text, "helping our customers to use cleaner energy")
    events, emit = emitted()
    assembler = Assembler(doc, [c1], emit)
    signal = assembler.add_signal(FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="Agency hedge.", strength=0.5))
    assert signal is not None
    assert [(s["start"], s["occurrence"]) for s in signal["spans"]] == [(c1["spans"][0]["start"], 1)], "only the occurrence inside C1, though 'helping' appears three times"
    assert signal["id"] == "L1" and signal["claim_ids"] == ["C1"] and signal["strength"] == 0.5
    assert events == [("language.signal", {"signal": signal})]


def test_every_occurrence_inside_the_named_claims_is_marked():
    doc = document()
    text = doc["text"]
    wide = claim("C1", text, "helping our customers to use cleaner energy, and helping suppliers too")
    signal = Assembler(doc, [wide]).add_signal(FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="x", strength=0.4))
    assert [s["occurrence"] for s in signal["spans"]] == [1, 2]
    assert all(wide["spans"][0]["start"] <= s["start"] and s["end"] <= wide["spans"][0]["end"] for s in signal["spans"])


def test_words_outside_the_claim_fall_back_to_its_paragraph_then_the_document():
    doc = document()
    text = doc["text"]
    c2 = claim("C2", text, "Emissions were around 70% lower than in 2016")
    assembler = Assembler(doc, [c2])
    nearby = assembler.add_signal(FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C2"], note="x", strength=0.3))
    assert len(nearby["spans"]) == 1 and nearby["spans"][0]["occurrence"] == 3, "the one in C2's paragraph, not the first in the document"
    heading = assembler.add_signal(FoundSignal(level="claim", kind="framing", polarity="flag", quotes=["Progress"], claim_ids=["C2"], note="A heading.", strength=0.6))
    assert heading["spans"][0]["text"] == "Progress" and "occurrence" not in heading["spans"][0]
    assert heading["id"] == "L2"


def test_unplaceable_signals_are_dropped_or_demoted_and_orphans_are_attached():
    doc = document()
    text = doc["text"]
    c1 = claim("C1", text, "helping our customers to use cleaner energy")
    assembler = Assembler(doc, [c1])
    assert assembler.add_signal(FoundSignal(level="claim", kind="vague_term", polarity="flag", quotes=["greenest ever"], claim_ids=["C1"], note="x", strength=0.6)) is None
    assert assembler.dropped == ["vague_term: greenest ever"]
    demoted = assembler.add_signal(FoundSignal(level="claim", kind="prominence", polarity="flag", quotes=[], claim_ids=["C1"], note="Top of page.", strength=0.7))
    assert demoted["level"] == "document" and demoted["spans"] == [] and demoted["claim_ids"] == ["C1"]
    orphan = assembler.add_signal(FoundSignal(level="claim", kind="comparative_without_baseline", polarity="flag", quotes=["cleaner"], claim_ids=["C9"], note="x", strength=0.8))
    assert orphan["claim_ids"] == ["C1"], "an unknown id is dropped and the signal attached to the claim whose span holds its words"
    assert assembler.unknown_ids == 1
    document_level = assembler.add_signal(FoundSignal(level="document", kind="register", polarity="benign", quotes=["ignored words"], claim_ids=[], note="Plain.", strength=0.1))
    assert document_level["spans"] == [] and document_level["claim_ids"] == []


def test_clarity_scores_are_one_per_claim_with_placeholders_for_the_rest():
    doc = document()
    text = doc["text"]
    claims = [claim("C1", text, "net-zero business by 2050"), claim("C2", text, "Emissions were around 70% lower than in 2016")]
    events, emit = emitted()
    assembler = Assembler(doc, claims, emit)
    first = assembler.add_clarity(ClarityScore(claim_id="C1", score=0.72, confidence=1.4, basis="  Undefined   term. "))
    assert first == {"claim_id": "C1", "dimension": "clarity", "score": 0.72, "confidence": 1.0, "basis": "Undefined term.", "stage": "language"}
    assert assembler.add_clarity(ClarityScore(claim_id="C1", score=0.1, confidence=0.9, basis="again")) is None
    assert assembler.add_clarity(ClarityScore(claim_id="C7", score=0.1, confidence=0.9, basis="nobody")) is None
    result = assembler.finish()
    assert [s["claim_id"] for s in result.scores] == ["C1", "C2"]
    assert result.scores[1] == {"claim_id": "C2", "dimension": "clarity", "score": 0.5, "confidence": 0.3, "basis": PLACEHOLDER_BASIS, "stage": "language"}
    assert result.placeholders == ["C2"]
    assert [t for t, _ in events] == ["dimension.scored", "dimension.scored"]
    assert "clarity scored for 2 of 2 claims, 1 with a neutral placeholder (C2)" in result.notes[0]
    assert "ignored 1 unknown claim ids and 1 duplicate scores" in result.notes[0]


def test_apply_review_emits_signals_then_scores_with_running_ids():
    doc = document()
    text = doc["text"]
    claims = [claim("C1", text, "helping our customers to use cleaner energy"), claim("C2", text, "well below the target")]
    review = LanguageReview(
        signals=[
            FoundSignal(level="claim", kind="comparative_without_baseline", polarity="flag", quotes=["cleaner"], claim_ids=["C1"], note="Cleaner than what?", strength=0.8),
            FoundSignal(level="claim", kind="intensifier", polarity="benign", quotes=["well below"], claim_ids=["C2"], note="Bears out.", strength=0.1),
            FoundSignal(level="document", kind="register", polarity="benign", quotes=[], claim_ids=[], note="Plain.", strength=0.1),
        ],
        clarity=[ClarityScore(claim_id="C2", score=0.2, confidence=0.9, basis="Specific."), ClarityScore(claim_id="C1", score=0.85, confidence=0.9, basis="Comparative.")],
    )
    events, emit = emitted()
    result = apply_review(review, doc, claims, emit)
    assert [t for t, _ in events] == ["language.signal"] * 3 + ["dimension.scored"] * 2
    assert [p["signal"]["id"] for _, p in events[:3]] == ["L1", "L2", "L3"]
    assert [p["score"]["claim_id"] for _, p in events[3:]] == ["C2", "C1"], "scores are emitted in the order the model gives them"
    assert result.notes == ["3 language signals placed (1 flagged, 2 benign, 0 credit; 2 claim-level, 1 document-level); clarity scored for 2 of 2 claims"]
    assert text[result.signals[0]["spans"][0]["start"] : result.signals[0]["spans"][0]["end"]] == "cleaner"


def test_reanchored_reference_claims_keep_their_words():
    from auditor.language import reanchored_claims

    doc = shell_fixture_document()
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    claims = reanchored_claims(analysis["claims"], doc["text"], analysis["document"]["text"])
    assert len(claims) == 25
    for live, golden in zip(claims, analysis["claims"]):
        assert live["id"] == golden["id"]
        assert [s["text"] for s in live["spans"]] == [s["text"] for s in golden["spans"]]
        assert all(doc["text"][s["start"] : s["end"]] == s["text"] for s in live["spans"])
    assert '"Our target is to become a net-zero emissions energy business by 2050"' in claims_listing(claims).splitlines()[0]


def test_the_golden_review_places_every_golden_signal_and_score():
    doc = shell_fixture_document()
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    result = apply_review(golden_review(), doc, analysis["claims"])
    assert len(result.signals) == 24 and result.dropped == [] and result.placeholders == []
    signals = compare_signals(result.signals, analysis["signals"], doc["text"], doc["text"])
    assert signals.recall == 1.0 and signals.precision == 1.0
    assert sum(1 for m in signals.matches if m.how == "span") == 21, "the three document-level signals match by kind"
    clarity = compare_clarity(result.scores, analysis["scores"])
    assert clarity.mean_abs_error == 0.0 and clarity.wrong_side == [] and clarity.unscored == []
    for signal in result.signals:
        for span in signal["spans"]:
            assert doc["text"][span["start"] : span["end"]] == span["text"]


def test_comparison_reports_misses_extras_and_the_seven_tenths_line():
    doc = shell_fixture_document()
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    review = golden_review()
    review.signals = review.signals[:10] + [FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["Maintaining"], claim_ids=["C10"], note="new", strength=0.4)]
    review.signals[1] = review.signals[1].model_copy(update={"quotes": ["transition to cleaner energy solutions"]})  # wider words, same kind: still L2
    review.clarity = [c.model_copy(update={"score": 0.9}) if c.claim_id == "C2" else c for c in review.clarity if c.claim_id != "C25"]
    result = apply_review(review, doc, analysis["claims"])
    signals = compare_signals(result.signals, analysis["signals"], doc["text"], doc["text"])
    assert len(signals.matches) == 10 and signals.missed == [f"L{i}" for i in range(11, 25)]
    assert signals.extra == ["L11"]
    assert "10 of 24 reference signals found (recall 42%, precision 91%" in signals.describe()
    clarity = compare_clarity(result.scores, analysis["scores"])
    assert clarity.wrong_side == ["C2"]
    assert clarity.unscored == [] , "C25 got a placeholder, so it is scored (at 0.5)"
    assert any(cid == "C25" and live == 0.5 for cid, live, _ in clarity.pairs)


def test_prompt_lists_claims_and_structure_without_the_document_itself():
    doc = document()
    text = doc["text"]
    claims = [claim("C1", text, "net-zero business by 2050", type="commitment", paragraph="P1", prominence=1.0)]
    listing = claims_listing(claims)
    assert listing == 'C1 | commitment | company | P1 | prominence 1.0 | "net-zero business by 2050"'
    structure = structure_summary(doc)
    assert structure.splitlines()[0] == "H1 Climate"
    assert any(line.startswith("P1: ") and "words" in line for line in structure.splitlines())
    assert "H2 Progress" in structure
    prompt = task_prompt(claims, doc)
    assert prompt.startswith("Assess how the claims are worded") and "<claims>" in prompt and "<structure>" in prompt
    assert "Our target is to become" not in prompt, "the document travels in the cached system prefix, not the task"
    assert "<review>" not in prompt
    batched = task_prompt(claims, doc, batch=claims[:1])
    assert "<review>\nIn this call, mark and score only these claims: C1." in batched
    page = document_prompt(claims, doc)
    assert page.startswith("Assess how the page as a whole") and "<claims>" in page and "<structure>" in page


def test_a_repeated_mark_on_the_same_words_is_folded():
    doc = document()
    text = doc["text"]
    c1 = claim("C1", text, "helping our customers to use cleaner energy")
    assembler = Assembler(doc, [c1])
    first = assembler.add_signal(FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="a", strength=0.5))
    again = assembler.add_signal(FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="b", strength=0.6))
    other_kind = assembler.add_signal(FoundSignal(level="claim", kind="weak_verb", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="c", strength=0.4))
    assert first is not None and again is None and other_kind is not None
    assert assembler.folded == 1 and "1 repeated marks folded" in assembler.finish().notes[0]


def usage() -> Usage:
    return Usage(model="fake", input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=0, stop_reason="end_turn", request_id=None, seconds=0.5)


class StreamingLlm:
    """A stand-in for auditor.llm.Llm.extract_streaming: every claim-level call hands over the
    same review's elements one by one (some of them, so the catch-up path is exercised too) and
    returns the whole; the page-level call does the same with `document`."""

    def __init__(self, review: LanguageReview, hand_over: int, document: DocumentSignals | None = None) -> None:
        self.review = review
        self.document = document or DocumentSignals(signals=[])
        self.hand_over = hand_over
        self.calls: list[dict] = []

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if output is DocumentSignals:
            for found in self.document.signals[: self.hand_over]:
                await on_element("signals", found.model_dump())
            return self.document, usage()
        for found in self.review.signals[: self.hand_over]:
            await on_element("signals", found.model_dump())
        for item in self.review.clarity[: self.hand_over]:
            await on_element("clarity", item.model_dump())
        await on_element("something_else", {"ignored": True})
        return self.review, usage()


def test_review_language_emits_while_streaming_and_catches_up_the_rest():
    doc = document()
    text = doc["text"]
    claims = [claim("C1", text, "helping our customers to use cleaner energy"), claim("C2", text, "well below the target")]
    review = LanguageReview(
        signals=[
            FoundSignal(level="claim", kind="hedge", polarity="flag", quotes=["helping"], claim_ids=["C1"], note="a", strength=0.5),
            FoundSignal(level="claim", kind="intensifier", polarity="benign", quotes=["well below"], claim_ids=["C2"], note="b", strength=0.1),
        ],
        clarity=[ClarityScore(claim_id="C1", score=0.6, confidence=0.8, basis="a"), ClarityScore(claim_id="C2", score=0.2, confidence=0.9, basis="b")],
    )
    page = DocumentSignals(signals=[FoundSignal(level="document", kind="register", polarity="benign", quotes=["ignored"], claim_ids=[], note="Plain.", strength=0.1)])
    llm = StreamingLlm(review, hand_over=1, document=page)
    events, emit = emitted()
    result: LanguageResult = asyncio.run(review_language(doc, claims, emit=emit, llm=llm))
    assert [t for t, _ in events] == ["language.signal", "dimension.scored", "language.signal", "dimension.scored", "language.signal"]
    assert [p.get("signal", p.get("score"))["id" if "signal" in p else "claim_id"] for _, p in events] == ["L1", "C1", "L2", "C2", "L3"]
    assert events[-1][1]["signal"]["level"] == "document" and events[-1][1]["signal"]["spans"] == []
    assert len(result.signals) == 3 and [s["claim_id"] for s in result.scores] == ["C1", "C2"]
    assert result.notes[0].startswith("Claude returned 3 signals and 2 clarity scores over 2 parallel calls (1 of up to 9 claims each, 1 for the page) (fake: 2 in + 6 read from cache, 4 out, ")
    assert result.usage is not None and result.usage.output_tokens == 4
    batch_call, page_call = llm.calls
    assert batch_call["cache"] is True and batch_call["output"] is LanguageReview and batch_call["system"].startswith("You are the reading stage")
    assert batch_call["prompt"].startswith("Assess how the claims are worded") and "only these claims: C1, C2." in batch_call["prompt"]
    assert page_call["output"] is DocumentSignals and page_call["prompt"].startswith("Assess how the page as a whole")


def test_claims_go_out_in_parallel_batches_with_one_score_each(monkeypatch):
    monkeypatch.setattr(language_module, "BATCH_SIZE", 3)
    doc = document()
    text = doc["text"]
    quotes = ["Our target", "net-zero business", "by 2050", "helping our customers", "cleaner energy", "helping suppliers", "around 70% lower"]
    claims = [claim(f"C{i + 1}", text, q) for i, q in enumerate(quotes)]
    review = LanguageReview(
        signals=[FoundSignal(level="claim", kind="comparative_without_baseline", polarity="flag", quotes=["cleaner"], claim_ids=["C5"], note="x", strength=0.8)],
        clarity=[ClarityScore(claim_id=c["id"], score=0.3, confidence=0.8, basis="b") for c in claims],
    )
    llm = StreamingLlm(review, hand_over=99)
    events, emit = emitted()
    result = asyncio.run(review_language(doc, claims, emit=emit, llm=llm))
    assert len(llm.calls) == 4, "three batches of three, three and one claim, plus the page"
    batches = [c["prompt"].split("only these claims: ")[1].split(".")[0] for c in llm.calls if c["output"] is LanguageReview]
    assert batches == ["C1, C2, C3", "C4, C5, C6", "C7"]
    assert [s["claim_id"] for s in result.scores] == [f"C{i}" for i in range(1, 8)], "each batch keeps the scores of its own claims; nothing scored twice"
    assert len(result.signals) == 1, "the same mark from three batches is one signal"
    assert sum(1 for t, _ in events if t == "dimension.scored") == 7
    assert "over 4 parallel calls (3 of up to 3 claims each, 1 for the page)" in result.notes[0]
    assert "14 scores for claims outside their call ignored" in result.notes[0]
    assert "2 repeated marks folded" in result.notes[-1] or "2 repeated marks folded" in result.notes[1]


def test_review_language_with_no_claims_makes_no_call():
    class NeverCalled:
        async def extract_streaming(self, *a, **k):
            raise AssertionError("must not be called")

    result = asyncio.run(review_language(document(), [], emit=lambda *_: None, llm=NeverCalled()))
    assert result.signals == [] and result.scores == [] and "No claims" in result.notes[0]
