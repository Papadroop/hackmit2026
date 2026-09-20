"""The knowledge stores (roadmap step 13; design-doc D5 "prebuilt knowledge"): substantiation
criteria and precedents, curated by hand in `knowledge/` at the repository root.

Two JSON files, one entry per rule or ruling. Every entry is a contract EvidenceItem without
its `links` (id, kind, tier, source, url, quote, verified, verification, retrieved, note),
plus an `index` block that only the matcher reads: the claim terms and types the entry bears
on, the rule it states or the wording it ruled on, the outcome, the jurisdiction. When the
substantiation evaluator cites an entry for a claim, `as_evidence` turns it into the evidence
item the log carries, `ext` keeping the store key and the index facts the contract has no
field for.

Rules the loader enforces (the same ones the contract validator applies to evidence): a
verified entry has a quote and a verification method; an unverified one has none, so its
quote is never displayed (D5 citation integrity); tiers are 1 to 5; dates are ISO.

    python -m auditor.knowledge check [--fetch]

`check` validates the files and prints what they hold; `--fetch` fetches every URL and looks
for each verified quote in the page, which is what "a working link" and "the quote is on the
page" mean. `quote_in` and `page_text` are the same two pieces external verification (step 14)
runs over every quote it retrieves, so the store and the live evidence are held to one bar.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .documents import normalise_url

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "knowledge"

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

EvidenceKind = Literal["ruling", "law", "filing", "report", "dataset", "standard", "company_page", "press_release", "news", "archive", "other"]
Verification = Literal["fetched_exact", "fetched_by_eye", "second_party_fetch", "unverified"]
Outcome = Literal["upheld", "upheld_in_part", "not_upheld", "dismissed", "settled", "pending"]
ClaimType = Literal["factual", "commitment", "comparative", "vague_attribute", "certification"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    publisher: str | None = None
    date: str | None = None
    locator: str | None = None


class CriteriaIndex(BaseModel):
    """What the matcher reads about a rule."""

    model_config = ConfigDict(extra="forbid")
    jurisdiction: str
    terms: list[str] = Field(default_factory=list, description="Claim terms and families the rule speaks to")
    applies_to: list[ClaimType] = Field(default_factory=list, description="Claim types the rule speaks to; empty means any")
    rule: str = Field(min_length=1, description="What must be true for a claim using these terms to be legitimate, in one or two sentences")


class PrecedentIndex(BaseModel):
    """What the matcher reads about a ruling."""

    model_config = ConfigDict(extra="forbid")
    jurisdiction: str
    body: str
    company: str
    industry: str | None = None
    claim_text: str = Field(min_length=1, description="The wording that was ruled on")
    outcome: Outcome
    reasoning: str = Field(min_length=1, description="Why, in one or two sentences")
    terms: list[str] = Field(default_factory=list)
    applies_to: list[ClaimType] = Field(default_factory=list)
    adjudicated_urls: list[str] = Field(default_factory=list, description="The texts ruled on, when they are web pages: held out when one of them is the document under analysis")


class StoreEntry(BaseModel):
    """One rule or ruling: a contract EvidenceItem without links, plus its index."""

    model_config = ConfigDict(extra="forbid")
    id: str
    kind: EvidenceKind
    tier: int = Field(ge=1, le=5)
    source: Source
    url: str | None = None
    text_url: str | None = Field(default=None, description="Where a script can read the text when `url` is a JavaScript page (not emitted)")
    quote: str | None = None
    verified: bool
    verification: Verification
    retrieved: str
    note: str | None = None
    index: CriteriaIndex | PrecedentIndex

    @model_validator(mode="after")
    def _contract_rules(self) -> "StoreEntry":
        if not ID_PATTERN.match(self.id):
            raise ValueError(f"{self.id!r} is not a contract id")
        if not DATE_PATTERN.match(self.retrieved):
            raise ValueError(f"{self.id}: retrieved must be an ISO date, not {self.retrieved!r}")
        for url in (self.url, self.text_url):
            if url is not None and not re.match(r"^https?://", url):
                raise ValueError(f"{self.id}: url must be http(s)")
        if self.verified:
            if not self.quote:
                raise ValueError(f"{self.id}: verified but no quote")
            if self.verification == "unverified":
                raise ValueError(f"{self.id}: verified but verification is 'unverified'")
        elif self.verification != "unverified":
            raise ValueError(f"{self.id}: not verified, so verification must be 'unverified'")
        return self

    @property
    def store(self) -> str:
        return "criteria" if isinstance(self.index, CriteriaIndex) else "precedents"

    def as_evidence(self, evidence_id: str, links: list[dict[str, str]], *, stage: str = "substantiate") -> dict[str, Any]:
        """The contract EvidenceItem for this entry, linked to the given targets. An unverified
        entry is listed by name and note, without its quote (D5)."""
        item: dict[str, Any] = {
            "id": evidence_id,
            "kind": self.kind,
            "tier": self.tier,
            "source": self.source.model_dump(exclude_none=True),
            "verified": self.verified,
            "verification": self.verification,
            "retrieved": self.retrieved,
            "stage": stage,
            "links": [dict(l) for l in links],
        }
        if self.url:
            item["url"] = self.url
        if self.verified and self.quote:
            item["quote"] = self.quote
        if self.note:
            item["note"] = self.note
        ext: dict[str, Any] = {"store": self.store, "store_id": self.id, "jurisdiction": self.index.jurisdiction}
        if isinstance(self.index, PrecedentIndex):
            ext.update({"body": self.index.body, "company": self.index.company, "claim_text": self.index.claim_text, "outcome": self.index.outcome})
        item["ext"] = ext
        return item

    def index_line(self, evidence_id: str) -> str:
        """One line for the model: what the entry is and what it says."""
        head = f"{evidence_id} [{'criterion' if self.store == 'criteria' else 'precedent'}; {self.index.jurisdiction}; tier {self.tier}] {self.source.name}"
        if isinstance(self.index, CriteriaIndex):
            body = f"Rule: {self.index.rule}"
            if self.index.terms:
                body += f" Terms: {', '.join(self.index.terms)}."
            if self.index.applies_to:
                body += f" Claim types: {', '.join(self.index.applies_to)}."
        else:
            i = self.index
            body = f"Company: {i.company}" + (f" ({i.industry})" if i.industry else "") + f". Wording ruled on: \"{i.claim_text}\". Outcome: {i.outcome.replace('_', ' ')}. Reasoning: {i.reasoning}"
            if i.terms:
                body += f" Terms: {', '.join(i.terms)}."
        return f"{head}\n  {body}"


@dataclass
class Knowledge:
    criteria: list[StoreEntry] = field(default_factory=list)
    precedents: list[StoreEntry] = field(default_factory=list)
    directory: Path | None = None
    held_out: list[str] = field(default_factory=list)

    @property
    def entries(self) -> list[StoreEntry]:
        return [*self.criteria, *self.precedents]

    def ids(self) -> dict[str, StoreEntry]:
        """Log id -> entry: `K1..` for criteria, `P1..` for precedents, in store order, so the
        panel's narrow id column stays readable and ids never collide with a recording's `E`,
        `X`, `C`, `L` and `O` ids. The store key travels in `ext.store_id`."""
        out: dict[str, StoreEntry] = {}
        for n, entry in enumerate(self.criteria, 1):
            out[f"K{n}"] = entry
        for n, entry in enumerate(self.precedents, 1):
            out[f"P{n}"] = entry
        return out

    def listing(self) -> str:
        """The index the matcher reads: criteria first, then precedents."""
        lines = ["Substantiation criteria (rules a claim is measured against):"]
        ids = self.ids()
        lines += [entry.index_line(eid) for eid, entry in ids.items() if entry.store == "criteria"]
        lines.append("")
        lines.append("Precedents (rulings on environmental claims):")
        lines += [entry.index_line(eid) for eid, entry in ids.items() if entry.store == "precedents"]
        return "\n".join(lines)

    def for_document(self, url: str | None) -> "Knowledge":
        """The store with any precedent that adjudicated this very text held out (the leakage
        rule in demo-documents.md §6), so a ruling on the page never scores the page."""
        if not url:
            return self
        wanted = normalise_url(url)
        kept, held = [], []
        for entry in self.precedents:
            index = entry.index
            if isinstance(index, PrecedentIndex) and any(normalise_url(u) == wanted for u in index.adjudicated_urls):
                held.append(entry.id)
            else:
                kept.append(entry)
        return Knowledge(self.criteria, kept, self.directory, held)

    def without(self, store_ids: set[str]) -> "Knowledge":
        """Leave-one-out for calibration (step 19)."""
        return Knowledge(
            [e for e in self.criteria if e.id not in store_ids],
            [e for e in self.precedents if e.id not in store_ids],
            self.directory,
            sorted(store_ids),
        )


class KnowledgeError(ValueError):
    """A store file is missing or invalid. The message says which and why."""


def knowledge_dir() -> Path:
    return Path(os.environ.get("AUDITOR_KNOWLEDGE_DIR") or DEFAULT_DIR)


def _load_file(path: Path, index_model: type[BaseModel]) -> list[StoreEntry]:
    if not path.is_file():
        raise KnowledgeError(f"{path} is missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise KnowledgeError(f"{path.name}: not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise KnowledgeError(f"{path.name}: expected a list of entries")
    entries: list[StoreEntry] = []
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not isinstance(item.get("index"), dict):
            raise KnowledgeError(f"{path.name} entry {n}: not an object with an index")
        try:
            index = index_model.model_validate(item["index"])
            entry = StoreEntry.model_validate({**item, "index": index})
        except ValueError as exc:
            raise KnowledgeError(f"{path.name} entry {n} ({item.get('id', '?')}): {exc}") from exc
        entries.append(entry)
    return entries


def load_knowledge(directory: Path | None = None) -> Knowledge:
    """Both stores, validated. Raises KnowledgeError with the file and entry at fault."""
    directory = directory or knowledge_dir()
    criteria = _load_file(directory / "criteria.json", CriteriaIndex)
    precedents = _load_file(directory / "precedents.json", PrecedentIndex)
    seen: set[str] = set()
    for entry in [*criteria, *precedents]:
        if entry.id in seen:
            raise KnowledgeError(f"duplicate store id {entry.id}")
        seen.add(entry.id)
    return Knowledge(criteria, precedents, directory)


_knowledge: Knowledge | None = None


def get_knowledge() -> Knowledge:
    """The stores, loaded once per process."""
    global _knowledge
    if _knowledge is None:
        _knowledge = load_knowledge()
    return _knowledge


# ----------------------------------------------------------------------------- checking quotes


_SQUASH = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def _squash(text: str) -> str:
    return " ".join(text.translate(_SQUASH).split()).lower()


def quote_in(text: str, quote: str) -> bool:
    """Whether the quote appears in the text with whitespace, quotation marks and dashes
    normalised and case ignored: the contract's `fetched_exact` bar for the store."""
    return _squash(quote) in _squash(text)


def check_quotes(knowledge: Knowledge, fetch_text) -> list[str]:
    """For every entry with a URL: fetch it with `fetch_text(url) -> str` and report whether a
    verified quote is on the page. Returns human lines; a line starting with FAIL is a problem."""
    lines: list[str] = []
    for entry in knowledge.entries:
        if not entry.url:
            lines.append(f"skip {entry.id}: no url")
            continue
        try:
            text = fetch_text(entry.text_url or entry.url)
        except Exception as exc:  # noqa: BLE001 - reported, never raised: one bad link must not stop the check
            status = getattr(exc, "status", None)
            if status in (401, 403, 429) or "did not respond" in str(exc) or "could not be fetched" in str(exc):
                lines.append(f"warn {entry.id}: {entry.url} refused the script ({str(exc)[:80]}); open it in a browser")
            else:
                lines.append(f"FAIL {entry.id}: {entry.url} could not be read ({type(exc).__name__}: {str(exc)[:80]})")
            continue
        if entry.verified and entry.quote:
            if quote_in(text, entry.quote):
                lines.append(f"ok   {entry.id}: quote found ({entry.verification})")
            else:
                lines.append(f"FAIL {entry.id}: quote not found on {entry.url}")
        else:
            lines.append(f"ok   {entry.id}: link works (no quote to check)")
    return lines


# Below this many words, a fetched page is a JavaScript shell rather than a page, and the
# ingester is asked instead (it knows where such sites keep their text).
THIN_PAGE_WORDS = 200

# Tags that start a new line of text when a browser renders them. Every other tag is inline
# and leaves no gap: an anchor around a cross-reference must not turn "(see § 260.4)" into
# "( see § 260.4 )", which is how a real quote from eCFR stops matching its page.
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "option", "p", "pre", "section", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
DROPPED_ELEMENTS = re.compile(r"<(script|style|noscript|template)\b[^>]*>.*?</\1\s*>", re.S | re.I)
TAG = re.compile(r"<\s*/?\s*([A-Za-z][A-Za-z0-9-]*)\b[^>]*>|<[^>]+>")


def strip_tags(markup: str) -> str:
    """The text of an HTML page as a browser would lay it out: block tags become line breaks,
    inline tags disappear without leaving a gap, scripts and styles go entirely."""
    def replace(match: re.Match[str]) -> str:
        name = (match.group(1) or "").lower()
        return "\n" if name in BLOCK_TAGS else ""

    return html.unescape(TAG.sub(replace, DROPPED_ELEMENTS.sub(" ", markup)))


def page_text(url: str) -> str:
    """Page text for quote checks: as much of the page as can be read. The question here is
    whether the quote is on the page at all, not whether it is in the part an ingester would
    keep, so this takes the raw page with its tags stripped — tables, footers and small print
    included — and the PDF's text for a PDF. Only when the raw page turns out to have almost
    no text in it (a JavaScript shell) does it ask the ingester, which knows where those sites
    keep theirs. One fetch, and the most inclusive text that fetch can yield. External
    verification (step 14) checks its retrieved quotes against exactly this."""
    from .ingest import ingest_url
    from .ingest.canonical import word_count
    from .ingest.fetch import fetch

    try:
        fetched = fetch(url, timeout=40)
    except Exception as exc:  # noqa: BLE001 - the ingester has the Wayback fallback; let it try
        try:
            return ingest_url(url).document["text"]
        except Exception:
            raise exc from None  # the original refusal, whose status says whether to blame the script
    if fetched.is_pdf:
        import pymupdf

        with pymupdf.open(stream=fetched.body, filetype="pdf") as pdf:
            return "\n".join(page.get_text() for page in pdf)
    text = strip_tags(fetched.text)
    if word_count(text) >= THIN_PAGE_WORDS:
        return text
    try:
        return ingest_url(url).document["text"]
    except Exception:  # noqa: BLE001 - nothing better to offer than what the page gave
        return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.knowledge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the stores; with --fetch, look for every quote on its page")
    check.add_argument("--dir", type=Path, default=None, help="the knowledge directory (default: knowledge/ at the repository root)")
    check.add_argument("--fetch", action="store_true", help="fetch every URL and look for the verified quotes")
    args = parser.parse_args(argv)
    try:
        knowledge = load_knowledge(args.dir)
    except KnowledgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verified = sum(1 for e in knowledge.entries if e.verified)
    print(f"{len(knowledge.criteria)} criteria and {len(knowledge.precedents)} precedents in {knowledge.directory}; {verified} with a verified quote, {len(knowledge.entries) - verified} listed by name only")
    for entry in knowledge.entries:
        flag = "quote" if entry.verified else "name only"
        print(f"  {entry.id:<28} tier {entry.tier} {entry.kind:<8} {flag:<9} {entry.source.name[:70]}")
    if args.fetch:
        print("\nfetching every URL:")
        failures = 0
        for line in check_quotes(knowledge, page_text):
            print("  " + line)
            failures += line.startswith("FAIL")
        print(f"{failures} problem(s)")
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
