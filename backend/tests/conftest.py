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


# ----------------------------------------------------------------------------- extraction (step 11)


def golden_extraction() -> "Extraction":
    """What a perfect extractor would return for the Shell page: the golden claims as quotes."""
    from auditor.extract import ExtractedClaim, Extraction

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    claims = []
    for c in analysis["claims"]:
        claims.append(
            ExtractedClaim(
                quote=c["spans"][0]["text"],
                repeats=[s["text"] for s in c["spans"][1:]],
                type=c["type"],
                scope=c["scope"],
                scope_note=c.get("scope_note"),
                attribute=c["attribute"],
                quantity=c.get("quantity"),
                baseline=c.get("baseline"),
                timeframe=c.get("timeframe"),
                note=c.get("note"),
            )
        )
    return Extraction(claims=claims)


class FakeExtractor:
    """Stands in for auditor.extract.extract_claims: returns a canned Extraction (default: none),
    assembled by the real placement code so spans, ids and paragraphs are computed as in production."""

    def __init__(self) -> None:
        from auditor.extract import Extraction

        self.extraction = Extraction(claims=[])
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, llm=None, on_progress=None):
        from auditor.extract import ExtractResult, assemble

        self.calls.append(document)
        if self.error is not None:
            raise self.error
        # The real extractor reports each claim as the model writes it, before any of them can
        # be emitted; the fake does the same so the pipeline's heartbeat is exercised.
        for n in range(1, len(self.extraction.claims) + 1):
            if on_progress is not None:
                await on_progress(n)
        result: ExtractResult = assemble(self.extraction, document)
        result.notes.append(f"fake extractor: {len(result.claims)} claims")
        return result


@pytest.fixture(autouse=True)
def fake_extract(monkeypatch) -> FakeExtractor:
    """No test calls the model: the pipeline's extractor is this fake unless a test sets it up."""
    from auditor import extract as extract_module

    fake = FakeExtractor()
    monkeypatch.setattr(extract_module, "extract_claims", fake)
    return fake


# ----------------------------------------------------------------------------- language (step 12)


def golden_review() -> "LanguageReview":
    """What a perfect linguistic evaluator would return for the Shell page: the golden signals
    as quotes, and the golden clarity scores."""
    from auditor.language import ClarityScore, FoundSignal, LanguageReview

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    signals = [
        FoundSignal(
            level=s["level"], kind=s["kind"], polarity=s["polarity"],
            quotes=list(dict.fromkeys(sp["text"] for sp in s["spans"])),
            claim_ids=s["claim_ids"], note=s["note"], strength=s.get("strength", 0.5),
        )
        for s in analysis["signals"]
    ]
    clarity = [
        ClarityScore(claim_id=s["claim_id"], score=s["score"], confidence=s["confidence"], basis=s["basis"])
        for s in analysis["scores"] if s["dimension"] == "clarity"
    ]
    return LanguageReview(signals=signals, clarity=clarity)


class FakeReviewer:
    """Stands in for auditor.language.review_language: applies a canned LanguageReview (default:
    nothing found, so every claim gets a placeholder clarity score) through the real placement
    code, emitting each entity as production does."""

    def __init__(self) -> None:
        from auditor.language import LanguageReview

        self.review = LanguageReview(signals=[], clarity=[])
        self.calls: list[tuple[dict, list[dict]]] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, claims: list[dict], *, emit=None, llm=None):
        from auditor.language import apply_review

        self.calls.append((document, claims))
        if self.error is not None:
            raise self.error
        result = apply_review(self.review, document, claims, emit)
        result.notes.insert(0, f"fake reviewer: {len(result.signals)} signals")
        return result


@pytest.fixture(autouse=True)
def fake_language(monkeypatch) -> FakeReviewer:
    """No test calls the model: the pipeline's linguistic evaluator is this fake unless a test sets it up."""
    from auditor import language as language_module

    fake = FakeReviewer()
    monkeypatch.setattr(language_module, "review_language", fake)
    return fake


# ----------------------------------------------------------------------------- substantiation (step 13)


def golden_substantiation() -> tuple["Matches", "Assessments"]:
    """What a perfect substantiation evaluator would return for the Shell page: the fixture's
    substantiate-stage evidence mapped to the store entries with the same URL (with the
    fixture's claim links), and the fixture's support scores."""
    from auditor.documents import normalise_url
    from auditor.knowledge import get_knowledge
    from auditor.substantiate import Assessment, Assessments, Match, Matches

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    by_url = {normalise_url(entry.url): eid for eid, entry in get_knowledge().ids().items() if entry.url}
    matches = []
    for item in analysis["evidence"]:
        if item.get("stage") != "substantiate" or not item.get("url"):
            continue
        eid = by_url.get(normalise_url(item["url"]))
        claim_ids = [l["target"] for l in item["links"] if l["target"].startswith("C")]
        if eid and claim_ids:
            matches.append(Match(evidence_id=eid, claim_ids=claim_ids, note=item.get("note") or "golden"))
    assessments = [
        Assessment(claim_id=s["claim_id"], score=s["score"], confidence=s["confidence"], basis=s["basis"])
        for s in analysis["scores"] if s["dimension"] == "support"
    ]
    return Matches(matches=matches), Assessments(assessments=assessments)


class FakeSubstantiator:
    """Stands in for auditor.substantiate.substantiate: applies canned matches and assessments
    (default: none, so every claim gets a placeholder support score when scoring is on)
    through the real assembly code, emitting each entity as production does."""

    def __init__(self) -> None:
        from auditor.substantiate import Assessments, Matches

        self.matches = Matches(matches=[])
        self.assessments = Assessments(assessments=[])
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, claims: list[dict], *, emit=None, llm=None, knowledge=None, score: bool = True):
        from auditor.substantiate import apply_substantiation

        self.calls.append({"document": document, "claims": claims, "score": score})
        if self.error is not None:
            raise self.error
        result = apply_substantiation(self.matches, self.assessments, document, claims, knowledge, emit, score=score)
        result.notes.insert(0, f"fake substantiator: {len(result.evidence)} evidence items, {len(result.scores)} scores")
        return result


@pytest.fixture(autouse=True)
def fake_substantiate(monkeypatch) -> FakeSubstantiator:
    """No test calls the model: the pipeline's substantiation evaluator is this fake unless a test sets it up."""
    from auditor import substantiate as substantiate_module

    fake = FakeSubstantiator()
    monkeypatch.setattr(substantiate_module, "substantiate", fake)
    return fake


# ----------------------------------------------------------------------------- verification (step 14)

# The fixture's computations were written by hand and never evaluated; their formulas use
# short names ("scope12" for the input "scope12_mt") and two of them are two sums in one line.
# Step 14 evaluates what it shows, so the golden verifier restates the six that are single
# expressions in the form the evaluator accepts, as percentages so the sentence's number is
# the number that is checked. X7 and X8 are left out; the scores that cited them lose those
# citations, which is what `compare_scores` is for.
GOLDEN_COMPUTATIONS = {
    "X1": ("scope12_mt / (scope12_mt + scope3_mt) * 100", {"scope12_mt": 53, "scope3_mt": 1065}, "%"),
    "X2": ("res_musd / total_musd * 100", {"res_musd": 1866, "total_musd": 20915}, "%"),
    "X3": ("(upstream_musd + integrated_gas_musd) / total_musd * 100", {"upstream_musd": 9316, "integrated_gas_musd": 4689, "total_musd": 20915}, "%"),
    "X4": ("achieved_pct / target_pct * 100", {"achieved_pct": 36, "target_pct": 50}, "%"),
    "X5": ("(y2021_mt - y2025_mt) / y2021_mt * 100", {"y2021_mt": 569, "y2025_mt": 467}, "%"),
    "X6": ("(y2024_mt - y2025_mt) / y2024_mt * 100", {"y2024_mt": 1084, "y2025_mt": 1065}, "%"),
}


def golden_verification() -> tuple["Findings", "Computations", "Assessments", dict[str, str], dict[str, str]]:
    """What a perfect external verification would return for the Shell page: the fixture's
    verify-stage sources as findings (quote, links and all), the six recomputable numbers, and
    the fixture's support and materiality scores. Also the page text for each URL, so the
    citation check passes, and the map from fixture evidence id to the id the live run gives
    it, so a test can say which row is which."""
    from auditor.verify import Assessment, Assessments, Bearing, Computation, Computations, Finding, Findings, evaluate

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in analysis["evidence"]}
    independence = {1: "regulator", 2: "assured_filing", 3: "independent", 4: "news", 5: "company"}
    findings, mapping, pages = [], {}, {}
    for item in analysis["evidence"]:
        if item.get("stage") != "verify" or item["kind"] == "computation" or not item.get("url"):
            continue
        bears = [Bearing(claim_id=l["target"], relation=l["relation"]) for l in item["links"] if l["target"].startswith("C")]
        if not bears:
            continue
        mapping[item["id"]] = f"V{len(findings) + 1}"
        source = item["source"]
        findings.append(Finding(
            kind=item["kind"], independence=independence[item["tier"]], name=source["name"],
            publisher=source.get("publisher", ""), date=source.get("date", ""), locator=source.get("locator", ""),
            url=item["url"], quote=item["quote"], bears_on=bears, note=item.get("note", ""),
        ))
        pages.setdefault(item["url"], []).append(item["quote"])
    computations = []
    for fixture_id, (expression, inputs, unit) in GOLDEN_COMPUTATIONS.items():
        item = by_id[fixture_id]
        bears = [Bearing(claim_id=l["target"], relation=l["relation"]) for l in item["links"] if l["target"].startswith("C")]
        if not bears:
            continue
        mapping[fixture_id] = f"N{len(computations) + 1}"
        computations.append(Computation(
            name=item["source"]["name"], expression=expression, inputs=inputs, value=evaluate(expression, inputs),
            unit=unit, sentence=item["computation"]["result"], bears_on=bears,
            derived_from=[mapping.get(e, e) for e in item.get("derived_from", [])],
        ))
    scores = {(s["claim_id"], s["dimension"]): s for s in analysis["scores"]}
    assessments = []
    for claim in analysis["claims"]:
        support, materiality = scores.get((claim["id"], "support")), scores.get((claim["id"], "materiality"))
        if support is None or materiality is None:
            continue
        assessments.append(Assessment(
            claim_id=claim["id"],
            support=support["score"], support_confidence=support["confidence"], support_basis=support["basis"],
            support_evidence_ids=[mapping[e] for e in support.get("evidence_ids", []) if e in mapping],
            materiality=materiality["score"], materiality_confidence=materiality["confidence"], materiality_basis=materiality["basis"],
            materiality_evidence_ids=[mapping[e] for e in materiality.get("evidence_ids", []) if e in mapping],
        ))
    return Findings(findings=findings), Computations(computations=computations), Assessments(assessments=assessments), mapping, {url: "\n".join(quotes) for url, quotes in pages.items()}


class FakeVerifier:
    """Stands in for auditor.verify.verify: applies canned findings, computations and
    assessments (default: none, so every claim gets placeholder support and materiality)
    through the real assembly code, emitting each entity as production does. `pages` is the
    web as far as the citation check is concerned; by default every finding's quote is on its
    own page, so setting `pages` is how a test makes a quote fail."""

    def __init__(self) -> None:
        from auditor.verify import Assessments, Computations, Findings

        self.findings = Findings(findings=[])
        self.computations = Computations(computations=[])
        self.assessments = Assessments(assessments=[])
        self.pages: dict[str, str] | None = None
        self.calls: list[dict] = []
        self.error: Exception | None = None

    def fetch_text(self, url: str) -> str:
        if self.pages is not None:
            if url not in self.pages:
                raise ValueError(f"{url} answered HTTP 404")
            return self.pages[url]
        return "\n".join(f.quote for f in self.findings.findings if f.url == url)

    async def __call__(self, document: dict, claims: list[dict], *, prior_evidence=None, emit=None, llm=None, fetch_text=None):
        from auditor.verify import apply_verification

        self.calls.append({"document": document, "claims": claims, "prior_evidence": prior_evidence or []})
        if self.error is not None:
            raise self.error
        result = apply_verification(
            self.findings, self.computations, self.assessments, document, claims,
            prior_evidence, emit, fetch_text=fetch_text or self.fetch_text,
        )
        result.notes.insert(0, f"fake verifier: {len(result.sources)} sources, {len(result.computations)} computations, {len(result.scores)} scores")
        return result


@pytest.fixture(autouse=True)
def fake_verify(monkeypatch) -> FakeVerifier:
    """No test calls the model or the network: the pipeline's external verification is this fake
    unless a test sets it up."""
    from auditor import verify as verify_module

    fake = FakeVerifier()
    monkeypatch.setattr(verify_module, "verify", fake)
    return fake


# ----------------------------------------------------------------------------- the verdict layer (step 17)


def golden_debate() -> tuple["Cases", "Cases", "Judgments"]:
    """What a perfect verdict layer would return for the Shell page: the fixture's own
    arguments as the two advocates' cases, and a judgment per claim carrying the fixture's
    rationale, tags, fix and rewrite, with the judge agreeing with the derived category. The
    numbers are not in here: the stage derives them from whatever scores it is given."""
    from auditor.verdict import Cases, Case, Judgment, Judgments

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))

    def cases(role: str) -> Cases:
        return Cases(cases=[
            Case(claim_id=a["claim_id"], text=a["text"], evidence_ids=a.get("evidence_ids", []))
            for a in analysis["arguments"] if a["role"] == role
        ])

    judgments = Judgments(judgments=[
        Judgment(
            claim_id=v["claim_id"], rationale=v["rationale"], tags=v["tags"], fix=v.get("fix", ""),
            rewrite=v.get("rewrite", ""), evidence_ids=v.get("evidence_ids", []),
            own_category=v["category"], own_likelihood=v["likelihood"],
        )
        for v in analysis["verdicts"]
    ])
    return cases("prosecutor"), cases("defence"), judgments


class FakeJudge:
    """Stands in for auditor.verdict.issue_verdicts: applies canned cases and judgments
    (default: none, so every claim gets a verdict derived from its scores with no debate)
    through the real assembly code, emitting each entity as production does."""

    def __init__(self) -> None:
        from auditor.verdict import Cases, Judgments

        self.prosecution = Cases(cases=[])
        self.defence = Cases(cases=[])
        self.judgments = Judgments(judgments=[])
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, claims: list[dict], scores: list[dict], evidence: list[dict], signals=None, *, emit=None, llm=None, samples=None):
        from auditor.verdict import apply_verdicts

        self.calls.append({"document": document, "claims": claims, "scores": scores, "evidence": evidence, "signals": signals or []})
        if self.error is not None:
            raise self.error
        result = apply_verdicts(self.prosecution, self.defence, self.judgments, claims, scores, evidence, signals, emit)
        result.notes.insert(0, f"fake judge: {len(result.arguments)} arguments, {len(result.verdicts)} verdicts")
        return result


@pytest.fixture(autouse=True)
def fake_verdict(monkeypatch) -> FakeJudge:
    """No test calls the model: the pipeline's verdict layer is this fake unless a test sets it up."""
    from auditor import verdict as verdict_module

    fake = FakeJudge()
    monkeypatch.setattr(verdict_module, "issue_verdicts", fake)
    return fake


# ----------------------------------------------------------------------------- self-consistency (step 15)


def golden_consistency() -> tuple["Statements", "Assessments", dict[str, str], dict[str, str]]:
    """What a perfect self-consistency evaluator would return for the Shell page: the fixture's
    consistency-stage sources as statements from the company's own material (quote, links and
    all), and the fixture's consistency scores. Also the map from fixture evidence id to the id
    the live run gives it, and the page text for each URL so the citation check passes.

    The fixture has no archived captures — the hand analysis was done from the live page — so
    the archive axis has nothing to reproduce here; `test_consistency.py` covers it on its own.
    """
    from auditor.consistency import Assessment, Assessments, Bearing, Statement, Statements

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    # Tier is derived from independence, never chosen: an assured filing is tier 2 because a
    # third party signed it, and everything else the company says about itself is tier 5.
    independence = {2: "assured_filing", 5: "company"}
    statements, mapping, pages = [], {}, {}
    for item in analysis["evidence"]:
        if item.get("stage") != "consistency" or not item.get("url"):
            continue
        bears = [Bearing(claim_id=l["target"], relation=l["relation"]) for l in item["links"] if l["target"].startswith("C")]
        if not bears or item["tier"] not in independence:
            continue
        mapping[item["id"]] = f"S{len(statements) + 1}"
        source = item["source"]
        statements.append(Statement(
            kind=item["kind"], independence=independence[item["tier"]], name=source["name"],
            publisher=source.get("publisher", ""), date=source.get("date", ""), locator=source.get("locator", ""),
            url=item["url"], quote=item["quote"], bears_on=bears, note=item.get("note", ""),
        ))
        pages.setdefault(item["url"], []).append(item["quote"])
    assessments = [
        Assessment(
            claim_id=s["claim_id"], score=s["score"], confidence=s["confidence"], basis=s["basis"],
            evidence_ids=[mapping[e] for e in s.get("evidence_ids", []) if e in mapping],
        )
        for s in analysis["scores"] if s["dimension"] == "consistency"
    ]
    return Statements(statements=statements), Assessments(assessments=assessments), mapping, {url: "\n".join(quotes) for url, quotes in pages.items()}


class FakeConsistency:
    """Stands in for auditor.consistency.consistency: applies canned statements, changes and
    assessments (default: none, so every claim gets a placeholder consistency score) through
    the real assembly code, emitting each entity as production does. `pages` is the web as far
    as the citation check is concerned; by default every statement's quote is on its own page,
    so setting `pages` is how a test makes a quote fail. No test reaches the Wayback Machine:
    `versions` is the archive, and it is empty unless a test fills it."""

    def __init__(self) -> None:
        from auditor.consistency import Assessments, Statements

        self.statements = Statements(statements=[])
        self.changes: dict[str, object] = {}
        self.assessments = Assessments(assessments=[])
        self.versions: list[object] = []
        self.pages: dict[str, str] | None = None
        self.calls: list[dict] = []
        self.error: Exception | None = None

    def fetch_text(self, url: str) -> str:
        if self.pages is not None:
            if url not in self.pages:
                raise ValueError(f"{url} answered HTTP 404")
            return self.pages[url]
        return "\n".join(s.quote for s in self.statements.statements if s.url == url)

    async def __call__(self, document: dict, claims: list[dict], *, prior_evidence=None, emit=None, llm=None,
                       fetch_text=None, fetcher=None, history=None, snapshots=None):
        from auditor.consistency import apply_consistency

        self.calls.append({"document": document, "claims": claims, "prior_evidence": prior_evidence or [], "snapshots": snapshots})
        if self.error is not None:
            raise self.error
        result = apply_consistency(
            self.statements, self.changes, self.assessments, document, claims, self.versions,
            prior_evidence, emit, fetch_text=fetch_text or self.fetch_text,
        )
        result.notes.insert(0, f"fake self-consistency: {len(result.statements)} statements, {len(result.archived)} captures, {len(result.scores)} scores")
        return result


@pytest.fixture(autouse=True)
def fake_consistency(monkeypatch) -> FakeConsistency:
    """No test calls the model and no test touches the Wayback Machine: the pipeline's
    self-consistency evaluator is this fake unless a test sets it up."""
    from auditor import consistency as consistency_module

    fake = FakeConsistency()
    monkeypatch.setattr(consistency_module, "consistency", fake)
    return fake


# ----------------------------------------------------------------------------- omissions (step 16)


GOLDEN_TOPICS = {"O1": "M2.1", "O2": "M2.3", "O3": "M2.2", "O4": "M1.4"}
"""The fixture's four omissions and the materiality store's topic for each: the absolute size
of total emissions, capital allocation, production plans, and the history of the targets."""

GOLDEN_NEAREST = {
    "O1": "Scope 1 and 2 emissions were down by 36% by the end of 2025 compared with the 2016 baseline year",
    "O2": "making portfolio changes such as acquisitions and investments in low carbon intensity projects",
    "O3": "while sustaining our liquids production",
    "O4": "",
}
"""The nearest the Shell page comes to each of them, in its own words. O4 has nothing: the page
does not mention the history of its targets at all."""


def golden_omissions() -> "Coverages":
    """What a perfect omissions stage would return for the Shell page: the golden reference's
    margin cards, each answered against the topic it belongs to."""
    from auditor.omissions import Coverage, Coverages

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    return Coverages(coverage=[
        Coverage(
            topic_id=GOLDEN_TOPICS[o["id"]], addressed="no", topic=o["topic"], why_material=o["why_material"],
            complete_text=o.get("complete_text", ""), nearest=GOLDEN_NEAREST[o["id"]],
            evidence_ids=[e for e in o.get("evidence_ids", []) if e != "E16"],
            score=o["score"], confidence=o["confidence"],
        )
        for o in analysis["omissions"] if o["id"] in GOLDEN_TOPICS
    ])


class FakeOmissions:
    """Stands in for auditor.omissions.find_omissions: applies a canned coverage answer
    (default: none, so no card is written) through the real assembly code, with the repository's
    materiality store, emitting each entity as production does."""

    def __init__(self) -> None:
        from auditor.omissions import Coverages

        self.coverages = Coverages(coverage=[])
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, claims: list[dict], *, prior_evidence=None, emit=None, llm=None, store=None, first_number: int = 1):
        from auditor.materiality import get_materiality
        from auditor.omissions import apply_omissions

        self.calls.append({"document": document, "claims": claims, "prior_evidence": prior_evidence or []})
        if self.error is not None:
            raise self.error
        store = store or get_materiality()
        result = apply_omissions(
            self.coverages, document, store, store.for_document(document), prior_evidence, emit, first_number=first_number,
        )
        result.notes.insert(0, f"fake omissions: {len(result.omissions)} cards from {len(store.topics(result.matches))} topics")
        return result


@pytest.fixture(autouse=True)
def fake_omissions(monkeypatch) -> FakeOmissions:
    """No test calls the model: the pipeline's omissions stage is this fake unless a test sets it up."""
    from auditor import omissions as omissions_module

    fake = FakeOmissions()
    monkeypatch.setattr(omissions_module, "find_omissions", fake)
    return fake


# ----------------------------------------------------------------------------- the summary (step 18)


def golden_header() -> "Header":
    """What a perfect writer would return for the Shell page: the reference's own titles for
    whichever targets the ranking picked, and its narrative. The numbers are not in here; the
    stage computes those from the claims it is given."""
    from auditor.summary import Header, Title

    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    summary = analysis["summary"]
    return Header(
        issues=[Title(target=t["target"], title=t["title"]) for t in summary["top_issues"]],
        credit=[Title(target=t["target"], title=t["title"]) for t in summary["credit"]],
        narrative=summary.get("narrative", ""),
    )


class FakeSummariser:
    """Stands in for auditor.summary.summarise: runs the real aggregation over whatever the
    pipeline produced and applies canned titles (default: none, so every target falls back to
    its own words), emitting the header as production does."""

    def __init__(self) -> None:
        self.header = None
        self.calls: list[dict] = []
        self.error: Exception | None = None

    async def __call__(self, document: dict, claims: list[dict], scores: list[dict], verdicts: list[dict], omissions: list[dict], *, emit=None, llm=None, power=None):
        from auditor.summary import POWER, build_summary

        self.calls.append({"document": document, "claims": claims, "scores": scores, "verdicts": verdicts, "omissions": omissions})
        if self.error is not None:
            raise self.error
        result = build_summary(document, claims, scores, verdicts, omissions, self.header, emit, power=power or POWER)
        result.notes.insert(0, f"fake summariser: headline {result.summary['headline']['score']}")
        return result


@pytest.fixture(autouse=True)
def fake_summary(monkeypatch) -> FakeSummariser:
    """No test calls the model: the pipeline's summary stage is this fake unless a test sets it up."""
    from auditor import summary as summary_module

    fake = FakeSummariser()
    monkeypatch.setattr(summary_module, "summarise", fake)
    return fake
