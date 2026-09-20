"""The knowledge stores: the curated files validate, entries become contract evidence items,
the hold-out and quote checks work, and bad entries are refused with their name."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import REPO

from auditor.knowledge import (
    CriteriaIndex,
    Knowledge,
    KnowledgeError,
    PrecedentIndex,
    StoreEntry,
    check_quotes,
    load_knowledge,
    quote_in,
)


def evidence_schema():
    schema = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))
    return {"$ref": "#/definitions/EvidenceItem", "definitions": schema["definitions"]}


def test_the_repository_stores_load_and_hold_the_demo_set_precedents():
    knowledge = load_knowledge()
    assert knowledge.directory == REPO / "knowledge"
    assert len(knowledge.criteria) >= 20 and len(knowledge.precedents) >= 20
    ids = {e.id for e in knowledge.entries}
    for wanted in ("cma-green-claims-code-generic-terms", "eu-2024-825-offset-neutrality", "cap-guidance-carbon-neutral-net-zero",
                   "asa-2023-shell-uk-omission", "paris-2025-totalenergies-carbon-neutrality", "lg-frankfurt-2025-apple-watch-co2-neutral",
                   "ndcal-2026-dib-v-apple-carbon-neutral", "bgh-2024-katjes-klimaneutral"):
        assert wanted in ids
    verified = [e for e in knowledge.entries if e.verified]
    assert len(verified) >= 40, "nearly every entry carries a quote a script found on its page"
    assert all(e.quote and e.verification != "unverified" for e in verified)
    assert all(e.quote is None or not e.verified for e in knowledge.entries if not e.verified)
    companies = {e.index.company for e in knowledge.precedents if isinstance(e.index, PrecedentIndex)}
    assert {"Shell", "TotalEnergies", "Apple"} <= companies, "the demo set's companies have precedents"


def test_every_entry_becomes_a_valid_contract_evidence_item():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(evidence_schema())
    knowledge = load_knowledge()
    for eid, entry in knowledge.ids().items():
        item = entry.as_evidence(eid, [{"target": "C1", "relation": "criteria" if entry.store == "criteria" else "precedent"}])
        errors = list(validator.iter_errors(item))
        assert not errors, (entry.id, [e.message for e in errors])
        assert item["stage"] == "substantiate" and item["ext"]["store_id"] == entry.id
        if entry.verified:
            assert item["quote"] == entry.quote
        else:
            assert "quote" not in item, "an unverified quote is never displayed"
    ids = list(knowledge.ids())
    assert ids[0] == "K1" and ids[len(knowledge.criteria)] == "P1"


def test_the_listing_names_every_entry_with_its_rule_or_ruling():
    knowledge = load_knowledge()
    listing = knowledge.listing()
    assert listing.startswith("Substantiation criteria")
    assert "Precedents (rulings on environmental claims):" in listing
    assert "K1 [criterion; UK; tier 1] CMA Green Claims Code: generic terms" in listing
    assert "Wording ruled on:" in listing and "Outcome: not upheld" in listing
    for eid in knowledge.ids():
        assert f"\n{eid} [" in listing


def test_a_precedent_that_adjudicated_the_document_is_held_out():
    knowledge = load_knowledge()
    paris = next(e for e in knowledge.precedents if e.id == "paris-2025-totalenergies-carbon-neutrality")
    assert isinstance(paris.index, PrecedentIndex) and paris.index.adjudicated_urls
    kept = knowledge.for_document(paris.index.adjudicated_urls[0])
    assert paris.id in kept.held_out and paris.id not in {e.id for e in kept.precedents}
    assert len(kept.criteria) == len(knowledge.criteria)
    assert knowledge.for_document("https://www.shell.com/sustainability/climate.html").held_out == []
    assert knowledge.for_document(None) is knowledge
    fewer = knowledge.without({paris.id, knowledge.criteria[0].id})
    assert len(fewer.precedents) == len(knowledge.precedents) - 1 and len(fewer.criteria) == len(knowledge.criteria) - 1


def entry(**overrides) -> dict:
    base = {
        "id": "test-entry", "kind": "ruling", "tier": 1, "source": {"name": "A ruling"}, "url": "https://example.org/r",
        "quote": "the words", "verified": True, "verification": "fetched_exact", "retrieved": "2026-09-20",
        "index": {"jurisdiction": "UK", "body": "ASA", "company": "Acme", "claim_text": "green", "outcome": "upheld", "reasoning": "vague"},
    }
    return {**base, **overrides}


def write_store(directory: Path, criteria: list[dict], precedents: list[dict]) -> Path:
    directory.mkdir(exist_ok=True)
    (directory / "criteria.json").write_text(json.dumps(criteria), encoding="utf-8")
    (directory / "precedents.json").write_text(json.dumps(precedents), encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    "bad, message",
    [
        (entry(verified=True, quote=None), "verified but no quote"),
        (entry(verified=True, verification="unverified"), "verified but verification"),
        (entry(verified=False, verification="fetched_exact"), "not verified"),
        (entry(retrieved="20 Sep 2026"), "ISO date"),
        (entry(tier=6), "less than or equal to 5"),
        (entry(id="bad id!"), "not a contract id"),
        (entry(url="ftp://x"), "http(s)"),
        (entry(index={"jurisdiction": "UK", "body": "ASA", "company": "Acme", "claim_text": "x", "outcome": "won", "reasoning": "y"}), "outcome"),
        (entry(extra="field"), "extra"),
    ],
)
def test_bad_entries_are_refused_by_name(tmp_path, bad, message):
    write_store(tmp_path / "k", [], [bad])
    with pytest.raises(KnowledgeError, match="precedents.json entry 1") as caught:
        load_knowledge(tmp_path / "k")
    assert message in str(caught.value)


def test_missing_files_duplicates_and_bad_json_are_refused(tmp_path):
    with pytest.raises(KnowledgeError, match="criteria.json is missing"):
        load_knowledge(tmp_path / "nowhere")
    directory = write_store(tmp_path / "k", [], [])
    (directory / "criteria.json").write_text("[{", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="not valid JSON"):
        load_knowledge(directory)
    criterion = {**entry(id="same", kind="standard"), "index": {"jurisdiction": "UK", "rule": "be clear"}}
    write_store(directory, [criterion], [entry(id="same")])
    with pytest.raises(KnowledgeError, match="duplicate store id same"):
        load_knowledge(directory)


def test_quotes_are_matched_with_typography_and_whitespace_normalised():
    page = "The ASA said: “claims must be\n  clear and unambiguous” — always."
    assert quote_in(page, 'claims must be clear and unambiguous')
    assert quote_in(page, '"Claims must be clear and unambiguous" - always')
    assert not quote_in(page, "claims must be substantiated")


def test_check_quotes_reports_each_entry(tmp_path):
    criterion = StoreEntry(id="c", kind="standard", tier=1, source={"name": "Code"}, url="https://x.org/code", quote="be clear", verified=True, verification="fetched_exact", retrieved="2026-09-20", index=CriteriaIndex(jurisdiction="UK", rule="r"))
    precedent = StoreEntry(id="p", kind="ruling", tier=1, source={"name": "R"}, url="https://x.org/js", text_url="https://x.org/text", quote="upheld", verified=True, verification="fetched_exact", retrieved="2026-09-20", index=PrecedentIndex(jurisdiction="UK", body="ASA", company="A", claim_text="g", outcome="upheld", reasoning="v"))
    unverified = StoreEntry(id="u", kind="standard", tier=3, source={"name": "ISO"}, url="https://x.org/iso", verified=False, verification="unverified", retrieved="2026-09-20", index=CriteriaIndex(jurisdiction="Intl", rule="r"))
    nourl = StoreEntry(id="n", kind="other", tier=3, source={"name": "N"}, verified=False, verification="unverified", retrieved="2026-09-20", index=CriteriaIndex(jurisdiction="Intl", rule="r"))
    missing = StoreEntry(id="m", kind="standard", tier=1, source={"name": "M"}, url="https://x.org/missing", quote="not there", verified=True, verification="fetched_exact", retrieved="2026-09-20", index=CriteriaIndex(jurisdiction="UK", rule="r"))
    knowledge = Knowledge([criterion, unverified, nourl, missing], [precedent])

    class Refused(Exception):
        status = 403

    def fetch_text(url: str) -> str:
        return {"https://x.org/code": "Be Clear.", "https://x.org/text": "Upheld", "https://x.org/missing": "other words"}.get(url) or (_ for _ in ()).throw(Refused("403"))

    lines = check_quotes(knowledge, fetch_text)
    assert lines[0] == "ok   c: quote found (fetched_exact)"
    assert lines[1].startswith("warn u:") and "open it in a browser" in lines[1]
    assert lines[2] == "skip n: no url"
    assert lines[3] == "FAIL m: quote not found on https://x.org/missing"
    assert lines[4] == "ok   p: quote found (fetched_exact)", "the text url is read when the page is a JavaScript shell"


def test_the_check_command_validates_the_repository_stores(capsys):
    from auditor.knowledge import main

    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "criteria and" in out and "precedents in" in out and "asa-2023-shell-uk-omission" in out


def test_the_contract_tool_accepts_a_log_with_store_evidence():
    """A minimal event log with a criteria item from the store passes the contract's event checks."""
    spec = importlib.util.spec_from_file_location("contract_tool", REPO / "contract" / "tools" / "contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    knowledge = load_knowledge()
    k1 = knowledge.ids()["K1"].as_evidence("K1", [{"target": "C1", "relation": "criteria"}])
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    claim = analysis["claims"][0]
    events = [
        {"seq": 1, "t_ms": 0, "type": "analysis.started", "payload": {"contract_version": "1.0.0"}},
        {"seq": 2, "t_ms": 0, "type": "stage.started", "payload": {"stage": "ingest"}},
        {"seq": 3, "t_ms": 0, "type": "document.ingested", "payload": {"document": analysis["document"]}},
        {"seq": 4, "t_ms": 0, "type": "stage.completed", "payload": {"stage": "ingest"}},
        {"seq": 5, "t_ms": 0, "type": "stage.started", "payload": {"stage": "extract"}},
        {"seq": 6, "t_ms": 0, "type": "claim.extracted", "payload": {"claim": claim}},
        {"seq": 7, "t_ms": 0, "type": "stage.completed", "payload": {"stage": "extract"}},
        {"seq": 8, "t_ms": 0, "type": "stage.started", "payload": {"stage": "substantiate"}},
        {"seq": 9, "t_ms": 0, "type": "evidence.added", "payload": {"evidence": k1}},
        {"seq": 10, "t_ms": 0, "type": "dimension.scored", "payload": {"score": {"claim_id": "C1", "dimension": "support", "score": 0.6, "confidence": 0.7, "basis": "b", "evidence_ids": ["K1"], "stage": "substantiate"}}},
        {"seq": 11, "t_ms": 0, "type": "stage.completed", "payload": {"stage": "substantiate"}},
        {"seq": 12, "t_ms": 0, "type": "analysis.failed", "payload": {"error": "stopped", "stage": "verify"}},
    ]
    report = module.Report()
    module.check_events(events, report)
    assert not report.errors, report.errors
