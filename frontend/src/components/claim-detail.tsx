import { useCallback, useMemo, useRef } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import type { Argument, Dimension, DimensionScore, Verdict } from "@contract"

import {
  CiteIds,
  EvidenceList,
  type EvidenceNames,
} from "@/components/evidence-list"
import { ScoreBar } from "@/components/score-bar"
import { SignalRow } from "@/components/signal-row"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { VerdictMark } from "@/components/verdict-mark"
import { flash, prefersReducedMotion } from "@/lib/document-dom"
import { TAG_LABELS, VERDICT_LABELS, formatScore } from "@/lib/encoding"
import {
  DIMENSION_LABELS,
  DIMENSION_ORDER,
  DIMENSION_QUESTIONS,
  ROLE_LABELS,
  citedIds,
  evidenceForClaim,
} from "@/lib/evidence"
import {
  CLAIM_TYPE_LABELS,
  SCOPE_LABELS,
  describeProminence,
} from "@/lib/format"
import { signalsForClaim } from "@/lib/language"
import type { AnchoredClaim } from "@/state/annotations"
import type { ClaimScores, Folded } from "@/state/fold"

const EMPTY_SCORES: ClaimScores = {}
const EMPTY_TURNS: Argument[] = []

/**
 * One claim, read like a ruling (design-plan.md, contract §8): the statement at issue, the
 * verdict with the judge's reasoning, the four dimensions that produced it, the wording
 * signals, the evidence, the debate folded away, the remedy, and the claim's extracted
 * fields last.
 */
export function ClaimDetail({
  anchored,
  folded,
  index,
  total,
  analysisFinished,
  onBack,
  onShow,
  onLocate,
}: {
  anchored: AnchoredClaim
  folded: Folded
  index: number
  total: number
  analysisFinished: boolean
  onBack: () => void
  onShow: (span: number) => void
  /** Show a language signal's span in the document. */
  onLocate?: (id: string, span: number) => void
}) {
  const { claim, spans, verdict } = anchored
  const scores = folded.scores[claim.id] ?? EMPTY_SCORES
  const turns = folded.arguments[claim.id] ?? EMPTY_TURNS
  const evidence = useMemo(
    () =>
      evidenceForClaim(
        claim.id,
        folded.evidence,
        citedIds(Object.values(scores), turns, verdict)
      ),
    [claim.id, folded.evidence, scores, turns, verdict]
  )
  const names: EvidenceNames = useMemo(
    () => new Map(folded.evidence.map((item) => [item.id, item.source.name])),
    [folded.evidence]
  )
  const present = useMemo(
    () => new Set(evidence.map((entry) => entry.item.id)),
    [evidence]
  )
  const wording = useMemo(
    () => signalsForClaim(folded.signals, claim.id),
    [folded.signals, claim.id]
  )

  const rootRef = useRef<HTMLDivElement>(null)
  const cite = useCallback((id: string) => {
    const row = rootRef.current?.querySelector<HTMLElement>(
      `[data-evidence="${CSS.escape(id)}"]`
    )
    if (!row) return
    row.scrollIntoView({
      block: "center",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    })
    flash(row)
  }, [])

  const type = CLAIM_TYPE_LABELS[claim.type] ?? claim.type
  const scope = SCOPE_LABELS[claim.scope] ?? claim.scope
  const where = [
    claim.paragraph ?? spans[0]?.paragraph ?? null,
    describeProminence(claim.prominence),
  ]
    .filter(Boolean)
    .join(", ")
  const fields: [string, string | undefined][] = [
    ["Attribute", claim.attribute],
    ["Quantity", claim.quantity],
    ["Baseline", claim.baseline],
    ["Timeframe", claim.timeframe],
    [
      "Scope",
      claim.scope_note
        ? `${capitalise(scope)}: ${claim.scope_note}`
        : capitalise(scope),
    ],
    ["Position", where || undefined],
    ["Note", claim.note],
  ]

  return (
    <div ref={rootRef} className="flex flex-col gap-5 p-4">
      <div className="-ml-2 flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft data-icon="inline-start" />
          All claims
        </Button>
        <span className="text-xs text-muted-foreground tabular-nums">
          {index + 1} of {total}
        </span>
      </div>

      <div>
        <p className="text-muted-foreground tabular-nums">{claim.id}</p>
        <h2 className="text-base font-medium">
          {type} about {scope}
        </h2>
      </div>

      <ol className="space-y-3">
        {claim.spans.map((span, i) => {
          const at = spans[i]
          return (
            <li key={i}>
              <button
                type="button"
                className="group w-full rounded-md text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                onClick={() => onShow(i)}
                disabled={at === null}
              >
                <blockquote className="border-l-2 border-graphite/40 pl-3 font-serif text-[15px] leading-snug group-hover:border-marker">
                  {span.text}
                </blockquote>
                <span className="mt-1 block pl-3 text-xs text-muted-foreground">
                  {at === null
                    ? "Not located in the text as ingested."
                    : [
                        at.paragraph,
                        i === 0 ? null : "repeated",
                        at.method === "offset"
                          ? null
                          : "re-anchored by its text",
                      ]
                        .filter(Boolean)
                        .join(", ") || "Show in the document"}
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      <section aria-label="Verdict">
        {verdict === null ? (
          <p className="text-muted-foreground">
            {analysisFinished ? "No verdict was issued." : "No verdict yet."}
          </p>
        ) : (
          <VerdictBlock
            verdict={verdict}
            names={names}
            present={present}
            onCite={cite}
          />
        )}
      </section>

      <section aria-label="Dimensions">
        <h3 className="font-medium">Dimensions</h3>
        <p className="text-xs text-muted-foreground">
          A problem score per dimension; the highest sets the likelihood.
        </p>
        <ul className="mt-2.5 space-y-2.5">
          {DIMENSION_ORDER.map((dimension) => (
            <DimensionRow
              key={dimension}
              dimension={dimension}
              score={scores[dimension]}
              finished={analysisFinished}
              names={names}
              present={present}
              onCite={cite}
            />
          ))}
        </ul>
      </section>

      {wording.length > 0 && (
        <section aria-label="Wording">
          <h3 className="font-medium">Wording</h3>
          <ul className="mt-1.5 space-y-2">
            {wording.map((signal) => (
              <SignalRow key={signal.id} signal={signal} onLocate={onLocate} />
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Evidence">
        <h3 className="font-medium">
          Evidence
          {evidence.length > 0 && (
            <span className="ml-2 font-normal text-muted-foreground tabular-nums">
              {evidence.length}
            </span>
          )}
        </h3>
        {evidence.length === 0 ? (
          <p className="mt-1 text-muted-foreground">
            {analysisFinished
              ? "No evidence was linked to this claim."
              : "Evidence appears here as it is found."}
          </p>
        ) : (
          <EvidenceList
            entries={evidence}
            names={names}
            present={present}
            onCite={cite}
          />
        )}
      </section>

      {turns.length > 0 && (
        <Debate turns={turns} names={names} present={present} onCite={cite} />
      )}

      {verdict?.fix !== undefined && (
        <section aria-label="Fix">
          <h3 className="font-medium">Fix</h3>
          <p className="mt-1">{verdict.fix}</p>
        </section>
      )}

      {verdict?.rewrite !== undefined && (
        <section aria-label="Honest rewrite">
          <h3 className="font-medium">Honest rewrite</h3>
          <blockquote className="mt-1.5 border-l-2 border-graphite/40 pl-3 font-serif text-[15px] leading-snug">
            {verdict.rewrite}
          </blockquote>
        </section>
      )}

      <section aria-label="Details">
        <h3 className="font-medium">Details</h3>
        <dl className="mt-2 grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1.5">
          {fields.map(([label, value]) =>
            value === undefined || value === "" ? null : (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd>{value}</dd>
              </div>
            )
          )}
        </dl>
      </section>
    </div>
  )
}

function VerdictBlock({
  verdict,
  names,
  present,
  onCite,
}: {
  verdict: Verdict
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
}) {
  const cited = verdict.evidence_ids ?? []
  return (
    <>
      <p>
        <VerdictMark
          category={verdict.category}
          confidence={verdict.confidence}
          className="text-[15px]"
        >
          {VERDICT_LABELS[verdict.category]}
        </VerdictMark>
        <span className="ml-2 inline-block text-muted-foreground tabular-nums">
          likelihood {formatScore(verdict.likelihood)}, confidence{" "}
          {formatScore(verdict.confidence)}
        </span>
      </p>
      {verdict.tags.length > 0 && (
        <p className="mt-1 text-muted-foreground">
          {verdict.tags.map((tag) => TAG_LABELS[tag] ?? tag).join(", ")}
        </p>
      )}
      {verdict.rationale !== "" && <p className="mt-2">{verdict.rationale}</p>}
      {cited.length > 0 && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Cites{" "}
          <CiteIds
            ids={cited}
            names={names}
            present={present}
            onCite={onCite}
          />
        </p>
      )}
    </>
  )
}

/** One dimension: name, a short bar for the score with its alpha as confidence (design-plan.md),
 * the numbers, and the evaluator's one-sentence basis. */
function DimensionRow({
  dimension,
  score,
  finished,
  names,
  present,
  onCite,
}: {
  dimension: Dimension
  score: DimensionScore | undefined
  finished: boolean
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
}) {
  const cited = score?.evidence_ids ?? []
  return (
    <li>
      <div className="grid grid-cols-[5.5rem_3.5rem_1fr] items-center gap-x-3">
        <span title={DIMENSION_QUESTIONS[dimension]}>
          {DIMENSION_LABELS[dimension]}
        </span>
        <ScoreBar
          score={score?.score ?? null}
          confidence={score?.confidence ?? 0}
        />
        <span className="text-muted-foreground tabular-nums">
          {score === undefined ? (
            finished ? (
              "not scored"
            ) : (
              "not yet scored"
            )
          ) : (
            <>
              <span className="text-foreground">
                {formatScore(score.score)}
              </span>
              , confidence {formatScore(score.confidence)}
            </>
          )}
        </span>
      </div>
      {score !== undefined && (score.basis !== "" || cited.length > 0) && (
        <p className="mt-1 text-xs leading-snug text-muted-foreground">
          {score.basis}
          {cited.length > 0 && (
            <>
              {score.basis !== "" && " "}
              From{" "}
              <CiteIds
                ids={cited}
                names={names}
                present={present}
                onCite={onCite}
              />
              .
            </>
          )}
        </p>
      )}
    </li>
  )
}

/** The prosecutor, defence and judge turns, collapsed by default (D7). */
function Debate({
  turns,
  names,
  present,
  onCite,
}: {
  turns: Argument[]
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
}) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group -ml-1 flex items-center gap-1 rounded-sm px-1 font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50">
        <ChevronRight
          aria-hidden
          className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
        />
        Debate
        <span className="ml-1 font-normal text-muted-foreground">
          {describeTurns(turns)}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-3">
        {turns.map((turn, i) => {
          const cited = turn.evidence_ids ?? []
          return (
            <div key={i}>
              <p className="text-xs text-muted-foreground">
                {ROLE_LABELS[turn.role] ?? turn.role}
              </p>
              <p className="mt-0.5">{turn.text}</p>
              {cited.length > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Cites{" "}
                  <CiteIds
                    ids={cited}
                    names={names}
                    present={present}
                    onCite={onCite}
                  />
                </p>
              )}
            </div>
          )
        })}
      </CollapsibleContent>
    </Collapsible>
  )
}

/** "prosecutor and defence", or a count when a role has spoken more than once. */
function describeTurns(turns: Argument[]): string {
  const roles = Object.keys(ROLE_LABELS).filter((role) =>
    turns.some((t) => t.role === role)
  )
  if (roles.length !== turns.length) return `${turns.length} turns`
  const words = roles.map((role) =>
    ROLE_LABELS[role as Argument["role"]].toLowerCase()
  )
  if (words.length === 1) return words[0]
  return `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
