"""Plain or lightly marked-up text -> blocks, and the reverse for the curated demo copies.

The curated format under demo-documents/ is this: optional `---` front matter of flat
`key: value` lines, then the text with `#` headings and `- ` bullets, one blank line between
blocks. Reading it gives exactly the fixture's canonical text; `to_curated` writes a Document
back in the same shape, so a page re-extracted in step 10 can be saved for review and diffed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .blocks import Block, Container, make_block
from .html import CAUTIONARY_HEADING, FOOTNOTE_HEADING, _section_containers

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
BULLET = re.compile(r"^[-*•‣◦▪]\s+(.*\S)\s*$")
QUOTE = re.compile(r"^>\s?(.*)$")


@dataclass
class TextResult:
    blocks: list[Block]
    frontmatter: dict[str, str] = field(default_factory=dict)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Flat `key: value` pairs between leading `---` lines, and the body after them."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fields: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, "\n".join(lines[i + 1 :])
        key, sep, value = line.partition(":")
        if sep and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key.strip()):
            fields[key.strip()] = value.strip()
    return {}, text


def text_blocks(text: str) -> TextResult:
    frontmatter, body = split_frontmatter(text.replace("\r\n", "\n").replace("\r", "\n"))
    blocks: list[Block] = []
    quote: Container | None = None
    joined = False
    for raw in body.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            joined = False
            quote = None
            continue
        m = HEADING.match(line)
        if m:
            level = len(m.group(1))
            blocks.append(make_block("title" if level == 1 and not any(b.kind == "title" for b in blocks) else "heading", m.group(2), level=level, joined=joined))
            joined = True
            continue
        m = BULLET.match(line)
        if m:
            blocks.append(make_block("list_item", m.group(1), joined=joined))
            joined = True
            continue
        m = QUOTE.match(line)
        if m:
            if quote is None:
                quote = Container("quote")
                joined = False
            blocks.append(make_block("paragraph", m.group(1), container=quote, joined=joined))
            joined = True
            continue
        blocks.append(make_block("paragraph", line, joined=joined))
        joined = True
    blocks = [b for b in blocks if b is not None]
    _merge_joined_lines(blocks)
    _section_containers(blocks)
    return TextResult(blocks, frontmatter)


def _merge_joined_lines(blocks: list[Block]) -> None:
    """Consecutive lines of the same kind in one block of text become one multi-line block, so a
    two-line paragraph stays one paragraph and a run of bullets one list block, as the fixture
    lays out the timeline."""
    i = 1
    while i < len(blocks):
        prev, cur = blocks[i - 1], blocks[i]
        if cur.joined and cur.kind == prev.kind and cur.kind in ("paragraph", "list_item") and cur.container is prev.container and prev.level == cur.level:
            prev.lines.extend(cur.lines)
            del blocks[i]
        else:
            i += 1


def to_curated(document: dict[str, Any], frontmatter: dict[str, str] | None = None) -> str:
    """The curated markdown for a Document: front matter, then the text with `#` and `- `
    markers restored from the regions."""
    text: str = document["text"]
    regions = document.get("regions") or []
    line_marker: dict[int, str] = {}
    for r in regions:
        if r["kind"] == "title":
            line_marker[r["start"]] = "# "
        elif r["kind"] == "heading":
            line_marker[r["start"]] = "#" * int(r.get("level") or 2) + " "
        elif r["kind"] == "list_item":
            line_marker[r["start"]] = "- "
    out: list[str] = []
    pos = 0
    for line in text.split("\n"):
        out.append(line_marker.get(pos, "") + line if line else "")
        pos += len(line) + 1
    body = "\n".join(out)
    if frontmatter is None:
        frontmatter = {}
        for key in ("title",):
            frontmatter[key] = document.get(key, "")
        frontmatter["company"] = document.get("company", {}).get("name", "")
        source = document.get("source", {})
        for key in ("url", "retrieved", "method", "archive_url"):
            if source.get(key):
                frontmatter[key] = source[key]
        frontmatter["text_type"] = document.get("text_type", "")
        frontmatter["industry"] = document.get("industry", {}).get("label", "")
        if document.get("industry", {}).get("sasb_codes"):
            frontmatter["sasb_codes"] = ", ".join(document["industry"]["sasb_codes"])
        frontmatter["words_total"] = str(document.get("word_count", ""))
    head = "\n".join(f"{k}: {v}" for k, v in frontmatter.items() if v not in (None, ""))
    return f"---\n{head}\n---\n\n{body}\n"


__all__ = ["text_blocks", "to_curated", "split_frontmatter", "TextResult", "FOOTNOTE_HEADING", "CAUTIONARY_HEADING"]
