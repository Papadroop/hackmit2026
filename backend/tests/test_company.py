"""Company aggregation: one bad page cannot be buried under bland ones a level up either, the
current page weighs more than an archived one without the record being erased, the trend says
plainly when there is too little of it to call, and the model is asked for the words only. No
test calls Claude."""

from __future__ import annotations

import asyncio
import json

import pytest
from conftest import REPO

from auditor.company import (
    EPSILON,
    HALFLIFE_DAYS,
    MIN_POINTS,
    POWER,
    Record,
    Words,
    aggregate_company,
    build_company,
    company_slug,
    describe_company,
    document_date,
    explain,
    find_company,
    fold_record,
    group_by_company,
    load_records,
    recency,
    write_prompt,
)
from auditor.envelope import Event
from auditor.llm import LlmError, Usage
from auditor.summary import aggregate_rows, Row


PROFILE = ("clarity", "support", "materiality", "consistency", "completeness")


def claim(cid: str, words: str = "a claim", prominence: float = 1.0) -> dict:
    return {"id": cid, "spans": [{"text": words, "start": 0, "end": len(words)}], "type": "factual",
            "scope": "company", "prominence": prominence}


def verdict(cid: str, likelihood: float, category: str = "misleading_by_framing", confidence: float = 0.8) -> dict:
    return {"claim_id": cid, "likelihood": likelihood, "confidence": confidence, "category": category,
            "tags": [], "rationale": f"{cid}."}


def omission(oid: str, score: float = 0.7, confidence: float = 0.9) -> dict:
    return {"id": oid, "topic": f"Topic {oid}", "why_material": "It is material.",
            "complete_text": "It would say this.", "score": score, "confidence": confidence}


def summary(score: float, confidence: float = 0.7, **over) -> dict:
    """A document header of the shape `auditor.summary.aggregate` produces."""
    out = {
        "headline": {"score": score, "confidence": confidence},
        "dimensions": {name: {"score": score, "confidence": confidence} for name in PROFILE},
        "verdict_distribution": {"supported": 0, "unsubstantiated": 0, "misleading_by_framing": 1, "contradicted": 0},
        "top_issues": [], "credit": [], "claim_count": 1, "omission_count": 0,
    }
    out.update(over)
    return out


def page(
    doc_id: str,
    date: str,
    score: float,
    confidence: float = 0.7,
    *,
    company: str = "Shell plc",
    url: str | None = None,
    archive_url: str | None = None,
    claims: list[dict] | None = None,
    verdicts: list[dict] | None = None,
    omissions: list[dict] | None = None,
    header: dict | None = None,
) -> Record:
    source: dict = {"retrieved": date}
    if url:
        source["url"] = url
    if archive_url:
        source["archive_url"] = archive_url
    document = {
        "id": doc_id, "title": f"{company} — {doc_id}", "company": {"name": company},
        "industry": {"label": "Oil & Gas – Integrated"}, "text_type": "web_page", "source": source,
        "text": "A page.", "regions": [],
    }
    header = header if header is not None else summary(score, confidence)
    return Record(
        document=document, summary=header, claims=claims or [], verdicts=verdicts or [],
        omissions=omissions or [], analysis_id=doc_id, origin={"kind": "fixture", "name": doc_id},
    )


def usage() -> Usage:
    return Usage("m", 10, 5, 0, 0, "end_turn", "req", 1.0)


def log(events: list[dict]) -> list[Event]:
    return [Event(seq=i + 1, t_ms=i, type=e["type"], payload=e.get("payload", {})) for i, e in enumerate(events)]


# ----------------------------------------------------------------------------- the arithmetic


def test_one_bad_page_cannot_be_buried_under_bland_ones():
    """The company-level form of the failure the document summary exists to prevent: there, a
    false headline buried under twenty true footnotes; here, one misleading page buried under a
    company's bland ones. This is the property the combination is chosen for."""
    pages = [page("bad", "2026-09-01", 0.9, 0.8)] + [page(f"ok{i}", "2026-09-01", 0.1, 0.8) for i in range(5)]
    view, _ = aggregate_company(pages)
    assert view["headline"]["score"] >= 0.8, "the page that misleads sets the company's number"
    plain = sum(r.summary["headline"]["score"] for r in pages) / len(pages)
    assert round(plain, 2) == 0.23, "a plain mean would have called this company clean"

    many = [page("bad", "2026-09-01", 0.9, 0.8)] + [page(f"ok{i}", "2026-09-01", 0.1, 0.8) for i in range(20)]
    assert aggregate_company(many)[0]["headline"]["score"] >= 0.7, "and twenty do not bury it either"


def test_the_company_number_never_leaves_the_range_of_its_documents():
    pages = [page("a", "2026-01-01", 0.9), page("b", "2026-06-01", 0.2), page("c", "2026-09-01", 0.4)]
    view, _ = aggregate_company(pages)
    scores = [r.summary["headline"]["score"] for r in pages]
    assert min(scores) <= view["headline"]["score"] <= max(scores)
    assert aggregate_company([page("only", "2026-09-01", 0.63, 0.55)])[0]["headline"] == {"score": 0.63, "confidence": 0.55}


def test_the_current_page_weighs_more_than_an_archived_one_without_erasing_it():
    """Recency is the company-level analogue of a claim's prominence: the page on the site today
    says more about the company than one it replaced, but the replaced one still counts."""
    assert recency("2026-09-19", "2026-09-19") == 1.0
    two_years = recency("2024-09-19", "2026-09-19")
    assert 0.45 <= two_years <= 0.55, f"a page a half-life old counts half, got {two_years}"
    assert recency("2020-01-01", "2026-09-19") > 0.05, "an old page still counts for something"

    fresh = aggregate_company([page("new", "2026-09-01", 0.75), page("old", "2024-03-01", 0.70)])[0]
    stale = aggregate_company([page("new", "2026-09-01", 0.70), page("old", "2024-03-01", 0.75)])[0]
    assert fresh["headline"]["score"] > stale["headline"]["score"], "the same pair reads worse when the recent page is the worse one"


def test_a_company_that_cleaned_up_keeps_its_record_and_the_trend_carries_the_news():
    """The deliberate choice: the headline says what the worst of the record is and the trend
    says which way it is moving. One number cannot do both without either erasing a company's
    2024 page the moment it is replaced, or condemning it for one forever."""
    view, _ = aggregate_company([page("old", "2024-03-01", 0.9, 0.8), page("new", "2026-09-19", 0.2, 0.8)])
    assert view["headline"]["score"] >= 0.7, "the page that misled is still part of the record"
    assert view["trend"]["direction"] == "improving" and view["trend"]["change"] < 0
    assert "0.9" in view["trend"]["note"] and "0.2" in view["trend"]["note"]


def test_the_newest_page_cannot_speak_for_the_company_on_its_own():
    """Reading only the latest document would let a company reset its record with one bland page
    published a week after a misleading one."""
    view, _ = aggregate_company([page("bad", "2026-09-01", 0.9, 0.8), page("bland", "2026-09-08", 0.1, 0.8)])
    assert view["headline"]["score"] >= 0.7, "last week's page is still the company's"


def test_every_number_says_which_documents_it_came_from():
    pages = [page("bad", "2026-09-01", 0.9), page("ok", "2026-09-01", 0.1)]
    view, parts = aggregate_company(pages)
    assert view["ext"]["drivers"]["headline"][0] == "bad"
    assert set(view["ext"]["drivers"]) == {*PROFILE, "headline"}
    assert view["ext"]["power"] == round(POWER, 2) and view["ext"]["halflife_days"] == HALFLIFE_DAYS
    shares = {d["document_id"]: d["share"] for d in view["documents"]}
    assert round(sum(shares.values()), 2) == 1.0, "the documents' shares of the headline add up"
    assert shares["bad"] > 0.9, f"the worst page is almost all of the number at power {POWER}"
    lines = explain(view, parts)
    assert any(line.startswith("headline") and "bad" in line for line in lines)
    assert any("bad" in line and "share" in line for line in lines), "and each document's own line"


def test_the_documents_are_listed_oldest_first_with_their_own_numbers():
    pages = [page("new", "2026-09-19", 0.8), page("old", "2024-03-01", 0.6)]
    view, _ = aggregate_company(pages)
    assert [d["document_id"] for d in view["documents"]] == ["old", "new"], "time order: the trend's order"
    first = view["documents"][0]
    assert first["date"] == "2024-03-01" and first["headline"] == {"score": 0.6, "confidence": 0.7}
    assert first["recency"] < view["documents"][1]["recency"] == 1.0
    assert first["weight"] == pytest.approx(first["recency"] * 0.7, abs=0.01)
    assert set(first["dimensions"]) == set(PROFILE)


def test_the_profile_and_the_counts_are_the_documents_own():
    pages = [
        page("a", "2026-01-01", 0.4, header=summary(0.4, claim_count=3, omission_count=2)),
        page("b", "2026-09-01", 0.8, header=summary(
            0.8, claim_count=5, omission_count=1,
            verdict_distribution={"supported": 2, "unsubstantiated": 1, "misleading_by_framing": 2, "contradicted": 0},
        )),
    ]
    view, _ = aggregate_company(pages)
    assert view["document_count"] == 2 and view["claim_count"] == 8 and view["omission_count"] == 3
    assert view["verdict_distribution"] == {"supported": 2, "unsubstantiated": 1, "misleading_by_framing": 3, "contradicted": 0}
    assert set(view["dimensions"]) == set(PROFILE)
    assert all(0.4 <= view["dimensions"][name]["score"] <= 0.8 for name in PROFILE)


def test_a_dimension_no_document_scored_reads_zero_rather_than_erroring():
    empty = {name: {"score": 0.0, "confidence": 0.0} for name in PROFILE}
    view, _ = aggregate_company([page("a", "2026-01-01", 0.0, 0.0, header=summary(0.0, 0.0, dimensions=empty))])
    assert view["headline"] == {"score": 0.0, "confidence": 0.0}
    assert view["dimensions"]["completeness"] == {"score": 0.0, "confidence": 0.0}


# ----------------------------------------------------------------------------- the trend


def test_one_document_is_not_a_trend_and_says_so():
    view, _ = aggregate_company([page("only", "2026-09-19", 0.71)])
    trend = view["trend"]
    assert trend["direction"] == "undetermined" and trend["confidence"] == 0.0
    assert trend["change"] is None and trend["per_year"] is None and trend["span_days"] is None
    assert trend["points"] == 1
    assert "one document" in trend["note"].lower(), trend["note"]
    assert view["documents"][0]["share"] == 1.0


def test_two_points_are_a_line_not_a_trend():
    view, _ = aggregate_company([page("old", "2024-03-01", 0.62, 0.8), page("new", "2026-09-19", 0.89, 0.8)])
    trend = view["trend"]
    assert trend["direction"] == "worsening" and trend["change"] == pytest.approx(0.27, abs=0.005)
    assert trend["points"] == 2 and trend["span_days"] == 932
    assert trend["per_year"] == pytest.approx(0.27 * 365.25 / 932, abs=0.01)
    assert trend["confidence"] <= 0.4, "two documents cannot establish a direction"
    assert "not a trend" in trend["note"], trend["note"]
    assert MIN_POINTS >= 3


def test_three_documents_moving_one_way_are_worth_more_than_two():
    steady_climb = [page("a", "2024-01-01", 0.3, 0.8), page("b", "2025-01-01", 0.55, 0.8), page("c", "2026-01-01", 0.8, 0.8)]
    trend = aggregate_company(steady_climb)[0]["trend"]
    assert trend["direction"] == "worsening" and trend["points"] == 3
    assert trend["confidence"] > aggregate_company(steady_climb[:2])[0]["trend"]["confidence"]
    assert "not a trend" not in trend["note"]
    assert trend["ext"]["consistency"] == 1.0, "every step goes the same way"


def test_a_direction_nobody_could_read_off_the_page_is_held_weakly():
    zigzag = [page("a", "2024-01-01", 0.3, 0.9), page("b", "2025-01-01", 0.9, 0.9), page("c", "2026-01-01", 0.4, 0.9)]
    trend = aggregate_company(zigzag)[0]["trend"]
    assert trend["direction"] == "worsening" and trend["change"] == pytest.approx(0.1, abs=0.005)
    assert trend["ext"]["consistency"] < 0.2, "0.1 of net movement out of 1.1 of movement"
    assert trend["confidence"] < 0.2
    assert "one way" in trend["note"] or "back" in trend["note"], trend["note"]


def test_a_move_smaller_than_the_noise_floor_is_not_a_direction():
    trend = aggregate_company([page("a", "2024-01-01", 0.60, 0.8), page("b", "2026-01-01", 0.63, 0.8)])[0]["trend"]
    assert trend["direction"] == "steady" and abs(trend["change"]) < EPSILON
    assert str(EPSILON) in trend["note"], trend["note"]


def test_the_trend_cannot_be_surer_than_the_numbers_that_moved():
    unsure = [page("a", "2024-01-01", 0.2, 0.9), page("b", "2025-01-01", 0.5, 0.9), page("c", "2026-01-01", 0.8, 0.15)]
    trend = aggregate_company(unsure)[0]["trend"]
    assert trend["confidence"] <= 0.15, "the last page's reading is barely held, so the movement is too"


def test_the_trend_reports_what_moved_in_the_profile():
    view, _ = aggregate_company([
        page("a", "2024-01-01", 0.4, 0.8, header=summary(0.4, dimensions={
            **{n: {"score": 0.4, "confidence": 0.8} for n in PROFILE}, "support": {"score": 0.2, "confidence": 0.8}})),
        page("b", "2026-01-01", 0.8, 0.8, header=summary(0.8, dimensions={
            **{n: {"score": 0.8, "confidence": 0.8} for n in PROFILE}, "support": {"score": 0.9, "confidence": 0.8}})),
    ])
    moved = view["trend"]["ext"]["dimension_change"]
    assert moved["support"] == pytest.approx(0.7, abs=0.005) and moved["clarity"] == pytest.approx(0.4, abs=0.005)


def test_two_captures_of_the_same_day_have_no_time_between_them():
    trend = aggregate_company([page("a", "2026-09-19", 0.2), page("b", "2026-09-19", 0.8)])[0]["trend"]
    assert trend["span_days"] == 0 and trend["per_year"] is None
    assert trend["direction"] in ("improving", "worsening"), "the change is still a fact"
    assert "same day" in trend["note"], trend["note"]


# ----------------------------------------------------------------------------- dates


def test_an_archived_page_is_dated_by_its_capture_not_by_the_day_it_was_fetched():
    """The ingester stamps `retrieved` with today even when it reads a Wayback capture, so a
    2024 page fetched this morning would otherwise sit on top of the trend beside the live one."""
    archived = {"retrieved": "2026-09-20", "url": "https://www.shell.com/our-climate-target.html",
                "archive_url": "https://web.archive.org/web/20240301120000/https://www.shell.com/our-climate-target.html"}
    assert document_date({"source": archived}) == ("2024-03-01", "archive")
    assert document_date({"source": {"retrieved": "2026-09-19"}}) == ("2026-09-19", "retrieved")
    assert document_date({"source": {"retrieved": "2026-09-19", "archive_url": "https://example.com/x"}}) == ("2026-09-19", "retrieved")
    assert document_date({}) == ("", "unknown")

    # The golden reference cites a capture of the very page it fetched live. A capture taken
    # around the fetch is a permalink for it, not where the text came from.
    permalink = {"retrieved": "2026-09-19", "url": "https://www.shell.com/sustainability/climate.html",
                 "archive_url": "https://web.archive.org/web/20260904004048/https://www.shell.com/sustainability/climate.html"}
    assert document_date({"source": permalink}) == ("2026-09-19", "retrieved")

    view, _ = aggregate_company([
        page("live", "2026-09-19", 0.89, url="https://www.shell.com/climate.html"),
        page("archived", "2026-09-20", 0.62, url="https://www.shell.com/our-climate-target.html",
             archive_url="https://web.archive.org/web/20240301120000/https://www.shell.com/our-climate-target.html"),
    ])
    assert [d["document_id"] for d in view["documents"]] == ["archived", "live"]
    assert view["documents"][0]["date"] == "2024-03-01" and view["documents"][0]["date_basis"] == "archive"
    assert view["trend"]["direction"] == "worsening", "the page got worse between the capture and today"


def test_a_document_with_no_date_is_dated_by_the_company_s_oldest_and_says_so():
    view, _ = aggregate_company([page("dated", "2026-09-19", 0.8), Record(
        document={"id": "undated", "title": "t", "company": {"name": "Shell plc"}, "source": {}},
        summary=summary(0.4), claims=[], verdicts=[], omissions=[])])
    undated = next(d for d in view["documents"] if d["document_id"] == "undated")
    assert undated["date_basis"] == "unknown" and "date" not in undated
    assert undated["recency"] < 1.0, "an undated page cannot claim to be the current one"
    assert view["trend"]["points"] == 1, "and it is not a point on the trend"
    assert "1 document without a date" in " ".join(view["ext"]["notes"])


# ----------------------------------------------------------------------------- the ranking


def test_top_issues_come_from_every_document_and_keep_the_titles_the_page_gave_them():
    old = page(
        "old", "2024-03-01", 0.6,
        claims=[claim("C1", "old words", 1.0)], verdicts=[verdict("C1", 0.6)],
        header=summary(0.6, top_issues=[{"rank": 1, "target": "C1", "title": "The 2024 target has no baseline"}]),
    )
    new = page(
        "new", "2026-09-19", 0.9,
        claims=[claim("C1", "new words", 1.0), claim("C2", "quiet words", 0.3)],
        verdicts=[verdict("C1", 0.9), verdict("C2", 0.9)],
        omissions=[omission("O1", 0.5)],
        header=summary(0.9, top_issues=[{"rank": 1, "target": "C1", "title": "The headline figure is the wrong scope"}]),
    )
    view, _ = aggregate_company([old, new])
    issues = view["top_issues"]
    assert [i["rank"] for i in issues] == list(range(1, len(issues) + 1))
    assert issues[0] == {"rank": 1, "document_id": "new", "target": "C1", "title": "The headline figure is the wrong scope"}
    assert {(i["document_id"], i["target"]) for i in issues} >= {("new", "C1"), ("new", "O1"), ("old", "C1")}
    assert next(i for i in issues if i["document_id"] == "old")["title"] == "The 2024 target has no baseline"
    quiet = next(i for i in issues if i["target"] == "C2")
    assert issues.index(quiet) > issues.index(issues[0]), "a footnote ranks below a headline of the same score"
    assert next(i for i in issues if i["target"] == "O1")["title"] == "Not mentioned: Topic O1"


def test_an_issue_is_identified_by_its_document_because_claim_ids_repeat_across_them():
    """`C1` is a different claim in every analysis, so a company-level target needs both halves."""
    view, _ = aggregate_company([
        page("a", "2026-01-01", 0.8, claims=[claim("C1", "one")], verdicts=[verdict("C1", 0.8)]),
        page("b", "2026-09-01", 0.8, claims=[claim("C1", "another")], verdicts=[verdict("C1", 0.8)]),
    ])
    assert sorted((i["document_id"], i["target"]) for i in view["top_issues"]) == [("a", "C1"), ("b", "C1")]
    assert [i["title"] for i in view["top_issues"]] == ["another", "one"], "each keeps its own words"


def test_credit_is_the_supported_claims_across_the_documents():
    view, _ = aggregate_company([
        page("a", "2026-01-01", 0.8,
             claims=[claim("C1", "assured figure"), claim("C2", "bad")],
             verdicts=[verdict("C1", 0.1, "supported"), verdict("C2", 0.8)],
             header=summary(0.8, credit=[{"target": "C1", "title": "Operational emissions 36% below 2016, assured"}])),
        page("b", "2026-09-01", 0.9, claims=[claim("C3", "also fine")], verdicts=[verdict("C3", 0.2, "supported")]),
    ])
    assert [(c["document_id"], c["target"]) for c in view["credit"]] == [("a", "C1"), ("b", "C3")]
    assert view["credit"][0]["title"] == "Operational emissions 36% below 2016, assured"
    assert view["credit"][1]["title"] == "also fine", "an untitled one falls back to the claim's own words"


# ----------------------------------------------------------------------------- reading the logs


def events_for(company: str, doc_id: str, date: str, score: float, *, final: bool = True) -> list[dict]:
    document = {"id": doc_id, "title": f"{company} page", "company": {"name": company},
                "industry": {"label": "Oil & Gas – Integrated"}, "text_type": "web_page",
                "source": {"retrieved": date, "url": f"https://example.com/{doc_id}"}, "text": "A page.", "regions": []}
    out = [
        {"type": "analysis.started", "payload": {"contract_version": "1.0.0", "analysis_id": f"an-{doc_id}"}},
        {"type": "document.ingested", "payload": {"document": document}},
        {"type": "claim.extracted", "payload": {"claim": claim("C1", "some words")}},
        {"type": "verdict.issued", "payload": {"verdict": verdict("C1", score)}},
        {"type": "omission.found", "payload": {"omission": omission("O1")}},
    ]
    if final:
        out.append({"type": "summary.updated", "payload": {"summary": summary(score), "final": True}})
    out.append({"type": "analysis.completed", "payload": {}})
    return out


def test_a_log_folds_into_the_one_row_the_company_view_needs():
    record = fold_record(log(events_for("Shell plc", "d1", "2026-09-19", 0.8)), {"kind": "run", "name": "r1"})
    assert record is not None
    assert record.company == "Shell plc" and record.document_id == "d1" and record.analysis_id == "an-d1"
    assert record.date == "2026-09-19" and record.headline["score"] == 0.8
    assert len(record.claims) == 1 and len(record.verdicts) == 1 and len(record.omissions) == 1
    assert record.origin == {"kind": "run", "name": "r1"}


def test_an_analysis_that_never_reached_a_summary_is_not_a_company_document():
    """A cancelled or half-finished run has no header, so there is no number to aggregate; it is
    left out rather than counted as a clean page."""
    assert fold_record(log(events_for("Shell plc", "d1", "2026-09-19", 0.8, final=False)), {}) is None
    assert fold_record(log([{"type": "analysis.started", "payload": {}}, {"type": "analysis.failed", "payload": {"error": "cancelled"}}]), {}) is None


def test_the_fullest_analysis_of_a_document_wins_and_the_rest_are_counted(tmp_path):
    fixtures, runs = tmp_path / "fixtures", tmp_path / "runs"
    for directory in (fixtures, runs):
        directory.mkdir()
    def write(path, events):
        path.write_text("".join(json.dumps({"t_ms": i * 10, **e}) + "\n" for i, e in enumerate(events)), encoding="utf-8")
    write(fixtures / "shell.jsonl", events_for("Shell plc", "shell-climate", "2026-09-19", 0.89))
    write(runs / "replay.jsonl", events_for("Shell plc", "shell-climate", "2026-09-19", 0.89))
    write(runs / "orsted.jsonl", events_for("Ørsted A/S", "orsted", "2026-09-19", 0.2))
    (runs / "broken.jsonl").write_text('{"t_ms": 0, "type": "stage.started", "payload": {"stage": "x"}}\n', encoding="utf-8")

    records, skipped = load_records([(fixtures, "fixture"), (runs, "run")])
    assert len(records) == 3 and len(skipped) == 1 and "broken.jsonl" in skipped[0]
    grouped = group_by_company(records)
    assert sorted(grouped) == ["Shell plc", "Ørsted A/S"]
    assert len(grouped["Shell plc"]) == 1, "the same page analysed twice is one document"
    assert grouped["Shell plc"][0].origin["kind"] == "fixture"

    view, _ = aggregate_company(grouped["Shell plc"])
    assert view["ext"]["duplicates"] == 1
    assert view["documents"][0]["ext"]["source"] == {"kind": "fixture", "name": "shell"}


def test_a_company_is_found_by_its_name_a_slug_or_an_unambiguous_prefix():
    names = ["Shell plc", "Ørsted A/S", "Apple Inc."]
    assert company_slug("Ørsted A/S") == "orsted-a-s"
    for wanted in ("Shell plc", "shell plc", "SHELL PLC", "shell-plc", "shell"):
        assert find_company(names, wanted) == "Shell plc", wanted
    assert find_company(names, "orsted") == "Ørsted A/S", "the slug folds the diacritic"
    assert find_company(names, "Exxon") is None
    assert find_company(["Shell plc", "Shell Energy Ltd"], "shell") is None, "an ambiguous prefix is not a match"


# ----------------------------------------------------------------------------- the words


class FakeWriter:
    def __init__(self, words: Words | None = None, error: Exception | None = None) -> None:
        self.words = words or Words()
        self.error = error
        self.calls: list[dict] = []

    async def extract(self, prompt, output, **kwargs):
        self.calls.append(dict(kwargs, prompt=prompt, output=output))
        if self.error is not None:
            raise self.error
        return self.words, usage()


def test_the_model_writes_the_narrative_and_changes_no_number():
    pages = [page("old", "2024-03-01", 0.62, 0.8), page("new", "2026-09-19", 0.89, 0.8)]
    before, _ = aggregate_company(pages)
    llm = FakeWriter(Words(narrative="  Two versions of one\n page. "))
    result = asyncio.run(describe_company(pages, llm=llm))
    assert result.view["headline"] == before["headline"] and result.view["trend"] == before["trend"]
    assert result.view["narrative"] == "Two versions of one page."
    assert len(llm.calls) == 1 and llm.calls[0]["cache"] is False
    assert result.usage is not None and result.usage.input_tokens == 10
    assert any(line.startswith("headline") for line in result.notes)


def test_the_prompt_gives_the_model_the_numbers_and_asks_only_for_words():
    pages = [page("old", "2024-03-01", 0.62, 0.8, claims=[claim("C1")], verdicts=[verdict("C1", 0.62)]),
             page("new", "2026-09-19", 0.89, 0.8, claims=[claim("C1")], verdicts=[verdict("C1", 0.89)])]
    view, _ = aggregate_company(pages)
    prompt = write_prompt(view)
    assert "<documents>" in prompt and "<issues>" in prompt and "<trend>" in prompt
    assert "2024-03-01" in prompt and "0.89" in prompt
    assert "not yours to change" in prompt


def test_a_company_with_one_document_still_gets_a_narrative_but_no_invented_trend():
    llm = FakeWriter(Words(narrative="One page, read once."))
    result = asyncio.run(describe_company([page("only", "2026-09-19", 0.7)], llm=llm))
    assert result.view["trend"]["direction"] == "undetermined"
    assert "one document" in llm.calls[0]["prompt"].lower()


def test_nothing_to_describe_needs_no_call_at_all():
    result = asyncio.run(describe_company([], company="Shell plc", llm=FakeWriter(error=LlmError("should not be called"))))
    assert result.view["document_count"] == 0 and result.view["headline"] == {"score": 0.0, "confidence": 0.0}
    assert result.view["company"] == {"name": "Shell plc"} and result.view["trend"]["direction"] == "undetermined"


def test_a_failing_writer_fails_with_a_plain_error():
    with pytest.raises(LlmError, match="went quiet"):
        asyncio.run(describe_company([page("a", "2026-01-01", 0.8)], llm=FakeWriter(error=LlmError("Claude's stream went quiet"))))


# ----------------------------------------------------------------------------- the contract


def contract_tool():
    import importlib.util

    spec = importlib.util.spec_from_file_location("contract_tool", REPO / "contract" / "tools" / "contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_company_view_satisfies_the_contracts_own_checks():
    module = contract_tool()
    pages = [
        page("old", "2024-03-01", 0.62, 0.8, claims=[claim("C1", "old words")], verdicts=[verdict("C1", 0.62)],
             header=summary(0.62, claim_count=1, top_issues=[{"rank": 1, "target": "C1", "title": "No baseline"}])),
        page("new", "2026-09-19", 0.89, 0.8, claims=[claim("C1", "new words"), claim("C2", "fine")],
             verdicts=[verdict("C1", 0.89), verdict("C2", 0.1, "supported")], omissions=[omission("O1")],
             header=summary(0.89, claim_count=2, omission_count=1,
                            verdict_distribution={"supported": 1, "unsubstantiated": 0, "misleading_by_framing": 1, "contradicted": 0})),
    ]
    result = build_company(pages, narrative="Two versions of one page.")
    report = module.Report()
    module.check_company(result.view, report)
    assert not report.errors, report.errors
    assert not report.warnings, report.warnings


def test_the_contract_catches_a_company_number_that_cannot_be_explained():
    module = contract_tool()
    result = build_company([page("a", "2026-01-01", 0.4, 0.8), page("b", "2026-09-01", 0.8, 0.8)])
    broken = json.loads(json.dumps(result.view))
    broken["headline"]["score"] = 0.95
    report = module.Report()
    module.check_company(broken, report)
    assert any("outside the range" in e for e in report.errors), report.errors

    shuffled = json.loads(json.dumps(result.view))
    shuffled["documents"].reverse()
    report = module.Report()
    module.check_company(shuffled, report)
    assert any("oldest first" in e for e in report.errors), report.errors

    invented = json.loads(json.dumps(result.view))
    invented["trend"]["direction"] = "improving"
    report = module.Report()
    module.check_company(invented, report)
    assert any("direction" in e for e in report.errors), report.errors


# ----------------------------------------------------------------------------- the endpoint


def write_log_file(path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps({"t_ms": i * 10, **e}) + "\n" for i, e in enumerate(events)), encoding="utf-8")


def test_the_company_view_is_served_from_the_recordings_and_the_runs(client, fixtures_dir, runs_dir):
    runs_dir.mkdir(exist_ok=True)
    write_log_file(fixtures_dir / "shell-now.jsonl", events_for("Shell plc", "shell-2026", "2026-09-19", 0.89))
    write_log_file(runs_dir / "20240301T000000Z-aaa.jsonl", events_for("Shell plc", "shell-2024", "2024-03-01", 0.62))

    got = client.get("/api/company/Shell%20plc")
    assert got.status_code == 200, got.text
    view = got.json()
    assert view["company"]["name"] == "Shell plc"
    assert [d["document_id"] for d in view["documents"]] == ["shell-2024", "shell-2026"]
    assert view["trend"]["direction"] == "worsening" and view["trend"]["points"] == 2
    assert view["headline"]["score"] >= 0.8 and view["document_count"] == 2
    assert view["top_issues"] and view["top_issues"][0]["document_id"] in ("shell-2024", "shell-2026")
    assert "narrative" not in view, "the endpoint serves arithmetic; no request waits on a model"
    assert client.get("/api/company/shell-plc").json() == view, "by slug too"
    assert client.get("/api/company/shell").json() == view, "and by an unambiguous prefix"


def test_a_company_with_no_analysis_yet_gets_a_404_that_says_what_there_is(client, fixtures_dir, runs_dir):
    runs_dir.mkdir(exist_ok=True)
    write_log_file(fixtures_dir / "shell-now.jsonl", events_for("Shell plc", "shell-2026", "2026-09-19", 0.89))

    missing = client.get("/api/company/Exxon")
    assert missing.status_code == 404
    detail = missing.json()["detail"]
    assert "Exxon" in detail and "Shell plc" in detail

    # A demo text whose page has never been analysed is named as a company that could be.
    known = client.get("/api/company/%C3%98rsted%20A%2FS")
    assert known.status_code == 404
    assert "no analysis" in known.json()["detail"].lower()


def test_one_document_is_served_without_pretending_to_a_trend(client, fixtures_dir):
    write_log_file(fixtures_dir / "shell-now.jsonl", events_for("Shell plc", "shell-2026", "2026-09-19", 0.89))
    view = client.get("/api/company/Shell plc").json()
    assert view["document_count"] == 1
    assert view["trend"] == {**view["trend"], "direction": "undetermined", "confidence": 0.0, "points": 1}
    assert view["headline"]["score"] == 0.89, "one document's numbers are the company's, unchanged"
