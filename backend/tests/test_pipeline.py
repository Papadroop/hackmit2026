"""Live analyses through the API: ingestion runs, and the stages after it replay from a
recording when one exists for the document."""

from __future__ import annotations

import json

from conftest import SHELL_URL, pdf_base64, read_sse, shell_fixture_document


def types_of(received):
    return [env["type"] for _, env in received]


def test_url_request_ingests_live_and_replays_the_recording_downstream(client, shell_pages, real_shell):
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
    assert "Replayed from recording shell-climate" in extract["payload"]["note"]
    notes = [env["payload"]["text"] for _, env in received if env["type"] == "debug.note"]
    assert any("replayed from recording 'shell-climate'" in n and "63 spans anchored" in n for n in notes), notes
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


def test_text_request_shows_the_document_and_stops_at_extract(client, fake_fetch):
    created = client.post("/api/analyses", json={"kind": "text", "text": "# Label\n\nWe are carbon neutral.", "title": "Label"})
    assert created.status_code == 201
    summary = created.json()
    assert summary["source"] == {"kind": "text", "title": "Label", "chars": 31}
    received = read_sse(client, summary["events_url"])
    types = types_of(received)
    assert types[:2] == ["analysis.started", "stage.started"]
    assert "document.ingested" in types
    assert types[-2:] == ["stage.started", "analysis.failed"]
    assert received[-2][1]["payload"]["stage"] == "extract"
    failed = received[-1][1]["payload"]
    assert failed["stage"] == "extract" and "not built yet" in failed["error"]
    document = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert document["text"] == "Label\n\nWe are carbon neutral." and document["title"] == "Label"
    assert client.get(f"/api/analyses/{summary['analysis_id']}").json()["status"] == "failed"


def test_pdf_request(client, fake_fetch):
    created = client.post("/api/analyses", json={"kind": "pdf", "filename": "acme.pdf", "data_base64": pdf_base64(2)})
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["source"]["kind"] == "pdf" and summary["source"]["filename"] == "acme.pdf" and summary["source"]["bytes"] > 1000
    received = read_sse(client, summary["events_url"])
    document = next(env for _, env in received if env["type"] == "document.ingested")["payload"]["document"]
    assert document["title"] == "Acme plc: Towards net zero" and document["text_type"] == "report"
    assert types_of(received)[-1] == "analysis.failed"
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
