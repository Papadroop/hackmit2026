import type { Summary } from "@contract"

import { useKeptScroll, type ScrollStore } from "@/lib/keep-scroll"

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
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import { isFinished, type AnalysisState } from "@/state/analysis"

/**
 * The verdict on the document: what the analysis found, written. The summary used to be a
 * band squeezed over the document, where its narrative had no room and its numbers read as
 * chrome. Given a section it can be read in the order an analyst would defend it: the finding
 * in words first, then the verdicts it rests on, the dimensions that produced them, and the
 * specific claims to go and look at.
 *
 * Nothing here is a stat tile. The one graphic is the distribution, drawn in the same hues the
 * document's own highlights use, so the bar and the page are read the same way.
 */
export function VerdictView({
  state,
  scrolls,
  onShowClaim,
  onShowOmission,
}: {
  state: AnalysisState
  scrolls: ScrollStore
  onShowClaim: (id: string) => void
  onShowOmission: (id: string) => void
}) {
  const rootRef = useKeptScroll<HTMLDivElement>(scrolls, "verdict")
  const { summary } = state
  const finished = isFinished(state.status)
  const claimIds = new Set(state.claims.map((claim) => claim.id))
  const omissionIds = new Set(state.omissions.map((o) => o.id))
  const distribution =
    summary?.verdict_distribution ?? countVerdicts(state.verdicts)
  const decided = VERDICT_ORDER.reduce((n, c) => n + distribution[c], 0)
  const claimCount = summary?.claim_count ?? state.claims.length
  const omissionCount = summary?.omission_count ?? state.omissions.length

  return (
    <div ref={rootRef} className="h-full overflow-auto">
      <div className="mx-auto w-full max-w-[64rem] px-4 py-7 sm:px-6 sm:py-9">
        <section aria-label="Finding">
          {summary === null ? (
            <p className="text-[17px] text-muted-foreground">
              {finished
                ? "The analysis ended without a summary."
                : "The verdict follows the claims. It is written once every claim has one."}
            </p>
          ) : (
            <>
              <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-[44px] leading-none font-medium tabular-nums">
                  {formatScore(summary.headline.score)}
                </span>
                <span className="text-[15px] text-muted-foreground tabular-nums">
                  greenwashing likelihood, confidence{" "}
                  {formatScore(summary.headline.confidence)}
                  {!summary.final && ", provisional"}
                </span>
              </p>
              {summary.narrative !== undefined && (
                <p className="mt-4 max-w-[66ch] font-serif text-[19px] leading-[1.55]">
                  {summary.narrative}
                </p>
              )}
            </>
          )}
        </section>

        <hr className="my-7" />

        <section aria-label="Verdicts">
          <h3 className="font-medium">
            Verdicts
            <span className="ml-2 font-normal text-muted-foreground tabular-nums">
              {decided === claimCount ? decided : `${decided} of ${claimCount}`}
            </span>
          </h3>
          {decided === 0 ? (
            <p className="mt-2 text-muted-foreground">
              {finished
                ? "No verdicts were issued."
                : "Verdicts follow the evidence."}
            </p>
          ) : (
            <>
              <div
                aria-hidden
                className="mt-3 flex h-2.5 w-full gap-px overflow-hidden rounded-xs bg-muted"
              >
                {VERDICT_ORDER.map((category) =>
                  distribution[category] === 0 ? null : (
                    <span
                      key={category}
                      data-verdict={category}
                      style={{
                        flexGrow: distribution[category],
                        backgroundColor:
                          "color-mix(in oklab, var(--mark-hue) 80%, transparent)",
                      }}
                    />
                  )
                )}
              </div>
              <ul className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1">
                {VERDICT_ORDER.map((category) => (
                  <li
                    key={category}
                    className="whitespace-nowrap tabular-nums"
                    data-empty={distribution[category] === 0 || undefined}
                  >
                    <span
                      className={cn(
                        distribution[category] === 0 && "text-muted-foreground"
                      )}
                    >
                      {distribution[category]}
                    </span>{" "}
                    <VerdictMark category={category} confidence={0.85}>
                      {VERDICT_LABELS[category].toLowerCase()}
                    </VerdictMark>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section aria-label="Dimensions" className="mt-7">
          <h3 className="font-medium">Dimensions</h3>
          <p className="text-[13px] text-muted-foreground">
            A problem score for the document on each: 0 is no signal, 1 is as
            bad as it gets.
          </p>
          <ul className="mt-3 space-y-2.5">
            {PROFILE_ORDER.map((dimension) => {
              const entry = summary?.dimensions[dimension]
              return (
                <li
                  key={dimension}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5"
                >
                  <span className="w-28">{PROFILE_LABELS[dimension]}</span>
                  <ScoreBar
                    score={entry?.score ?? null}
                    confidence={entry?.confidence ?? 0}
                    className="w-16"
                  />
                  <span className="w-[13rem] text-muted-foreground tabular-nums">
                    {entry === undefined ? (
                      finished ? (
                        "not scored"
                      ) : (
                        "not yet scored"
                      )
                    ) : (
                      <>
                        <span className="text-foreground">
                          {formatScore(entry.score)}
                        </span>
                        , confidence {formatScore(entry.confidence)}
                      </>
                    )}
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] text-muted-foreground">
                    {PROFILE_QUESTIONS[dimension]}
                  </span>
                </li>
              )
            })}
          </ul>
        </section>

        {summary !== null &&
          (summary.top_issues.length > 0 || summary.credit.length > 0) && (
            <div className="mt-7 grid gap-7 lg:grid-cols-2">
              {summary.top_issues.length > 0 && (
                <section aria-label="Top issues">
                  <h3 className="font-medium">Top issues</h3>
                  <ol className="mt-2 space-y-1.5">
                    {summary.top_issues.map((issue) => (
                      <li
                        key={`${issue.rank}-${issue.target}`}
                        className="flex gap-3"
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
                          onShowClaim={onShowClaim}
                          onShowOmission={onShowOmission}
                        />
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {summary.credit.length > 0 && (
                <section aria-label="Credit">
                  <h3 className="font-medium">Credit where due</h3>
                  <ul className="mt-2 space-y-1.5">
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
                          onShowClaim={onShowClaim}
                          onShowOmission={onShowOmission}
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}

        <p className="mt-8 text-[13px] text-muted-foreground tabular-nums">
          {formatNumber(claimCount)} {claimCount === 1 ? "claim" : "claims"},{" "}
          {formatNumber(omissionCount)}{" "}
          {omissionCount === 1 ? "omission" : "omissions"},{" "}
          {formatNumber(state.evidence.length)}{" "}
          {state.evidence.length === 1 ? "piece" : "pieces"} of evidence.
        </p>
      </div>
    </div>
  )
}

/** A top issue or a credit: a button to the section that can show it, or plain text for a
 * target that has not arrived. */
function Target({
  target,
  kind,
  onShowClaim,
  onShowOmission,
}: {
  target: Summary["credit"][number]
  kind: "claim" | "omission" | null
  onShowClaim: (id: string) => void
  onShowOmission: (id: string) => void
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
      className="rounded-xs text-left underline decoration-border decoration-dotted underline-offset-2 outline-none hover:text-marker hover:decoration-marker focus-visible:ring-3 focus-visible:ring-ring/50"
      onClick={() =>
        kind === "claim"
          ? onShowClaim(target.target)
          : onShowOmission(target.target)
      }
    >
      {target.title}
      {id}
    </button>
  )
}
