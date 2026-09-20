"""Canonical plain text (contract/CONTRACT.md §3).

Every offset in an analysis indexes into `Document.text`, so the text has one exact form: NFC,
ASCII spaces only (no tabs, no U+00A0, no runs), `\\n` line breaks, blocks separated by one blank
line, nothing leading or trailing, no markdown markers. `canonical_line` is applied to every line
an adapter produces and `check_canonical` proves the assembled text before it leaves ingestion,
so a Document can never carry text the contract validator would refuse.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible to a reader, and not whitespace to Python, so `\s` would keep them: zero-width
# space/joiners, word joiner, byte-order mark, soft hyphen.
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_WHITESPACE = re.compile(r"\s+")


class CanonicalError(ValueError):
    """The assembled text breaks a canonical-form rule. A bug in an adapter, never user input."""


def canonical_line(text: str) -> str:
    """One line of canonical text: NFC, invisible characters dropped, every run of whitespace
    (including U+00A0 and line breaks) one ASCII space, trimmed. Empty when nothing is left."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    return _WHITESPACE.sub(" ", text).strip()


def check_canonical(text: str) -> None:
    """The rules `contract/tools/contract.py check_text` enforces, raised as CanonicalError."""
    if not text:
        raise CanonicalError("document text is empty")
    if unicodedata.normalize("NFC", text) != text:
        raise CanonicalError("text is not NFC-normalised")
    if "\r" in text:
        raise CanonicalError("text contains carriage returns")
    bad = sorted({ch for ch in text if ch.isspace() and ch not in (" ", "\n")})
    if bad:
        raise CanonicalError(f"text contains non-canonical whitespace {[hex(ord(c)) for c in bad]}")
    if "  " in text:
        raise CanonicalError("text contains runs of spaces")
    if re.search(r" \n|\n ", text):
        raise CanonicalError("text has spaces at a line boundary")
    if "\n\n\n" in text or text != text.strip():
        raise CanonicalError("text has blank-line runs or leading/trailing whitespace")


def word_count(text: str) -> int:
    """What the contract validator compares `word_count` against."""
    return len(text.split())
