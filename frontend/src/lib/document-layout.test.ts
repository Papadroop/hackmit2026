import { describe, expect, it } from "vitest"

import type { Region } from "@contract"

import { makeOffsetIndex } from "./anchor"
import {
  blockRange,
  layoutDocument,
  markKey,
  paragraphAt,
  segmentRange,
  splitLines,
  type Mark,
} from "./document-layout"

const text = [
  "Climate", // title 0-7
  "", //
  "Our target is net zero.", // P1 9-32
  "", //
  "Our targets", // H2 34-45
  "", //
  "The metrics include:", // P2 intro 47-67
  "", //
  "Halving Scope 1 and 2.", // list item 69-91 (in P2)
  "", //
  "Cutting methane.", // list item 93-109 (in P2)
  "", //
  "2-3% by 2021", // P3 with single-newline list 111-123
  "3-4% by 2022", // 124-136
  "", //
  "Cautionary note", // H3 inside container 138-153
  "", //
  "The companies in which we invest.", // P4 in container 155-188
  "", //
  "Words like we and us.", // P4 second block 190-211
].join("\n")

const regions: Region[] = [
  { kind: "title", start: 0, end: 7, label: "H1 Climate" },
  { kind: "paragraph", start: 9, end: 32, label: "P1", prominence: 1.0 },
  { kind: "heading", start: 34, end: 45, label: "H2 Our targets", level: 2 },
  { kind: "paragraph", start: 47, end: 109, label: "P2", prominence: 0.7 },
  { kind: "list_item", start: 69, end: 91 },
  { kind: "list_item", start: 93, end: 109 },
  { kind: "paragraph", start: 111, end: 136, label: "P3", prominence: 0.8 },
  { kind: "list_item", start: 111, end: 123 },
  { kind: "list_item", start: 124, end: 136 },
  {
    kind: "cautionary_note",
    start: 138,
    end: 211,
    label: "Cautionary note",
    prominence: 0.3,
  },
  {
    kind: "heading",
    start: 138,
    end: 153,
    label: "H3 Cautionary note",
    level: 3,
  },
  { kind: "paragraph", start: 155, end: 211, label: "P4", prominence: 0.3 },
]

describe("splitLines", () => {
  it("numbers blocks by blank lines and drops empty lines", () => {
    const lines = splitLines("a\nb\n\nc\n\n\nd")
    expect(lines).toEqual([
      { start: 0, end: 1, block: 0 },
      { start: 2, end: 3, block: 0 },
      { start: 5, end: 6, block: 1 },
      { start: 9, end: 10, block: 2 },
    ])
  })
})

describe("layoutDocument", () => {
  const index = makeOffsetIndex(text)
  const sections = layoutDocument(text, regions, index)

  it("splits the text into a body section and a container section", () => {
    expect(sections.map((s) => s.container?.kind ?? null)).toEqual([
      null,
      "cautionary_note",
    ])
    expect(sections[1].container).toEqual({
      kind: "cautionary_note",
      label: "Cautionary note",
      start: 138,
    })
  })

  it("classifies lines and groups list items across blank lines and within one block", () => {
    const body = sections[0].groups
    expect(body.map((g) => g.type)).toEqual([
      "heading",
      "paragraph",
      "heading",
      "paragraph",
      "list",
      "list",
    ])
    expect(body[0]).toMatchObject({
      type: "heading",
      level: 1,
      line: { kind: "title", start: 0, end: 7 },
    })
    expect(body[1]).toMatchObject({
      type: "paragraph",
      lines: [{ paragraph: "P1", prominence: 1.0 }],
    })
    expect(body[2]).toMatchObject({ type: "heading", level: 2 })
    expect(body[3]).toMatchObject({
      type: "paragraph",
      lines: [{ paragraph: "P2", start: 47, end: 67 }],
    })
    // Two list items separated by a blank line, then a fresh list: the text of P3 is a separate block
    // run, and it still groups its single-newline items into one list.
    const firstList = body[4]
    const secondList = body[5]
    if (firstList.type !== "list" || secondList.type !== "list")
      throw new Error("expected lists")
    expect(firstList.lines.map((l) => text.slice(l.start, l.end))).toEqual([
      "Halving Scope 1 and 2.",
      "Cutting methane.",
    ])
    expect(firstList.lines.map((l) => l.prominence)).toEqual([0.7, 0.7]) // inherited from P2
    expect(secondList.lines.map((l) => text.slice(l.start, l.end))).toEqual([
      "2-3% by 2021",
      "3-4% by 2022",
    ])
    expect(secondList.lines[1].paragraph).toBe("P3")
  })

  it("puts the container's heading and paragraphs inside it, with the container's prominence", () => {
    const note = sections[1].groups
    expect(note.map((g) => g.type)).toEqual([
      "heading",
      "paragraph",
      "paragraph",
    ])
    expect(note[0]).toMatchObject({
      type: "heading",
      level: 3,
      line: { prominence: 0.3 },
    })
    expect(note[2]).toMatchObject({
      type: "paragraph",
      lines: [{ start: 190, end: 211, paragraph: "P4" }],
    })
  })

  it("renders every block as a paragraph when there are no regions", () => {
    const plain = layoutDocument(
      "One.\n\nTwo\nlines.\n\nThree.",
      [],
      makeOffsetIndex("")
    )
    expect(plain).toHaveLength(1)
    expect(plain[0].container).toBeNull()
    expect(plain[0].groups.map((g) => g.type)).toEqual([
      "paragraph",
      "paragraph",
      "paragraph",
    ])
    const second = plain[0].groups[1]
    if (second.type !== "paragraph") throw new Error("expected paragraph")
    expect(second.lines).toHaveLength(2)
  })

  it("converts region offsets from code points", () => {
    const astral = "🌍 Title\n\nBody."
    const idx = makeOffsetIndex(astral)
    const out = layoutDocument(
      astral,
      [{ kind: "title", start: 0, end: 7 }],
      idx
    )
    expect(out[0].groups[0]).toMatchObject({
      type: "heading",
      line: { start: 0, end: 8, kind: "title" },
    })
  })

  it("finds the paragraph label at an offset", () => {
    expect(paragraphAt(regions, index, 70)).toBe("P2")
    expect(paragraphAt(regions, index, 3)).toBeNull()
  })
})

describe("blockRange", () => {
  const index = makeOffsetIndex(text)
  const body = layoutDocument(text, regions, index)[0].groups

  it("runs from the first line's start to the last line's end", () => {
    // A heading is one line; a list group is every item in it, which is the row the corrected
    // version's split puts a block on.
    expect(blockRange(body[0])).toEqual([0, 7])
    expect(blockRange(body[1])).toEqual([9, 32])
    const list = body.find((g) => g.type === "list")
    expect(list).toBeDefined()
    expect(blockRange(list!)[0]).toBeLessThan(blockRange(list!)[1])
  })

  it("gives every block a start of its own, so a start is a usable key", () => {
    const starts = body.map((g) => blockRange(g)[0])
    expect(new Set(starts).size).toBe(starts.length)
  })
})

describe("segmentRange", () => {
  const mark = (id: string, start: number, end: number, span = 0): Mark => ({
    id,
    layer: "claim",
    span,
    start,
    end,
  })

  it("returns the range untouched when nothing covers it", () => {
    expect(segmentRange(10, 20, [mark("C1", 30, 40)])).toEqual([
      { start: 10, end: 20, marks: [] },
    ])
    expect(segmentRange(10, 20, [mark("C1", 10, 10)])).toEqual([
      { start: 10, end: 20, marks: [] },
    ])
  })

  it("cuts at mark boundaries inside the range and clips marks that cross it", () => {
    const segments = segmentRange(10, 30, [
      mark("C1", 15, 20),
      mark("C2", 25, 40),
    ])
    expect(
      segments.map((s) => [s.start, s.end, s.marks.map((m) => m.id)])
    ).toEqual([
      [10, 15, []],
      [15, 20, ["C1"]],
      [20, 25, []],
      [25, 30, ["C2"]],
    ])
  })

  it("flattens partial overlaps into neighbours, outermost mark first", () => {
    const segments = segmentRange(0, 50, [
      mark("C21", 20, 45),
      mark("L17", 10, 25),
    ])
    expect(
      segments.map((s) => [s.start, s.end, s.marks.map((m) => m.id)])
    ).toEqual([
      [0, 10, []],
      [10, 20, ["L17"]],
      [20, 25, ["C21", "L17"]],
      [25, 45, ["C21"]],
      [45, 50, []],
    ])
  })

  it("keys marks by id and span index", () => {
    expect(markKey({ id: "C1", span: 2 })).toBe("C1:2")
  })
})
