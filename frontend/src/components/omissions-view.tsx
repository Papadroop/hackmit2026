import { useCallback, useEffect, useMemo, useRef } from "react"
import { ChevronRight } from "lucide-react"

import type { Omission } from "@contract"

import { EvidenceList, type EvidenceNames } from "@/components/evidence-list"
import { ScoreBar } from "@/components/score-bar"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { flash, prefersReducedMotion, type Focus } from "@/lib/document-dom"
import { useKeptScroll, type ScrollStore } from "@/lib/keep-scroll"
import { formatScore } from "@/lib/encoding"
import { evidenceForClaim } from "@/lib/evidence"
import { isFinished, type AnalysisState } from "@/state/analysis"

/**
 * Omissions: what the page does not say (design-doc D4 Q3, contract §8). An omission has no
 * place in the text, which is why it never worked as a layer over it — it was a slip of paper
 * pushed above the sheet. Here it has the desk to itself: one card per topic, worst first, each
 * saying why the absence is material, what the page would say if it were complete, and how
 * near it came to saying it.
 */
export function OmissionsView({
  state,
  scrolls,
  focus,
}: {
  state: AnalysisState
  scrolls: ScrollStore
  /** An omission another section asked for; flashed once this one is on screen. */
  focus: Focus | null
}) {
  const rootRef = useKeptScroll<HTMLDivElement>(scrolls, "omissions")
  const omissions = useMemo(
    () =>
      [...state.omissions]
        .map((omission, order) => ({ omission, order }))
        .sort(
          (a, b) =>
            b.omission.score - a.omission.score ||
            b.omission.confidence - a.omission.confidence ||
            a.order - b.order
        )
        .map(({ omission }) => omission),
    [state.omissions]
  )
  const names: EvidenceNames = useMemo(
    () => new Map(state.evidence.map((item) => [item.id, item.source.name])),
    [state.evidence]
  )

  useEffect(() => {
    if (focus === null) return
    const card = rootRef.current?.querySelector<HTMLElement>(
      `[data-omission="${CSS.escape(focus.id)}"]`
    )
    if (card === null || card === undefined) return
    card.scrollIntoView({
      block: "center",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    })
    flash(card)
  }, [focus, rootRef])

  return (
    <div ref={rootRef} className="h-full overflow-auto">
      <div className="mx-auto w-full max-w-[66rem] px-4 py-6 sm:px-6 sm:py-8">
        <h2 className="font-serif text-[24px] leading-tight font-medium">
          What the page does not say
        </h2>
        <p className="mt-1.5 max-w-[68ch] text-[15px] leading-normal text-muted-foreground">
          Material topics the page leaves out, worst first. Materiality is how
          much the absence changes the picture a reader is left with; the
          reference beneath each one is the standard that makes it material.
        </p>
        {omissions.length === 0 ? (
          <p className="mt-8 text-[15px] text-muted-foreground">
            {isFinished(state.status)
              ? "Nothing material was found missing."
              : "Looking for what is left out."}
          </p>
        ) : (
          <ul className="mt-7 grid gap-4 lg:grid-cols-2">
            {omissions.map((omission) => (
              <OmissionCard
                key={omission.id}
                omission={omission}
                evidence={state.evidence}
                names={names}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/**
 * The nearest the page comes to the topic, when the omissions stage found anything at all
 * (`auditor.omissions` puts the passage it located in the text here). It is what makes "not
 * mentioned" answerable: the reader can see the words that are there instead.
 */
function nearestOf(omission: Omission): string | undefined {
  const nearest = (omission.ext as { nearest?: unknown } | undefined)?.nearest
  return typeof nearest === "string" && nearest !== "" ? nearest : undefined
}

function OmissionCard({
  omission,
  evidence,
  names,
}: {
  omission: Omission
  evidence: AnalysisState["evidence"]
  names: EvidenceNames
}) {
  const cardRef = useRef<HTMLLIElement>(null)
  const entries = useMemo(
    () =>
      evidenceForClaim(
        omission.id,
        evidence,
        new Set(omission.evidence_ids ?? [])
      ),
    [omission.id, omission.evidence_ids, evidence]
  )
  const present = useMemo(
    () => new Set(entries.map((entry) => entry.item.id)),
    [entries]
  )
  const cite = useCallback((id: string) => {
    const row = cardRef.current?.querySelector<HTMLElement>(
      `[data-evidence="${CSS.escape(id)}"]`
    )
    if (!row) return
    row.scrollIntoView({
      block: "center",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    })
    flash(row)
  }, [])
  const nearest = nearestOf(omission)

  return (
    <li
      ref={cardRef}
      data-omission={omission.id}
      tabIndex={-1}
      className="flex h-full flex-col rounded-sm border bg-paper p-4 text-[15px] leading-normal outline-none sm:p-5"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-[19px] leading-snug font-medium">
          {omission.topic}
        </h3>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {omission.id}
        </span>
      </div>
      {omission.why_material !== "" && (
        <p className="mt-2">{omission.why_material}</p>
      )}
      {omission.complete_text !== undefined && (
        <>
          <p className="mt-3 text-xs text-muted-foreground">
            What the page would say
          </p>
          <blockquote className="mt-1 border-l-2 border-graphite/40 pl-3 font-serif leading-snug">
            {omission.complete_text}
          </blockquote>
        </>
      )}
      {nearest !== undefined && (
        <p className="mt-3 text-[13px] leading-snug text-muted-foreground">
          Nearest the page comes:{" "}
          <span className="font-serif text-foreground">“{nearest}”</span>
        </p>
      )}
      <div className="mt-auto pt-4">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] tabular-nums">
          <span className="text-muted-foreground">Materiality</span>
          <ScoreBar score={omission.score} confidence={omission.confidence} />
          <span>
            {formatScore(omission.score)}
            <span className="text-muted-foreground">
              , confidence {formatScore(omission.confidence)}
            </span>
          </span>
        </p>
        {omission.materiality_reference !== undefined && (
          <p className="mt-1 text-xs leading-snug text-muted-foreground">
            {omission.materiality_reference}
          </p>
        )}
        {entries.length > 0 && (
          <Collapsible className="mt-2">
            <CollapsibleTrigger className="group -ml-1 flex items-center gap-1 rounded-sm px-1 text-[13px] outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50">
              <ChevronRight
                aria-hidden
                className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]:rotate-90 motion-reduce:transition-none"
              />
              Evidence
              <span className="ml-1 text-muted-foreground tabular-nums">
                {entries.length}
              </span>
            </CollapsibleTrigger>
            <CollapsibleContent className="text-sm">
              <EvidenceList
                entries={entries}
                names={names}
                present={present}
                onCite={cite}
              />
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    </li>
  )
}
