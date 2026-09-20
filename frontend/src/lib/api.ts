/** Client for the backend API (backend/auditor/main.py). */

import type { CalibrationReport } from "@/lib/calibration"
import type { CompanyView } from "@/lib/company"

export type ReplayRequest = {
  kind: "replay"
  fixture?: string
  run?: string
  speed?: number
}
export type TextRequest = { kind: "text"; text: string; title?: string }
export type UrlRequest = { kind: "url"; url: string }
export type AnalysisRequest = ReplayRequest | TextRequest | UrlRequest

export type ServerStatus = "running" | "completed" | "failed"

export type AnalysisSummary = {
  analysis_id: string
  created_at: string
  source: Record<string, unknown>
  /** The document's title once analysis.started has been emitted. */
  title: string | null
  status: ServerStatus
  event_count: number
  last_seq: number
  events_url: string
}

export type FixtureInfo = {
  name: string
  file: string
  title: string | null
  events: number | null
  duration_ms: number | null
  types: Record<string, number> | null
  error: string | null
}

export type Recording = { fixture: string; events: number; duration_ms: number }

export type DemoDocument = {
  id: string
  title: string
  company: string | null
  url: string | null
  retrieved: string | null
  words: number | null
  text_type: string | null
  recordings: Recording[]
}

export type DocumentsResponse = {
  documents: DemoDocument[]
  live_analysis: boolean
  invalid_recordings: { file: string; error: string }[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(
      0,
      "The API is not reachable. Is the backend running on port 8400?"
    )
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") detail = body.detail
      else if (Array.isArray(body.detail))
        detail = body.detail
          .map((d: { msg?: string }) => d.msg ?? "invalid")
          .join("; ")
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  listFixtures: () => request<FixtureInfo[]>("/api/fixtures"),
  listDocuments: () => request<DocumentsResponse>("/api/documents"),
  listAnalyses: () => request<AnalysisSummary[]>("/api/analyses"),
  createAnalysis: (body: AnalysisRequest) =>
    request<AnalysisSummary>("/api/analyses", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getAnalysis: (id: string) => request<AnalysisSummary>(`/api/analyses/${id}`),
  cancelAnalysis: (id: string) =>
    request<void>(`/api/analyses/${id}`, { method: "DELETE" }),
  eventsUrl: (id: string, after = 0) =>
    `/api/analyses/${id}/events${after > 0 ? `?after=${after}` : ""}`,
  logUrl: (id: string) => `/api/analyses/${id}/log`,
  /** The calibration run (backend/data/calibration.json); 404 until one has been made. */
  getCalibration: () => request<CalibrationReport>("/api/calibration"),
  /** One company across its analysed documents; `name` is its name, slug or a prefix. */
  getCompany: (name: string) =>
    request<CompanyView>(`/api/company/${encodeURIComponent(name)}`),
}
