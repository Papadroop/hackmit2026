"""Live analyses through the API: ingestion runs, and the stages after it replay from a
recording when one exists for the document."""

from __future__ import annotations

import json

import importlib.util

from conftest import REPO, SHELL_URL, golden_consistency, golden_debate, golden_extraction, golden_header, golden_omissions, golden_review, golden_substantiation, golden_verification, pdf_base64, read_sse, shell_fixture_document

from auditor.extract import ExtractedClaim, Extraction
from auditor.llm import LlmError
from auditor.verdict import derive_category


def types_of(received):
    return [env["type"] for _, env in received]


def check_contract(received, *, analysis_level: bool = False) -> dict:
    """Run the contract tool's full event-log check (schema, ordering, references) on a stream;
    with `analysis_level`, also the checks on the folded analysis (every claim scored on every
    dimension, one verdict each, derivation rules, summary consistency)."""
    spec = importlib.util.spec_from_file_location("contract_tool", REPO / "contract" / "tools" / "contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    report = module.Report()
    folded = module.check_events([env for _, env in received], report)
    assert not report.errors, report.errors
    if analysis_level:
        module.check_analysis(folded, report, strict_summary=True)
        assert not report.errors, report.errors
    return folded


def test_url_request_runs_every_stage_live_and_measures_itself_against_the_recording(client, shell_pages, real_shell, fake_extract, fake_language, fake_substantiate, fake_verify, fake_consistency, fake_omissions, fake_verdict, fake_summary):
    fake_extract.extraction = golden_extraction()
    fake_language.review = golden_review()
    fake_substantiate.matches, fake_substantiate.assessments = golden_substantiation()
    fake_verify.findings, fake_verify.computations, fake_verify.assessments, verify_ids, _ = golden_verification()
    fake_consistency.statements, fake_consistency.assessments, consistency_ids, fake_consistency.pages = golden_consistency()
    fake_omissions.coverages = golden_omissions()
    fake_verdict.prosecution, fake_verdict.defence, fake_verdict.judgments = golden_debate()
    fake_summary.header = golden_header()
    created = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6})
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["source"] == {"kind": "url", "url": SHELL_URL}
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[:2] == ["analysis.started", "stage.started"]
    started = received[0][1]["payload"]
    assert started["mode"] == "live" and started["document_ref"] == {"url": SHELL_URL}

    ingested = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert ingested["text"] == shell_fixture_document()["text"]
    assert ingested["company"]["name"] == "Shell plc"
    index = types.index("document.ingested")
    assert types[index + 1] == "stage.completed" and received[index + 1][1]["payload"]["stage"] == "ingest"

    assert types[-1] == "analysis.completed"
    assert types.count("claim.extracted") == 25 and types.count("verdict.issued") == 25
    extract = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "extract")
    assert "note" not in extract["payload"], "extraction ran live"
    language = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "language")
    assert "note" not in language["payload"], "the language stage ran live"
    substantiate = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "substantiate")
    assert "note" not in substantiate["payload"], "the substantiate stage ran live"
    verify = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "verify")
    assert "note" not in verify["payload"], "external verification ran live"
    verdict = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "verdict")
    assert "note" not in verdict["payload"], "the verdict layer ran live"
    consistency = next(env for _, env in received if env["type"] == "stage.started" and env["payload"]["stage"] == "consistency")
    assert "note" not in consistency["payload"], "the self-consistency evaluator ran live"
    assert types.index("stage.started") < types.index("argument.made") < types.index("verdict.issued")
    notes = [env["payload"]["text"] for _, env in received if env["type"] == "debug.note"]
    assert any("25 of 25 reference claims found (recall 100%, precision 100%)" in n for n in notes), notes
    assert any("24 of 24 reference signals found (recall 100%, precision 100%" in n and "mean absolute difference 0.00" in n for n in notes), notes
    assert any("11 of 11 reference criteria and precedent links found (11 from the same source)" in n for n in notes), notes
    assert any("10 sources retrieved for 17 of 25 claims, 10 with a quote found on the page" in n and "5 numbers recomputed" in n for n in notes), notes
    assert any("3 of 3 reference sources matched by host (ogmpartnership.org, sec.gov, transitionpathwayinitiative.org)" in n and "support scored for 25 reference claims, mean absolute difference 0.00" in n for n in notes), notes
    assert any("header profile within 0.08 of the reference on average" in n and "3 of 5 top issues" in n for n in notes), notes
    assert not any("replayed from recording" in n for n in notes), "the recording is a reference to measure against, not a source of events"
    assert [env["payload"]["stage"] for _, env in received if env["type"] == "stage.started" and "note" in env["payload"]] == [], "no stage is replayed"
    assert any("25 of 25 categories agree, mean absolute likelihood difference 0.00" in n for n in notes), notes
    evidence = {env["payload"]["evidence"]["id"]: env["payload"]["evidence"] for _, env in received if env["type"] == "evidence.added"}
    assert not {"E8", "E8b", "E8c", "E9", "E11", "E12"} & set(evidence), "the recording's criteria and precedents are replaced"
    assert not {"E2", "E3", "E4", "E5", "E6", "E10", "E17", "E18", "E19", "X1", "X2", "X4", "X5", "X6"} & set(evidence), "the recording's retrieved sources and computations are replaced"
    sources = [e for e in evidence.values() if e["id"].startswith("V")]
    computations = [e for e in evidence.values() if e["id"].startswith("N")]
    assert len(sources) == 10 and all(e["stage"] == "verify" and e["verified"] and e["quote"] and e["url"] for e in sources)
    assert [e["tier"] for e in sources] == [2, 2, 2, 2, 2, 2, 3, 3, 2, 2], "the tier follows from who stands behind the source"
    assert len(computations) == 5 and all(e["kind"] == "computation" and e["verification"] == "computed" and e["derived_from"] for e in computations)
    footprint = evidence[verify_ids["X1"]]
    assert footprint["computation"]["formula"] == "scope12_mt / (scope12_mt + scope3_mt) * 100"
    assert footprint["ext"]["recomputed"] == 4.7406 and footprint["derived_from"] == [verify_ids["E4"], verify_ids["E5"]]
    assert footprint["quote"] == "Scope 1 and 2 (53 Mt) are 4.7% of total reported emissions (1,118 Mt)."
    live = [e for e in evidence.values() if e["stage"] == "substantiate"]
    assert len(live) == 6 and all(e["id"][0] in "KP" and e["url"] and e["ext"]["store_id"] for e in live)
    precedent = next(e for e in live if e["ext"]["store_id"] == "paris-2025-totalenergies-carbon-neutrality")
    assert precedent["links"] == [{"target": "C1", "relation": "precedent"}, {"target": "C7", "relation": "precedent"}] and precedent["quote"].startswith("en ayant recours")
    substantiate_index = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.started" and env["payload"]["stage"] == "substantiate")
    substantiate_done = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.completed" and env["payload"]["stage"] == "substantiate")
    assert all(substantiate_index < i < substantiate_done for i, (_, env) in enumerate(received) if env["type"] == "evidence.added" and env["payload"]["evidence"]["id"][0] in "KP")
    for _, env in received:
        entity = env["payload"].get("score") or env["payload"].get("verdict") or env["payload"].get("argument") or env["payload"].get("omission")
        if entity:
            assert not {"E8", "E8b", "E8c", "E9", "E11", "E12"} & set(entity.get("evidence_ids", [])), "references to replaced evidence are stripped"
    for dimension in ("support", "materiality"):
        scored = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == dimension]
        assert len(scored) == 25 and all(s["stage"] == "verify" for s in scored), f"{dimension} is scored live by external verification"
    consistency_scores = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "consistency"]
    assert len(consistency_scores) == 25 and all(s["stage"] == "consistency" for s in consistency_scores), "consistency is scored live by the self-consistency evaluator (step 15)"
    assert not {"E1", "E1b", "E7", "E13", "E14", "E15"} & set(evidence), "the recording's self-consistency sources are replaced"
    statements = [e for e in evidence.values() if e["stage"] == "consistency"]
    assert len(statements) == 6 and all(e["verified"] and e["quote"] and e["url"] for e in statements)
    assert sorted({e["tier"] for e in statements}) == [2, 5], "an assured filing and the company's own material"
    assert evidence[consistency_ids["E1"]]["links"] == [{"target": "C1", "relation": "contradicts"}, {"target": "C7", "relation": "contradicts_framing"}], \
        "the company contradicted by its own annual report: the visual check for step 15"
    consistency_index = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.started" and env["payload"]["stage"] == "consistency")
    consistency_done = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.completed" and env["payload"]["stage"] == "consistency")
    assert all(consistency_index < i < consistency_done for i, (_, env) in enumerate(received) if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "consistency")
    assert all(consistency_index < i < consistency_done for i, (_, env) in enumerate(received) if env["type"] == "evidence.added" and env["payload"]["evidence"]["id"][0] == "S")
    verify_index = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.started" and env["payload"]["stage"] == "verify")
    verify_done = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.completed" and env["payload"]["stage"] == "verify")
    assert all(verify_index < i < verify_done for i, (_, env) in enumerate(received) if env["type"] == "evidence.added" and env["payload"]["evidence"]["id"][0] in "VN")
    assert all(verify_index < i < verify_done for i, (_, env) in enumerate(received) if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] in ("support", "materiality"))
    first_score = next(i for i, (_, env) in enumerate(received) if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "support")
    assert all(i < first_score for i, (_, env) in enumerate(received) if env["type"] == "evidence.added" and env["payload"]["evidence"]["id"][0] in "VN"), "every retrieved item exists before a score cites it"
    signals = [env["payload"]["signal"] for _, env in received if env["type"] == "language.signal"]
    assert [g["id"] for g in signals] == [f"L{i}" for i in range(1, 25)]
    language_index = types.index("stage.started", types.index("stage.completed", types.index("claim.extracted")))
    language_done = next(i for i, (_, env) in enumerate(received) if env["type"] == "stage.completed" and env["payload"]["stage"] == "language")
    assert all(language_index < i < language_done for i, (_, env) in enumerate(received) if env["type"] == "language.signal")
    clarity = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "clarity"]
    assert len(clarity) == 25 and all(s["stage"] == "language" for s in clarity)
    assert all(language_index < i < language_done for i, (_, env) in enumerate(received) if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "clarity")
    golden = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text())
    golden_verdicts = {v["claim_id"]: v for v in golden["verdicts"]}
    for _, env in received:
        if env["type"] == "verdict.issued":
            v = env["payload"]["verdict"]
            assert (v["likelihood"], v["category"]) == (golden_verdicts[v["claim_id"]]["likelihood"], golden_verdicts[v["claim_id"]]["category"]), "golden clarity leaves every golden verdict as it was"
    claims = [env["payload"]["claim"] for _, env in received if env["type"] == "claim.extracted"]
    assert {c["id"] for c in claims} == {f"C{i}" for i in range(1, 26)}, "every live claim took its golden id"
    assert [c["spans"][0]["start"] for c in claims] == sorted(c["spans"][0]["start"] for c in claims), "emitted in document order"
    completed = received[-1][1]["payload"]
    assert completed["counts"] == {"claims": 25, "signals": 24, "evidence": 29, "omissions": 4}
    check_contract(received, analysis_level=True)
    for _, env in received:
        if env["type"] in ("claim.extracted", "language.signal"):
            entity = env["payload"].get("claim") or env["payload"]["signal"]
            for span in entity["spans"]:
                assert ingested["text"][span["start"] : span["end"]] == span["text"]
    t_ms = [env["t_ms"] for _, env in received]
    assert t_ms == sorted(t_ms)
    final = client.get(f"/api/analyses/{summary['analysis_id']}").json()
    assert final["status"] == "completed"
    assert final["title"] == "Climate | Shell Global", "a live run takes its title from the ingested document"
    assert client.get("/api/analyses").json()[0]["title"] == "Climate | Shell Global"


def test_text_request_runs_the_whole_pipeline_on_a_page_with_no_recording(client, fake_fetch, fake_extract, fake_language, fake_substantiate, fake_verify):
    from auditor.language import ClarityScore, FoundSignal, LanguageReview
    from auditor.substantiate import Match, Matches
    from auditor.verify import Assessment, Assessments, Bearing, Computation, Computations, Finding, Findings

    fake_extract.extraction = Extraction(claims=[ExtractedClaim(quote="We are carbon neutral", type="vague_attribute", scope="company", attribute="carbon neutral")])
    fake_language.review = LanguageReview(
        signals=[FoundSignal(level="claim", kind="undefined_term", polarity="flag", quotes=["carbon neutral"], claim_ids=["C1"], note="No standard named.", strength=0.7)],
        clarity=[ClarityScore(claim_id="C1", score=0.75, confidence=0.9, basis="Undefined term.")],
    )
    fake_substantiate.matches = Matches(matches=[Match(evidence_id="K1", claim_ids=["C1"], note="generic term")])
    fake_verify.findings = Findings(findings=[
        Finding(kind="filing", independence="assured_filing", name="Acme Annual Report 2025, p. 4", publisher="Acme plc",
                url="https://acme.example/annual-report", quote="Our residual emissions were offset with purchased credits.",
                bears_on=[Bearing(claim_id="C1", relation="contradicts_framing")], note="Offsets, not abatement."),
        Finding(kind="company_page", independence="company", name="Acme, our climate page", url="https://acme.example/climate",
                quote="We are proud of our progress.", bears_on=[Bearing(claim_id="C1", relation="supports")]),
    ])
    fake_verify.computations = Computations(computations=[Computation(
        name="Share of emissions offset rather than cut", expression="offset_mt / total_mt * 100",
        inputs={"offset_mt": 40, "total_mt": 50}, value=80.0, unit="%",
        sentence="80% of the claimed neutrality is bought credits, not emissions cut.",
        derived_from=["V1"], bears_on=[Bearing(claim_id="C1", relation="contradicts_framing")],
    )])
    fake_verify.assessments = Assessments(assessments=[Assessment(
        claim_id="C1", support=0.7, support_confidence=0.7, support_basis="Neutrality rests on offsets.",
        support_evidence_ids=["K1", "V1", "N1"], materiality=0.6, materiality_confidence=0.7,
        materiality_basis="Most of it is bought, not cut.", materiality_evidence_ids=["N1"], gap="Say offsets are used.",
    )])
    created = client.post("/api/analyses", json={"kind": "text", "text": "# Label\n\nWe are carbon neutral.", "title": "Label"})
    assert created.status_code == 201
    summary = created.json()
    assert summary["source"] == {"kind": "text", "title": "Label", "chars": 31}
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[:2] == ["analysis.started", "stage.started"]
    assert "document.ingested" in types
    assert types[-2:] == ["stage.completed", "analysis.completed"]
    assert received[-2][1]["payload"]["stage"] == "summary", "nothing is replayed, so the run finishes on its own"
    header = next(env["payload"] for _, env in received if env["type"] == "summary.updated")
    assert header["final"] is True and header["summary"]["claim_count"] == 1
    assert header["summary"]["ext"]["drivers"]["headline"] == ["C1"], "the header says which claim it came from"
    signal = next(env["payload"]["signal"] for _, env in received if env["type"] == "language.signal")
    assert signal["id"] == "L1" and signal["spans"] == [{"text": "carbon neutral", "start": 14, "end": 28}] and signal["claim_ids"] == ["C1"]
    scores = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored"]
    assert scores[0] == {"claim_id": "C1", "dimension": "clarity", "score": 0.75, "confidence": 0.9, "basis": "Undefined term.", "stage": "language"}
    assert scores[1] == {"claim_id": "C1", "dimension": "support", "score": 0.7, "confidence": 0.7, "basis": "Neutrality rests on offsets.", "stage": "verify", "evidence_ids": ["K1", "V1", "N1"], "ext": {"gap": "Say offsets are used."}}
    assert scores[2] == {"claim_id": "C1", "dimension": "materiality", "score": 0.6, "confidence": 0.7, "basis": "Most of it is bought, not cut.", "stage": "verify", "evidence_ids": ["N1"]}
    assert [x["dimension"] for x in scores] == ["clarity", "support", "materiality", "consistency"], "every dimension is live; the verdict layer is what needs a recording"
    items = {env["payload"]["evidence"]["id"]: env["payload"]["evidence"] for _, env in received if env["type"] == "evidence.added"}
    assert items["K1"]["links"] == [{"target": "C1", "relation": "criteria"}] and items["K1"]["url"].startswith("https://www.gov.uk/") and items["K1"]["quote"] and items["K1"]["stage"] == "substantiate"
    assert items["V1"]["tier"] == 2 and items["V1"]["verified"] and items["V1"]["quote"].startswith("Our residual emissions") and items["V1"]["verification"] == "fetched_exact"
    assert items["V2"]["tier"] == 5 and items["V2"]["links"] == [{"target": "C1", "relation": "context"}], "the company's own page cannot substantiate its own claim (D5)"
    assert "context, not substantiation" in items["V2"]["note"]
    assert items["N1"]["kind"] == "computation" and items["N1"]["tier"] == 2 and items["N1"]["derived_from"] == ["V1"]
    assert items["N1"]["computation"] == {"formula": "offset_mt / total_mt * 100", "inputs": {"offset_mt": 40, "total_mt": 50}, "result": "80% of the claimed neutrality is bought credits, not emissions cut."}
    assert items["N1"]["ext"]["recomputed"] == 80.0 and items["N1"]["verification"] == "computed"
    assert types.index("evidence.added") < types.index("dimension.scored", types.index("evidence.added")), "the criteria item exists before the score cites it"
    stages = [(env["type"], env["payload"]["stage"]) for _, env in received if env["type"] in ("stage.started", "stage.completed")]
    assert stages == [(t, stage) for stage in ("ingest", "extract", "language", "substantiate", "verify", "consistency", "omissions", "verdict", "summary") for t in ("stage.started", "stage.completed")]
    check_contract(received)
    document = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert document["text"] == "Label\n\nWe are carbon neutral." and document["title"] == "Label"
    claims = [env["payload"]["claim"] for _, env in received if env["type"] == "claim.extracted"]
    assert len(claims) == 1 and claims[0]["id"] == "C1" and claims[0]["spans"][0] == {"text": "We are carbon neutral", "start": 7, "end": 28}
    assert claims[0]["paragraph"] == "P1"
    extract_index = types.index("stage.started", 2)
    assert types.index("claim.extracted") > extract_index and types.index("stage.completed", extract_index) > types.index("claim.extracted")
    assert client.get(f"/api/analyses/{summary['analysis_id']}").json()["status"] == "completed"


def test_pdf_request(client, fake_fetch):
    created = client.post("/api/analyses", json={"kind": "pdf", "filename": "acme.pdf", "data_base64": pdf_base64(2)})
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["source"]["kind"] == "pdf" and summary["source"]["filename"] == "acme.pdf" and summary["source"]["bytes"] > 1000
    received = read_sse(client, summary["events_url"])
    document = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert document["title"] == "Acme plc: Towards net zero" and document["text_type"] == "report"
    assert types_of(received)[-1] == "analysis.completed"
    assert client.post("/api/analyses", json={"kind": "pdf", "filename": "x.pdf", "data_base64": "%%%"}).status_code == 201
    assert client.post("/api/analyses", json={"kind": "pdf"}).status_code == 422


def test_unreadable_url_fails_at_ingest_with_the_reason(client, fake_fetch):
    fake_fetch.refuse("https://example.com", 403)
    summary = client.post("/api/analyses", json={"kind": "url", "url": "https://example.com"}).json()
    received = read_sse(client, summary["events_url"])
    assert types_of(received) == ["analysis.started", "stage.started", "analysis.failed"]
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "ingest" and "HTTP 403" in failed["error"] and "Wayback" in failed["error"]


def test_blocked_demo_page_falls_back_to_the_curated_copy_and_still_replays(client, fake_fetch, real_shell):
    fake_fetch.refuse(SHELL_URL, 403)
    summary = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6}).json()
    received = read_sse(client, summary["events_url"])
    document = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert document["source"]["fixture_path"] == "demo-documents/shell-climate-2026-09-19.md"
    assert types_of(received)[-1] == "analysis.completed"


def test_live_run_is_saved_like_any_other(client, fake_fetch, runs_dir):
    summary = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral."}).json()
    read_sse(client, summary["events_url"])
    saved = list(runs_dir.glob("*.jsonl"))
    assert len(saved) == 1
    lines = [json.loads(line) for line in saved[0].read_text().splitlines()]
    assert lines[0]["payload"]["mode"] == "live"
    assert "We are carbon neutral." not in json.dumps(lines[0]), "the pasted text is not in the source summary"
    assert any(line["type"] == "document.ingested" for line in lines)


def test_a_claim_the_recording_never_had_is_analysed_like_the_rest(client, shell_pages, real_shell, fake_extract):
    """Three golden claims found (one with its quote slightly off), plus one claim the golden
    reference does not have. Every evaluator runs live, so the fourth claim is scored on all
    four dimensions and decided like the rest; what the recording still supplies reaches only
    the three it knows, and the log still satisfies the contract."""
    golden = golden_extraction().claims
    fake_extract.extraction = Extraction(
        claims=[
            golden[0],  # C1
            golden[13].model_copy(update={"quote": golden[13].quote.replace("36%", "36%").rstrip(".") + "."}),  # C14, trailing stop
            golden[22],  # C23
            ExtractedClaim(quote="See how we are providing energy today", type="vague_attribute", scope="company", attribute="providing energy"),
        ]
    )
    summary = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6}).json()
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[-1] == "analysis.completed"
    claims = [env["payload"]["claim"] for _, env in received if env["type"] == "claim.extracted"]
    assert [c["id"] for c in claims] == ["C1", "C14", "C26", "C23"], "matched claims take the recorded ids; the new one is numbered after them"
    verdicts = {env["payload"]["verdict"]["claim_id"] for _, env in received if env["type"] == "verdict.issued"}
    assert verdicts == {"C1", "C14", "C23", "C26"}, "every claim is scored on every dimension, so every claim is decided"
    scores = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored"]
    for dimension in ("clarity", "support", "materiality", "consistency"):
        assert sorted(s["claim_id"] for s in scores if s["dimension"] == dimension) == ["C1", "C14", "C23", "C26"], f"live {dimension} for every claim, the new one included"
    assert all(s["stage"] == "language" for s in scores if s["dimension"] == "clarity")
    assert all(s["stage"] == "verify" for s in scores if s["dimension"] in ("support", "materiality"))
    for _, env in received:
        if env["type"] == "language.signal":
            assert all(c in {"C1", "C14", "C23"} for c in env["payload"]["signal"]["claim_ids"])
        if env["type"] == "evidence.added":
            assert all(l["target"] in {"C1", "C14", "C23"} or l["target"].startswith("O") for l in env["payload"]["evidence"]["links"])
    final = next(env["payload"]["summary"] for _, env in received if env["type"] == "summary.updated")
    assert final["claim_count"] == 4 and sum(final["verdict_distribution"].values()) == 4
    assert all(x["target"] in {"C1", "C14", "C23", "C26"} or x["target"].startswith("O") for x in final["top_issues"] + final["credit"])
    assert "C26" in {x["target"] for x in final["top_issues"] + final["credit"]}, "the new claim reaches the header like any other"
    assert [x["rank"] for x in final["top_issues"]] == list(range(1, len(final["top_issues"]) + 1))
    completed = received[-1][1]["payload"]["counts"]
    assert completed["claims"] == 4 and completed["omissions"] == 0, "the omissions stage ran live and this test gives it nothing to find"
    notes = [env["payload"]["text"] for _, env in received if env["type"] == "debug.note"]
    assert any("3 of 25 reference claims found" in n and "new C26" in n for n in notes), notes
    check_contract(received)


def test_live_clarity_moves_the_verdicts_the_layer_issues(client, shell_pages, real_shell, fake_extract, fake_language, fake_substantiate, fake_verify, fake_consistency, fake_omissions, fake_verdict):
    """C14 (Scope 1 and 2 down 36%) is `supported` in the recording with clarity 0.15; a live
    clarity of 0.9 makes it the weakest link, so the rule says `unsubstantiated` at likelihood
    0.9 — and the judge, arguing the reference's own case, does not agree. The dissent is
    recorded and costs the verdict a tenth of its confidence. C3 is `unsubstantiated` on
    clarity 0.85 alone; a live 0.2 leaves its next-weakest dimension to set the verdict. The
    other live stages reproduce the reference, so clarity is the only thing that moved."""
    fake_substantiate.matches, fake_substantiate.assessments = golden_substantiation()
    fake_verify.findings, fake_verify.computations, fake_verify.assessments, _, _ = golden_verification()
    fake_consistency.statements, fake_consistency.assessments, _, fake_consistency.pages = golden_consistency()
    fake_omissions.coverages = golden_omissions()
    fake_extract.extraction = golden_extraction()
    fake_verdict.prosecution, fake_verdict.defence, fake_verdict.judgments = golden_debate()
    review = golden_review()
    review.clarity = [
        c.model_copy(update={"score": 0.9, "confidence": 0.95}) if c.claim_id == "C14"
        else c.model_copy(update={"score": 0.2, "confidence": 0.5}) if c.claim_id == "C3"
        else c
        for c in review.clarity
    ]
    fake_language.review = review
    summary = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6}).json()
    received = read_sse(client, summary["events_url"])
    assert types_of(received)[-1] == "analysis.completed"
    verdicts = {env["payload"]["verdict"]["claim_id"]: env["payload"]["verdict"] for _, env in received if env["type"] == "verdict.issued"}
    golden = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text())
    scores = {(s["claim_id"], s["dimension"]): s for s in golden["scores"]}

    assert verdicts["C14"]["likelihood"] == 0.9 and verdicts["C14"]["category"] == "unsubstantiated"
    assert verdicts["C14"]["rationale"] == next(v for v in golden["verdicts"] if v["claim_id"] == "C14")["rationale"], "the judge's words, not the rule's"
    judge = verdicts["C14"]["ext"]["judge"]
    assert judge["own_category"] == "supported" and judge["agreement"] == 0.0, "the judge reached the reference's category, the rule did not"
    assert verdicts["C14"]["confidence"] == 0.8 == round(0.95 - 0.05 - 0.10, 2), "clarity's confidence, less the humility and the dissent"
    assert "the judge did not reach the same category" in verdicts["C14"]["ext"]["confidence_basis"]

    others = max(scores[("C3", d)]["score"] for d in ("support", "materiality", "consistency"))
    assert verdicts["C3"]["likelihood"] == others, "clarity no longer the weakest link"
    live_c3 = {d: scores[("C3", d)] for d in ("support", "materiality", "consistency")} | {"clarity": {"score": 0.2, "confidence": 0.5}}
    assert verdicts["C3"]["category"] == derive_category(live_c3, False)
    assert verdicts["C3"]["confidence"] >= 0.4, "confidence stays within a tenth of the lowest dimension confidence"

    final = next(env["payload"]["summary"] for _, env in received if env["type"] == "summary.updated")
    assert sum(final["verdict_distribution"].values()) == 25
    assert final["verdict_distribution"] != golden["summary"]["verdict_distribution"]
    assert final["dimensions"]["clarity"]["score"] != golden["summary"]["dimensions"]["clarity"]["score"], "the document's Clarity is the mean of the live scores"
    notes = [env["payload"]["text"] for _, env in received if env["type"] == "debug.note"]
    assert any("24 of 25 categories agree" in n and "mean absolute likelihood difference 0.03" in n for n in notes), notes
    assert any("The judge dissented from the derived category on 1 claims" in n and "C14 rule unsubstantiated / judge supported" in n for n in notes), notes
    check_contract(received, analysis_level=True)


def test_language_failure_is_reported_at_language(client, fake_fetch, fake_extract, fake_language):
    fake_extract.extraction = Extraction(claims=[ExtractedClaim(quote="We are carbon neutral", type="vague_attribute", scope="company", attribute="carbon neutral")])
    fake_language.error = LlmError("the model's stream went quiet")
    summary = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral."}).json()
    received = read_sse(client, summary["events_url"])
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "language" and failed["error"] == "Language review failed: the model's stream went quiet"
    assert "claim.extracted" in types_of(received), "the claims found are kept"


def test_extraction_failure_is_reported_at_extract(client, fake_fetch, fake_extract):
    fake_extract.error = LlmError("No the model credentials found.")
    summary = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral."}).json()
    received = read_sse(client, summary["events_url"])
    assert types_of(received)[-1] == "analysis.failed"
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "extract" and "Claim extraction failed: No the model credentials found." == failed["error"]
    assert "document.ingested" in types_of(received)


def test_substantiation_failure_is_reported_at_substantiate(client, fake_fetch, fake_extract, fake_substantiate):
    fake_extract.extraction = Extraction(claims=[ExtractedClaim(quote="We are carbon neutral", type="vague_attribute", scope="company", attribute="carbon neutral")])
    fake_substantiate.error = LlmError("the model's stream went quiet")
    summary = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral."}).json()
    received = read_sse(client, summary["events_url"])
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "substantiate" and failed["error"] == "Substantiation failed: the model's stream went quiet"
    assert "language.signal" not in types_of(received) and "dimension.scored" in types_of(received), "the language stage's output is kept"


def test_a_broken_knowledge_store_is_reported_at_substantiate(client, fake_fetch, fake_extract, fake_substantiate):
    from auditor.knowledge import KnowledgeError

    fake_extract.extraction = Extraction(claims=[ExtractedClaim(quote="We are carbon neutral", type="vague_attribute", scope="company", attribute="carbon neutral")])
    fake_substantiate.error = KnowledgeError("criteria.json entry 3 (x): verified but no quote")
    summary = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral."}).json()
    received = read_sse(client, summary["events_url"])
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "substantiate" and failed["error"] == "The knowledge stores could not be read: criteria.json entry 3 (x): verified but no quote"


def test_the_substantiation_evaluator_never_scores_support_and_hands_its_evidence_on(client, shell_pages, real_shell, fake_extract, fake_substantiate, fake_verify):
    """Support is scored once, by external verification, from the criteria and precedents and
    the facts together (CONTRACT.md §6, D6), so the substantiation evaluator only matches,
    whether or not a recording exists, and passes what it matched to the next stage."""
    from auditor.substantiate import Match, Matches

    fake_substantiate.matches = Matches(matches=[Match(evidence_id="K1", claim_ids=["C1"], note="generic term")])
    requests = [
        (golden_extraction(), {"kind": "url", "url": SHELL_URL, "speed": 1e6}),
        (Extraction(claims=[ExtractedClaim(quote="We are carbon neutral", type="vague_attribute", scope="company", attribute="carbon neutral")]),
         {"kind": "text", "text": "We are carbon neutral."}),
    ]
    for extraction, request in requests:
        fake_extract.extraction = extraction
        fake_verify.calls.clear()
        summary = client.post("/api/analyses", json=request).json()
        received = read_sse(client, summary["events_url"])
        assert fake_substantiate.calls[-1]["score"] is False
        assert [e["id"] for e in fake_verify.calls[-1]["prior_evidence"]] == ["K1"], "the criteria reach the stage that scores Support"
        support = [env["payload"]["score"] for _, env in received if env["type"] == "dimension.scored" and env["payload"]["score"]["dimension"] == "support"]
        assert support and all(s["stage"] == "verify" for s in support)


def test_verdict_failure_is_reported_at_verdict(client, shell_pages, real_shell, fake_extract, fake_verdict):
    """The verdict layer runs inside the replay, so it cannot return to `run_live` to be
    caught. It must still name itself the way every other stage does, rather than falling
    through to the store's generic producer-failed handler."""
    fake_extract.extraction = golden_extraction()
    fake_verdict.error = LlmError("the model did not answer within 600 s.")
    summary = client.post("/api/analyses", json={"kind": "url", "url": SHELL_URL, "speed": 1e6}).json()
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[-1] == "analysis.failed" and types.count("analysis.failed") == 1
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "verdict", "not the store's untyped 'LlmError: ...' fallback"
    assert failed["error"] == "The verdict layer failed: the model did not answer within 600 s."
    assert [e["payload"]["stage"] for _, e in received if e["type"] == "stage.started"][-1] == "verdict"
    assert "summary.updated" not in types, "the replay stopped rather than carrying on to the summary"
