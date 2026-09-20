"""Self-consistency: the company's own other words and its own earlier pages become evidence,
every quote is checked against the page or the capture it came from and never displayed unless
it is found, an archived target that was weakened or dropped is marked as greenrinsing, and
Consistency is scored from both axes. No test calls the model and no test touches the network."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO, data_text

from auditor.consistency import (
    ARCHIVE_MIN_WORDS,
    PLACEHOLDER_BASIS,
    PLACEHOLDER_CONFIDENCE,
    PLACEHOLDER_SCORE,
    ArchivedVersion,
    Assessment,
    Assessments,
    Bearing,
    Change,
    Changes,
    ConsistencyResult,
    Page,
    Statement,
    Statements,
    apply_consistency,
    archived_versions,
    check_quote,
    compare_consistency,
    consistency,
    contradicted_claims,
    load_page,
    read_capture,
    spread,
)
from auditor.ingest.fetch import FetchError, Fetched, Snapshot
from auditor.language import reanchored_claims
from auditor.llm import LlmError, Usage

REPORT = "https://www.acme.example/annual-report-2025.html"
FAQ = "https://www.acme.example/climate-faq.html"
PAGES = {
    REPORT: "Our business plan cannot reflect our 2050 net-zero target, as it is outside the planning period.",
    FAQ: "The target covers our operated assets only.",
}


def document(text: str = "We are carbon neutral. Our target is net zero by 2050.") -> dict:
    return {
        "id": "d", "title": "Climate", "company": {"name": "Acme"}, "text_type": "policy",
        "source": {"url": "https://www.acme.example/climate", "retrieved": "2026-09-20"},
        "text": text, "word_count": 11, "regions": [],
    }


def claim(cid: str, text: str, words: str) -> dict:
    start = text.index(words)
    return {"id": cid, "spans": [{"text": words, "start": start, "end": start + len(words)}],
            "type": "factual", "scope": "company", "attribute": words, "paragraph": "P1", "prominence": 1.0}


def two_claims():
    doc = document()
    text = doc["text"]
    return doc, [claim("C1", text, "We are carbon neutral"), claim("C2", text, "Our target is net zero by 2050")]


def fetch_text(url: str) -> str:
    if url not in PAGES:
        raise ValueError(f"{url} answered HTTP 404")
    return PAGES[url]


def emitted():
    events: list[tuple[str, dict]] = []
    return events, lambda type_, payload: events.append((type_, payload))


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def statement(**kwargs) -> Statement:
    base = dict(
        kind="filing", independence="assured_filing", name="Acme Annual Report 2025", publisher="Acme plc",
        date="2026-03", locator="p. 7", url=REPORT,
        quote="Our business plan cannot reflect our 2050 net-zero target, as it is outside the planning period.",
        bears_on=[Bearing(claim_id="C2", relation="contradicts")], note="",
    )
    return Statement(**{**base, **kwargs})


def version(stamp: str = "20240301120000", text: str = "In 2024 we said: we will cut emissions by 45% by 2035.") -> ArchivedVersion:
    return ArchivedVersion(stamp, f"https://web.archive.org/web/{stamp}/https://www.acme.example/climate", text, len(text.split()))


def change(**kwargs) -> Change:
    base = dict(claim_ids=["C2"], then_quote="we will cut emissions by 45% by 2035", change="dropped",
                note="The page promised 45% by 2035 in 2024 and no longer mentions it.")
    return Change(**{**base, **kwargs})


# ----------------------------------------------------------------------------- the company's other words


def test_a_verified_statement_becomes_tiered_evidence_on_the_consistency_stage():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[statement()]), {}, Assessments(assessments=[]), doc, claims, fetch_text=fetch_text,
    )
    item = result.statements[0]
    assert item["id"] == "S1" and item["kind"] == "filing" and item["stage"] == "consistency"
    assert item["tier"] == 2, "an assured filing is tier 2 because a third party signed it"
    assert item["verified"] is True and item["verification"] == "fetched_exact"
    assert item["quote"].startswith("Our business plan cannot reflect")
    assert item["links"] == [{"target": "C2", "relation": "contradicts"}]
    assert item["source"] == {"name": "Acme Annual Report 2025", "publisher": "Acme plc", "date": "2026-03", "locator": "p. 7"}
    assert item["ext"] == {"independence": "assured_filing", "axis": "elsewhere"}
    assert result.contradictions == [item], "this is what the stage exists to find"


def test_an_unverified_quote_is_kept_by_name_but_never_displayed():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[statement(quote="A sentence the filing does not contain.")]),
        {}, Assessments(assessments=[]), doc, claims, fetch_text=fetch_text,
    )
    item = result.statements[0]
    assert item["verified"] is False and item["verification"] == "unverified"
    assert "quote" not in item, "an unverified quote is never displayed (design-doc D5)"
    assert item["source"]["name"] == "Acme Annual Report 2025", "the source is still listed by name"
    assert "Quote not found" in item["note"] and result.unverified == [REPORT]
    assert result.contradictions == [], "an unverified contradiction is not a contradiction"


def test_a_page_that_cannot_be_read_leaves_the_item_unverified_rather_than_failing():
    page = load_page("https://nowhere.example/x", fetch_text)
    assert page.error is not None and page.text is None
    verified, why = check_quote(page, "anything")
    assert verified is False and "could not be read from here" in why and "Open the link by hand" in why
    assert check_quote(Page("u", text="the quote is here"), "The Quote  Is Here")[0] is True


def test_the_company_cannot_substantiate_its_own_claim_so_tier_five_supports_becomes_context():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[statement(
            independence="company", kind="company_page", url=FAQ, name="Acme climate FAQ",
            quote="The target covers our operated assets only.",
            bears_on=[Bearing(claim_id="C1", relation="supports"), Bearing(claim_id="C2", relation="contradicts_framing")],
        )]),
        {}, Assessments(assessments=[]), doc, claims, fetch_text=fetch_text,
    )
    item = result.statements[0]
    assert item["tier"] == 5
    assert item["links"] == [{"target": "C1", "relation": "context"}, {"target": "C2", "relation": "contradicts_framing"}]
    assert "context, not substantiation" in item["note"]
    assert "1 tier-5 'supports' links made 'context'" in result.notes[0]


def test_an_assured_filing_may_still_support_because_a_third_party_signed_it():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[statement(bears_on=[Bearing(claim_id="C1", relation="supports")])]),
        {}, Assessments(assessments=[]), doc, claims, fetch_text=fetch_text,
    )
    assert result.statements[0]["links"] == [{"target": "C1", "relation": "supports"}]


def test_a_source_an_earlier_stage_already_showed_is_not_shown_twice():
    doc, claims = two_claims()
    prior = [{"id": "V1", "url": REPORT, "quote": PAGES[REPORT], "tier": 2, "kind": "filing",
              "source": {"name": "Acme Annual Report 2025"}, "links": [{"target": "C1", "relation": "supports"}], "stage": "verify"}]
    result = apply_consistency(
        Statements(statements=[statement(), statement(url=FAQ, quote="The target covers our operated assets only.", independence="company", kind="company_page")]),
        {}, Assessments(assessments=[]), doc, claims, prior_evidence=prior, fetch_text=fetch_text,
    )
    assert [e["url"] for e in result.statements] == [FAQ], "step 14 already put the annual report in front of the reader"
    assert "1 already on the table from an earlier stage" in result.notes[0]
    assert result.statements[0]["id"] == "S1", "the ids are this stage's own, and skip the prior ones"


def test_a_statement_about_no_claim_this_stage_knows_is_dropped():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[statement(bears_on=[Bearing(claim_id="C99", relation="contradicts")])]),
        {}, Assessments(assessments=[]), doc, claims, fetch_text=fetch_text,
    )
    assert result.statements == [] and "1 unknown claim ids ignored" in result.notes[0]


# ----------------------------------------------------------------------------- the page over time


def test_an_archived_change_is_checked_against_the_capture_it_was_read_from():
    doc, claims = two_claims()
    old = version()
    result = apply_consistency(
        Statements(statements=[]), {old.stamp: Changes(changes=[change()])}, Assessments(assessments=[]),
        doc, claims, versions=[old], fetch_text=fetch_text,
    )
    item = result.archived[0]
    assert item["id"] == "A1" and item["kind"] == "archive" and item["stage"] == "consistency"
    assert item["tier"] == 5, "an archived version of the company's own page is still the company's own material"
    assert item["verified"] is True and item["verification"] == "fetched_exact"
    assert item["quote"] == "we will cut emissions by 45% by 2035"
    assert item["url"] == old.url and item["source"]["date"] == "2024-03-01" and item["source"]["locator"] == "capture 20240301120000"
    assert item["links"] == [{"target": "C2", "relation": "contradicts_framing"}], "a dropped target contradicts the framing, not the words"
    assert item["ext"]["change"] == "dropped" and item["ext"]["greenrinsing"] is True
    assert result.greenrinsing == [item]


def test_a_quote_the_capture_does_not_contain_is_not_displayed():
    doc, claims = two_claims()
    old = version()
    result = apply_consistency(
        Statements(statements=[]), {old.stamp: Changes(changes=[change(then_quote="we promised 90% by 2030")])},
        Assessments(assessments=[]), doc, claims, versions=[old], fetch_text=fetch_text,
    )
    item = result.archived[0]
    assert item["verified"] is False and "quote" not in item
    assert "not found in the capture of 2024-03-01" in item["note"]
    assert any("Not in the capture, so not shown: 2024-03-01" in n for n in result.notes)


@pytest.mark.parametrize(
    "kind, relation, rinsing",
    [("weakened", "contradicts_framing", True), ("dropped", "contradicts_framing", True), ("delayed", "contradicts_framing", True),
     ("scope_narrowed", "contradicts_framing", False), ("restated", "contradicts_framing", False), ("softened", "contradicts_framing", False),
     ("strengthened", "context", False), ("unchanged", "context", False)],
)
def test_what_changed_decides_the_relation_and_whether_it_is_greenrinsing(kind, relation, rinsing):
    doc, claims = two_claims()
    old = version()
    result = apply_consistency(
        Statements(statements=[]), {old.stamp: Changes(changes=[change(change=kind)])}, Assessments(assessments=[]),
        doc, claims, versions=[old], fetch_text=fetch_text,
    )
    item = result.archived[0]
    assert item["links"][0]["relation"] == relation
    assert item["ext"].get("greenrinsing", False) is rinsing, "greenrinsing is a target changed before it was met"


def test_changes_for_a_capture_that_was_not_read_are_dropped():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[]), {"20200101000000": Changes(changes=[change()])}, Assessments(assessments=[]),
        doc, claims, versions=[version()], fetch_text=fetch_text,
    )
    assert result.archived == []


# ----------------------------------------------------------------------------- choosing and reading captures


def snapshot(stamp: str) -> Snapshot:
    return Snapshot(stamp, f"https://web.archive.org/web/{stamp}id_/https://www.acme.example/climate", stamp[:8])


def test_captures_are_spread_over_time_not_over_the_list():
    """The archive captures a page in bursts. Ten captures in one January plus one in June and
    one in December is a year of history; spread over the list it would be read as three steps
    through January and June would go unexamined."""
    burst = [snapshot(f"202401{day:02d}000000") for day in range(1, 11)]
    history = [*burst, snapshot("20240615000000"), snapshot("20241231000000")]
    assert [s.date for s in spread(history, 3)] == ["2024-01-01", "2024-06-15", "2024-12-31"]
    assert [history[i].date for i in (0, len(history) // 2, -1)] == ["2024-01-01", "2024-01-07", "2024-12-31"], \
        "which is what spreading over the list would have picked"
    assert spread([], 3) == [] and spread(burst, 0) == []
    assert spread(burst[:2], 5) == burst[:2], "fewer captures than asked for is all of them"


def test_captures_too_close_to_the_page_under_analysis_are_skipped():
    old, recent = snapshot("20240101000000"), snapshot("20260915000000")
    assert [s.date for s in spread([old, recent], 2, before="20260920000000")] == ["2024-01-01"]
    assert [s.date for s in spread([recent], 2, before="20260920000000")] == ["2026-09-15"], \
        "a page the archive has only just noticed is read anyway"


def page_html(body: str) -> str:
    return f"<html><head><title>Climate</title></head><body><main><h1>Climate</h1><p>{body}</p></main></body></html>"


LONG = " ".join(["Our target is to cut emissions by 45% by 2035 against a 2016 baseline."] * 12)


class FakeArchive:
    """The Wayback Machine as far as these tests are concerned: a table of URL -> body, and the
    redirect to the capture it actually holds."""

    def __init__(self, bodies: dict[str, tuple[str, str]]) -> None:
        self.bodies = bodies  # requested url -> (final url, body)
        self.calls: list[str] = []

    def __call__(self, url: str) -> Fetched:
        self.calls.append(url)
        if url not in self.bodies:
            raise FetchError(f"{url} answered HTTP 404", status=404)
        final, body = self.bodies[url]
        kind = "application/json" if body.lstrip().startswith("{") else "text/html; charset=utf-8"
        return Fetched(final, 200, kind, body.encode("utf-8"), "utf-8")


def test_a_capture_is_read_into_canonical_text_with_the_stamp_the_archive_served():
    snap = snapshot("20240301120000")
    archive = FakeArchive({snap.url: ("https://web.archive.org/web/20240228090000id_/https://www.acme.example/climate", page_html(LONG))})
    read, why = read_capture(snap, "https://www.acme.example/climate", fetcher=archive)
    assert why == "" and read is not None
    assert read.stamp == "20240228090000" and read.date == "2024-02-28", "the date is the one the archive served, not the one asked for"
    assert read.url == "https://web.archive.org/web/20240228090000/https://www.acme.example/climate"
    assert "45% by 2035" in read.text and read.words > ARCHIVE_MIN_WORDS and read.via_model is False


def test_a_javascript_shell_is_read_from_the_content_model_captured_nearest_it():
    """What the archive holds for most modern corporate pages is the shell, and the live
    ingester already answers that with the page's content model. The real Shell model stands
    in for the archived one, so this walks the same adapter production would."""
    snap = snapshot("20240301120000")
    archive = FakeArchive({
        snap.url: (snap.url, page_html("Loading.")),
        "https://web.archive.org/web/20240301120000id_/https://www.acme.example/climate.model.json":
            ("https://web.archive.org/web/20240305000000id_/https://www.acme.example/climate.model.json", data_text("shell-climate.model.json")),
    })
    read, why = read_capture(snap, "https://www.acme.example/climate", fetcher=archive)
    assert read is not None, why
    assert read.via_model is True and read.words > ARCHIVE_MIN_WORDS
    assert read.stamp == "20240305000000", "The model capture's own date, not the shell capture's"
    assert read.date == "2024-03-05" and "net-zero emissions energy business by 2050" in read.text


def test_a_capture_that_is_a_shell_with_no_archived_model_is_reported_not_guessed():
    snap = snapshot("20240301120000")
    archive = FakeArchive({snap.url: (snap.url, page_html("Loading."))})
    read, why = read_capture(snap, "https://www.acme.example/climate", fetcher=archive)
    assert read is None and "JavaScript shell" in why and "content model" in why


def test_a_capture_too_short_to_compare_is_refused():
    """Past the JavaScript-shell threshold but still too little to be a version of the page:
    a consent wall, a holding page, an error the archive captured as a 200."""
    snap = snapshot("20240301120000")
    short = " ".join(["We use cookies on this site to improve your experience."] * 8)
    archive = FakeArchive({snap.url: (snap.url, page_html(short))})
    read, why = read_capture(snap, "https://www.acme.example/climate", fetcher=archive)
    assert 60 <= len(short.split()) < ARCHIVE_MIN_WORDS, "not a JavaScript shell; just not a document"
    assert read is None and "words; too little to compare" in why


def test_the_archive_axis_says_what_it_found_and_never_raises():
    doc = document()
    found, notes = archived_versions(doc, history=lambda url: [])
    assert found == [] and "holds no usable capture" in notes[0]
    found, notes = archived_versions({"source": {}}, history=lambda url: [])
    assert found == [] and "No URL for this document" in notes[0]

    snaps = [snapshot("20240101000000"), snapshot("20250101000000")]
    archive = FakeArchive({snaps[0].url: (snaps[0].url, page_html(LONG))})
    found, notes = archived_versions(doc, count=2, history=lambda url: snaps, fetcher=archive)
    assert [v.date for v in found] == ["2024-01-01"]
    assert any("holds 2 distinct captures" in n for n in notes)
    assert any("could not be fetched" in n for n in notes) and any("Read 1 earlier versions" in n for n in notes)


def test_two_captures_of_the_shell_that_resolve_to_one_archived_model_are_read_once():
    doc = document()
    snaps = [snapshot("20240101000000"), snapshot("20250101000000")]
    same = "https://web.archive.org/web/20240601000000id_/https://www.acme.example/climate"
    archive = FakeArchive({s.url: (same, page_html(LONG)) for s in snaps})
    found, notes = archived_versions(doc, count=2, history=lambda url: snaps, fetcher=archive)
    assert [v.date for v in found] == ["2024-06-01"]
    assert any("resolves to the same archived content" in n for n in notes)
    assert any("is a JavaScript shell; the nearest archived content" in n for n in notes), \
        "the reader is told the date moved, so a 2024 capture is never read as 2025 content"


# ----------------------------------------------------------------------------- scores


def test_every_claim_gets_exactly_one_consistency_score_and_a_skipped_one_gets_a_low_placeholder():
    doc, claims = two_claims()
    events, emit = emitted()
    result = apply_consistency(
        Statements(statements=[statement()]), {},
        Assessments(assessments=[
            Assessment(claim_id="C1", score=0.8, confidence=0.9, basis="The filing says otherwise.", evidence_ids=["S1", "nope"], gap="Say so on the page."),
            Assessment(claim_id="C1", score=0.1, confidence=0.1, basis="twice"),
            Assessment(claim_id="C99", score=0.1, confidence=0.1, basis="unknown"),
        ]),
        doc, claims, emit=emit, fetch_text=fetch_text,
    )
    scored = [s["score"] for s in result.scores]
    assert [s["claim_id"] for s in result.scores] == ["C1", "C2"] and len(scored) == 2
    first = result.scores[0]
    assert first["dimension"] == "consistency" and first["stage"] == "consistency"
    assert first["evidence_ids"] == ["S1"] and first["ext"] == {"gap": "Say so on the page."}

    placeholder = result.scores[1]
    assert placeholder["score"] == PLACEHOLDER_SCORE == 0.3 and placeholder["confidence"] == PLACEHOLDER_CONFIDENCE == 0.2
    assert placeholder["basis"] == PLACEHOLDER_BASIS and result.placeholders == ["C2"]
    assert placeholder["score"] <= 0.5, (
        "nothing found on this dimension means no contradiction was found, so a placeholder must never be "
        "the thing that pushes a claim's likelihood (the weakest link) above neutral"
    )
    assert "1 unknown evidence ids ignored" in result.notes[0] and "1 repeated assessments ignored" in result.notes[0]
    assert [t for t, _ in events] == ["evidence.added", "dimension.scored", "dimension.scored"]


def test_scores_are_clamped_and_a_basis_is_never_empty():
    doc, claims = two_claims()
    result = apply_consistency(
        Statements(statements=[]), {},
        Assessments(assessments=[Assessment(claim_id="C1", score=3.0, confidence=-1.0, basis="   ")]),
        doc, claims, fetch_text=fetch_text,
    )
    assert result.scores[0]["score"] == 1.0 and result.scores[0]["confidence"] == 0.0
    assert result.scores[0]["basis"] == "No basis given."


# ----------------------------------------------------------------------------- the live stage


class StreamingLlm:
    """A stand-in for auditor.llm.Llm.extract_streaming: hands over some of each call's items
    one by one (so the catch-up path is exercised too) and returns the whole. The archive call
    is answered by the capture date in its prompt, since there is one call per capture."""

    def __init__(self, statements: Statements, changes: dict[str, Changes], assessments: Assessments,
                 hand_over: int = 1, *, fail: type | None = None) -> None:
        self.statements, self.changes, self.assessments = statements, changes, assessments
        self.hand_over = hand_over
        self.fail = fail
        self.calls: list[dict] = []

    async def extract_streaming(self, prompt, output, *, on_element, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if self.fail is output:
            raise LlmError("the model's stream went quiet")
        if output is Changes:
            captured = prompt.split('captured="')[1][:10]
            whole, key = self.changes.get(captured, Changes(changes=[])), "changes"
        elif output is Statements:
            whole, key = self.statements, "statements"
        else:
            whole, key = self.assessments, "assessments"
        items = list(getattr(whole, key))
        if "<review>" in prompt:
            wanted = {x.strip() for x in prompt.split("these claims")[-1].split(":")[1].split(".")[0].split(",")}

            def mine(item):
                ids = {b.claim_id for b in item.bears_on} if hasattr(item, "bears_on") else \
                    set(getattr(item, "claim_ids", [])) or {item.claim_id}
                return bool(ids & wanted)

            items = [i for i in items if mine(i)]
        for item in items[: self.hand_over]:
            await on_element(key, item.model_dump())
        await on_element("something_else", {"ignored": True})
        return type(whole)(**{key: items}), usage()


def archive_of(*versions: ArchivedVersion):
    def history(url: str):
        return [snapshot(v.stamp) for v in versions]
    fetcher = FakeArchive({snapshot(v.stamp).url: (snapshot(v.stamp).url, page_html(v.text)) for v in versions})
    return history, fetcher


def test_the_stage_searches_and_reads_the_archive_then_scores_from_both(monkeypatch):
    from auditor import consistency as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims = two_claims()
    old = version("20240301120000", LONG)
    history, fetcher = archive_of(old)
    llm = StreamingLlm(
        Statements(statements=[statement()]),
        {"2024-03-01": Changes(changes=[change(then_quote="cut emissions by 45% by 2035", change="weakened")])},
        Assessments(assessments=[
            Assessment(claim_id="C1", score=0.3, confidence=0.5, basis="Nothing found either way."),
            Assessment(claim_id="C2", score=0.8, confidence=0.9, basis="The filing says otherwise.", evidence_ids=["S1", "A1"]),
        ]),
    )
    events, emit = emitted()
    result = asyncio.run(consistency(doc, claims, emit=emit, llm=llm, fetch_text=fetch_text, history=history, fetcher=fetcher, snapshots=1))

    types = [t for t, _ in events]
    assert types.count("evidence.added") == 2 and types.count("dimension.scored") == 2
    assert max(i for i, t in enumerate(types) if t == "evidence.added") < min(i for i, t in enumerate(types) if t == "dimension.scored"), \
        "every item exists before a score can cite it (contract §2, rule 3)"
    assert {e["evidence"]["id"] for t, e in events if t == "evidence.added"} == {"S1", "A1"}
    assert result.scores[1]["evidence_ids"] == ["S1", "A1"], "the score cites both axes"

    searches = [c for c in llm.calls if c["output"] is Statements]
    assert len(searches) == 2, "one call per claim at BATCH_SIZE 1, in parallel"
    assert [t["name"] for t in searches[0]["tools"]] == ["web_search", "web_fetch"]
    assert searches[0]["cache"] is True and searches[0]["system"].startswith("You are")
    archive_calls = [c for c in llm.calls if c["output"] is Changes]
    assert len(archive_calls) == 1 and "tools" not in archive_calls[0], \
        "the capture is already in the prompt, so the archive call needs no search"
    assert "tools" not in [c for c in llm.calls if c["output"] is Assessments][0]
    assert "compared 1 archived versions of the page" in result.notes[0]
    assert result.usage is not None and result.usage.input_tokens == 40, "two searches, one capture, one scoring call"


def test_an_archive_with_nothing_in_it_still_leaves_the_search_and_the_scores():
    doc, claims = two_claims()
    llm = StreamingLlm(Statements(statements=[statement()]), {}, Assessments(assessments=[]))
    result = asyncio.run(consistency(doc, claims, llm=llm, fetch_text=fetch_text, history=lambda url: []))
    assert len(result.statements) == 1 and result.archived == []
    assert [s["claim_id"] for s in result.scores] == ["C1", "C2"] and result.placeholders == ["C1", "C2"]
    assert "with no archived version to compare" in result.notes[0]
    assert any("holds no usable capture" in n for n in result.notes)


def test_one_failed_search_does_not_lose_the_other_batches(monkeypatch):
    from auditor import consistency as module

    monkeypatch.setattr(module, "BATCH_SIZE", 1)
    doc, claims = two_claims()
    llm = StreamingLlm(Statements(statements=[]), {}, Assessments(assessments=[]), fail=Statements)
    result = asyncio.run(consistency(doc, claims, llm=llm, fetch_text=fetch_text, history=lambda url: []))
    assert [s["dimension"] for s in result.scores] == ["consistency", "consistency"], "the stage still owes the verdict its dimension"
    assert result.placeholders == ["C1", "C2"]
    assert sum(n.startswith("Failed: the company's other words on") for n in result.notes) == 2


def test_a_failed_archive_comparison_does_not_lose_the_search():
    doc, claims = two_claims()
    old = version("20240301120000", LONG)
    history, fetcher = archive_of(old)
    llm = StreamingLlm(Statements(statements=[statement()]), {}, Assessments(assessments=[]), fail=Changes)
    result = asyncio.run(consistency(doc, claims, llm=llm, fetch_text=fetch_text, history=history, fetcher=fetcher, snapshots=1))
    assert len(result.statements) == 1
    assert any(n.startswith("Failed: the capture of 2024-03-01") for n in result.notes)


def test_a_failed_scoring_call_fails_the_stage():
    doc, claims = two_claims()
    llm = StreamingLlm(Statements(statements=[statement()]), {}, Assessments(assessments=[]), fail=Assessments)
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(consistency(doc, claims, llm=llm, fetch_text=fetch_text, history=lambda url: []))
    assert asyncio.run(consistency(doc, [], llm=llm, fetch_text=fetch_text)).notes == ["No claims to check for consistency."]


# ----------------------------------------------------------------------------- against the reference


def test_the_comparison_reports_which_claims_the_company_contradicts_itself_on():
    reference = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))["evidence"]
    assert contradicted_claims(reference) == ["C1", "C11", "C13", "C17", "C22", "C7"], \
        "the golden reference's self-consistency findings"
    live = [
        {"id": "S1", "url": "https://www.sec.gov/Archives/x.htm", "verified": True, "stage": "consistency",
         "links": [{"target": "C1", "relation": "contradicts"}]},
        {"id": "A1", "url": "https://web.archive.org/web/20250101000000/https://www.shell.com/sustainability/climate.html",
         "verified": True, "stage": "consistency", "links": [{"target": "C11", "relation": "contradicts_framing"}]},
    ]
    comparison = compare_consistency(live, reference)
    assert comparison.agreed == ["C1", "C11"] and comparison.missed == ["C13", "C17", "C22", "C7"]
    assert "sec.gov" in comparison.found_hosts
    assert "shell.com" in comparison.found_hosts, "an archived capture matches the page it is a copy of, not archive.org"
    assert comparison.live_sources == 2 and comparison.verified == 2
    assert "2 the same (C1, C11)" in comparison.describe() and "4 missed" in comparison.describe()


def test_the_reference_scores_survive_a_round_trip_through_the_real_assembly():
    """The fixture's consistency scores, run through the real assembly: a perfect evaluator
    reproduces the reference exactly."""
    from auditor.verify import compare_scores

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    doc = analysis["document"]
    claims = reanchored_claims(analysis["claims"], doc["text"], doc["text"])
    assessments = Assessments(assessments=[
        Assessment(claim_id=s["claim_id"], score=s["score"], confidence=s["confidence"], basis=s["basis"])
        for s in analysis["scores"] if s["dimension"] == "consistency"
    ])
    result = apply_consistency(Statements(statements=[]), {}, assessments, doc, claims, fetch_text=fetch_text)
    comparison = compare_scores(result.scores, analysis["scores"], "consistency")
    assert comparison.mean_abs_error == 0 and comparison.wrong_band() == [] and comparison.unscored == []
    assert result.placeholders == [], "the reference scores every claim"


def test_the_result_sorts_its_evidence_into_the_two_axes():
    empty = ConsistencyResult([], [])
    assert empty.statements == [] and empty.archived == [] and empty.contradictions == [] and empty.greenrinsing == []


def test_the_golden_consistency_reproduces_the_reference_scores_and_sources():
    """The fixture's consistency-stage sources and its consistency scores, run through the real
    assembly: a perfect evaluator reproduces the reference exactly, every quote the hand
    analysis recorded is found on the page it was recorded from, and the claims the company
    contradicts itself on are the ones the golden reference found."""
    from conftest import golden_consistency

    from auditor.verify import compare_scores

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    doc = analysis["document"]
    claims = reanchored_claims(analysis["claims"], doc["text"], doc["text"])
    statements, assessments, mapping, pages = golden_consistency()
    result = apply_consistency(statements, {}, assessments, doc, claims, fetch_text=lambda url: pages[url])

    assert len(result.statements) == 6 and all(e["verified"] for e in result.statements)
    assert sorted({e["tier"] for e in result.statements}) == [2, 5], "an assured filing and the company's own material"
    assert result.placeholders == [] and result.archived == []
    comparison = compare_scores(result.scores, analysis["scores"], "consistency")
    assert comparison.mean_abs_error == 0 and comparison.wrong_band() == [] and comparison.unscored == []
    assert contradicted_claims(result.evidence) == ["C1", "C11", "C13", "C17", "C22", "C7"]
    against = compare_consistency(result.evidence, analysis["evidence"])
    assert against.agreed == contradicted_claims(analysis["evidence"]) and against.missed == []
    assert mapping["E1"] in {e["id"] for e in result.statements}


def test_the_archive_notes_are_told_in_order():
    """They are a sequence — what the archive held, which captures were read, what each cost —
    so they must not come out backwards."""
    doc, claims = two_claims()
    snaps = [snapshot("20240101000000"), snapshot("20250101000000")]
    archive = FakeArchive({snaps[0].url: (snaps[0].url, page_html(LONG))})
    llm = StreamingLlm(Statements(statements=[]), {}, Assessments(assessments=[]))
    result = asyncio.run(consistency(
        doc, claims, llm=llm, fetch_text=fetch_text, history=lambda url: snaps, fetcher=archive, snapshots=2,
    ))
    archive_notes = [n for n in result.notes if "captures of this page" in n or "could not be fetched" in n or "Read 1 earlier versions" in n]
    assert len(archive_notes) == 3
    assert "holds 2 distinct captures" in archive_notes[0]
    assert "could not be fetched" in archive_notes[1]
    assert "Read 1 earlier versions" in archive_notes[2]


def test_what_the_stage_emits_validates_against_the_contract():
    """The archive axis is the only place `kind: archive` is produced, and the pipeline's own
    contract check never sees one (the golden reference was read from the live page), so it is
    checked here against contract/schema.json directly."""
    import jsonschema

    schema = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))
    doc, claims = two_claims()
    old = version()
    result = apply_consistency(
        Statements(statements=[statement()]), {old.stamp: Changes(changes=[change()])},
        Assessments(assessments=[
            Assessment(claim_id="C1", score=0.8, confidence=0.9, basis="Dropped target.", evidence_ids=["A1"], gap="Say so."),
            Assessment(claim_id="C2", score=0.2, confidence=0.7, basis="The filing agrees.", evidence_ids=["S1"]),
        ]),
        doc, claims, versions=[old], fetch_text=fetch_text,
    )
    assert len(result.evidence) == 2 and len(result.scores) == 2
    for seq, item in enumerate(result.evidence, start=1):
        jsonschema.validate({"seq": seq, "t_ms": seq, "type": "evidence.added", "payload": {"evidence": item}}, schema)
    for seq, score in enumerate(result.scores, start=10):
        jsonschema.validate({"seq": seq, "t_ms": seq, "type": "dimension.scored", "payload": {"score": score}}, schema)
