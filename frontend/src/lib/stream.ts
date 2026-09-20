import { isEnvelope, isTerminal, type ReceivedEvent } from "./events"

export type StreamStatus = "open" | "reconnecting" | "closed"

export type StreamHandlers = {
  onEvent: (event: ReceivedEvent) => void
  /** `detail` is set only when the stream closed for a reason the user should see. */
  onStatus: (status: StreamStatus, detail?: string) => void
}

/**
 * Subscribe to an analysis's event stream. The server puts the whole envelope in `data:` so
 * one `onmessage` handler sees every event type. The browser reconnects on its own and sends
 * `Last-Event-ID`, so a dropped connection resumes where it left off. Returns a closer.
 */
export function openEventStream(
  url: string,
  handlers: StreamHandlers
): () => void {
  const source = new EventSource(url)
  const openedAt = performance.now()
  let finished = false

  const fail = (detail: string) => {
    finished = true
    source.close()
    handlers.onStatus("closed", detail)
  }

  source.onopen = () => handlers.onStatus("open")

  source.onmessage = (message: MessageEvent<string>) => {
    let parsed: unknown
    try {
      parsed = JSON.parse(message.data)
    } catch {
      fail("The server sent an event that is not JSON.")
      return
    }
    if (!isEnvelope(parsed)) {
      fail(
        "The server sent an event without the expected envelope (seq, t_ms, type, payload)."
      )
      return
    }
    handlers.onEvent({
      ...parsed,
      received_ms: Math.round(performance.now() - openedAt),
    })
    if (isTerminal(parsed.type)) {
      finished = true
      source.close()
      handlers.onStatus("closed")
    }
  }

  source.onerror = () => {
    if (finished) return
    if (source.readyState === EventSource.CLOSED) {
      fail("The event stream was refused or closed by the server.")
    } else {
      handlers.onStatus("reconnecting")
    }
  }

  return () => {
    finished = true
    source.close()
  }
}
