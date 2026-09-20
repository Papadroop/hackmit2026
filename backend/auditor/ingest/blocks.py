"""Blocks: the one intermediate form every adapter produces, and the assembly of canonical text
plus regions from it.

An adapter (HTML, AEM model, PDF, pasted text) turns its input into an ordered list of Blocks.
`assemble` lays them out as canonical text and computes the regions *while* writing, so every
offset is exact by construction rather than found by searching afterwards. The layout rules are
the ones the golden fixture uses (fixtures/shell-climate.analysis.json): one blank line between
blocks, `\\n` between lines of one block, a paragraph region per group of blocks, a list item
region per list line, container regions (promo card, footnote, cautionary note, quote) around the
blocks they hold.

Determinism: the same blocks always give the same text and regions; nothing here depends on the
clock, the environment or iteration order of a set. That, with the canonical form, is what makes
character offsets stable across runs and across copies of the same document.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .canonical import canonical_line, check_canonical, word_count

CONTAINER_KINDS = ("cautionary_note", "promo", "footnote", "quote")
CONTAINER_PROMINENCE = {"cautionary_note": 0.3, "footnote": 0.3, "promo": 0.5, "quote": 0.7}
CONTAINER_LABELS = {"cautionary_note": "Cautionary note", "footnote": "Footnote", "promo": "Promo card", "quote": "Quote"}

# A heading this long is a styled statement, not a heading (Shell sets two of its paragraphs
# as h2/h4). It becomes a paragraph, which is how the golden reference reads it.
HEADING_MAX_WORDS = 15
HERO_PROMINENCE = 1.0
BODY_PROMINENCE = 0.6
CAPTION_PROMINENCE = 0.4
SMALL_PRINT_PROMINENCE = 0.3


@dataclass(eq=False)
class Container:
    """A run of blocks that render as one unit. Identity is by instance: two footnotes are two
    containers of the same kind."""

    kind: str
    label: str | None = None
    prominence: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in CONTAINER_KINDS:
            raise ValueError(f"unknown container kind {self.kind!r}")
        if self.prominence is None:
            self.prominence = CONTAINER_PROMINENCE[self.kind]


@dataclass
class Block:
    kind: str  # title | heading | paragraph | list_item | caption | other
    lines: list[str]
    level: int | None = None
    container: Container | None = None
    prominence: float | None = None
    joined: bool = False
    """Separated from the previous block by one `\\n` instead of a blank line, and part of its
    paragraph group (the fixture's timeline list is seven list lines in one block)."""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def words(self) -> int:
        return word_count(self.text)


def make_block(kind: str, text: str | list[str], **attrs: Any) -> Block | None:
    """A block from raw text (line breaks kept as lines) or raw lines. None when nothing is left
    after canonicalisation, so adapters can `append_block(...)` without checking."""
    raw = text.split("\n") if isinstance(text, str) else list(text)
    lines = [line for line in (canonical_line(part) for part in raw) if line]
    if not lines:
        return None
    if kind == "heading":
        level = attrs.get("level") or 2
        attrs["level"] = max(1, min(6, level))
        if word_count(" ".join(lines)) > HEADING_MAX_WORDS:
            kind = "paragraph"
            attrs.pop("level")
    return Block(kind, lines, **attrs)


def tidy(blocks: list[Block]) -> list[Block]:
    """Post-processing shared by every adapter: promote the first level-1 heading to the title,
    drop headings that head nothing, assign default prominence."""
    out = [b for b in blocks if b is not None and b.lines]

    if not any(b.kind == "title" for b in out):
        for b in out:
            if b.kind == "heading" and b.level == 1:
                b.kind, b.level = "title", None
                break

    # A heading followed by nothing, or directly by a heading of the same or a higher level,
    # heads an empty section (a link-card section whose cards were dropped). Repeat until stable
    # because dropping one can empty the one above it.
    changed = True
    while changed:
        changed = False
        kept: list[Block] = []
        for i, b in enumerate(out):
            if b.kind == "heading":
                nxt = out[i + 1] if i + 1 < len(out) else None
                if nxt is None or (nxt.kind == "heading" and (nxt.level or 6) <= (b.level or 6)) or nxt.kind == "title":
                    changed = True
                    continue
            kept.append(b)
        out = kept

    seen_title = False
    seen_hero = False
    for b in out:
        if b.kind == "title":
            seen_title = True
            continue
        if b.kind == "heading":
            continue
        if b.prominence is not None or b.container is not None:
            continue
        if b.kind == "caption":
            b.prominence = CAPTION_PROMINENCE
        elif not seen_hero and seen_title and b.kind == "paragraph":
            b.prominence = HERO_PROMINENCE
            seen_hero = True
        else:
            b.prominence = BODY_PROMINENCE
    return out


def _unique_labels(regions: list[dict[str, Any]]) -> None:
    counts: Counter[str] = Counter(r["label"] for r in regions if r.get("label"))
    seen: Counter[str] = Counter()
    for r in regions:
        label = r.get("label")
        if not label or counts[label] == 1:
            continue
        seen[label] += 1
        if seen[label] > 1:
            r["label"] = f"{label} ({seen[label]})"


def assemble(blocks: list[Block]) -> tuple[str, list[dict[str, Any]]]:
    """Canonical text and regions for a tidied block list."""
    parts: list[str] = []
    regions: list[dict[str, Any]] = []
    pos = 0
    paragraph_no = 0
    group: dict[str, Any] | None = None
    container_region: dict[str, Any] | None = None
    open_container: Container | None = None
    container_counts: Counter[str] = Counter()
    prev: Block | None = None

    def close_group() -> None:
        nonlocal group, paragraph_no
        if group is not None:
            paragraph_no += 1
            region = {"kind": "paragraph", "start": group["start"], "end": group["end"], "label": f"P{paragraph_no}"}
            if group.get("prominence") is not None:
                region["prominence"] = group["prominence"]
            regions.append(region)
            group = None

    def close_container() -> None:
        nonlocal container_region, open_container
        if container_region is not None:
            regions.append(container_region)
        container_region, open_container = None, None

    for i, b in enumerate(blocks):
        sep = "" if i == 0 else ("\n" if b.joined and prev is not None else "\n\n")
        parts.append(sep)
        pos += len(sep)
        start = pos
        body = b.text
        parts.append(body)
        pos += len(body)
        end = pos

        if b.container is not open_container:
            close_container()
            if b.container is not None:
                open_container = b.container
                container_counts[b.container.kind] += 1
                n = container_counts[b.container.kind]
                base = b.container.label or CONTAINER_LABELS[b.container.kind]
                label = base if b.container.label or n == 1 else f"{base} {n}"
                container_region = {"kind": b.container.kind, "start": start, "end": end, "label": label}
                if b.container.prominence is not None:
                    container_region["prominence"] = b.container.prominence
        if container_region is not None:
            container_region["end"] = end

        if b.kind == "title":
            close_group()
            regions.append({"kind": "title", "start": start, "end": end, "label": f"H1 {b.lines[0][:60]}"})
        elif b.kind == "heading":
            close_group()
            regions.append({"kind": "heading", "start": start, "end": end, "label": f"H{b.level} {b.lines[0][:60]}", "level": b.level})
        else:
            if b.kind == "list_item":
                line_pos = start
                for line in b.lines:
                    regions.append({"kind": "list_item", "start": line_pos, "end": line_pos + len(line)})
                    line_pos += len(line) + 1
            elif b.kind == "caption":
                regions.append({"kind": "caption", "start": start, "end": end})
            joins = group is not None and prev is not None and prev.container is b.container and (
                b.joined
                or (b.kind == "list_item" and (prev.kind == "list_item" or (prev.kind == "paragraph" and prev.lines[-1].endswith(":"))))
            )
            if joins and group is not None:
                group["end"] = end
            else:
                close_group()
                group = {"start": start, "end": end, "prominence": b.prominence if b.container is None else None}
        prev = b

    close_group()
    close_container()
    text = "".join(parts)
    check_canonical(text)
    order = {"title": 0, "cautionary_note": 1, "promo": 1, "footnote": 1, "quote": 1, "heading": 2, "paragraph": 3, "list_item": 4, "caption": 4, "other": 5}
    regions.sort(key=lambda r: (r["start"], -(r["end"] - r["start"]), order.get(r["kind"], 9)))
    _unique_labels(regions)
    return text, regions


@dataclass
class DocumentMeta:
    """Everything about a document that is not its text."""

    title: str
    company: str
    method: str
    retrieved: str
    text_type: str = "web_page"
    industry: str = "Not identified"
    sasb_codes: list[str] = field(default_factory=list)
    url: str | None = None
    archive_url: str | None = None
    fixture_path: str | None = None
    language: str = "en"
    id: str | None = None
    company_extra: dict[str, Any] = field(default_factory=dict)


def build_document(blocks: list[Block], meta: DocumentMeta) -> dict[str, Any]:
    """A contract `Document` (contract/schema.json) from blocks and metadata."""
    text, regions = assemble(tidy(blocks))
    company: dict[str, Any] = {"name": meta.company or "Not identified"}
    company.update({k: v for k, v in meta.company_extra.items() if v})
    industry: dict[str, Any] = {"label": meta.industry or "Not identified"}
    if meta.sasb_codes:
        industry["sasb_codes"] = list(meta.sasb_codes)
    source: dict[str, Any] = {"retrieved": meta.retrieved, "method": meta.method}
    if meta.url:
        source["url"] = meta.url
    if meta.archive_url:
        source["archive_url"] = meta.archive_url
    if meta.fixture_path:
        source["fixture_path"] = meta.fixture_path
    return {
        "id": meta.id or slug(meta.title, meta.retrieved),
        "title": meta.title,
        "company": company,
        "industry": industry,
        "text_type": meta.text_type,
        "source": source,
        "language": meta.language,
        "text": text,
        "word_count": word_count(text),
        "regions": regions,
    }


def slug(*parts: str, limit: int = 64) -> str:
    """An id matching the contract's Id pattern, from any strings."""
    import re
    import unicodedata

    raw = "-".join(p for p in parts if p)
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    raw = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").lower()
    return (raw or "document")[:limit].rstrip("-.")
