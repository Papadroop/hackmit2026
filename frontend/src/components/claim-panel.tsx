import { ClaimDetail } from "@/components/claim-detail"
import { SignalRow } from "@/components/signal-row"
import { VerdictMark } from "@/components/verdict-mark"
import { Toggle } from "@/components/ui/toggle"
import { formatScore } from "@/lib/encoding"
import { CLAIM_TYPE_LABELS } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AnchoredClaim, Marks } from "@/state/annotations"
import { isFinished, type AnalysisState } from "@/state/analysis"

/**
 * The right-hand column of the Claims section. Its head is the control for what the sheet is
 * marked with; under it, the claims in document order, or the selected claim read like a
 * ruling (components/claim-detail.tsx).
 */
export function ClaimPanel({
  state,
  claims,
  marks,
  onMarksChange,
  selectedId,
  onSelect,
  onLocate,
  className,
}: {
  state: AnalysisState
  claims: AnchoredClaim[]
  marks: Marks
  onMarksChange: (marks: Marks) => void
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
        "flex h-full min-h-0 flex-col overflow-hidden border-l bg-card text-sm",
        className
      )}
    >
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
        <span className="text-xs text-muted-foreground">In the text</span>
        <Toggle
          variant="outline"
          size="sm"
          pressed={marks.claims}
          onPressedChange={(claims) => onMarksChange({ ...marks, claims })}
        >
          Claims
          <Count n={state.claims.length} />
        </Toggle>
        <Toggle
          variant="outline"
          size="sm"
          pressed={marks.wording}
          onPressedChange={(wording) => onMarksChange({ ...marks, wording })}
        >
          Wording
          <Count n={state.signals.length} />
        </Toggle>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
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
            onShow={(span) =>
              onSelect(selected.claim.id, { scroll: true, span })
            }
            onLocate={onLocate}
          />
        )}
      </div>
    </aside>
  )
}

function Count({ n }: { n: number }) {
  if (n === 0) return null
  return (
    <span className="font-normal text-muted-foreground tabular-nums">{n}</span>
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
  const finished = isFinished(state.status)
  const unplaced = claims.filter((c) => c.spans[0] === null).length
  const documentSignals = state.signals.filter((s) => s.level === "document")

  return (
    <div className="flex flex-col gap-6 p-4">
      {state.error !== null && state.error !== "cancelled" && (
        <p role="alert" className="text-destructive">
          {state.error}
        </p>
      )}

      <section aria-label="Claims">
        <h2 className="font-medium">
          Claims
          <span className="ml-2 font-normal text-muted-foreground tabular-nums">
            {claims.length}
            {!finished && " so far"}
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
    </div>
  )
}
