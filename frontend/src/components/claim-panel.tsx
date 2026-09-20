import { ClaimDetail } from "@/components/claim-detail"
import { SignalRow } from "@/components/signal-row"
import { VerdictMark } from "@/components/verdict-mark"
import { VERDICT_ORDER, countVerdicts, formatScore } from "@/lib/encoding"
import { CLAIM_TYPE_LABELS, formatDuration } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AnchoredClaim } from "@/state/annotations"
import { isFinished, selectStages, type AnalysisState } from "@/state/analysis"

/**
 * The right-hand panel (design-plan.md). With nothing selected it shows the pipeline's progress
 * and the claims found so far, in document order. With a claim selected it shows that claim
 * (components/claim-detail.tsx).
 */
export function ClaimPanel({
  state,
  claims,
  selectedId,
  onSelect,
  onLocate,
  className,
}: {
  state: AnalysisState
  claims: AnchoredClaim[]
  selectedId: string | null
  onSelect: (
    id: string | null,
    options?: { scroll?: boolean; span?: number }
  ) => void
  /** Show a language signal's span in the document. */
  onLocate?: (id: string, span: number) => void
  className?: string
}) {
  const selected =
    selectedId === null
      ? null
      : (claims.find((c) => c.claim.id === selectedId) ?? null)
  return (
    <aside
      className={cn(
        "flex h-full min-h-0 flex-col overflow-auto border-l bg-card text-sm",
        className
      )}
    >
      {selected === null ? (
        <Overview state={state} claims={claims} onSelect={onSelect} />
      ) : (
        <ClaimDetail
          anchored={selected}
          folded={state}
          index={claims.indexOf(selected)}
          total={claims.length}
          analysisFinished={isFinished(state.status)}
          onBack={() => onSelect(null)}
          onShow={(span) => onSelect(selected.claim.id, { scroll: true, span })}
          onLocate={onLocate}
        />
      )}
    </aside>
  )
}

function Overview({
  state,
  claims,
  onSelect,
}: {
  state: AnalysisState
  claims: AnchoredClaim[]
  onSelect: (id: string, options?: { scroll?: boolean }) => void
}) {
  const stages = selectStages(state.events)
  const finished = isFinished(state.status)
  const elapsed = state.events.at(-1)?.t_ms ?? 0
  const extracting = stages.some(
    (s) => s.stage === "extract" && s.status === "running"
  )
  const unplaced = claims.filter((c) => c.spans[0] === null).length
  const deciding = stages.some(
    (s) => s.stage === "verdict" && s.status === "running"
  )
  const counts = countVerdicts(state.verdicts)
  const decided = Object.keys(state.verdicts).length
  const documentSignals = state.signals.filter((s) => s.level === "document")

  return (
    <div className="flex flex-col gap-6 p-4">
      <section aria-label="Progress">
        {finished ? (
          <p className="text-muted-foreground">
            {finishedText(state, elapsed)}
          </p>
        ) : stages.length === 0 ? (
          <p className="text-muted-foreground">
            {state.status === "connecting"
              ? "Opening the analysis."
              : "Waiting for the first stage."}
          </p>
        ) : (
          <ol className="space-y-1">
            {stages.map((stage, i) => (
              <li
                key={`${i}-${stage.stage}`}
                className="flex items-center gap-2.5"
              >
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    stage.status === "done"
                      ? "bg-graphite"
                      : "bg-marker motion-safe:animate-pulse"
                  )}
                />
                <span
                  className={
                    stage.status === "done"
                      ? "text-muted-foreground"
                      : undefined
                  }
                >
                  {stage.label}
                </span>
              </li>
            ))}
          </ol>
        )}
        {state.error !== null && state.error !== "cancelled" && (
          <p role="alert" className="mt-2 text-destructive">
            {state.error}
          </p>
        )}
      </section>

      {state.summary !== null && (
        <section aria-label="Summary">
          <h2 className="font-medium">
            Summary
            {!state.summary.final && (
              <span className="ml-2 font-normal text-muted-foreground">
                provisional
              </span>
            )}
          </h2>
          <p className="mt-1">
            {state.summary.narrative ??
              `Likelihood ${formatScore(state.summary.headline.score)}, confidence ${formatScore(state.summary.headline.confidence)}.`}
          </p>
        </section>
      )}

      {documentSignals.length > 0 && (
        <section aria-label="Wording">
          <h2 className="font-medium">Wording, document-level</h2>
          <ul className="mt-2 space-y-2">
            {documentSignals.map((signal) => (
              <SignalRow key={signal.id} signal={signal} />
            ))}
          </ul>
        </section>
      )}

      {decided > 0 && (
        <section aria-label="Verdicts">
          <h2 className="font-medium">
            Verdicts
            <span className="ml-2 font-normal text-muted-foreground tabular-nums">
              {deciding ? `${decided} of ${claims.length}` : decided}
            </span>
          </h2>
          <ul className="mt-2 space-y-1.5">
            {VERDICT_ORDER.map((category) => (
              <li key={category} className="flex items-baseline gap-3">
                <VerdictMark category={category} confidence={0.85} />
                <span className="text-muted-foreground tabular-nums">
                  {counts[category]}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Claims">
        <h2 className="font-medium">
          Claims
          <span className="ml-2 font-normal text-muted-foreground tabular-nums">
            {claims.length}
            {extracting && " so far"}
          </span>
        </h2>
        {claims.length === 0 ? (
          <p className="mt-2 text-muted-foreground">
            {finished
              ? "No claims were found."
              : "Claims appear here as they are found."}
          </p>
        ) : (
          <ol className="-mx-2 mt-2">
            {claims.map(({ claim, spans, verdict }) => (
              <li key={claim.id}>
                <button
                  type="button"
                  className="flex w-full gap-3 rounded-md px-2 py-1.5 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                  onClick={() => onSelect(claim.id, { scroll: true })}
                >
                  <span className="w-8 shrink-0 text-muted-foreground tabular-nums">
                    {claim.id}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 font-serif text-[15px] leading-snug">
                      {claim.spans[0].text}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {verdict === null ? (
                        (CLAIM_TYPE_LABELS[claim.type] ?? claim.type)
                      ) : (
                        <>
                          <VerdictMark
                            category={verdict.category}
                            confidence={verdict.confidence}
                          />
                          <span className="tabular-nums">
                            , confidence {formatScore(verdict.confidence)}
                          </span>
                        </>
                      )}
                      {spans[0] === null && ", not located in the text"}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
        {unplaced > 0 && (
          <p className="mt-2 text-muted-foreground">
            {unplaced === 1 ? "One claim" : `${unplaced} claims`} could not be
            located in the text and {unplaced === 1 ? "is" : "are"} not
            highlighted.
          </p>
        )}
      </section>
    </div>
  )
}

function finishedText(state: AnalysisState, elapsed: number): string {
  switch (state.status) {
    case "completed":
      return `Analysis complete in ${formatDuration(elapsed)}.`
    case "failed":
      return state.error === "cancelled"
        ? "Analysis stopped."
        : "Analysis failed."
    default:
      return ""
  }
}
