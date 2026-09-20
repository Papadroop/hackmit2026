import { describe, expect, it } from "vitest"

import type { Document as ContractDocument, LanguageSignal } from "@contract"

import { makeOffsetIndex } from "@/lib/anchor"
import { segmentRange } from "@/lib/document-layout"
import { anchorSignals, languageMarks, sortMarks } from "./annotations"

const text = "We may choose to grow cleaner energy. If required, we may choose."
const doc = { id: "d", text, regions: [] } as unknown as ContractDocument
const index = makeOffsetIndex(text)

const signal = (
  id: string,
  spans: LanguageSignal["spans"],
  polarity: LanguageSignal["polarity"] = "flag"
): LanguageSignal => ({
  id,
  level: "claim",
  kind: "hedge",
  polarity,
  spans,
  note: "",
  claim_ids: [],
})

describe("language marks", () => {
  it("anchors each signal span, repeats included, and skips what cannot be placed", () => {
    const anchored = anchorSignals(doc, index, [
      signal("L1", [
        { text: "may choose", start: 3, end: 13, occurrence: 1 },
        { text: "may choose", start: 0, end: 0, occurrence: 2 },
      ]),
      signal("L2", [{ text: "not in the text", start: 0, end: 15 }]),
    ])
    expect(
      anchored[0].spans.map((s) => s && [s.start, s.end, s.method])
    ).toEqual([
      [3, 13, "offset"],
      [
        text.lastIndexOf("may choose"),
        text.lastIndexOf("may choose") + 10,
        "occurrence",
      ],
    ])
    expect(anchored[1].spans).toEqual([null])
    const marks = languageMarks(anchored)
    expect(marks.map((m) => [m.id, m.layer, m.span, m.start])).toEqual([
      ["L1", "language", 0, 3],
      ["L1", "language", 1, text.lastIndexOf("may choose")],
    ])
  })

  it("keeps segmentation flat when both layers are cut together", () => {
    const marks = sortMarks([
      { id: "C1", layer: "claim", span: 0, start: 0, end: 36 },
      { id: "L1", layer: "language", span: 0, start: 3, end: 13 },
      { id: "L3", layer: "language", span: 0, start: 22, end: 44 }, // straddles the claim's end
    ])
    const segments = segmentRange(0, 50, marks)
    expect(
      segments.map((s) => [s.start, s.end, s.marks.map((m) => m.id)])
    ).toEqual([
      [0, 3, ["C1"]],
      [3, 13, ["C1", "L1"]],
      [13, 22, ["C1"]],
      [22, 36, ["C1", "L3"]],
      [36, 44, ["L3"]],
      [44, 50, []],
    ])
  })
})
