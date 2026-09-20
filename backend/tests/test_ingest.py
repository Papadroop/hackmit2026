"""Ingestion (roadmap step 10): text, URL and PDF to canonical text with stable offsets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import APPLE_URL, ORSTED_URL, REPO, SHELL_MODEL_URL, SHELL_URL, data_text, make_pdf, shell_fixture_document

from auditor.ingest import IngestError, ingest_curated, ingest_file, ingest_pdf, ingest_text, ingest_url
from auditor.ingest.aem import model_url_for
from auditor.ingest.anchor import anchor_span
from auditor.ingest.blocks import Block, Container, assemble, tidy
from auditor.ingest.canonical import CanonicalError, canonical_line, check_canonical
from auditor.ingest.html import html_blocks, is_thin
from auditor.ingest.text import to_curated

SCHEMA = json.loads((REPO / "contract" / "schema.json").read_text(encoding="utf-8"))


def validate_document(document: dict) -> None:
    """The contract's Document schema plus its region rules (contract.py check_analysis)."""
    from jsonschema import Draft7Validator, FormatChecker

    schema = {"$ref": "#/definitions/Document", "definitions": SCHEMA["definitions"]}
    errors = [e.message for e in Draft7Validator(schema, format_checker=FormatChecker()).iter_errors(document)]
    assert not errors, errors
    check_canonical(document["text"])
    n = len(document["text"])
    by_kind: dict[str, list[dict]] = {}
    labels: list[str] = []
    for r in document["regions"]:
        assert 0 <= r["start"] < r["end"] <= n, r
        by_kind.setdefault(r["kind"], []).append(r)
        if r.get("label"):
            labels.append(r["label"])
    assert len(labels) == len(set(labels)), "region labels must be unique"
    for kind, rs in by_kind.items():
        rs = sorted(rs, key=lambda r: r["start"])
        for p, q in zip(rs, rs[1:]):
            assert q["start"] >= p["end"], f"{kind} regions overlap: {p} {q}"
    assert document["word_count"] == len(document["text"].split())


def region_texts(document: dict, kind: str) -> list[str]:
    return [document["text"][r["start"] : r["end"]] for r in document["regions"] if r["kind"] == kind]


# ----------------------------------------------------------------------------- canonical form


def test_canonical_line_normalises_every_kind_of_whitespace():
    assert canonical_line("  we are \t reducing\r\n emissions​ ") == "we are reducing emissions"
    assert canonical_line("café") == "café", "NFC"
    assert canonical_line(" \n\t") == ""


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "empty"),
        ("a\r\nb", "carriage"),
        ("a\tb", "whitespace"),
        ("a  b", "runs"),
        ("a \nb", "boundary"),
        ("a\n\n\nb", "blank-line"),
        (" a", "blank-line"),
    ],
)
def test_check_canonical_refuses_what_the_contract_refuses(text, message):
    with pytest.raises(CanonicalError, match=message):
        check_canonical(text)


# ----------------------------------------------------------------------------- Shell: curated copy and AEM model


def test_curated_shell_copy_reproduces_the_fixture_text_exactly():
    fixture = shell_fixture_document()
    document = ingest_curated(REPO / "demo-documents" / "shell-climate-2026-09-19.md").document
    validate_document(document)
    assert document["text"] == fixture["text"]
    assert document["title"] == "Climate | Shell Global"
    assert document["company"]["name"] == "Shell plc"
    assert document["text_type"] == "policy"
    assert document["industry"] == {"label": "Oil & Gas – Integrated", "sasb_codes": ["EM-EP", "EM-RM"]}
    assert document["source"]["fixture_path"] == "demo-documents/shell-climate-2026-09-19.md"
    assert document["id"] == "shell-climate-2026-09-19"


def test_every_golden_span_anchors_at_its_recorded_offset_in_the_curated_text():
    analysis = json.loads((REPO / "fixtures" / "shell-climate.analysis.json").read_text(encoding="utf-8"))
    text = ingest_curated(REPO / "demo-documents" / "shell-climate-2026-09-19.md").document["text"]
    spans = [s for c in analysis["claims"] for s in c["spans"]] + [s for g in analysis["signals"] for s in g["spans"]]
    assert len(spans) >= 60
    for span in spans:
        assert text[span["start"] : span["end"]] == span["text"]
        assert anchor_span(text, span) == (span["start"], span["end"], "offset")


def test_aem_model_reproduces_the_fixture_text_and_its_structure():
    fixture = shell_fixture_document()
    document = ingest_file(Path(__file__).parent / "data" / "shell-climate.model.json").document
    validate_document(document)
    assert document["text"] == fixture["text"]
    mine = {(r["kind"], r["start"], r["end"]) for r in document["regions"] if r["kind"] != "paragraph"}
    theirs = {(r["kind"], r["start"], r["end"]) for r in fixture["regions"] if r["kind"] != "paragraph"}
    assert mine == theirs, "title, headings, list items, promo, footnote and cautionary note where the hand analysis put them"
    heading_levels = {r["label"]: r["level"] for r in document["regions"] if r["kind"] == "heading"}
    assert heading_levels["H2 Our targets and ambition"] == 2
    assert heading_levels["H3 2025 performance:"] == 3
    assert "You may also be interested in" not in document["text"], "link cards are navigation"
    assert document["text"].count("Climate") >= 2, "the page title and the page header are both on the page"


def test_the_shell_html_is_a_javascript_shell_that_names_its_model():
    result = html_blocks(data_text("shell-climate.shell.html"), SHELL_URL)
    assert is_thin(result)
    assert result.meta.aem_model_url == SHELL_MODEL_URL
    assert model_url_for(SHELL_URL) == SHELL_MODEL_URL
    assert model_url_for("https://example.com/a/b/") == "https://example.com/a/b.model.json"


# ----------------------------------------------------------------------------- Apple and Ørsted pages


@pytest.fixture(scope="module")
def apple() -> dict:
    return ingest_file_html("apple-carbon-neutral-2023-09-12.html.gz", APPLE_URL)


@pytest.fixture(scope="module")
def orsted() -> dict:
    return ingest_file_html("orsted-decarbonisation-2026-09-19.html.gz", ORSTED_URL)


def ingest_file_html(name: str, url: str) -> dict:
    from auditor.ingest import _build, _page_document_meta

    result = html_blocks(data_text(name), url)
    return _build(result.blocks, _page_document_meta(result, url, url, None))


def test_apple_press_release_is_the_article_without_the_chrome(apple):
    validate_document(apple)
    text = apple["text"]
    assert apple["title"] == "Apple unveils its first carbon neutral products - Apple"
    assert apple["company"]["name"] == "Apple"
    assert apple["text_type"] == "press_release"
    assert text.startswith("PRESS RELEASE September 12, 2023\n\nApple unveils its first carbon neutral products\n\n")
    for chrome in ("Share article", "Text of this article", "Press Contacts", "More from Apple Newsroom", "Download all media", "Images in this article", "Store\n", "(Pictured:"):
        assert chrome not in text, chrome
    assert text.count("CUPERTINO, CALIFORNIA") == 1, "the hidden copy-text duplicate is gone"
    assert 2200 <= apple["word_count"] <= 2500
    assert [t[:30] for t in region_texts(apple, "heading")][:3] == ["Every Product Carbon Neutral b", "The Path to 2030", "Spurring Progress in Clean Ele"]


def test_apple_footnotes_and_captions_are_labelled(apple):
    footnotes = region_texts(apple, "footnote")
    assert len(footnotes) == 5
    assert footnotes[0].startswith("1. Carbon reductions are calculated against a baseline scenario")
    assert footnotes[4] == "5. All cobalt content claims are based on a mass balance allocation."
    assert "Apple Watch.1 This milestone" in apple["text"], "the inline footnote marker is kept"
    captions = region_texts(apple, "caption")
    assert any(c.startswith("The popular Sport Loop band has been redesigned") for c in captions)
    assert all("(Pictured" not in c for c in captions), "carousel captions are not reading order"
    prominences = {r["label"]: r.get("prominence") for r in apple["regions"] if r["kind"] == "paragraph"}
    assert prominences["P2"] == 1.0, "the deck under the title is the hero paragraph"


def test_orsted_page_keeps_quote_attribution_and_link_card_copy(orsted):
    validate_document(orsted)
    text = orsted["text"]
    assert text.startswith("Towards net zero\n\nFrom reducing our own emissions to leading decarbonisation throughout our supply chain\n\nWith renewable energy")
    for chrome in ("Whistleblower", "Cookie policy", "Home", "Follow us", "info@orsted.com"):
        assert chrome not in text.split("\n\n")[:3] and chrome not in text, chrome
    assert "​" not in text
    assert "Decarbonisation by the book\n\n" in text
    quotes = region_texts(orsted, "quote")
    assert len(quotes) == 1 and quotes[0].startswith("By meeting our target of a 98% reduction") and quotes[0].endswith("Head of Global Sustainability")
    assert region_texts(orsted, "caption") == ["Anders Johannes Enghild", "Head of Global Sustainability"]
    promos = region_texts(orsted, "promo")
    assert [p.split("\n")[0] for p in promos] == ["Scope 1 and 2 emissions", "Scope 3 emissions", "What is net zero?", "Biodiversity", "Community impact"]
    assert orsted["company"]["name"] == "Ørsted"
    assert 680 <= orsted["word_count"] <= 760


def test_extraction_is_deterministic(orsted):
    again = ingest_file_html("orsted-decarbonisation-2026-09-19.html.gz", ORSTED_URL)
    assert again["text"] == orsted["text"] and again["regions"] == orsted["regions"]


# ----------------------------------------------------------------------------- generic HTML rules

PAGE = """<!doctype html><html lang="en-GB"><head><title>Our footprint | Acme</title>
<meta property="og:site_name" content="Acme"><script>var x = 1;</script></head><body>
<header><nav><a href="/">Home</a><a href="/about">About</a></nav></header>
<div class="cookie-banner">We use cookies.</div>
<main>
  <h1>Our footprint</h1>
  <p class="standfirst">We measure what we emit.</p>
  <p>Our operations emit 1.2 million tonnes of CO2e a year.<br>That is 12% less than in 2019.</p>
  <p>Our targets are:</p>
  <ul><li>Halve emissions by 2030</li><li>Net zero by 2050<ul><li>including Scope 3</li></ul></li></ul>
  <h2>A heading that is really a long statement about how we believe our approach is aligned with the goals of the Paris Agreement</h2>
  <h2>Empty section</h2>
  <h2>Data</h2>
  <div>Text in a div<br><br>Second paragraph in the div<br><br><br></div>
  <table><tr><th>Year</th><th>Tonnes</th></tr><tr><td>2019</td><td>1.4m</td></tr></table>
  <blockquote><p>We take this seriously.</p></blockquote>
  <p class="quote-author">Jane Doe</p><p>Chief executive</p>
  <figure><img src="x.png"><figcaption>Our plant in 2025.</figcaption></figure>
  <div aria-hidden="true">hidden copy</div><p hidden>also hidden</p><p style="display:none">and this</p>
  <h2>Footnotes</h2>
  <ol><li>Scope 1 and 2, market-based.</li><li>Restated in 2024.</li></ol>
  <a href="/more"><h3>Read our report</h3></a>
</main>
<aside class="related">Related articles</aside>
<footer>© Acme 2026 · Privacy</footer>
</body></html>"""


def test_generic_html_rules():
    document = ingest_file_html_text(PAGE, "https://www.acme.example/sustainability/footprint")
    validate_document(document)
    text = document["text"]
    for chrome in ("Home", "cookies", "hidden copy", "also hidden", "and this", "Related articles", "Privacy", "var x", "Read our report"):
        assert chrome not in text, chrome
    blocks = text.split("\n\n")
    assert blocks[0] == "Our footprint"
    assert blocks[1] == "We measure what we emit."
    assert blocks[2] == "Our operations emit 1.2 million tonnes of CO2e a year.\nThat is 12% less than in 2019.", "<br> is a line break inside the block"
    assert blocks[3:6] == ["Our targets are:", "Halve emissions by 2030", "Net zero by 2050"]
    assert blocks[6] == "including Scope 3", "nested list items are flattened"
    assert "A heading that is really a long statement" in blocks[7] and all(r["kind"] != "heading" or "long statement" not in text[r["start"]:r["end"]] for r in document["regions"])
    assert "Empty section" not in text
    assert "Text in a div\n\nSecond paragraph in the div" in text, "<br><br> splits a block"
    assert "Year | Tonnes\n\n2019 | 1.4m" in text
    assert region_texts(document, "quote") == ["We take this seriously.\n\nJane Doe\n\nChief executive"]
    assert region_texts(document, "caption") == ["Jane Doe", "Chief executive", "Our plant in 2025."]
    assert region_texts(document, "footnote") == ["1. Scope 1 and 2, market-based.", "2. Restated in 2024."]
    paragraphs = {r["label"]: text[r["start"] : r["end"]] for r in document["regions"] if r["kind"] == "paragraph"}
    assert paragraphs["P3"].startswith("Our targets are:\n\nHalve emissions by 2030"), "a list under an introducing colon shares its paragraph region"
    assert paragraphs["P2"].startswith("Our operations emit")
    assert {r["label"]: r.get("prominence") for r in document["regions"] if r["kind"] == "paragraph"}["P1"] == 1.0
    assert document["company"]["name"] == "Acme"
    assert document["language"] == "en"


def ingest_file_html_text(html: str, url: str) -> dict:
    from auditor.ingest import _build, _page_document_meta

    result = html_blocks(html, url)
    return _build(result.blocks, _page_document_meta(result, url, url, None))


def test_page_without_an_h1_gets_its_title_from_the_head():
    document = ingest_file_html_text("<html><head><title>Climate report | Acme</title></head><body><main><p>Body text of the page that is long enough to count.</p></main></body></html>", "https://acme.example/x")
    assert document["text"].startswith("Climate report\n\nBody text")
    assert region_texts(document, "title") == ["Climate report"]


# ----------------------------------------------------------------------------- text and the curated round trip


def test_pasted_text_paragraphs_headings_and_bullets():
    document = ingest_text("# Carbon neutral\n\nOur product is carbon neutral.\nSince 2020.\n\n- Certified\n- Offset\n\n> A quote\n", title=None).document
    validate_document(document)
    assert document["text"] == "Carbon neutral\n\nOur product is carbon neutral.\nSince 2020.\n\nCertified\nOffset\n\nA quote"
    assert document["title"] == "Carbon neutral"
    assert region_texts(document, "title") == ["Carbon neutral"]
    assert region_texts(document, "list_item") == ["Certified", "Offset"]
    assert region_texts(document, "quote") == ["A quote"]
    assert document["text_type"] == "other" and document["company"]["name"] == "Not identified"

    plain = ingest_text("We are carbon neutral.\n\nAll of our products.", title="Label").document
    assert plain["title"] == "Label" and plain["text"] == "We are carbon neutral.\n\nAll of our products."
    untitled = ingest_text("A very long first line " * 8).document
    assert untitled["title"].endswith("…") and len(untitled["title"]) <= 80
    with pytest.raises(IngestError):
        ingest_text("   \n\n  ")


def test_curated_markdown_round_trips():
    path = REPO / "demo-documents" / "shell-climate-2026-09-19.md"
    original = path.read_text(encoding="utf-8")
    document = ingest_curated(path).document
    body = original.split("---", 2)[2].strip("\n")
    written = to_curated(document, {"title": document["title"]}).split("---", 2)[2].strip("\n")
    assert written == body


# ----------------------------------------------------------------------------- PDF


def test_pdf_drops_running_headers_and_repairs_the_layout():
    document = ingest_pdf(make_pdf(4), filename="acme-report.pdf").document
    validate_document(document)
    text = document["text"]
    assert "Sustainability Report 2025" not in text, "running header"
    assert "Page 1 of 4" not in text and "Page 3" not in text, "page numbers"
    assert document["title"] == "Acme plc: Towards net zero"
    assert region_texts(document, "heading")[:3] == ["A message from our chief executive", "Chapter 2: Progress on our journey", "Chapter 3: Targets on our journey"]
    assert "Scope 1 and 2 emissions by 36% against the 2016 baseline, while production volumes stayed flat." in text, "hyphenation repaired"
    assert region_texts(document, "list_item")[:3] == ["Scope 1 and 2 emissions down 36% since 2016", "Methane intensity held below 0.2%", "Routine flaring ended in 2025"]
    footnotes = region_texts(document, "footnote")
    assert footnotes[0] == "1 Figures are assured to a limited level by our auditor." and len(footnotes) == 4
    assert document["text_type"] == "report"
    with pytest.raises(IngestError, match="not a PDF"):
        ingest_pdf(b"hello")


def test_two_column_pdf_reads_column_by_column():
    text = ingest_pdf(make_pdf(2, two_columns=True)).document["text"]
    assert "Left column first line left column second line. Left column third line." in text
    assert "Right column first line right column second line. Right column third line." in text
    assert text.index("Left column first") < text.index("Right column first")


# ----------------------------------------------------------------------------- anchoring


def test_anchor_span_follows_the_contract_rules():
    text = "a b c. a b d. a b c."
    assert anchor_span(text, {"text": "b c", "start": 2, "end": 5}) == (2, 5, "offset")
    assert anchor_span(text, {"text": "b c", "start": 0, "end": 3, "context": "a b d. a b c"}) == (16, 19, "context")
    assert anchor_span(text, {"text": "b c", "start": 0, "end": 3, "occurrence": 2}) == (16, 19, "occurrence")
    assert anchor_span(text, {"text": "b d", "start": 0, "end": 3}) == (9, 12, "unique")
    assert anchor_span(text, {"text": "b c", "start": 0, "end": 3}) is None, "ambiguous"
    old = "x. a b c. a b d. a b c."
    assert anchor_span(text, {"text": "b c", "start": 19, "end": 22}, old) == (16, 19, "same_occurrence")
    assert anchor_span(text, {"text": "zzz", "start": 0, "end": 3}) is None


# ----------------------------------------------------------------------------- URL routing and fallbacks


def test_url_routes_by_content(fake_fetch, tmp_path):
    fake_fetch.pdf("https://x.example/report.pdf", make_pdf(2))
    document = ingest_url("https://x.example/report.pdf").document
    assert document["title"] == "Acme plc: Towards net zero" and document["source"]["url"] == "https://x.example/report.pdf"
    assert document["company"]["name"] == "X"

    fake_fetch.json(SHELL_MODEL_URL, data_text("shell-climate.model.json"))
    document = ingest_url(SHELL_MODEL_URL).document
    assert document["text"] == shell_fixture_document()["text"]

    fake_fetch.plain("https://x.example/label.txt", "We are carbon neutral.\n\nAll of it.")
    assert ingest_url("https://x.example/label.txt").document["text"] == "We are carbon neutral.\n\nAll of it."


def test_javascript_shell_falls_back_to_its_content_model(shell_pages):
    ingested = ingest_url(SHELL_URL)
    assert ingested.document["text"] == shell_fixture_document()["text"]
    assert shell_pages.calls == [SHELL_URL, SHELL_MODEL_URL]
    assert "AEM content model" in ingested.document["source"]["method"]
    assert any("only 4 words" in note or "words of readable text" in note for note in ingested.notes)


def test_javascript_shell_without_a_model_is_reported(fake_fetch):
    fake_fetch.html("https://spa.example/page", "<html><head><title>App</title></head><body><div id='root'></div></body></html>")
    with pytest.raises(IngestError, match="words of readable text"):
        ingest_url("https://spa.example/page")


def test_blocked_demo_url_uses_the_curated_copy(fake_fetch, demo_dir):
    fake_fetch.refuse(SHELL_URL, 403)
    ingested = ingest_url(SHELL_URL, demo_dir=demo_dir)
    assert ingested.document["source"]["fixture_path"].endswith("shell-climate-2026-09-19.md")
    assert "HTTP 403" in ingested.document["source"]["method"]
    assert ingested.document["title"] == "Climate | Shell Global"


def test_blocked_unknown_url_uses_the_wayback_machine(fake_fetch, monkeypatch):
    from auditor.ingest import fetch as fetch_module

    url = "https://blocked.example/page"
    snapshot = "https://web.archive.org/web/20250101000000id_/" + url
    fake_fetch.refuse(url, 403)
    fake_fetch.html(snapshot, "<html><head><title>Archived page</title></head><body><main><h1>Archived page</h1><p>" + "Words of the archived copy. " * 20 + "</p></main></body></html>")
    monkeypatch.setattr(fetch_module, "wayback_snapshot", lambda u, **_: (snapshot, "20250101000000"))
    ingested = ingest_url(url)
    assert ingested.document["source"]["archive_url"] == "https://web.archive.org/web/20250101000000/" + url
    assert ingested.document["source"]["url"] == url
    assert any("Wayback" in note for note in ingested.notes)

    fake_fetch.refuse("https://gone.example/", None)
    monkeypatch.setattr(fetch_module, "wayback_snapshot", lambda u, **_: None)
    with pytest.raises(IngestError, match="Wayback Machine has no copy"):
        ingest_url("https://gone.example/")


def test_live_demo_page_takes_the_curated_metadata(shell_pages, demo_dir):
    document = ingest_url(SHELL_URL, demo_dir=demo_dir).document
    assert document["company"]["name"] == "Shell plc"
    assert document["title"] == "Climate | Shell Global"
    assert document["source"]["fixture_path"].endswith("shell-climate-2026-09-19.md")
    assert "AEM content model" in document["source"]["method"], "the text is the live page's"
