"""PDF -> blocks, with PyMuPDF.

Reads each page's text as lines with font size and weight, drops what repeats at the top or the
bottom of pages (running headers, footers, page numbers), rebuilds paragraphs from the layout
blocks (repairing words hyphenated across lines), reads two-column pages column by column, and
uses font size to tell the title and headings from the body and small print from the rest.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import pymupdf

from .blocks import Block, Container, SMALL_PRINT_PROMINENCE, make_block
from .canonical import canonical_line, word_count

BULLET = re.compile(r"^[•·‣◦▪●○■\-–—*]\s+(.*\S)\s*$")
PAGE_NUMBER = re.compile(r"^(page\s+)?\d+(\s*(of|/)\s*\d+)?$|^\d+\s*[|/]\s*.{0,40}$|^.{0,40}\s*[|/]\s*\d+$", re.I)
BAND = 0.12  # share of the page height that counts as top or bottom margin
BOLD = 1 << 4


@dataclass
class Line:
    text: str
    size: float
    bold: bool
    y0: float
    y1: float
    x0: float
    x1: float
    block: int
    page: int


@dataclass
class PdfResult:
    blocks: list[Block]
    title: str | None
    pages: int
    dropped: int
    metadata: dict[str, Any]


def pdf_blocks(data: bytes) -> PdfResult:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
        pages: list[list[Line]] = []
        heights: list[float] = []
        widths: list[float] = []
        for page_no, page in enumerate(doc):
            heights.append(page.rect.height)
            widths.append(page.rect.width)
            pages.append(_page_lines(page, page_no))

    if not any(pages):
        return PdfResult([], _meta_title(metadata), len(pages), 0, metadata)

    body_size = _body_size(pages)
    repeated = _repeated_lines(pages, heights)
    dropped = 0
    kept_pages: list[list[Line]] = []
    for page_no, lines in enumerate(pages):
        kept: list[Line] = []
        for line in lines:
            key = _repeat_key(line.text)
            in_band = line.y0 < heights[page_no] * BAND or line.y1 > heights[page_no] * (1 - BAND)
            if in_band and (key in repeated or PAGE_NUMBER.match(line.text)):
                dropped += 1
                continue
            kept.append(line)
        kept_pages.append(_reading_order(kept, widths[page_no]))

    heading_sizes = sorted({round(l.size, 1) for page in kept_pages for l in page if l.size >= body_size * 1.15 and word_count(l.text) <= 20}, reverse=True)
    level_of = {size: min(index + 1, 6) for index, size in enumerate(heading_sizes)}

    blocks: list[Block] = []
    title_done = False
    footnote_no = 0
    for page in kept_pages:
        for group in _group_blocks(page):
            size = round(max(l.size for l in group), 1)
            text_lines = [l.text for l in group]
            if size in level_of and all(l.size >= body_size * 1.15 for l in group) and word_count(" ".join(text_lines)) <= 20:
                text = " ".join(text_lines)
                if not title_done and level_of[size] == 1:
                    blocks.append(Block("title", [canonical_line(text)]))
                    title_done = True
                else:
                    blocks.append(make_block("heading", text, level=level_of[size] + (0 if title_done else 1)))
                continue
            if all(BULLET.match(l.text) for l in group):
                for l in group:
                    blocks.append(make_block("list_item", BULLET.match(l.text).group(1)))  # type: ignore[union-attr]
                continue
            paragraph = _join_lines(text_lines)
            first = BULLET.match(text_lines[0])
            if first:
                rest = _join_lines(text_lines[1:])
                blocks.append(make_block("list_item", first.group(1) + (" " + rest if rest else "")))
                continue
            if size < body_size * 0.85 and word_count(paragraph) >= 3:
                footnote_no += 1
                if re.match(r"^(\[?\d+\]?|[a-z]\)|\(\d+\)|\*+)\s", paragraph):
                    blocks.append(make_block("paragraph", paragraph, container=Container("footnote", label=f"Footnote {footnote_no}")))
                else:
                    blocks.append(make_block("paragraph", paragraph, prominence=SMALL_PRINT_PROMINENCE))
                continue
            blocks.append(make_block("paragraph", paragraph))
    blocks = [b for b in blocks if b is not None]
    _merge_page_breaks(blocks)
    title = next((b.lines[0] for b in blocks if b.kind == "title"), None) or _meta_title(metadata)
    return PdfResult(blocks, title, len(pages), dropped, metadata)


def _meta_title(metadata: dict[str, Any]) -> str | None:
    title = metadata.get("title")
    return canonical_line(str(title)) or None if title else None


def _page_lines(page: pymupdf.Page, page_no: int) -> list[Line]:
    lines: list[Line] = []
    layout = page.get_text("dict", sort=True)
    for block_index, block in enumerate(layout.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = canonical_line("".join(s["text"] for s in line["spans"]))
            if not text:
                continue
            weights = Counter()
            for s in spans:
                weights[round(float(s["size"]), 1)] += len(s["text"])
            size = weights.most_common(1)[0][0]
            bold = all(int(s.get("flags", 0)) & BOLD for s in spans)
            x0, y0, x1, y1 = line["bbox"]
            lines.append(Line(text, size, bold, y0, y1, x0, x1, block_index, page_no))
    return lines


def _body_size(pages: list[list[Line]]) -> float:
    weights: Counter[float] = Counter()
    for page in pages:
        for line in page:
            weights[round(line.size * 2) / 2] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 10.0


def _repeat_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def _repeated_lines(pages: list[list[Line]], heights: list[float]) -> set[str]:
    """Texts (digits masked) that sit in the top or bottom band on most pages."""
    if len(pages) < 2:
        return set()
    on_pages: dict[str, set[int]] = defaultdict(set)
    for page_no, lines in enumerate(pages):
        for line in lines:
            in_band = line.y0 < heights[page_no] * BAND or line.y1 > heights[page_no] * (1 - BAND)
            if in_band:
                on_pages[_repeat_key(line.text)].add(page_no)
    # A running header is on nearly every page; two pages sharing a heading position is not one.
    threshold = 2 if len(pages) <= 3 else max(3, math.ceil(0.5 * len(pages)))
    return {key for key, where in on_pages.items() if len(where) >= threshold}


def _reading_order(lines: list[Line], page_width: float) -> list[Line]:
    """Two-column pages read column by column. Lines that span the middle keep their place in
    vertical order and separate the column runs above and below them."""
    if not lines:
        return lines
    mid = page_width / 2
    narrow_left = [l for l in lines if l.x1 < mid + page_width * 0.05]
    narrow_right = [l for l in lines if l.x0 > mid - page_width * 0.05]
    if len(narrow_left) < 3 or len(narrow_right) < 3:
        return sorted(lines, key=lambda l: (round(l.y0), l.x0))
    out: list[Line] = []
    run: list[Line] = []

    def flush_run() -> None:
        left = sorted((l for l in run if l.x1 < mid + page_width * 0.05), key=lambda l: (l.y0, l.x0))
        right = sorted((l for l in run if l.x0 > mid - page_width * 0.05), key=lambda l: (l.y0, l.x0))
        out.extend(left + right)
        run.clear()

    for line in sorted(lines, key=lambda l: (round(l.y0), l.x0)):
        spans_middle = line.x0 < mid - page_width * 0.05 and line.x1 > mid + page_width * 0.05
        if spans_middle:
            flush_run()
            out.append(line)
        else:
            run.append(line)
    flush_run()
    return out


def _group_blocks(lines: list[Line]) -> list[list[Line]]:
    """Lines of one layout block, in one column, form one group; a jump in font size starts a
    new group so a heading set in the same block as its paragraph is still separated."""
    groups: list[list[Line]] = []
    for line in lines:
        if groups and groups[-1][-1].block == line.block and groups[-1][-1].page == line.page and abs(groups[-1][-1].size - line.size) < 0.6 and not BULLET.match(line.text):
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def _join_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        if not out:
            out = line
        elif out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        else:
            out = out + " " + line
    return out


def _merge_page_breaks(blocks: list[Block]) -> None:
    """A paragraph cut by a page break continues in the next paragraph when the first does not
    end a sentence and the second starts in lower case."""
    i = 1
    while i < len(blocks):
        prev, cur = blocks[i - 1], blocks[i]
        if prev.kind == "paragraph" and cur.kind == "paragraph" and prev.container is None and cur.container is None:
            last = prev.lines[-1]
            first = cur.lines[0]
            if not re.search(r"[.!?:;\"”’)\]]$", last) and first[:1].islower():
                prev.lines[-1] = _join_lines([last, first])
                prev.lines.extend(cur.lines[1:])
                del blocks[i]
                continue
        i += 1
