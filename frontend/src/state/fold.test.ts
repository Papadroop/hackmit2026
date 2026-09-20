import { describe, expect, it } from "vitest"

import { emptyFolded, foldEvent, type Folded } from "./fold"

const ev = (type: string, payload: Record<string, unknown>) => ({
  seq: 1,
  t_ms: 0,
  type,
  payload,
})

const fold = (events: ReturnType<typeof ev>[], from: Folded = emptyFolded) =>
  events.reduce(foldEvent, from)

const item = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  kind: "filing",
  tier: 2,
  source: { name: "Annual report" },
  quote: "Plans cannot reflect the target.",
  verified: true,
  verification: "fetched_exact",
  retrieved: "2026-09-19",
  links: [{ target: "C1", relation: "contradicts" }],
  ...extra,
})

describe("fold evidence", () => {
  it("keeps items in arrival order and replaces an item by id in place", () => {
    const folded = fold([
      ev("evidence.added", { evidence: item("E1") }),
      ev("evidence.added", { evidence: item("E2") }),
      ev("evidence.added", { evidence: item("E1", { tier: 1 }) }),
    ])
    expect(folded.evidence.map((e) => [e.id, e.tier])).toEqual([
      ["E1", 1],
      ["E2", 2],
    ])
  })

  it("keeps a quote only when the item is verified by a real method", () => {
    const folded = fold([
      ev("evidence.added", { evidence: item("E1") }),
      ev("evidence.added", { evidence: item("E2", { verified: false }) }),
      ev("evidence.added", {
        evidence: item("E3", { verification: "unverified" }),
      }),
      ev("evidence.added", { evidence: item("E4", { quote: undefined }) }),
      ev("evidence.added", { evidence: item("E5", { verified: "yes" }) }),
    ])
    const by = Object.fromEntries(folded.evidence.map((e) => [e.id, e]))
    expect(by.E1.verified).toBe(true)
    expect(by.E1.quote).toBe("Plans cannot reflect the target.")
    for (const id of ["E2", "E3", "E4", "E5"]) {
      expect(by[id].verified, id).toBe(false)
      expect(by[id].quote, id).toBeUndefined()
    }
    expect(by.E3.verification).toBe("unverified")
  })

  it("drops items without a source name, a tier from 1 to 5 or a well-formed link", () => {
    const folded = fold([
      ev("evidence.added", { evidence: item("E1", { source: {} }) }),
      ev("evidence.added", { evidence: item("E2", { tier: 0 }) }),
      ev("evidence.added", { evidence: item("E3", { tier: "2" }) }),
      ev("evidence.added", { evidence: item("E4", { links: [] }) }),
      ev("evidence.added", {
        evidence: item("E5", { links: [{ target: "C1" }] }),
      }),
      ev("evidence.added", {
        evidence: item("E6", {
          links: [{ target: "C1" }, { target: "C2", relation: "context" }],
        }),
      }),
      ev("evidence.added", { nope: true }),
    ])
    expect(folded.evidence.map((e) => e.id)).toEqual(["E6"])
    expect(folded.evidence[0].links).toEqual([
      { target: "C2", relation: "context" },
    ])
    expect(folded.evidence[0].derived_from).toEqual([])
  })
})

describe("fold scores", () => {
  const score = (claim_id: string, dimension: string, extra = {}) => ({
    claim_id,
    dimension,
    score: 0.4,
    confidence: 0.8,
    basis: "The term is defined only on the FAQ page.",
    evidence_ids: ["E13", 7],
    ...extra,
  })

  it("files scores by claim then dimension, last wins", () => {
    const folded = fold([
      ev("dimension.scored", { score: score("C1", "clarity") }),
      ev("dimension.scored", { score: score("C1", "support", { score: 0.9 }) }),
      ev("dimension.scored", { score: score("C2", "clarity") }),
      ev("dimension.scored", {
        score: score("C1", "clarity", { score: 0.5, basis: 3 }),
      }),
    ])
    expect(Object.keys(folded.scores)).toEqual(["C1", "C2"])
    expect(folded.scores.C1.clarity?.score).toBe(0.5)
    expect(folded.scores.C1.clarity?.basis).toBe("")
    expect(folded.scores.C1.clarity?.evidence_ids).toEqual(["E13"])
    expect(folded.scores.C1.support?.score).toBe(0.9)
    expect(folded.scores.C2.support).toBeUndefined()
  })

  it("skips unknown dimensions and non-numeric scores", () => {
    const folded = fold([
      ev("dimension.scored", { score: score("C1", "completeness") }),
      ev("dimension.scored", {
        score: score("C1", "clarity", { score: "high" }),
      }),
      ev("dimension.scored", {
        score: score("C1", "clarity", { confidence: Number.NaN }),
      }),
      ev("dimension.scored", { score: score("", "clarity") }),
    ])
    expect(folded.scores).toEqual({})
  })
})

describe("fold arguments", () => {
  const turn = (
    claim_id: string,
    role: string,
    text = "The plan says no."
  ) => ({
    claim_id,
    role,
    text,
    evidence_ids: ["E1"],
  })

  it("appends turns per claim in order and skips unknown roles or empty text", () => {
    const folded = fold([
      ev("argument.made", { argument: turn("C1", "prosecutor") }),
      ev("argument.made", {
        argument: turn("C1", "defence", "Outside the plan."),
      }),
      ev("argument.made", { argument: turn("C1", "witness") }),
      ev("argument.made", { argument: turn("C1", "judge", "") }),
      ev("argument.made", { argument: turn("C2", "prosecutor") }),
    ])
    expect(folded.arguments.C1.map((t) => t.role)).toEqual([
      "prosecutor",
      "defence",
    ])
    expect(folded.arguments.C1[1].text).toBe("Outside the plan.")
    expect(folded.arguments.C2).toHaveLength(1)
  })
})

describe("fold verdict fields", () => {
  it("keeps fix and rewrite only when they are non-empty strings, and string ids only", () => {
    const folded = fold([
      ev("verdict.issued", {
        verdict: {
          claim_id: "C1",
          likelihood: 0.8,
          confidence: 0.7,
          category: "supported",
          tags: [],
          rationale: "Fine.",
          fix: "",
          rewrite: 4,
          evidence_ids: ["E1", null, "E2"],
        },
      }),
    ])
    expect(folded.verdicts.C1.fix).toBeUndefined()
    expect(folded.verdicts.C1.rewrite).toBeUndefined()
    expect(folded.verdicts.C1.evidence_ids).toEqual(["E1", "E2"])
  })
})

describe("fold summary", () => {
  const summary = (extra: Record<string, unknown> = {}) => ({
    headline: { score: 0.8, confidence: 0.85 },
    dimensions: {
      clarity: { score: 0.55, confidence: 0.85 },
      support: { score: 0.45, confidence: 0.8 },
      materiality: { score: "high", confidence: 0.85 },
      consistency: { score: 0.7, confidence: 0.9 },
      completeness: { score: 0.7, confidence: 0.85 },
    },
    verdict_distribution: { supported: 10, unsubstantiated: 7 },
    top_issues: [
      { rank: 2, target: "C23", title: "Growing gas sales" },
      { rank: 1, target: "C1", title: "The cautionary note" },
      { target: "O2" },
    ],
    credit: [{ target: "C14", title: "Assured" }, { title: "no target" }],
    claim_count: 25,
    omission_count: "4",
    narrative: "",
    ...extra,
  })

  it("keeps the latest summary, marks it final, and drops malformed parts individually", () => {
    let folded = fold([
      ev("summary.updated", { summary: summary(), final: false }),
    ])
    expect(folded.summary?.final).toBe(false)
    expect(folded.summary?.headline).toEqual({ score: 0.8, confidence: 0.85 })
    expect(Object.keys(folded.summary?.dimensions ?? {})).toEqual([
      "clarity",
      "support",
      "consistency",
      "completeness",
    ])
    expect(folded.summary?.verdict_distribution).toEqual({
      contradicted: 0,
      misleading_by_framing: 0,
      unsubstantiated: 7,
      supported: 10,
    })
    expect(folded.summary?.top_issues.map((i) => [i.rank, i.target])).toEqual([
      [1, "C1"],
      [2, "C23"],
    ])
    expect(folded.summary?.credit).toEqual([
      { target: "C14", title: "Assured" },
    ])
    expect(folded.summary?.claim_count).toBe(25)
    expect(folded.summary?.omission_count).toBeNull()
    expect(folded.summary?.narrative).toBeUndefined()

    folded = fold(
      [
        ev("summary.updated", {
          summary: summary({ headline: { score: 0.6, confidence: 0.5 } }),
          final: true,
        }),
      ],
      folded
    )
    expect(folded.summary?.headline.score).toBe(0.6)
    expect(folded.summary?.final).toBe(true)
  })

  it("skips a summary without a numeric headline", () => {
    const folded = fold([
      ev("summary.updated", {
        summary: summary({ headline: null }),
        final: true,
      }),
      ev("summary.updated", { summary: "done", final: true }),
    ])
    expect(folded.summary).toBeNull()
  })
})

describe("fold signals and omissions", () => {
  it("keeps signals with a known level and polarity, dropping malformed spans", () => {
    const folded = fold([
      ev("language.signal", {
        signal: {
          id: "L1",
          level: "claim",
          kind: "hedge",
          polarity: "flag",
          spans: [{ text: "may", start: 3, end: 6 }, { text: "" }],
          note: "Hedged.",
          claim_ids: ["C1", 4],
          strength: 0.5,
        },
      }),
      ev("language.signal", {
        signal: {
          id: "L2",
          level: "document",
          kind: "register",
          polarity: "benign",
          spans: [],
          claim_ids: [],
          strength: "low",
        },
      }),
      ev("language.signal", {
        signal: { id: "L3", level: "page", kind: "hedge", polarity: "flag" },
      }),
      ev("language.signal", {
        signal: { id: "L4", level: "claim", kind: "hedge", polarity: "maybe" },
      }),
    ])
    expect(folded.signals.map((s) => s.id)).toEqual(["L1", "L2"])
    expect(folded.signals[0].spans).toEqual([{ text: "may", start: 3, end: 6 }])
    expect(folded.signals[0].claim_ids).toEqual(["C1"])
    expect(folded.signals[1].note).toBe("")
    expect(folded.signals[1].strength).toBeUndefined()
  })

  it("keeps omissions with a topic and numeric scores, last one wins by id", () => {
    const folded = fold([
      ev("omission.found", {
        omission: {
          id: "O1",
          topic: "Capital allocation",
          why_material: "Where the money goes.",
          score: 0.7,
          confidence: 0.85,
          complete_text: "",
          evidence_ids: ["E4", null],
        },
      }),
      ev("omission.found", {
        omission: { id: "O2", topic: "", score: 0.5, confidence: 0.5 },
      }),
      ev("omission.found", {
        omission: {
          id: "O3",
          topic: "Volumes",
          score: "high",
          confidence: 0.5,
        },
      }),
      ev("omission.found", {
        omission: {
          id: "O1",
          topic: "Capital allocation, revised",
          score: 0.8,
          confidence: 0.9,
        },
      }),
    ])
    expect(folded.omissions.map((o) => [o.id, o.topic])).toEqual([
      ["O1", "Capital allocation, revised"],
    ])
    expect(folded.omissions[0].why_material).toBe("")
    expect(folded.omissions[0].complete_text).toBeUndefined()
    expect(folded.omissions[0].evidence_ids).toEqual([])
  })
})
