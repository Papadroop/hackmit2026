import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auditor.main import Settings, create_app

REPO = Path(__file__).resolve().parents[2]


def write_log(path: Path, events: list[dict]) -> Path:
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


QUICK = [
    {"t_ms": 0, "type": "analysis.started", "payload": {}},
    {"t_ms": 300, "type": "stage.started", "payload": {"stage": "extract"}},
    {"t_ms": 600, "type": "stage.completed", "payload": {"stage": "extract"}},
    {"t_ms": 900, "type": "analysis.completed", "payload": {}},
]


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "fixtures"
    directory.mkdir()
    shutil.copy(REPO / "fixtures" / "smoke.jsonl", directory / "smoke.jsonl")
    write_log(directory / "quick.jsonl", QUICK)
    (directory / "broken.jsonl").write_text('{"t_ms": 0, "type": "stage.started", "payload": {"stage": "x"}}\n')
    return directory


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


SHELL_URL = "https://www.shell.com/sustainability/climate.html"


@pytest.fixture
def demo_dir(tmp_path: Path, fixtures_dir: Path) -> Path:
    """Two demo texts and a recording that matches the first by URL."""
    directory = tmp_path / "demo-documents"
    directory.mkdir()
    (directory / "shell-climate-2026-09-19.md").write_text(
        "---\ntitle: Climate | Shell Global\ncompany: Shell plc\n"
        f"url: {SHELL_URL}\nretrieved: 2026-09-19\nwords_total: 2164\nrole: likely greenwashing\n---\n\n# Climate\n"
    )
    (directory / "orsted.md").write_text(
        "---\ntitle: Towards net zero | Ørsted\ncompany: Ørsted A/S\n"
        "url: https://orsted.com/en/about-us/sustainability/decarbonisation\nretrieved: 2026-09-19\nwords_total: ~700\n---\n"
    )
    write_log(fixtures_dir / "shell-climate.events.jsonl", [
        {"t_ms": 0, "type": "analysis.started", "payload": {"contract_version": "1.0.0", "document_ref": {"url": SHELL_URL + "/", "title": "Climate | Shell Global"}}},
        {"t_ms": 100, "type": "document.ingested", "payload": {"document": {"id": "d", "title": "Climate | Shell Global", "company": {"name": "Shell plc"}, "text_type": "policy", "source": {"url": SHELL_URL, "retrieved": "2026-09-19"}, "word_count": 2164}}},
        {"t_ms": 900, "type": "analysis.completed", "payload": {}},
    ])
    return directory


@pytest.fixture
def client(fixtures_dir: Path, runs_dir: Path, demo_dir: Path):
    settings = Settings(fixtures_dir=fixtures_dir, runs_dir=runs_dir, demo_documents_dir=demo_dir, frontend_dist=None)
    with TestClient(create_app(settings)) as client:
        yield client


def read_sse(client: TestClient, url: str, headers: dict | None = None) -> list[tuple[int | None, dict]]:
    """Collect (id, envelope) pairs from an SSE response until the server closes it."""
    received: list[tuple[int | None, dict]] = []
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        event_id: int | None = None
        data: list[str] = []
        for line in response.iter_lines():
            if line == "":
                if data:
                    received.append((event_id, json.loads("\n".join(data))))
                event_id, data = None, []
            elif line.startswith(":"):
                continue
            elif line.startswith("id: "):
                event_id = int(line[4:])
            elif line.startswith("data: "):
                data.append(line[6:])
    return received


# ----------------------------------------------------------------------------- ingestion helpers

import base64  # noqa: E402
import gzip  # noqa: E402

DATA = Path(__file__).parent / "data"
SHELL_MODEL_URL = "https://www.shell.com/sustainability/climate.model.json"
APPLE_URL = "https://www.apple.com/newsroom/2023/09/apple-unveils-its-first-carbon-neutral-products/"
ORSTED_URL = "https://orsted.com/en/about-us/sustainability/decarbonisation"


def data_text(name: str) -> str:
    path = DATA / name
    if name.endswith(".gz"):
        return gzip.decompress(path.read_bytes()).decode("utf-8")
    return path.read_text(encoding="utf-8")


def shell_fixture_document() -> dict:
    return json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))["document"]


def make_pdf(pages: int = 3, *, two_columns: bool = False) -> bytes:
    """A small report with a running header, page numbers, a title, headings, hyphenated line
    breaks, bullets and small-print footnotes. Optionally a two-column page."""
    import pymupdf

    body = [
        "Our operations reduced absolute Scope 1 and 2 emis-",
        "sions by 36% against the 2016 baseline, while produc-",
        "tion volumes stayed flat. We continue to invest in",
        "renewable electricity for our sites.",
    ]
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 30), "Acme plc Sustainability Report 2025", fontsize=8)
        page.insert_text((280, 820), f"Page {n} of {pages}", fontsize=8)
        y = 100
        if n == 1:
            page.insert_text((72, y), "Acme plc: Towards net zero", fontsize=22)
            y += 40
            page.insert_text((72, y), "A message from our chief executive", fontsize=14)
        else:
            page.insert_text((72, y), f"Chapter {n}: {'Progress' if n == 2 else 'Targets'} on our journey", fontsize=14)
        y += 28
        if two_columns and n == 2:
            for i, line in enumerate(["Left column first line", "left column second line.", "Left column third line."]):
                page.insert_text((72, y + 14 * i), line, fontsize=10)
            for i, line in enumerate(["Right column first line", "right column second line.", "Right column third line."]):
                page.insert_text((320, y + 14 * i), line, fontsize=10)
            y += 14 * 4
        for line in body:
            page.insert_text((72, y), line, fontsize=10)
            y += 14
        y += 10
        for item in ["• Scope 1 and 2 emissions down 36% since 2016", "• Methane intensity held below 0.2%", "• Routine flaring ended in 2025"]:
            page.insert_text((80, y), item, fontsize=10)
            y += 14
        y += 10
        page.insert_text((72, y), f"{n} Figures are assured to a limited level by our auditor.", fontsize=7)
    return doc.tobytes()


def pdf_base64(pages: int = 2) -> str:
    return base64.b64encode(make_pdf(pages)).decode("ascii")


class FakeFetch:
    """Stands in for auditor.ingest.fetch.fetch: a table of URL -> Fetched or FetchError."""

    def __init__(self) -> None:
        from auditor.ingest.fetch import FetchError, Fetched

        self.Fetched = Fetched
        self.FetchError = FetchError
        self.responses: dict[str, object] = {}
        self.calls: list[str] = []

    def html(self, url: str, body: str, *, final_url: str | None = None) -> "FakeFetch":
        self.responses[url] = self.Fetched(final_url or url, 200, "text/html; charset=utf-8", body.encode("utf-8"), "utf-8")
        return self

    def json(self, url: str, body: str) -> "FakeFetch":
        self.responses[url] = self.Fetched(url, 200, "application/json;charset=utf-8", body.encode("utf-8"), "utf-8")
        return self

    def pdf(self, url: str, body: bytes) -> "FakeFetch":
        self.responses[url] = self.Fetched(url, 200, "application/pdf", body, None)
        return self

    def plain(self, url: str, body: str) -> "FakeFetch":
        self.responses[url] = self.Fetched(url, 200, "text/plain; charset=utf-8", body.encode("utf-8"), "utf-8")
        return self

    def refuse(self, url: str, status: int | None = 403) -> "FakeFetch":
        self.responses[url] = self.FetchError(f"{url} answered HTTP {status}" if status else f"{url} could not be fetched", status=status)
        return self

    def __call__(self, url: str, **_: object):
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            raise self.FetchError(f"{url} answered HTTP 404", status=404)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake_fetch(monkeypatch) -> FakeFetch:
    """No test touches the network: every fetch and every Wayback lookup goes through this."""
    from auditor.ingest import fetch as fetch_module

    fake = FakeFetch()
    monkeypatch.setattr(fetch_module, "fetch", fake)
    monkeypatch.setattr(fetch_module, "wayback_snapshot", lambda url, **_: None)
    return fake


@pytest.fixture
def shell_pages(fake_fetch: FakeFetch) -> FakeFetch:
    """The live Shell page as fetched on 2026-09-19: a JavaScript shell, and its content model."""
    fake_fetch.html(SHELL_URL, data_text("shell-climate.shell.html"))
    fake_fetch.json(SHELL_MODEL_URL, data_text("shell-climate.model.json"))
    return fake_fetch


@pytest.fixture
def real_shell(fixtures_dir: Path, demo_dir: Path) -> None:
    """The real Shell recording and curated copy, in place of the stubs."""
    shutil.copy(REPO / "fixtures" / "shell-climate.jsonl", fixtures_dir / "shell-climate.jsonl")
    (fixtures_dir / "shell-climate.events.jsonl").unlink()
    shutil.copy(REPO / "demo-documents" / "shell-climate-2026-09-19.md", demo_dir / "shell-climate-2026-09-19.md")
