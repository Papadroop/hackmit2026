import { describe, expect, it } from "vitest"

import type { EvidenceItem } from "@contract"

import {
  citedIds,
  describeProvenance,
  describeRelations,
  describeSourceDate,
  evidenceForClaim,
  hostOf,
} from "./evidence"

const item = (
  id: string,
  tier: number,
  links: { target: string; relation: string }[],
  extra: Partial<EvidenceItem> = {}
): EvidenceItem =>
  ({
    id,
    kind: "filing",
    tier,
    source: { name: `Source ${id}` },
    verified: false,
    verification: "unverified",
    retrieved: "2026-04-09",
    links,
    ...extra,
  }) as EvidenceItem

describe("evidenceForClaim", () => {
  const evidence = [
    item("E1", 2, [{ target: "C1", relation: "context" }]),
    item("E2", 1, [{ target: "C1", relation: "context" }]),
    item("E3", 5, [
      { target: "C1", relation: "context" },
      { target: "C1", relation: "contradicts_framing" },
    ]),
    item("E4", 3, [{ target: "C2", relation: "supports" }]),
    item("E5", 1, [{ target: "C1", relation: "supports" }]),
    item("E6", 2, [{ target: "C2", relation: "context" }]),
  ]

  it("orders by the strongest relation, then tier, then arrival, keeping every relation", () => {
    const list = evidenceForClaim("C1", evidence)
    expect(list.map((e) => [e.item.id, e.relations])).toEqual([
      ["E3", ["contradicts_framing", "context"]],
      ["E5", ["supports"]],
      ["E2", ["context"]],
      ["E1", ["context"]],
    ])
    expect(describeRelations(list[0].relations)).toBe(
      "Contradicts the framing, context"
    )
  })

  it("appends cited items that are not linked, as cited, and ignores unknown ids", () => {
    const list = evidenceForClaim("C1", evidence, new Set(["E6", "E1", "E99"]))
    expect(list.map((e) => [e.item.id, e.relations[0]])).toEqual([
      ["E3", "contradicts_framing"],
      ["E5", "supports"],
      ["E2", "context"],
      ["E1", "context"],
      ["E6", "cited"],
    ])
  })

  it("collects the ids scores, arguments and the verdict cite", () => {
    const ids = citedIds(
      [
        {
          claim_id: "C1",
          dimension: "clarity",
          score: 0,
          confidence: 1,
          basis: "",
          evidence_ids: ["E1"],
        },
      ],
      [
        {
          claim_id: "C1",
          role: "defence",
          text: "x",
          evidence_ids: ["E2", "E1"],
        },
      ],
      {
        claim_id: "C1",
        likelihood: 0,
        confidence: 1,
        category: "supported",
        tags: [],
        rationale: "",
        evidence_ids: ["E3"],
      }
    )
    expect([...ids]).toEqual(["E1", "E2", "E3"])
    expect([...citedIds([], [], null)]).toEqual([])
  })
})

describe("evidence wording", () => {
  it("names the host of a url and falls back to the text", () => {
    expect(hostOf("https://www.sec.gov/Archives/edgar/x.htm")).toBe("sec.gov")
    expect(hostOf("https://sasb.ifrs.org/standards/")).toBe("sasb.ifrs.org")
    expect(hostOf("not a url")).toBe("not a url")
  })

  it("reformats only full ISO dates", () => {
    expect(describeSourceDate("2025-04-09")).toBe("9 Apr 2025")
    expect(describeSourceDate("2026-03")).toBe("2026-03")
    expect(describeSourceDate("applies from 2026-09-27")).toBe(
      "applies from 2026-09-27"
    )
  })

  it("describes provenance one fact per sentence", () => {
    expect(
      describeProvenance(
        item("E1", 2, [], {
          verified: true,
          verification: "fetched_exact",
          stage: "consistency",
        })
      )
    ).toBe(
      "Filing. Quote matched against the fetched source. Retrieved 9 Apr 2026 by the Self-consistency evaluator."
    )
    expect(describeProvenance(item("E2", 1, [], { kind: "law" }))).toBe(
      "Law. Not verified, so no quote is shown. Retrieved 9 Apr 2026."
    )
  })
})
