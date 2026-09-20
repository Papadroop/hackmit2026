"""Adobe Experience Manager content model (`<page>.model.json`) -> blocks.

Sites such as shell.com serve an empty HTML shell and render from this JSON. The model is a tree
of components; each carries a `model` with a `title` and/or a rich-text `text` field. Sections
give level-2 headings, components level-3, rich text is read by the HTML walker, a list of
title-only items becomes one block of lines (the fixture's timeline), promo cards keep their
copy and drop when they are only a link, and the page's header and footer subtrees are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .blocks import Block, Container, HERO_PROMINENCE, make_block
from .canonical import canonical_line
from .html import CAUTIONARY_HEADING, FOOTNOTE_HEADING, fragment_blocks

SKIP_SEGMENTS = re.compile(r"^(header|footer|contentowner|breadcrumb|navigation|inherited)($|_)")


@dataclass
class AemResult:
    blocks: list[Block]
    title: str | None
    dropped: int


def model_url_for(page_url: str) -> str:
    """`https://host/a/b.html` -> `https://host/a/b.model.json`."""
    parts = urlsplit(page_url)
    path = re.sub(r"\.html?$", "", parts.path.rstrip("/")) or "/index"
    return urlunsplit((parts.scheme, parts.netloc, path + ".model.json", "", ""))


def looks_like_model(data: Any) -> bool:
    return isinstance(data, dict) and ("children" in data or ":items" in data) and isinstance(data.get("model", data.get(":type")), (dict, str))


def aem_blocks(model: dict[str, Any]) -> AemResult:
    blocks: list[Block] = []
    dropped = 0
    page_model = model.get("model") if isinstance(model.get("model"), dict) else {}
    page_title = canonical_line(str(page_model.get("title") or "")) or None

    def segment(node: dict[str, Any]) -> str:
        return str(node.get("id") or "").rsplit("/", 1)[-1]

    def fields(node: dict[str, Any]) -> tuple[str | None, str | None]:
        m = node.get("model") if isinstance(node.get("model"), dict) else {}
        title = canonical_line(str(m.get("title") or "")) or None
        text = m.get("text") if isinstance(m.get("text"), str) else None
        return title, text

    def visit(node: dict[str, Any], container: Container | None, depth: int) -> None:
        nonlocal dropped
        if not isinstance(node, dict):
            return
        seg = segment(node)
        node_id = str(node.get("id") or "")
        if SKIP_SEGMENTS.match(seg) or "/header/" in node_id or "/footer/" in node_id:
            dropped += 1
            return
        title, text = fields(node)
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        items = node.get(":items")
        if isinstance(items, dict):
            order = node.get(":itemsOrder") or list(items.keys())
            children += [items[k] for k in order if isinstance(items.get(k), dict)]

        if seg == "metadata":
            if title:
                blocks.append(Block("title", [title]))
            if text:
                blocks.extend(fragment_blocks(text, prominence=HERO_PROMINENCE))
            return

        if seg.startswith("section"):
            if title:
                blocks.append(make_block("heading", title, level=2, container=container))
            for child in children:
                visit(child, container, depth + 1)
            return

        if seg.startswith("list") and children and all(fields(c)[0] and not fields(c)[1] and not c.get("children") for c in children):
            lines = [fields(c)[0] for c in children]
            blocks.append(make_block("list_item", [line for line in lines if line], container=container))
            return

        own_container = container
        heading_in_container = True
        if title and FOOTNOTE_HEADING.match(title):
            own_container = Container("footnote")
            heading_in_container = False
        elif title and CAUTIONARY_HEADING.match(title):
            own_container = Container("cautionary_note")
        elif seg.startswith("promo"):
            if not text or not canonical_line(_strip_tags(text)):
                dropped += 1
                return
            own_container = Container("promo")

        if title:
            blocks.append(make_block("heading", title, level=3, container=own_container if heading_in_container else container))
        if text:
            blocks.extend(fragment_blocks(text, container=own_container))
        for child in children:
            visit(child, own_container, depth + 1)

    for child in model.get("children") or []:
        visit(child, None, 1)
    if not any(b.kind == "title" for b in blocks if b is not None) and page_title:
        blocks.insert(0, Block("title", [page_title]))
    return AemResult([b for b in blocks if b is not None], page_title, dropped)


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)
