import { createContext, useContext } from "react"

import type { AnalysisSummary } from "@/lib/api"
import {
  ANALYSIS_COMPLETED,
  ANALYSIS_FAILED,
  ANALYSIS_STARTED,
  DOCUMENT_INGESTED,
  STAGE_COMPLETED,
  STAGE_STARTED,
  type ReceivedEvent,
} from "@/lib/events"
import type { StreamStatus } from "@/lib/stream"
import { emptyFolded, foldEvent, pickFolded, type Folded } from "./fold"

/**
 * The state of one analysis is a fold over the events received so far (design-doc D8).
 * Views derive what they show from `events`; nothing is stored that the log does not
 * contain, so replaying the same log reproduces the same screen.
 */
export type AnalysisStatus =
  | "connecting"
  | "streaming"
  | "reconnecting"
  | "completed"
  | "failed"
  | "missing"

export type AnalysisState = Folded & {
  analysisId: string
  /** The analysis record from the API (id, source, title); not the document summary. */
  record: AnalysisSummary | null
  status: AnalysisStatus
  events: ReceivedEvent[]
  error: string | null
}

export type AnalysisAction =
  | { type: "record"; record: AnalysisSummary }
  | { type: "event"; event: ReceivedEvent }
  | { type: "stream"; status: StreamStatus; detail?: string }
  | { type: "missing"; error: string }

export function initialState(analysisId: string): AnalysisState {
  return {
    ...emptyFolded,
    analysisId,
    record: null,
    status: "connecting",
    events: [],
    error: null,
  }
}

export function analysisReducer(
  state: AnalysisState,
  action: AnalysisAction
): AnalysisState {
  switch (action.type) {
    case "record":
      return { ...state, record: action.record }
    case "event": {
      const lastSeq = state.events.at(-1)?.seq ?? 0
      if (action.event.seq <= lastSeq) return state // already seen (reconnect, StrictMode)
      const events = [...state.events, action.event]
      const folded = foldEvent(pickFolded(state), action.event)
      if (action.event.type === ANALYSIS_COMPLETED)
        return { ...state, ...folded, events, status: "completed" }
      if (action.event.type === ANALYSIS_FAILED) {
        const error = action.event.payload.error
        return {
          ...state,
          ...folded,
          events,
          status: "failed",
          error: typeof error === "string" ? error : "The analysis failed.",
        }
      }
      return { ...state, ...folded, events, status: "streaming" }
    }
    case "stream":
      if (isFinished(state.status)) return state
      if (action.status === "open") return { ...state, status: "streaming" }
      if (action.status === "reconnecting")
        return { ...state, status: "reconnecting" }
      return action.detail
        ? { ...state, status: "failed", error: action.detail }
        : state
    case "missing":
      return { ...state, status: "missing", error: action.error }
  }
}

export function isFinished(status: AnalysisStatus): boolean {
  return status === "completed" || status === "failed" || status === "missing"
}

export type StageProgress = {
  stage: string
  label: string
  status: "running" | "done"
}

/** What each pipeline stage (contract/schema.json, `Stage`) is doing, in the tool's voice. */
export const STAGE_LABELS: Record<string, string> = {
  ingest: "Reading the document",
  extract: "Finding claims",
  language: "Reading how claims are worded",
  substantiate: "Checking criteria and precedents",
  verify: "Checking against independent data",
  consistency: "Comparing with the company's other statements",
  omissions: "Looking for what is left out",
  verdict: "Deciding",
  summary: "Summarising",
}

/** Pipeline stages in the order they started, from the lifecycle events. */
export function selectStages(events: ReceivedEvent[]): StageProgress[] {
  const stages: StageProgress[] = []
  for (const event of events) {
    const stage = event.payload.stage
    if (typeof stage !== "string") continue
    if (event.type === STAGE_STARTED) {
      const label =
        typeof event.payload.label === "string"
          ? event.payload.label
          : (STAGE_LABELS[stage] ?? stage)
      stages.push({ stage, label, status: "running" })
    } else if (event.type === STAGE_COMPLETED) {
      const found = stages.findLast((s) => s.stage === stage)
      if (found) found.status = "done"
    }
  }
  return stages
}

export type DocumentInfo = {
  title: string | null
  company: string | null
  url: string | null
  textType: string | null
  words: number | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null
}

/** What is known about the document under analysis: the reference announced in
 * analysis.started, refined by the Document object in document.ingested. */
export function selectDocument(events: ReceivedEvent[]): DocumentInfo | null {
  let info: DocumentInfo | null = null
  const ref = events.find((e) => e.type === ANALYSIS_STARTED)?.payload
    .document_ref
  if (isRecord(ref)) {
    info = {
      title: asString(ref.title),
      company: null,
      url: asString(ref.url),
      textType: null,
      words: null,
    }
  }
  const document = events.find((e) => e.type === DOCUMENT_INGESTED)?.payload
    .document
  if (isRecord(document)) {
    const company = document.company
    const source = document.source
    info = {
      title: asString(document.title) ?? info?.title ?? null,
      company: isRecord(company) ? asString(company.name) : null,
      url:
        (isRecord(source) ? asString(source.url) : null) ?? info?.url ?? null,
      textType: asString(document.text_type),
      words:
        typeof document.word_count === "number" ? document.word_count : null,
    }
  }
  return info
}

export type AnalysisApi = {
  state: AnalysisState
  /** Ask the server to stop. The stream then delivers the terminal event. */
  stop: () => Promise<void>
}

export const AnalysisContext = createContext<AnalysisApi | null>(null)

export function useAnalysis(): AnalysisApi {
  const context = useContext(AnalysisContext)
  if (context === null)
    throw new Error("useAnalysis must be used within AnalysisProvider")
  return context
}
