/**
 * The event envelope shared by fixtures, live runs and replay. The rules are in
 * fixtures/README.md. Payload shapes belong to the data contract (roadmap step 2) and are
 * opaque here.
 */
export type Envelope = {
  seq: number
  t_ms: number
  type: string
  payload: Record<string, unknown>
}

/** An envelope as the client received it, with the arrival time in ms since the stream opened. */
export type ReceivedEvent = Envelope & { received_ms: number }

export const ANALYSIS_STARTED = "analysis.started"
export const ANALYSIS_COMPLETED = "analysis.completed"
export const ANALYSIS_FAILED = "analysis.failed"
export const STAGE_STARTED = "stage.started"
export const STAGE_COMPLETED = "stage.completed"
/** Contract event (contract/schema.json) that carries the Document object. */
export const DOCUMENT_INGESTED = "document.ingested"

export function isTerminal(type: string): boolean {
  return type === ANALYSIS_COMPLETED || type === ANALYSIS_FAILED
}

export function isLifecycle(type: string): boolean {
  return type.startsWith("analysis.") || type.startsWith("stage.")
}

export function isEnvelope(value: unknown): value is Envelope {
  if (typeof value !== "object" || value === null) return false
  const v = value as Record<string, unknown>
  return (
    Number.isInteger(v.seq) &&
    Number.isInteger(v.t_ms) &&
    typeof v.type === "string" &&
    typeof v.payload === "object" &&
    v.payload !== null &&
    !Array.isArray(v.payload)
  )
}
