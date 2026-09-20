"""HTML page -> blocks.

Reads the page the way a person does: the main content (article, main, or the body), with the
chrome pruned away: navigation, headers and footers of the page, share sheets, galleries and
carousels (one slide at a time is not reading order), hidden copy-to-clipboard duplicates, press
contacts, "more from" lists, cookie and consent banners. Inside the content, block elements
become blocks, `<br><br>` inside a div splits a block, lists become list items, blockquotes and
link cards become containers, captions stay as captions, footnote and legal lists become
footnotes, and a heading that is really a long statement becomes a paragraph.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .blocks import Block, Container, SMALL_PRINT_PROMINENCE, make_block
from .canonical import canonical_line, word_count

DROP_TAGS = frozenset(
    "script style noscript template svg iframe canvas object embed video audio picture source img "
    "input select textarea button form map area meta link head dialog menu".split()
)
INLINE_TAGS = frozenset(
    "a abbr b bdi bdo cite code data del dfn em i ins kbd mark q s samp small span strong sub sup "
    "time u var wbr font label".split()
)
BLOCK_KINDS = {"p": "paragraph", "pre": "paragraph", "figcaption": "caption", "caption": "caption", "dt": "paragraph", "dd": "paragraph", "address": "paragraph", "summary": "paragraph"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
LANDMARK_ROLES = frozenset("navigation banner contentinfo complementary search dialog menu menubar toolbar tablist alertdialog".split())

# Class or id fragments that mark chrome rather than content. Matched at a token boundary so
# "share" hits "nr-article-share" and "sharesheet" but "shareholder" does not.
BOILERPLATE = re.compile(
    r"(^|[-_\s:])("
    r"nav|navbar|navigation|menu|breadcrumbs?|cookie|cookies|consent|gdpr|share|sharesheet|sharing|social|subscribe|newsletter|"
    r"related|recommend(ed|ations)?|more-from|sidebar|popup|modal|overlay|banner|advert|ads?|pagination|pager|search|login|signin|"
    r"comments?|skip|skiplink|toolbar|dotnav|paddlenav|carousel|slider|slideshow|gallery|docsanddownloads|presscontacts?|contactinfo|"
    r"footertile|globalmessage|globalnav|localnav|visuallyhidden|sr-only|screen-reader|tooltip|dropdown|tablist|footer|masthead|"
    r"wm-ipp|site-header|page-header-nav|back-to-top|latest-news|read-more"
    r")([-_\s:]|$)",
    re.IGNORECASE,
)
FOOTNOTE_CLASS = re.compile(r"(^|[-_\s])(footnotes?|sosumi|legal-notes?|endnotes?|references)([-_\s]|$)", re.I)
CAUTIONARY_CLASS = re.compile(r"(^|[-_\s])(cautionary|disclaimer|forward-looking|safe-harbou?r)([-_\s]|$)", re.I)
CAPTION_CLASS = re.compile(r"caption", re.I)
DECK_CLASS = re.compile(r"(^|[-_\s])(subhead(line)?|deck|standfirst|lead|intro(duction)?|summary-text|hero-text)([-_\s]|$)", re.I)
QUOTE_ATTRIBUTION_CLASS = re.compile(r"(^|[-_\s])(cite|name|author|position|title|role|attribution|source|info)([-_\s]|$)", re.I)
FOOTNOTE_HEADING = re.compile(r"^(foot ?notes?|notes|end ?notes|references)\b", re.I)
CAUTIONARY_HEADING = re.compile(r"^(cautionary (note|statement)s?|forward[- ]looking statements?|disclaimer|legal (notice|disclaimer)|safe harbou?r)", re.I)
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
THIN_WORDS = 60


@dataclass
class PageMeta:
    title: str | None = None
    site_name: str | None = None
    organisation: str | None = None
    language: str | None = None
    published: str | None = None
    og_type: str | None = None
    canonical_url: str | None = None
    aem_model_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def page_meta(soup: BeautifulSoup, url: str | None = None) -> PageMeta:
    meta = PageMeta()
    if soup.html is not None and soup.html.get("lang"):
        meta.language = str(soup.html.get("lang")).split("-")[0].lower() or None
    if soup.title is not None and soup.title.string:
        meta.title = canonical_line(soup.title.string) or None

    def content(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag is not None and tag.get("content"):
                return canonical_line(str(tag.get("content"))) or None
        return None

    meta.site_name = content("og:site_name")
    meta.og_type = content("og:type")
    meta.published = content("article:published_time", "datePublished", "date", "pubdate")
    og_title = content("og:title")
    if not meta.title and og_title:
        meta.title = og_title
    canonical = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    if canonical is not None and canonical.get("href"):
        meta.canonical_url = str(canonical["href"])
    for link in soup.find_all("link", attrs={"rel": lambda v: v and "preload" in v}):
        href = str(link.get("href") or "")
        if href.endswith(".model.json"):
            meta.aem_model_url = urljoin(url or "", href)
            break
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.get_text() or "")
        except (ValueError, TypeError):
            continue
        for node in _ld_nodes(data):
            typ = node.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if "Organization" in types and isinstance(node.get("name"), str) and not meta.organisation:
                meta.organisation = canonical_line(node["name"]) or None
            publisher = node.get("publisher")
            if isinstance(publisher, dict) and isinstance(publisher.get("name"), str) and not meta.organisation:
                meta.organisation = canonical_line(publisher["name"]) or None
            author = node.get("author")
            if isinstance(author, str) and author.strip() and not meta.extra.get("author"):
                meta.extra["author"] = canonical_line(author)
            if isinstance(node.get("datePublished"), str) and not meta.published:
                meta.published = node["datePublished"]
            if isinstance(node.get("headline"), str) and not og_title:
                og_title = canonical_line(node["headline"]) or None
    meta.extra["og_title"] = og_title
    if not meta.organisation and meta.extra.get("author"):
        meta.organisation = meta.extra["author"]
    return meta


def _ld_nodes(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from _ld_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from _ld_nodes(item)


# ----------------------------------------------------------------------------- pruning


def _attr_text(el: Tag, name: str) -> str:
    value = el.get(name)
    if isinstance(value, list):
        return " ".join(value)
    return str(value or "")


def is_boilerplate(el: Tag) -> bool:
    """Chrome by markup: hidden, a landmark role, or a class/id that names navigation, sharing,
    galleries and the like."""
    if el.name in DROP_TAGS:
        return True
    if el.has_attr("hidden") or _attr_text(el, "aria-hidden").lower() == "true":
        return True
    if HIDDEN_STYLE.search(_attr_text(el, "style")):
        return True
    if _attr_text(el, "role").lower() in LANDMARK_ROLES:
        return True
    classes = _attr_text(el, "class")
    if "hidden" in classes.split():
        return True
    if BOILERPLATE.search(classes) or BOILERPLATE.search(_attr_text(el, "id")):
        return True
    # Sites that name their regions only for analytics or assistive technology.
    for name, value in el.attrs.items():
        if name in ("aria-label", "aria-labelledby") or name.startswith("data-"):
            text = " ".join(value) if isinstance(value, list) else str(value)
            if len(text) <= 80 and BOILERPLATE.search(text):
                return True
    return False


def _is_page_level(el: Tag) -> bool:
    """A header/footer that belongs to the page, not to a card or section inside the content."""
    parent = el.parent
    while parent is not None and isinstance(parent, Tag):
        if parent.name in ("article", "section", "figure", "blockquote", "li", "td", "th", "aside"):
            return False
        if parent.name in ("main", "body", "html"):
            return True
        parent = parent.parent
    return True


def prune(soup: BeautifulSoup) -> int:
    """Remove chrome from the whole tree. Returns how many elements were dropped."""
    dropped = 0
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for el in list(soup.find_all(True)):
        if el.decomposed or not el.parent:
            continue
        if is_boilerplate(el) or (el.name in ("header", "footer", "nav") and _is_page_level(el)):
            el.decompose()
            dropped += 1
    return dropped


def _text_len(el: Tag | None) -> int:
    return len(el.get_text(" ", strip=True)) if el is not None else 0


def choose_root(soup: BeautifulSoup) -> tuple[Tag, str]:
    """The element to read: the largest article when it carries most of the page, else main,
    else the body."""
    body = soup.body or soup
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    scope = main if isinstance(main, Tag) else body
    articles = [a for a in soup.find_all("article") if isinstance(a, Tag)]
    if articles:
        best = max(articles, key=_text_len)
        if _text_len(best) >= 0.5 * _text_len(scope):
            return best, _describe(best)
    return scope, _describe(scope)


def _describe(el: Tag) -> str:
    ident = el.get("id")
    classes = _attr_text(el, "class").split()
    if ident:
        return f"{el.name}#{ident}"
    if classes:
        return f"{el.name}.{classes[0]}"
    return el.name


# ----------------------------------------------------------------------------- walking


class Walker:
    """Turns an element subtree into blocks. Inline content between block children accumulates
    into an anonymous run; `<br>` breaks a line; two `<br>` in a row end the block."""

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.container: Container | None = None
        self.kind_override: str | None = None  # list_item inside <li>
        self.prominence: float | None = None
        self._lines: list[str] = []
        self._parts: list[str] = []
        self._breaks = 0
        self.dropped = 0

    # -- inline run ---------------------------------------------------------------------------
    def _line_text(self) -> str:
        return canonical_line("".join(self._parts))

    def _end_line(self) -> None:
        line = self._line_text()
        if line:
            self._lines.append(line)
        self._parts = []

    def flush(self, kind: str | None = None, **attrs: Any) -> None:
        self._end_line()
        self._breaks = 0
        if self._lines:
            self.add(kind or self.kind_override or "paragraph", list(self._lines), **attrs)
        self._lines = []

    def add(self, kind: str, text: str | list[str], **attrs: Any) -> Block | None:
        attrs.setdefault("container", self.container)
        if self.prominence is not None and attrs.get("prominence") is None and self.container is None:
            attrs["prominence"] = self.prominence
        block = make_block(kind, text, **attrs)
        if block is not None:
            self.blocks.append(block)
        return block

    def text(self, s: str) -> None:
        if s.strip():
            self._breaks = 0
        self._parts.append(s)

    def br(self) -> None:
        self._end_line()
        self._breaks += 1
        if self._breaks >= 2:
            self.flush()

    # -- elements -----------------------------------------------------------------------------
    def walk(self, el: Tag) -> None:
        for child in list(el.children):
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                self.text(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            self.element(child)

    def element(self, el: Tag) -> None:  # noqa: C901 - one dispatch table is clearer than ten methods
        name = el.name
        if is_boilerplate(el):
            self.dropped += 1
            return
        if name == "br":
            self.br()
            return
        if name in INLINE_TAGS:
            if _has_block_children(el):
                # An anchor wrapping a card: its heading and copy read as a promo card; a card
                # with a heading and nothing else is navigation.
                if name == "a":
                    self._card(el)
                else:
                    self.flush()
                    self.walk(el)
                    self.flush()
                return
            self.walk(el)
            return
        if name in HEADINGS:
            self.flush()
            heading = canonical_line(el.get_text(" "))
            if heading:
                self.add("heading", heading, level=HEADINGS[name])
            return
        if name in ("ul", "ol"):
            self.flush()
            self._list(el)
            return
        if name == "li":
            self.flush()
            self._list_item(el, ordered=False, index=None)
            return
        if name == "blockquote":
            self.flush()
            self._with_container(Container("quote"), el)
            return
        if name == "figure":
            if _inside(el, lambda p: BOILERPLATE.search(_attr_text(p, "class")) is not None):
                self.dropped += 1
                return
            self.flush()
            self.walk(el)
            self.flush()
            return
        if name == "table":
            self.flush()
            self._table(el)
            return
        if name == "pre":
            self.flush()
            self.add("paragraph", el.get_text())
            return
        if name in BLOCK_KINDS or name in ("div", "section", "article", "main", "aside", "header", "footer", "details", "body", "html", "dl", "fieldset", "center", "hgroup", "nav"):
            self.flush()
            classes = _attr_text(el, "class") + " " + _attr_text(el, "id")
            kind = BLOCK_KINDS.get(name)
            if kind is None and CAPTION_CLASS.search(classes) and not _has_block_children(el):
                kind = "caption"
            if FOOTNOTE_CLASS.search(classes):
                self._footnotes(el)
                return
            if CAUTIONARY_CLASS.search(classes):
                self._with_container(Container("cautionary_note"), el)
                return
            if kind is not None and not _has_block_children(el):
                saved = self.prominence
                if DECK_CLASS.search(classes) and kind == "paragraph":
                    self.prominence = 1.0
                self.walk(el)
                self.flush(kind)
                self.prominence = saved
                return
            saved = self.prominence
            if DECK_CLASS.search(classes) and not _has_block_children(el):
                self.prominence = 1.0
            self.walk(el)
            self.flush()
            self.prominence = saved
            return
        if name == "hr":
            self.flush()
            return
        # Anything else (custom elements, unknown tags): read through it.
        self.walk(el)

    def _with_container(self, container: Container, el: Tag, *, heading: str | None = None) -> None:
        saved = self.container
        self.container = container
        if heading:
            self.add("heading", heading, level=3)
        self.walk(el)
        self.flush()
        self.container = saved

    def _card(self, anchor: Tag) -> None:
        heading_text = " ".join(canonical_line(h.get_text(" ")) for h in anchor.find_all(HEADINGS.keys()))
        body_text = canonical_line(anchor.get_text(" "))
        if heading_text and word_count(body_text) <= word_count(heading_text) + 3:
            self.dropped += 1
            return
        self.flush()
        if heading_text:
            self._with_container(Container("promo"), anchor)
        else:
            self.walk(anchor)
            self.flush()

    def _list(self, el: Tag) -> None:
        ordered = el.name == "ol"
        index = 0
        for child in el.children:
            if isinstance(child, Tag) and child.name == "li":
                index += 1
                self._list_item(child, ordered=ordered, index=index)
            elif isinstance(child, Tag):
                self.element(child)
            elif isinstance(child, NavigableString) and child.strip():
                self.text(str(child))
                self.flush("list_item")

    def _list_item(self, li: Tag, *, ordered: bool, index: int | None) -> None:
        if is_boilerplate(li):
            self.dropped += 1
            return
        saved = self.kind_override
        self.kind_override = "list_item"
        before = len(self.blocks)
        self.walk(li)
        self.flush("list_item")
        if ordered and index is not None and len(self.blocks) > before:
            self.blocks[before].meta["number"] = index
        self.kind_override = saved

    def _footnotes(self, el: Tag) -> None:
        """Each item of a footnote list is its own footnote container; an ordered list keeps its
        numbers because the body refers to them."""
        items = [li for li in el.find_all("li") if _list_depth(li, el) == 1]
        if not items:
            self._with_container(Container("footnote"), el)
            return
        ordered = any(p.name == "ol" for p in items[0].parents)
        for index, li in enumerate(items, start=1):
            container = Container("footnote", label=f"Footnote {index}")
            saved_container, saved_kind = self.container, self.kind_override
            self.container, self.kind_override = container, "paragraph"
            self.walk(li)
            self._end_line()
            if self._lines and ordered:
                self._lines[0] = f"{index}. {self._lines[0]}"
            self.flush("paragraph")
            self.container, self.kind_override = saved_container, saved_kind

    def _table(self, table: Tag) -> None:
        caption = table.find("caption")
        if caption is not None:
            self.add("caption", caption.get_text(" "))
        for row in table.find_all("tr"):
            cells = [canonical_line(c.get_text(" ")) for c in row.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if cells:
                self.add("other", " | ".join(cells))


def _has_block_children(el: Tag) -> bool:
    for d in el.descendants:
        if isinstance(d, Tag) and d.name not in INLINE_TAGS and d.name != "br" and d.name not in DROP_TAGS:
            return True
    return False


def _list_depth(li: Tag, top: Tag) -> int:
    depth = 0
    parent = li.parent
    while isinstance(parent, Tag) and parent is not top:
        if parent.name in ("ul", "ol"):
            depth += 1
        parent = parent.parent
    return depth


def _inside(el: Tag, predicate: Any) -> bool:
    parent = el.parent
    while isinstance(parent, Tag):
        if predicate(parent):
            return True
        parent = parent.parent
    return False


# ----------------------------------------------------------------------------- entry points


@dataclass
class HtmlResult:
    blocks: list[Block]
    meta: PageMeta
    root: str
    dropped: int
    words: int


def html_blocks(html: str, url: str | None = None) -> HtmlResult:
    soup = parse(html)
    meta = page_meta(soup, url)
    dropped = prune(soup)
    root, description = choose_root(soup)
    walker = Walker()
    walker.walk(root)
    walker.flush()
    blocks = walker.blocks
    _attach_quote_attributions(blocks)
    _section_containers(blocks)
    if not any(b.kind in ("title",) or (b.kind == "heading" and b.level == 1) for b in blocks):
        title = meta.extra.get("og_title") or _short_title(meta.title, meta.site_name)
        if title:
            blocks.insert(0, Block("title", [title]))
    words = sum(b.words for b in blocks)
    return HtmlResult(blocks, meta, description, dropped + walker.dropped, words)


def fragment_blocks(html: str, *, container: Container | None = None, prominence: float | None = None) -> list[Block]:
    """Blocks of an HTML fragment (a rich-text field of a content model), no pruning of chrome."""
    soup = BeautifulSoup(f"<div>{html}</div>", "lxml")
    walker = Walker()
    walker.container = container
    walker.prominence = prominence
    root = soup.body or soup
    walker.walk(root)
    walker.flush()
    return walker.blocks


def _section_containers(blocks: list[Block]) -> None:
    """A heading that says "Footnotes" or "Cautionary note" makes the blocks under it (until the
    next heading of the same or a higher level) footnotes or a cautionary note. The cautionary
    heading belongs to its note; a footnotes heading stays outside, each note its own region, as
    the golden fixture lays them out."""
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind != "heading" or b.container is not None:
            i += 1
            continue
        text = b.lines[0]
        kind = "footnote" if FOOTNOTE_HEADING.match(text) else "cautionary_note" if CAUTIONARY_HEADING.match(text) else None
        if kind is None:
            i += 1
            continue
        level = b.level or 6
        j = i + 1
        while j < len(blocks) and not (blocks[j].kind == "heading" and (blocks[j].level or 6) <= level) and blocks[j].kind != "title":
            j += 1
        section = [x for x in blocks[i + 1 : j] if x.container is None]
        if kind == "cautionary_note":
            container = Container("cautionary_note")
            b.container = container
            for x in section:
                x.container = container
        else:
            n = 0
            for x in section:
                if x.kind in ("heading",):
                    continue
                n += 1
                x.container = Container("footnote", label=f"Footnote {n}")
                if x.kind == "list_item" and x.meta.get("number"):
                    x.lines[0] = f"{x.meta['number']}. {x.lines[0]}"
                x.kind = "paragraph"
        i = j


def _attach_quote_attributions(blocks: list[Block]) -> None:
    """Up to three short lines straight after a quotation (a name, a job title) are its
    attribution: captions inside the quote container rather than paragraphs of the body."""
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.container is None or b.container.kind != "quote":
            i += 1
            continue
        container = b.container
        j = i + 1
        while j < len(blocks) and blocks[j].container is container:
            j += 1
        k = j
        while k < len(blocks) and k - j < 3 and blocks[k].kind == "paragraph" and blocks[k].container is None and blocks[k].words <= 8 and len(blocks[k].lines) == 1:
            blocks[k].kind = "caption"
            blocks[k].container = container
            blocks[k].prominence = None
            k += 1
        i = k


def _short_title(title: str | None, site_name: str | None) -> str | None:
    if not title:
        return None
    for sep in (" | ", " - ", " – ", " — "):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if site_name and canonical_line(tail).lower() == site_name.lower():
                return head
            return head
    return title


def is_thin(result: HtmlResult) -> bool:
    return result.words < THIN_WORDS


def company_from_host(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    host = host.removeprefix("www.")
    labels = [p for p in host.split(".") if p]
    if len(labels) < 2:
        return None
    # second-level label, ignoring country-code second levels such as co.uk
    label = labels[-3] if len(labels) >= 3 and len(labels[-2]) <= 3 and len(labels[-1]) == 2 else labels[-2]
    return label.capitalize() if label else None
