import { describe, expect, it } from "vitest"

import { anchorSpan, findAll, makeOffsetIndex } from "./anchor"

const text =
  "Climate\n\nOur target is net zero by 2050. Our target is net zero by 2050, again."
// Offsets below are derived from the text rather than counted by hand.
const second = text.indexOf("Our target", 10) // 41
const again = text.indexOf("again") // 73

describe("makeOffsetIndex", () => {
  it("is the identity when every character is in the Basic Multilingual Plane", () => {
    const index = makeOffsetIndex(text)
    expect(index.toUnit(9)).toBe(9)
    expect(index.toUnit(999)).toBe(text.length)
    expect(index.toCodePoint(-5)).toBe(0)
  })

  it("shifts offsets past astral characters", () => {
    const astral = "🌍 net zero"
    const index = makeOffsetIndex(astral)
    // "🌍" is one code point but two UTF-16 units.
    expect(index.toUnit(0)).toBe(0)
    expect(index.toUnit(1)).toBe(2)
    expect(index.toUnit(2)).toBe(3)
    expect(index.toUnit(10)).toBe(11)
    expect(index.toUnit(50)).toBe(11)
    expect(index.toCodePoint(2)).toBe(1)
    expect(index.toCodePoint(1)).toBe(0) // inside the pair
    expect(index.toCodePoint(11)).toBe(10)
  })
})

describe("findAll", () => {
  it("lists non-overlapping occurrences and nothing for an empty needle", () => {
    expect(findAll("aaaa", "aa")).toEqual([0, 2])
    expect(findAll(text, "Our target")).toEqual([9, second])
    expect(findAll(text, "")).toEqual([])
  })
})

describe("anchorSpan", () => {
  const index = makeOffsetIndex(text)

  it("trusts offsets whose slice equals the text", () => {
    expect(
      anchorSpan(text, { text: "net zero by 2050", start: 23, end: 39 }, index)
    ).toEqual({
      start: 23,
      end: 39,
      method: "offset",
    })
  })

  it("converts code-point offsets to UTF-16 before slicing", () => {
    const astral = "🌍🌍 Our target is net zero."
    const idx = makeOffsetIndex(astral)
    // Code points: two emoji (0, 1), space (2), "Our" starts at 3.
    expect(
      anchorSpan(astral, { text: "Our target", start: 3, end: 13 }, idx)
    ).toEqual({
      start: 5,
      end: 15,
      method: "offset",
    })
  })

  it("re-anchors stale offsets by context", () => {
    const span = {
      text: "net zero by 2050",
      start: 0,
      end: 16,
      context: "net zero by 2050, again",
    }
    expect(anchorSpan(text, span, index)).toEqual({
      start: second + 14,
      end: second + 30,
      method: "context",
    })
  })

  it("re-anchors stale offsets by occurrence", () => {
    const span = { text: "Our target", start: 100, end: 110, occurrence: 2 }
    expect(anchorSpan(text, span, index)).toEqual({
      start: second,
      end: second + 10,
      method: "occurrence",
    })
    expect(anchorSpan(text, { ...span, occurrence: 3 }, index)).toBeNull()
    expect(anchorSpan(text, { ...span, occurrence: 0 }, index)).toBeNull()
  })

  it("re-anchors a unique phrase without hints, and refuses an ambiguous one", () => {
    expect(
      anchorSpan(text, { text: "again", start: 0, end: 5 }, index)
    ).toEqual({
      start: again,
      end: again + 5,
      method: "unique",
    })
    expect(
      anchorSpan(text, { text: "Our target", start: 0, end: 10 }, index)
    ).toBeNull()
  })

  it("refuses a context that is missing, repeated, or does not contain the text", () => {
    const base = { text: "net zero", start: 0, end: 8 }
    expect(
      anchorSpan(text, { ...base, context: "not in the text" }, index)
    ).toBeNull()
    expect(
      anchorSpan(text, { ...base, context: "net zero by 2050" }, index)
    ).toBeNull() // twice
    expect(anchorSpan(text, { ...base, context: ", again." }, index)).toBeNull()
  })

  it("refuses text that is not in the document, and empty text", () => {
    expect(
      anchorSpan(text, { text: "carbon neutral", start: 0, end: 14 }, index)
    ).toBeNull()
    expect(anchorSpan(text, { text: "", start: 0, end: 0 }, index)).toBeNull()
  })
})
