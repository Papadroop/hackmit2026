from pathlib import Path

from auditor.documents import list_documents, parse_frontmatter, parse_int
from conftest import SHELL_URL, write_log


def test_frontmatter_is_flat_key_values():
    text = "---\ntitle: A | B\nurl: https://x.y/z\nwords_total: ~700\nweird line without colon\n---\nbody: not parsed\n"
    assert parse_frontmatter(text) == {"title": "A | B", "url": "https://x.y/z", "words_total": "~700"}
    assert parse_frontmatter("no front matter") == {}


def test_parse_int_is_lenient():
    assert parse_int("4093") == 4093
    assert parse_int("~700") == 700
    assert parse_int("2,164") == 2164
    assert parse_int("unknown") is None
    assert parse_int(None) is None


def test_documents_join_recordings_by_url(demo_dir: Path, fixtures_dir: Path):
    write_log(fixtures_dir / "other.jsonl", [
        {"t_ms": 0, "type": "analysis.started", "payload": {"contract_version": "1.0.0", "document_ref": {"url": "https://example.com/report", "title": "Example report"}}},
        {"t_ms": 5, "type": "analysis.completed", "payload": {}},
    ])
    response = list_documents(demo_dir, fixtures_dir, live_analysis=False)

    by_title = {d.title: d for d in response.documents}
    shell = by_title["Climate | Shell Global"]
    assert shell.company == "Shell plc"
    assert shell.words == 2164
    assert shell.text_type == "policy", "taken from the recording's document.ingested"
    assert [r.fixture for r in shell.recordings] == ["shell-climate"]
    assert shell.recordings[0].events == 3 and shell.recordings[0].duration_ms == 900

    orsted = by_title["Towards net zero | Ørsted"]
    assert orsted.words == 700
    assert orsted.recordings == []

    example = by_title["Example report"]
    assert example.id == "other" and example.url == "https://example.com/report"
    assert [r.fixture for r in example.recordings] == ["other"]

    assert "Transport smoke test" not in by_title, "a recording without a document URL is not a document"
    assert [d.title for d in response.documents] == [
        "Climate | Shell Global", "Example report", "Towards net zero | Ørsted",
    ], "openable first, curated before stray recordings"
    assert [d.curated for d in response.documents] == [True, False, True]
    assert [i.file for i in response.invalid_recordings] == ["broken.jsonl"]
    assert "first event must be analysis.started" in response.invalid_recordings[0].error
    assert response.live_analysis is False, "as passed in"
    assert all(not hasattr(d, "role") for d in response.documents)


def test_documents_endpoint(client):
    body = client.get("/api/documents").json()
    assert body["live_analysis"] is True, "ingestion is built (roadmap step 10)"
    titles = [d["title"] for d in body["documents"]]
    assert titles[0] == "Climate | Shell Global"
    assert "role" not in body["documents"][0]
