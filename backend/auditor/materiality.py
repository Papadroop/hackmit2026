"""The materiality reference (roadmap step 16; design-doc D4 Q3, open question 2): what counts
as material per industry, curated by hand in `knowledge/materiality.json`.

D4 Q3 asks what a document leaves out, and "left out" only means something against a list of
what should have been there. That list is this store: one entry per industry, each an external
reference (the SASB Standard for the industry, a GRI Sector Standard, a disclosure regulation)
with the disclosure topics it names. An entry is a contract EvidenceItem without its `links`,
exactly like a criterion or a precedent (`auditor.knowledge`), so an omission can cite the
reference that makes its topic material and the citation is held to the same bar: a verified
entry has a quote a script found on the page, an unverified one is listed by name and its
quote is never displayed.

`index` holds what the evaluator reads: the industry, its SASB code, the aliases and keywords
that match a document to it, and the topics. A topic carries its code, its name, why it is
material for this industry, what a complete text would address, and `terms`: the words that
appear when a page does address it. The terms are the absence check — `mentions` finds them in
the document, so a margin card that says "not mentioned" can be held to it (roadmap step 16's
visual check) and the nearest thing the page does say can be shown beside it.

One entry is the cross-industry fallback (`sasb_code: "*"`): the topics material to any
company making environmental claims, for a document whose industry the store does not know.

    python -m auditor.materiality check [--fetch]
    python -m auditor.materiality match "<industry label>" [--codes EM-EP,EM-RM]
    python -m auditor.materiality coverage <file or url>

`check` validates the file and prints what it holds; `--fetch` fetches every URL and looks for
each verified quote on its page, the same check `auditor.knowledge` runs over the other two
stores. `match` shows which entry a document lands on and why. `coverage` reads a document and
prints, topic by topic, which of the reference's words are in it and which are not: the
absence check on its own, with no model in the loop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .knowledge import DEFAULT_DIR, KnowledgeError, StoreEntry, check_quotes, page_text

STORE_FILE = "materiality.json"

# The id the cross-industry entry carries in `index.sasb_code`.
ANY_INDUSTRY = "*"


class Topic(BaseModel):
    """One material topic: what a complete document would address, and how to tell whether
    this one does."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(description="The reference's own code for the topic, e.g. EM-EP-110a; empty when it has none")
    name: str = Field(min_length=1, description="The topic as the reference names it")
    why_material: str = Field(min_length=1, description="Why this topic decides whether the industry's environmental story is honest, in one or two sentences")
    expects: str = Field(min_length=1, description="What a document that addressed the topic would say")
    terms: list[str] = Field(default_factory=list, description="Words and phrases that appear when a page does address the topic: the absence check")


class MaterialityIndex(BaseModel):
    """What the omissions evaluator reads about an industry."""

    model_config = ConfigDict(extra="forbid")
    industry: str = Field(min_length=1, description="The industry as the reference names it")
    reference: str = Field(min_length=1, description="The reference in a few characters, for the line under a margin card: 'SASB EM-EP', 'GRI 11', 'ESRS E1'")
    sasb_code: str = Field(min_length=1, description="The SASB industry code (EM-EP), or '*' for the cross-industry entry")
    also_codes: list[str] = Field(default_factory=list, description="Neighbouring SASB codes this entry also answers for (EM-RM for an oil and gas entry)")
    aliases: list[str] = Field(default_factory=list, description="Other names for the industry, matched against the document's industry label")
    keywords: list[str] = Field(default_factory=list, description="Words in the document or the company name that place a company in this industry")
    topics: list[Topic] = Field(min_length=1)

    @property
    def jurisdiction(self) -> str:
        """StoreEntry's ext block asks its index for this; a materiality reference is global."""
        return "global"

    @property
    def codes(self) -> list[str]:
        return [self.sasb_code, *self.also_codes]


class MaterialityEntry(StoreEntry):
    """One industry's reference: a contract EvidenceItem without links, plus its topics. The
    contract rules a store entry must meet are `StoreEntry`'s, checked the same way."""

    index: MaterialityIndex

    @property
    def store(self) -> str:
        return "materiality"

    def as_evidence(self, evidence_id: str, links: list[dict[str, str]], *, stage: str = "omissions") -> dict[str, Any]:
        item = super().as_evidence(evidence_id, links, stage=stage)
        item["ext"].update({"industry": self.index.industry, "sasb_code": self.index.sasb_code})
        return item

    def topic_ids(self, evidence_id: str) -> dict[str, Topic]:
        """`M1.1` -> topic, the ids the evaluator answers with."""
        return {f"{evidence_id}.{n}": topic for n, topic in enumerate(self.index.topics, 1)}

    def index_lines(self, evidence_id: str) -> str:
        """The topics as the evaluator sees them: one block per topic, under a heading naming
        the industry and the reference it comes from."""
        head = f"{self.index.industry} ({self.index.sasb_code}) — {self.source.name}"
        lines = [head]
        for topic_id, topic in self.topic_ids(evidence_id).items():
            code = f" [{topic.code}]" if topic.code else ""
            lines.append(f"{topic_id}{code} {topic.name}\n  Material because: {topic.why_material}\n  A document that addressed it would say: {topic.expects}")
        return "\n".join(lines)


@dataclass
class Match:
    """Why a document landed on an entry, for the log."""

    evidence_id: str
    entry: MaterialityEntry
    how: str


@dataclass
class Materiality:
    entries: list[MaterialityEntry] = field(default_factory=list)
    directory: Path | None = None

    def ids(self) -> dict[str, MaterialityEntry]:
        """Log id -> entry: `M1..` in store order, so ids never collide with the criteria (`K`),
        the precedents (`P`) or a recording's `E`, `X`, `C`, `L` and `O` ids."""
        return {f"M{n}": entry for n, entry in enumerate(self.entries, 1)}

    def general(self) -> Match | None:
        """The cross-industry entry, which every document is measured against as well."""
        for evidence_id, entry in self.ids().items():
            if entry.index.sasb_code == ANY_INDUSTRY:
                return Match(evidence_id, entry, "every industry")
        return None

    def industries_listing(self) -> str:
        """The industries on offer, for the call that places a document the store has no code
        for. The cross-industry entry is not one of the choices."""
        lines = []
        for evidence_id, entry in self.ids().items():
            if entry.index.sasb_code == ANY_INDUSTRY:
                continue
            names = ", ".join([*entry.index.aliases, *entry.index.keywords][:12])
            lines.append(f"{entry.index.sasb_code} | {entry.index.industry}" + (f" | {names}" if names else ""))
        return "\n".join(lines)

    def by_code(self, code: str) -> Match | None:
        """The entry for a SASB code: its own, or a neighbouring one it answers for."""
        wanted = code.strip().upper()
        if not wanted:
            return None
        for exact in (True, False):
            for evidence_id, entry in self.ids().items():
                codes = [c.upper() for c in (entry.index.codes if not exact else [entry.index.sasb_code])]
                if wanted in codes:
                    how = f"SASB code {entry.index.sasb_code}" if exact else f"SASB code {code.strip()} is covered by {entry.index.sasb_code}"
                    return Match(evidence_id, entry, how)
        return None

    def by_label(self, label: str) -> Match | None:
        """The entry whose industry name or alias the label names. Longest alias first, so
        'Oil & Gas – Refining & Marketing' does not stop at 'Oil & Gas'."""
        wanted = _fold(label)
        if not wanted:
            return None
        best: tuple[int, Match] | None = None
        for evidence_id, entry in self.ids().items():
            if entry.index.sasb_code == ANY_INDUSTRY:
                continue
            for name in [entry.index.industry, *entry.index.aliases]:
                folded = _fold(name)
                if folded and (folded in wanted or wanted in folded):
                    match = Match(evidence_id, entry, f"industry {label!r} matched {name!r}")
                    if best is None or len(folded) > best[0]:
                        best = (len(folded), match)
        return best[1] if best else None

    def for_document(self, document: dict[str, Any]) -> list[Match]:
        """The references this document is measured against: the entry for its industry, when
        the document declares one the store knows, plus the cross-industry entry. A document
        whose industry the store cannot place gets the cross-industry entry alone, and the
        evaluator asks the model to place it (`choose_industry`)."""
        industry = document.get("industry") or {}
        matches: list[Match] = []
        for code in industry.get("sasb_codes") or []:
            match = self.by_code(code)
            if match is not None and all(m.evidence_id != match.evidence_id for m in matches):
                matches.append(match)
        if not matches:
            match = self.by_label(str(industry.get("label") or ""))
            if match is not None:
                matches.append(match)
        general = self.general()
        if general is not None and all(m.evidence_id != general.evidence_id for m in matches):
            matches.append(general)
        return matches

    def topics_listing(self, matches: list[Match]) -> str:
        return "\n\n".join(match.entry.index_lines(match.evidence_id) for match in matches)

    def topics(self, matches: list[Match]) -> dict[str, tuple[Match, Topic]]:
        """Topic id -> the entry it came from and the topic itself."""
        out: dict[str, tuple[Match, Topic]] = {}
        for match in matches:
            for topic_id, topic in match.entry.topic_ids(match.evidence_id).items():
                out[topic_id] = (match, topic)
        return out


def _fold(text: str) -> str:
    """Industry names differ by punctuation and dashes more than by words."""
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("&", " and ")).strip()


# ----------------------------------------------------------------------------- the absence check


def mentions(text: str, terms: list[str]) -> list[str]:
    """The terms that appear in the text, matched on whole words and case ignored. What makes
    "not mentioned" checkable: a topic whose terms are all absent is absent from the page."""
    folded = text.lower()
    found = []
    for term in terms:
        needle = term.lower().strip()
        if not needle:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
        if re.search(pattern, folded):
            found.append(term)
    return found


# ----------------------------------------------------------------------------- loading


def store_path(directory: Path | None = None) -> Path:
    directory = directory or Path(os.environ.get("AUDITOR_KNOWLEDGE_DIR") or DEFAULT_DIR)
    return directory / STORE_FILE


def load_materiality(directory: Path | None = None) -> Materiality:
    """The store, validated. Raises KnowledgeError with the file and entry at fault."""
    path = store_path(directory)
    if not path.is_file():
        raise KnowledgeError(f"{path} is missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise KnowledgeError(f"{path.name}: not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise KnowledgeError(f"{path.name}: expected a list of entries")
    entries: list[MaterialityEntry] = []
    seen: set[str] = set()
    codes: set[str] = set()
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not isinstance(item.get("index"), dict):
            raise KnowledgeError(f"{path.name} entry {n}: not an object with an index")
        try:
            entry = MaterialityEntry.model_validate(item)
        except ValueError as exc:
            raise KnowledgeError(f"{path.name} entry {n} ({item.get('id', '?')}): {exc}") from exc
        if entry.id in seen:
            raise KnowledgeError(f"duplicate store id {entry.id}")
        for code in (c.upper() for c in entry.index.codes):
            if code in codes:
                raise KnowledgeError(f"{path.name} entry {n} ({entry.id}): a second entry for industry {code}")
            codes.add(code)
        seen.add(entry.id)
        entries.append(entry)
    if not entries:
        raise KnowledgeError(f"{path.name}: the store is empty")
    return Materiality(entries, path.parent)


_materiality: Materiality | None = None


def get_materiality() -> Materiality:
    """The store, loaded once per process."""
    global _materiality
    if _materiality is None:
        _materiality = load_materiality()
    return _materiality


# ----------------------------------------------------------------------------- command line


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.materiality", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the store; with --fetch, look for every quote on its page")
    check.add_argument("--dir", type=Path, default=None, help="the knowledge directory (default: knowledge/ at the repository root)")
    check.add_argument("--fetch", action="store_true", help="fetch every URL and look for the verified quotes")
    match = sub.add_parser("match", help="show which entry a document lands on")
    match.add_argument("label", help="an industry label, as a document's front matter carries it")
    match.add_argument("--codes", default="", help="the document's SASB codes, comma separated")
    match.add_argument("--dir", type=Path, default=None)
    coverage = sub.add_parser("coverage", help="for one document, which topics' words are in the text and which are not")
    coverage.add_argument("source", help="a URL or a path (curated .md, .html, .pdf, .json content model)")
    coverage.add_argument("--dir", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        store = load_materiality(args.dir)
    except KnowledgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.command == "coverage":
        from .ingest import IngestError, ingest_file, ingest_url

        try:
            ingested = ingest_url(args.source, demo_dir=REPO_ROOT / "demo-documents") if args.source.startswith(("http://", "https://")) else ingest_file(Path(args.source))
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        document = ingested.document
        matches = store.for_document(document)
        print(f"{document['title']} — {document['word_count']} words, industry {document['industry']['label']!r} -> {', '.join(m.entry.index.sasb_code for m in matches)}")
        print("(the words are the reference's own; a topic with none of them in the text is one the page does not raise at all)")
        for topic_id, (_, topic) in store.topics(matches).items():
            seen = mentions(document["text"], topic.terms)
            print(f"  {topic_id:<6} {'mentioned' if seen else 'ABSENT   '} {topic.name[:56]:<56} {', '.join(seen[:5])}")
        return 0
    if args.command == "match":
        codes = [c for c in (c.strip() for c in args.codes.split(",")) if c]
        document = {"industry": {"label": args.label, "sasb_codes": codes}}
        matches = store.for_document(document)
        for m in matches:
            print(f"{m.evidence_id}  {m.entry.index.industry} ({m.entry.index.sasb_code}): {m.how}; {len(m.entry.index.topics)} topics")
        print()
        print(store.topics_listing(matches))
        return 0
    topics = sum(len(e.index.topics) for e in store.entries)
    verified = sum(1 for e in store.entries if e.verified)
    print(f"{len(store.entries)} industries and {topics} material topics in {store.directory}; {verified} references with a verified quote, {len(store.entries) - verified} listed by name only")
    for evidence_id, entry in store.ids().items():
        flag = "quote" if entry.verified else "name only"
        print(f"  {evidence_id:<4} {entry.index.sasb_code:<6} {len(entry.index.topics):>2} topics  tier {entry.tier} {flag:<9} {entry.index.industry[:48]:<48} {entry.source.name[:60]}")
    if args.fetch:
        print("\nfetching every URL:")
        failures = 0
        for line in check_quotes(Materiality(store.entries), page_text):
            print("  " + line)
            failures += line.startswith("FAIL")
        print(f"{failures} problem(s)")
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
