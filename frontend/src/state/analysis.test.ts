import { describe, expect, it } from "vitest"

import type { AnalysisSummary } from "@/lib/api"
import type { ReceivedEvent } from "@/lib/events"
import {
  analysisReducer,
  initialState,
  selectDocument,
  selectStages,
} from "./analysis"

const ev = (
  seq: number,
  type: string,
  payload: Record<string, unknown> = {}
): ReceivedEvent => ({
  seq,
  t_ms: seq * 100,
  type,
  payload,
  received_ms: seq,
})

const summary: AnalysisSummary = {
  analysis_id: "abc",
  created_at: "2026-09-19T22:00:00Z",
  source: { kind: "replay", fixture: "shell-climate", speed: 1 },
  title: null,
  status: "running",
  event_count: 0,
  last_seq: 0,
  events_url: "/api/analyses/abc/events",
}

describe("analysisReducer", () => {
  it("starts connecting, streams on events, and finishes on the terminal event", () => {
    let state = initialState("abc")
    expect(state.status).toBe("connecting")
    state = analysisReducer(state, { type: "record", record: summary })
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "analysis.started"),
    })
    expect(state.status).toBe("streaming")
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "analysis.completed"),
    })
    expect(state.status).toBe("completed")
    expect(state.events.map((e) => e.seq)).toEqual([1, 2])
  })

  it("ignores events it has already seen", () => {
    let state = initialState("abc")
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "analysis.started"),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "stage.started", { stage: "extract" }),
    })
    const again = analysisReducer(state, {
      type: "event",
      event: ev(2, "stage.started", { stage: "extract" }),
    })
    expect(again).toBe(state)
    expect(
      analysisReducer(state, {
        type: "event",
        event: ev(1, "analysis.started"),
      })
    ).toBe(state)
  })

  it("records the failure reason and stays finished whatever the stream says next", () => {
    let state = initialState("abc")
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "analysis.started"),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "analysis.failed", { error: "cancelled" }),
    })
    expect(state.status).toBe("failed")
    expect(state.error).toBe("cancelled")
    expect(
      analysisReducer(state, { type: "stream", status: "reconnecting" }).status
    ).toBe("failed")
    expect(
      analysisReducer(state, { type: "stream", status: "closed", detail: "x" })
        .error
    ).toBe("cancelled")
  })

  it("treats a closed stream with a reason as a failure, and a plain close as nothing", () => {
    let state = initialState("abc")
    state = analysisReducer(state, { type: "stream", status: "open" })
    expect(state.status).toBe("streaming")
    expect(analysisReducer(state, { type: "stream", status: "closed" })).toBe(
      state
    )
    const failed = analysisReducer(state, {
      type: "stream",
      status: "closed",
      detail: "refused",
    })
    expect(failed.status).toBe("failed")
    expect(failed.error).toBe("refused")
  })

  it("marks a missing analysis", () => {
    const state = analysisReducer(initialState("nope"), {
      type: "missing",
      error: "no such analysis",
    })
    expect(state.status).toBe("missing")
    expect(state.error).toBe("no such analysis")
  })
})

describe("selectStages", () => {
  it("orders stages as started, labels them, and marks completion", () => {
    const stages = selectStages([
      ev(1, "analysis.started"),
      ev(2, "stage.started", { stage: "ingest" }),
      ev(3, "stage.completed", { stage: "ingest" }),
      ev(4, "stage.started", { stage: "extract", label: "Custom label" }),
      ev(5, "stage.started", { stage: "made_up" }),
      ev(6, "claim.extracted", { stage: "not a lifecycle event" }),
    ])
    expect(stages).toEqual([
      { stage: "ingest", label: "Reading the document", status: "done" },
      { stage: "extract", label: "Custom label", status: "running" },
      { stage: "made_up", label: "made_up", status: "running" },
    ])
  })
})

describe("selectDocument", () => {
  it("is null before analysis.started and grows as the document arrives", () => {
    expect(selectDocument([])).toBeNull()
    const started = ev(1, "analysis.started", {
      contract_version: "1.0.0",
      document_ref: {
        url: "https://www.shell.com/sustainability/climate.html",
        title: "Climate | Shell Global",
      },
    })
    expect(selectDocument([started])).toEqual({
      title: "Climate | Shell Global",
      company: null,
      url: "https://www.shell.com/sustainability/climate.html",
      textType: null,
      words: null,
    })
    const ingested = ev(2, "document.ingested", {
      document: {
        title: "Climate | Shell Global",
        company: { name: "Shell plc" },
        text_type: "policy",
        source: { url: "https://www.shell.com/sustainability/climate.html" },
        word_count: 2164,
      },
    })
    expect(selectDocument([started, ingested])).toEqual({
      title: "Climate | Shell Global",
      company: "Shell plc",
      url: "https://www.shell.com/sustainability/climate.html",
      textType: "policy",
      words: 2164,
    })
  })

  it("tolerates payloads that do not match the contract", () => {
    expect(
      selectDocument([ev(1, "analysis.started", { document_ref: "nope" })])
    ).toBeNull()
    expect(
      selectDocument([ev(1, "analysis.started", { document_ref: {} })])
    ).toEqual({
      title: null,
      company: null,
      url: null,
      textType: null,
      words: null,
    })
  })
})

describe("fold", () => {
  const document = {
    id: "doc",
    title: "Climate",
    company: { name: "Shell plc" },
    industry: { label: "Oil & Gas" },
    text_type: "policy",
    source: { retrieved: "2026-09-19" },
    text: "Climate\n\nOur target is net zero by 2050.",
    regions: [
      { kind: "title", start: 0, end: 7 },
      { kind: "paragraph", start: "nope", end: 40 }, // dropped: not an offset
    ],
  }
  const claim = (id: string, text = "net zero by 2050") => ({
    id,
    spans: [{ text, start: 23, end: 39 }],
    type: "commitment",
    scope: "company",
    attribute: "net zero",
  })

  it("keeps the document and the claims in arrival order, replacing a repeated id", () => {
    let state = initialState("abc")
    expect(state.document).toBeNull()
    expect(state.claims).toEqual([])
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "document.ingested", { document }),
    })
    expect(state.document?.title).toBe("Climate")
    expect(state.document?.regions).toEqual([
      { kind: "title", start: 0, end: 7 },
    ])
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "claim.extracted", { claim: claim("C1") }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(3, "claim.extracted", { claim: claim("C2") }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(4, "claim.extracted", { claim: claim("C1", "target") }),
    })
    expect(state.claims.map((c) => [c.id, c.spans[0].text])).toEqual([
      ["C1", "target"],
      ["C2", "net zero by 2050"],
    ])
  })

  it("skips payloads that lack what the views need, without dropping the event", () => {
    let state = initialState("abc")
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "document.ingested", { document: { id: "d" } }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "claim.extracted", { claim: { id: "C1", spans: [] } }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(3, "claim.extracted", {
        claim: { ...claim("C3"), spans: [{ text: "", start: 0, end: 0 }] },
      }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(4, "claim.extracted", { nope: true }),
    })
    expect(state.document).toBeNull()
    expect(state.claims).toEqual([])
    expect(state.events).toHaveLength(4)
  })

  it("keeps the fold on the terminal event", () => {
    let state = initialState("abc")
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "claim.extracted", { claim: claim("C1") }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "analysis.completed"),
    })
    expect(state.status).toBe("completed")
    expect(state.claims).toHaveLength(1)
  })
})

describe("fold verdicts", () => {
  const verdict = (claim_id: string, extra: Record<string, unknown> = {}) => ({
    claim_id,
    likelihood: 0.85,
    confidence: 0.85,
    category: "contradicted",
    tags: ["hidden_trade_off", 7],
    rationale: "The plan does not reach it.",
    ...extra,
  })

  it("stores verdicts by claim id, last one wins, and keeps only string tags", () => {
    let state = initialState("abc")
    expect(state.verdicts).toEqual({})
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "verdict.issued", { verdict: verdict("C1") }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "verdict.issued", {
        verdict: verdict("C1", { category: "supported", tags: [] }),
      }),
    })
    expect(Object.keys(state.verdicts)).toEqual(["C1"])
    expect(state.verdicts.C1.category).toBe("supported")
    state = analysisReducer(state, {
      type: "event",
      event: ev(3, "verdict.issued", { verdict: verdict("C2") }),
    })
    expect(state.verdicts.C2.tags).toEqual(["hidden_trade_off"])
  })

  it("skips verdicts with an unknown category or non-numeric scores", () => {
    let state = initialState("abc")
    state = analysisReducer(state, {
      type: "event",
      event: ev(1, "verdict.issued", {
        verdict: verdict("C1", { category: "greenwashed" }),
      }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(2, "verdict.issued", {
        verdict: verdict("C2", { confidence: "high" }),
      }),
    })
    state = analysisReducer(state, {
      type: "event",
      event: ev(3, "verdict.issued", { nope: true }),
    })
    expect(state.verdicts).toEqual({})
    expect(state.events).toHaveLength(3)
  })
})
