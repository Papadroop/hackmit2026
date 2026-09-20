/**
 * Span anchoring (contract/CONTRACT.md §3). A Span carries `text` plus code-point offsets
 * `start`/`end` into Document.text, and `text` is authoritative. Two things can go wrong when
 * the browser uses the offsets directly:
 *
 * 1. JavaScript strings are UTF-16, the contract counts Unicode code points. They agree until
 *    the text contains a character outside the Basic Multilingual Plane (an emoji, some CJK),
 *    after which every UTF-16 index is ahead of its code-point index.
 * 2. The offsets can simply be stale (a live extractor working from a slightly different copy
 *    of the text). Then the span's `text`, `context` and `occurrence` re-anchor it, by the same
 *    rules contract/tools/contract.py uses.
 *
 * Every anchored span is verified: the slice of the document at the resulting UTF-16 range
 * equals the span's text, or the span is reported as unanchored and never drawn.
 */
import type { Span } from "@contract"

/** Maps contract (code-point) offsets to UTF-16 string indices for one text. */
export type OffsetIndex = {
  /** UTF-16 index of the given code-point offset. Clamped to the text's length. */
  toUnit: (codePoint: number) => number
  /** Code-point offset of a UTF-16 index; the inverse of toUnit for indices on a code point boundary. */
  toCodePoint: (unit: number) => number
}

const SURROGATE = /[\uD800-\uDBFF]/

export function makeOffsetIndex(text: string): OffsetIndex {
  if (!SURROGATE.test(text)) {
    const length = text.length
    const clamp = (n: number) => Math.min(Math.max(n, 0), length)
    return { toUnit: clamp, toCodePoint: clamp }
  }
  // Astral characters present: build the mapping once. units[i] is the UTF-16 index of code point i.
  const units: number[] = []
  let unit = 0
  for (const ch of text) {
    units.push(unit)
    unit += ch.length
  }
  units.push(unit)
  const unitToCp = new Map<number, number>()
  units.forEach((u, cp) => unitToCp.set(u, cp))
  return {
    toUnit: (cp) => units[Math.min(Math.max(cp, 0), units.length - 1)],
    toCodePoint: (u) => {
      const clamped = Math.min(Math.max(u, 0), unit)
      const hit = unitToCp.get(clamped)
      if (hit !== undefined) return hit
      // Inside a surrogate pair: attribute it to the code point that starts there.
      return unitToCp.get(clamped - 1) ?? 0
    },
  }
}

export type AnchorMethod = "offset" | "context" | "occurrence" | "unique"

/** A span located in the text, as UTF-16 indices. */
export type Anchored = { start: number; end: number; method: AnchorMethod }

/** Every index at which `needle` occurs in `text`, non-overlapping, left to right. */
export function findAll(text: string, needle: string): number[] {
  const hits: number[] = []
  if (needle === "") return hits
  let from = 0
  for (;;) {
    const at = text.indexOf(needle, from)
    if (at < 0) return hits
    hits.push(at)
    from = at + needle.length
  }
}

/**
 * Locate a span in `text`. The offsets are tried first and trusted only if the slice equals
 * the span's text; otherwise the span is re-anchored from its text: by `context` (must occur
 * exactly once and contain the text), by `occurrence` (1-based), or as the unique occurrence.
 * Returns null when the span cannot be placed unambiguously.
 */
export function anchorSpan(
  text: string,
  span: Span,
  index: OffsetIndex
): Anchored | null {
  const needle = span.text
  if (typeof needle !== "string" || needle === "") return null

  if (
    Number.isInteger(span.start) &&
    Number.isInteger(span.end) &&
    span.start < span.end
  ) {
    const start = index.toUnit(span.start)
    const end = index.toUnit(span.end)
    if (text.slice(start, end) === needle)
      return { start, end, method: "offset" }
  }

  if (typeof span.context === "string" && span.context !== "") {
    const hits = findAll(text, span.context)
    if (hits.length !== 1) return null
    const rel = span.context.indexOf(needle)
    if (rel < 0) return null
    const start = hits[0] + rel
    return { start, end: start + needle.length, method: "context" }
  }

  const hits = findAll(text, needle)
  if (
    typeof span.occurrence === "number" &&
    Number.isInteger(span.occurrence)
  ) {
    if (span.occurrence < 1 || span.occurrence > hits.length) return null
    const start = hits[span.occurrence - 1]
    return { start, end: start + needle.length, method: "occurrence" }
  }
  if (hits.length !== 1) return null
  return { start: hits[0], end: hits[0] + needle.length, method: "unique" }
}
