import {
  STAGE_LABELS,
  isFinished,
  selectStages,
  type AnalysisState,
} from "@/state/analysis"
import { formatDuration } from "@/lib/format"
import { cn } from "@/lib/utils"

/**
 * The pipeline in the header, where the events panel used to be. The nine stages are a
 * sequence (contract `Stage`), so they are drawn as one: a tick each, filling as they
 * complete, with the running stage named beside them. It is the only thing on this screen
 * that moves on its own, and when the analysis stops the ticks give way to how it ended.
 */
const STAGE_ORDER: readonly string[] = [
  "ingest",
  "extract",
  "language",
  "substantiate",
  "verify",
  "consistency",
  "omissions",
  "verdict",
  "summary",
]

export function Pipeline({ state }: { state: AnalysisState }) {
  if (isFinished(state.status))
    return (
      <p
        className={cn(
          "text-[13px] whitespace-nowrap",
          state.status === "failed" && state.error !== "cancelled"
            ? "text-destructive"
            : "text-muted-foreground"
        )}
      >
        {endedText(state)}
      </p>
    )

  const stages = selectStages(state.events)
  const status = new Map(stages.map((stage) => [stage.stage, stage.status]))
  // Canonical order, plus any stage a live run emitted that the contract does not list.
  const order = [
    ...STAGE_ORDER,
    ...stages.map((s) => s.stage).filter((s) => !STAGE_ORDER.includes(s)),
  ]
  const running = stages.findLast((stage) => stage.status === "running")

  return (
    <p
      className="flex items-center gap-2.5 text-[13px] text-muted-foreground"
      aria-live="polite"
    >
      <span aria-hidden className="flex items-center gap-[3px]">
        {order.map((stage) => {
          const tick = status.get(stage)
          return (
            <span
              key={stage}
              title={STAGE_LABELS[stage] ?? stage}
              className={cn(
                "h-2.5 w-[3px] rounded-[1px]",
                tick === "done"
                  ? "bg-graphite/70"
                  : tick === "running"
                    ? "bg-primary motion-safe:animate-pulse"
                    : "bg-border"
              )}
            />
          )
        })}
      </span>
      <span className="hidden truncate lg:inline">
        {running?.label ?? "Opening the analysis"}
      </span>
    </p>
  )
}

function endedText(state: AnalysisState): string {
  const elapsed = state.events.at(-1)?.t_ms ?? 0
  switch (state.status) {
    case "completed":
      return `Complete in ${formatDuration(elapsed)}`
    case "failed":
      return state.error === "cancelled" ? "Stopped" : "Analysis failed"
    default:
      return ""
  }
}
