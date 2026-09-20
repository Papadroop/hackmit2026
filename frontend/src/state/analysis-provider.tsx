import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react"

import { ApiError, api } from "@/lib/api"
import { openEventStream } from "@/lib/stream"
import {
  AnalysisContext,
  analysisReducer,
  initialState,
  type AnalysisApi,
} from "./analysis"

/**
 * Holds one analysis: fetches its summary, then tails its event stream until the terminal
 * event. Mount it with `key={analysisId}` so a different id starts from a clean state.
 */
export function AnalysisProvider({
  analysisId,
  children,
}: {
  analysisId: string
  children: ReactNode
}) {
  const [state, dispatch] = useReducer(
    analysisReducer,
    analysisId,
    initialState
  )

  useEffect(() => {
    let cancelled = false
    let closeStream: (() => void) | null = null
    api
      .getAnalysis(analysisId)
      .then((summary) => {
        if (cancelled) return
        dispatch({ type: "record", record: summary })
        closeStream = openEventStream(api.eventsUrl(analysisId), {
          onEvent: (event) => dispatch({ type: "event", event }),
          onStatus: (status, detail) =>
            dispatch({ type: "stream", status, detail }),
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof ApiError && error.status === 404
            ? "There is no analysis with this id. It may belong to an earlier run of the server."
            : error instanceof Error
              ? error.message
              : String(error)
        dispatch({ type: "missing", error: message })
      })
    return () => {
      cancelled = true
      closeStream?.()
    }
  }, [analysisId])

  const stop = useCallback(async () => {
    try {
      await api.cancelAnalysis(analysisId)
    } catch {
      // The stream reports whatever the server did.
    }
  }, [analysisId])

  const value = useMemo<AnalysisApi>(() => ({ state, stop }), [state, stop])

  return (
    <AnalysisContext.Provider value={value}>
      {children}
    </AnalysisContext.Provider>
  )
}
