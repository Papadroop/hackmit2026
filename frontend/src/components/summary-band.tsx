import type { Summary } from "@contract"

import { ScoreBar } from "@/components/score-bar"
import { VerdictMark } from "@/components/verdict-mark"
import {
  VERDICT_LABELS,
  VERDICT_ORDER,
  countVerdicts,
  formatScore,
} from "@/lib/encoding"
import {
  PROFILE_LABELS,
  PROFILE_ORDER,
  PROFILE_QUESTIONS,
} from "@/lib/evidence"
import { cn } from "@/lib/utils"
import { isFinished, type AnalysisState } from "@/state/analysis"

/**
 * The summary header (design-plan.md, design-doc D6): one dense band, not stat tiles. The
 * headline likelihood with its confidence first, then the five-dimension profile, then the
 * verdict distribution and counts, then the top issues and the credit, each linking to its
 * claim. Before the summary stage the band shows what is known so far; below the width where
 * the side panel fits it keeps only the headline and the counts.
 */
export function SummaryBand({
  state,
  selectedId,
  onSelect,
  onShowOmission,
}: {
  state: AnalysisState
  selectedId: string | null
  onSelect: (id: string, options?: { scroll?: boolean }) => void
  /** Switch the Omissions layer on and scroll to a card, or to the first card. */
  onShowOmission: (id?: string) => void
}) {
  const { summary } = state
  const finished = isFinished(state.status)
  const claimIds = new Set(state.claims.map((claim) => claim.id))
  const omissionIds = new Set(state.omissions.map((o) => o.id))
  const distribution =
    summary?.verdict_distribution ?? countVerdicts(state.verdicts)
  const decided = VERDICT_ORDER.reduce((n, c) => n + distribution[c], 0)
  const claimCount = summary?.claim_count ?? state.claims.length
  const counts = [
    `${claimCount} ${claimCount === 1 ? "claim" : "claims"}`,
    summary?.omission_count === null || summary === null
      ? null
      : `${summary.omission_count} ${summary.omission_count === 1 ? "omission" : "omissions"}`,
  ]
    .filter(Boolean)
    .join(", ")

  return (
    <section
      aria-label="Summary"
      className="border-b bg-card px-4 py-2.5 text-[13px] leading-snug sm:px-6"
    >
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <p className="flex items-baseline gap-2 whitespace-nowrap">
          <span className="text-muted-foreground">Likelihood</span>
          {summary === null ? (
            <span className="text-muted-foreground">
              {finished ? "not summarised" : "follows the verdicts"}
            </span>
          ) : (
            <>
              <span className="text-[22px] leading-none font-medium tabular-nums">
                {formatScore(summary.headline.score)}
              </span>
              <span className="text-muted-foreground tabular-nums">
                confidence {formatScore(summary.headline.confidence)}
              </span>
              {!summary.final && (
                <span className="text-muted-foreground">provisional</span>
              )}
            </>
          )}
        </p>
        <ul
          aria-label="Profile"
          className="hidden flex-wrap items-baseline gap-x-5 gap-y-1 min-[56rem]:flex"
        >
          {PROFILE_ORDER.map((dimension) => {
            const entry = summary?.dimensions[dimension]
            return (
              <li
                key={dimension}
                className="flex items-baseline gap-1.5 whitespace-nowrap"
                title={PROFILE_QUESTIONS[dimension]}
              >
                <span className="text-muted-foreground">
                  {PROFILE_LABELS[dimension]}
                </span>
                <ScoreBar
                  score={entry?.score ?? null}
                  confidence={entry?.confidence ?? 0}
                  className="w-10"
                />
                {entry !== undefined && (
                  <span className="tabular-nums">
                    {formatScore(entry.score)}
                    <span className="text-muted-foreground">
                      , confidence {formatScore(entry.confidence)}
                    </span>
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      </div>

      <div className="mt-1 flex flex-wrap items-baseline gap-x-5 gap-y-1">
        {decided === 0 ? (
          <span className="text-muted-foreground">
            {finished ? "No verdicts." : "Verdicts follow the evidence."}
          </span>
        ) : (
          VERDICT_ORDER.map((category) => (
            <span key={category} className="whitespace-nowrap tabular-nums">
              {distribution[category]}{" "}
              <VerdictMark category={category} confidence={0.85}>
                {VERDICT_LABELS[category].toLowerCase()}
              </VerdictMark>
            </span>
          ))
        )}
        <span className="text-muted-foreground tabular-nums">
          {state.omissions.length > 0 ? (
            <>
              {counts.split(", ")[0]},{" "}
              <button
                type="button"
                className="rounded-xs underline decoration-border decoration-dotted underline-offset-2 outline-none hover:text-marker hover:decoration-marker focus-visible:ring-3 focus-visible:ring-ring/50"
                onClick={() => onShowOmission()}
              >
                {counts.split(", ")[1] ??
                  `${state.omissions.length} ${state.omissions.length === 1 ? "omission" : "omissions"}`}
              </button>
            </>
          ) : (
            counts
          )}
        </span>
      </div>

      {summary !== null &&
        (summary.top_issues.length > 0 || summary.credit.length > 0) && (
          <div className="mt-2 hidden grid-cols-[auto_1fr] gap-x-4 gap-y-1 min-[56rem]:grid">
            {summary.top_issues.length > 0 && (
              <>
                <span className="text-muted-foreground">Top issues</span>
                <ol className="columns-2 gap-x-8">
                  {summary.top_issues.map((issue) => (
                    <li
                      key={`${issue.rank}-${issue.target}`}
                      className="flex break-inside-avoid gap-2"
                    >
                      <span className="w-3 shrink-0 text-right text-muted-foreground tabular-nums">
                        {issue.rank}
                      </span>
                      <Target
                        target={issue}
                        kind={
                          claimIds.has(issue.target)
                            ? "claim"
                            : omissionIds.has(issue.target)
                              ? "omission"
                              : null
                        }
                        selected={selectedId === issue.target}
                        onSelect={onSelect}
                        onShowOmission={onShowOmission}
                      />
                    </li>
                  ))}
                </ol>
              </>
            )}
            {summary.credit.length > 0 && (
              <>
                <span className="text-muted-foreground">Credit</span>
                <ul className="flex flex-wrap gap-x-5 gap-y-1">
                  {summary.credit.map((item, i) => (
                    <li key={`${item.target}-${i}`}>
                      <Target
                        target={item}
                        kind={
                          claimIds.has(item.target)
                            ? "claim"
                            : omissionIds.has(item.target)
                              ? "omission"
                              : null
                        }
                        selected={selectedId === item.target}
                        onSelect={onSelect}
                        onShowOmission={onShowOmission}
                      />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
    </section>
  )
}

/** A top issue or a credit: a button to its claim, or to its omission card (switching the
 * Omissions layer on), or plain text for a target that has not arrived. */
function Target({
  target,
  kind,
  selected,
  onSelect,
  onShowOmission,
}: {
  target: Summary["credit"][number]
  kind: "claim" | "omission" | null
  selected: boolean
  onSelect: (id: string, options?: { scroll?: boolean }) => void
  onShowOmission: (id?: string) => void
}) {
  const id = (
    <span className="ml-1.5 text-muted-foreground tabular-nums">
      {target.target}
    </span>
  )
  if (kind === null)
    return (
      <span>
        {target.title}
        {id}
      </span>
    )
  return (
    <button
      type="button"
      className={cn(
        "rounded-xs text-left underline decoration-border decoration-dotted underline-offset-2 outline-none hover:text-marker hover:decoration-marker focus-visible:ring-3 focus-visible:ring-ring/50",
        selected && "font-medium"
      )}
      aria-pressed={kind === "claim" ? selected : undefined}
      onClick={() =>
        kind === "claim"
          ? onSelect(target.target, { scroll: true })
          : onShowOmission(target.target)
      }
    >
      {target.title}
      {id}
    </button>
  )
}
