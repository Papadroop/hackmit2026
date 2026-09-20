import json
import time

from fastapi.testclient import TestClient

from auditor.main import Settings, create_app
from conftest import read_sse

FAST = {"kind": "replay", "fixture": "quick", "speed": 1e6}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_fixture_listing_reports_broken_files(client):
    by_name = {f["name"]: f for f in client.get("/api/fixtures").json()}
    assert by_name["smoke"]["events"] == 15
    assert by_name["smoke"]["duration_ms"] == 6100
    assert by_name["smoke"]["types"]["stage.started"] == 6
    assert by_name["quick"]["events"] == 4
    assert "first event must be analysis.started" in by_name["broken"]["error"]


def test_replay_streams_every_event_in_order(client):
    created = client.post("/api/analyses", json=FAST)
    assert created.status_code == 201, created.text
    summary = created.json()
    assert summary["source"] == {"kind": "replay", "fixture": "quick", "speed": 1e6}

    received = read_sse(client, summary["events_url"])
    assert [event_id for event_id, _ in received] == [1, 2, 3, 4]
    assert [env["seq"] for _, env in received] == [1, 2, 3, 4]
    assert [env["type"] for _, env in received] == [
        "analysis.started", "stage.started", "stage.completed", "analysis.completed",
    ]
    assert [env["t_ms"] for _, env in received] == [0, 300, 600, 900], "replay keeps the log's own timing"

    final = client.get(f"/api/analyses/{summary['analysis_id']}").json()
    assert final["status"] == "completed"
    assert final["last_seq"] == 4


def test_stream_can_resume_after_a_seq(client):
    summary = client.post("/api/analyses", json=FAST).json()
    read_sse(client, summary["events_url"])  # let it finish
    url = summary["events_url"]

    assert [env["seq"] for _, env in read_sse(client, f"{url}?after=2")] == [3, 4]
    assert [env["seq"] for _, env in read_sse(client, url, headers={"Last-Event-ID": "3"})] == [4]
    assert read_sse(client, f"{url}?after=4") == []
    assert client.get(f"{url}?after=5").status_code == 400
    assert client.get(url, headers={"Last-Event-ID": "x"}).status_code == 400


def test_replay_honours_timing(client):
    summary = client.post("/api/analyses", json={"kind": "replay", "fixture": "quick", "speed": 1}).json()
    started = time.perf_counter()
    received = read_sse(client, summary["events_url"])
    elapsed = time.perf_counter() - started
    assert len(received) == 4
    assert 0.8 <= elapsed <= 3.0, f"expected about 0.9 s of replay, took {elapsed:.2f} s"

    summary = client.post("/api/analyses", json={"kind": "replay", "fixture": "quick", "speed": 3}).json()
    started = time.perf_counter()
    read_sse(client, summary["events_url"])
    assert time.perf_counter() - started < 0.8


def test_unknown_and_broken_fixtures(client):
    assert client.post("/api/analyses", json={"kind": "replay", "fixture": "nope"}).status_code == 404
    assert client.post("/api/analyses", json={"kind": "replay", "fixture": "../etc/passwd"}).status_code == 404
    broken = client.post("/api/analyses", json={"kind": "replay", "fixture": "broken"})
    assert broken.status_code == 422
    assert "first event must be analysis.started" in broken.json()["detail"]
    assert client.post("/api/analyses", json={"kind": "replay"}).status_code == 422
    assert client.post("/api/analyses", json={"kind": "replay", "fixture": "quick", "run": "x"}).status_code == 422
    assert client.post("/api/analyses", json={"kind": "replay", "fixture": "quick", "speed": 0}).status_code == 422
    assert client.post("/api/analyses", json={"kind": "pdf"}).status_code == 422
    assert client.get("/api/analyses/nope").status_code == 404
    assert client.get("/api/analyses/nope/events").status_code == 404


def test_live_requests_are_accepted(client, fake_fetch):
    """Ingestion (roadmap step 10) is built: text, URL and PDF requests start an analysis."""
    assert client.get("/api/documents").json()["live_analysis"] is True
    for body in ({"kind": "text", "text": "We are carbon neutral."}, {"kind": "url", "url": "https://example.com"}):
        response = client.post("/api/analyses", json=body)
        assert response.status_code == 201, body


def test_live_request_goes_through_the_same_stream(client, fake_fetch):
    created = client.post("/api/analyses", json={"kind": "text", "text": "We are carbon neutral.", "title": "Label"})
    assert created.status_code == 201
    summary = created.json()
    assert summary["source"] == {"kind": "text", "title": "Label", "chars": 22}
    received = read_sse(client, summary["events_url"])
    types = [env["type"] for _, env in received]
    assert types[:2] == ["analysis.started", "stage.started"]
    assert "document.ingested" in types and types[-1] == "analysis.completed"
    assert [env["payload"]["stage"] for _, env in received if env["type"] == "stage.started"] == [
        "ingest", "extract", "language", "substantiate", "verify", "consistency", "omissions", "verdict", "summary",
    ], "every stage runs live; a page with no recording of its own goes all the way through"
    assert "summary.updated" in types and received[-2][1]["payload"]["stage"] == "summary"
    assert client.get(f"/api/analyses/{summary['analysis_id']}").json()["status"] == "completed"


def test_cancel_emits_a_terminal_event(client):
    # Slow replay: the first event is immediate, the second is 300 s away.
    summary = client.post("/api/analyses", json={"kind": "replay", "fixture": "quick", "speed": 0.001}).json()
    analysis_id = summary["analysis_id"]
    deadline = time.time() + 2
    while client.get(f"/api/analyses/{analysis_id}").json()["last_seq"] < 1 and time.time() < deadline:
        time.sleep(0.01)
    assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
    final = client.get(f"/api/analyses/{analysis_id}").json()
    assert final["status"] == "failed"
    received = read_sse(client, summary["events_url"])
    assert [env["type"] for _, env in received] == ["analysis.started", "analysis.failed"]
    assert received[-1][1]["payload"]["error"] == "cancelled"
    assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204, "cancelling twice is harmless"


def test_runs_are_saved_and_can_be_replayed(client, runs_dir):
    summary = client.post("/api/analyses", json=FAST).json()
    read_sse(client, summary["events_url"])

    saved = list(runs_dir.glob("*.jsonl"))
    assert len(saved) == 1
    lines = saved[0].read_text().splitlines()
    assert len(lines) == 4
    assert json.loads(lines[0])["seq"] == 1

    log = client.get(f"/api/analyses/{summary['analysis_id']}/log")
    assert log.status_code == 200
    assert log.text.splitlines() == lines

    again = client.post("/api/analyses", json={"kind": "replay", "run": saved[0].stem, "speed": 1e6})
    assert again.status_code == 201, again.text
    assert again.json()["source"]["run"] == saved[0].stem
    assert [env["type"] for _, env in read_sse(client, again.json()["events_url"])][-1] == "analysis.completed"
    assert [a["analysis_id"] for a in client.get("/api/analyses").json()] == [
        again.json()["analysis_id"], summary["analysis_id"],
    ]


def test_fixture_names_and_titles(client, fixtures_dir):
    (fixtures_dir / "shell.events.jsonl").write_text(
        '{"t_ms": 0, "type": "analysis.started", "payload": {"contract_version": "1.0.0", "document_ref": {"title": "Climate | Shell Global"}}}\n'
        '{"t_ms": 10, "type": "analysis.completed", "payload": {}}\n'
    )
    by_name = {f["name"]: f for f in client.get("/api/fixtures").json()}
    assert by_name["shell"]["file"] == "shell.events.jsonl"
    assert by_name["shell"]["title"] == "Climate | Shell Global"
    assert by_name["smoke"]["title"] == "Transport smoke test"
    assert by_name["quick"]["title"] is None
    for name in ("shell", "shell.events", "shell.events.jsonl"):
        created = client.post("/api/analyses", json={"kind": "replay", "fixture": name, "speed": 1e6})
        assert created.status_code == 201, name
        assert created.json()["source"]["fixture"] == "shell"


def test_live_start_carries_the_contract_version(client, fake_fetch):
    fake_fetch.refuse("https://example.com", 403)
    summary = client.post("/api/analyses", json={"kind": "url", "url": "https://example.com"}).json()
    received = read_sse(client, summary["events_url"])
    started = received[0][1]["payload"]
    assert started["contract_version"] == "1.0.0"
    assert started["mode"] == "live"
    assert started["source"] == {"kind": "url", "url": "https://example.com"}
    assert received[-1][1]["payload"]["stage"] == "ingest"


def test_summary_carries_the_document_title(client):
    summary = client.post("/api/analyses", json={"kind": "replay", "fixture": "shell-climate", "speed": 1e6}).json()
    assert summary["title"] is None, "no events yet"
    read_sse(client, summary["events_url"])
    assert client.get(f"/api/analyses/{summary['analysis_id']}").json()["title"] == "Climate | Shell Global"
    assert client.get("/api/analyses").json()[0]["title"] == "Climate | Shell Global"


def test_built_frontend_gets_spa_fallback(tmp_path, fixtures_dir, demo_dir):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Greenwashing Auditor</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    settings = Settings(fixtures_dir=fixtures_dir, runs_dir=None, demo_documents_dir=demo_dir, frontend_dist=dist)
    with TestClient(create_app(settings)) as client:
        for path in ("/", "/a/abc123", "/anything/deeper"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Greenwashing Auditor" in response.text
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/favicon.svg").text == "<svg/>"
        assert client.get("/api/nope").status_code == 404
        assert client.get("/api/nope").headers["content-type"].startswith("application/json")
        assert client.get("/api/health").status_code == 200


def test_the_calibration_report_is_served_once_it_has_been_run(client, tmp_path, monkeypatch):
    """The metrics page (step 19) reads a file a run wrote, so the app never waits on a model."""
    from auditor.calibration import Case, measure, report

    path = tmp_path / "calibration.json"
    client.app.state.settings.calibration_file = path

    missing = client.get("/api/calibration")
    assert missing.status_code == 404 and "auditor.calibration run" in missing.json()["detail"]

    cases = [
        Case(store_id="a", claim_text="t", outcome="upheld", label=1, likelihood=0.9, category="unsubstantiated"),
        Case(store_id="b", claim_text="t", outcome="not_upheld", label=0, likelihood=0.2, category="supported"),
    ]
    path.write_text(json.dumps(report(cases, measure(cases))), encoding="utf-8")
    try:
        got = client.get("/api/calibration")
        assert got.status_code == 200
        body = got.json()
        assert body["metrics"]["precision"] == 1.0 and body["metrics"]["recall"] == 1.0
        assert body["metrics"]["caveat"] and body["metrics"]["bins"] and body["metrics"]["sweep"]
        assert [c["store_id"] for c in body["cases"]] == ["a", "b"]
        assert "leave-one-out" in body["method"]
        path.write_text("not json", encoding="utf-8")
        assert client.get("/api/calibration").status_code == 500
    finally:
        path.unlink(missing_ok=True)

