import {
  Fragment,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type Ref,
} from "react"

import { DocumentBlock } from "@/components/document-blocks"
import { blockRange, type Group, type Section } from "@/lib/document-layout"
import { cn } from "@/lib/utils"
import type { AnalysisState } from "@/state/analysis"
import type { Annotations } from "@/state/annotations"

const NO_REWRITES: Record<string, string> = {}
const NO_MARKS: Annotations["marks"] = []

/**
 * The corrected version as a split: the page as published on the left, the same page as the
 * evidence allows it on the right, block beside block. A redline reads well when a rewrite is
 * a few words; when it is a paragraph — and the worst claims here are rewritten wholesale — the
 * struck text and its replacement run into each other and neither can be read as prose.
 *
 * Both columns are one grid with a row per block, not two scrolling panes, so a paragraph and
 * its rewrite always start on the same line however much longer the rewrite is. Between them,
 * the ids of the claims that changed in that row: the sheet's margin ids, in the one place a
 * split diff leaves for them. What the page omits comes last, with nothing on the left.
 */
export function CorrectedSplit({
  ref,
  state,
  annotations,
  rewrites,
  onShowClaim,
  onShowOmission,
  className,
}: {
  ref?: Ref<HTMLDivElement>
  state: AnalysisState
  annotations: Annotations
  rewrites: Record<string, string>
  onShowClaim: (id: string) => void
  onShowOmission: (id: string) => void
  className?: string
}) {
  const doc = state.document
  const added = state.omissions.filter(
    (omission) => omission.complete_text !== undefined
  )

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    const selection = window.getSelection()
    if (selection !== null && !selection.isCollapsed) return // the reader is selecting text
    const target = event.target as HTMLElement
    const insert = target.closest<HTMLElement>("[data-omission-text]")
    if (insert !== null) {
      onShowOmission(insert.dataset.omissionText ?? "")
      return
    }
    const claim = target.closest<HTMLElement>("[data-claim]")
    if (claim?.dataset.claim !== undefined) onShowClaim(claim.dataset.claim)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return
    const target = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-claim][tabindex]"
    )
    if (target?.dataset.claim === undefined) return
    event.preventDefault()
    onShowClaim(target.dataset.claim)
  }

  return (
    <div ref={ref} className={cn("h-full overflow-auto", className)}>
      <article
        className="mx-auto my-4 w-full max-w-[76rem] border bg-paper px-5 py-8 sm:my-8 sm:px-9 sm:py-10"
        aria-label={doc?.title ?? "Document"}
        data-honest="clean"
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        <div className="document grid grid-cols-[1fr_3rem_1fr] items-start">
          <Label>As published</Label>
          {/* The rule under the labels runs across the gutter too, so it is one rule and not
              two; the space holds the line at the labels' own height. */}
          <Label> </Label>
          <Label>As the evidence allows</Label>

          {doc !== null &&
            annotations.sections.map((section, i) =>
              rows(section).map(({ group, first, tight }) => {
                const changed = rewrittenIn(group, annotations, rewrites)
                return (
                  <Fragment key={`${i}-${blockRange(group)[0]}`}>
                    <Cell section={section} first={first} tight={tight}>
                      <DocumentBlock
                        group={group}
                        text={doc.text}
                        marks={annotations.marks}
                        languageMarks={NO_MARKS}
                        verdicts={state.verdicts}
                        signals={annotations.signals}
                        rewrites={NO_REWRITES}
                        redline={false}
                        selectedId={null}
                      />
                    </Cell>
                    <p
                      className={cn(
                        "text-center",
                        lead(group, section, first, tight)
                      )}
                    >
                      {changed.map((id) => (
                        <button
                          key={id}
                          type="button"
                          className="block w-full rounded-xs font-sans text-[13px] leading-[27px] text-graphite tabular-nums outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                          onClick={() => onShowClaim(id)}
                        >
                          {id}
                        </button>
                      ))}
                    </p>
                    <Cell section={section} first={first} tight={tight}>
                      <DocumentBlock
                        group={group}
                        text={doc.text}
                        marks={annotations.marks}
                        languageMarks={NO_MARKS}
                        verdicts={state.verdicts}
                        signals={annotations.signals}
                        rewrites={rewrites}
                        redline={false}
                        selectedId={null}
                      />
                    </Cell>
                  </Fragment>
                )
              })
            )}

          {added.map((omission) => (
            <Fragment key={omission.id}>
              <p className="document-paragraph font-sans text-[13px] leading-[27px] text-graphite">
                Not on the page.
              </p>
              <p className="document-paragraph text-center">
                <button
                  type="button"
                  className="block w-full rounded-xs font-sans text-[13px] leading-[27px] text-graphite tabular-nums outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                  onClick={() => onShowOmission(omission.id)}
                >
                  {omission.id}
                </button>
              </p>
              <p
                className="document-paragraph document-insert"
                data-omission-text={omission.id}
                title={`Not mentioned: ${omission.topic}`}
              >
                <ins className="honest-ins">{omission.complete_text}</ins>
              </p>
            </Fragment>
          ))}
        </div>
        {doc === null && (
          <p className="document mt-6 text-graphite">
            There is no document to correct yet.
          </p>
        )}
      </article>
    </div>
  )
}

function Label({ children }: { children: string }) {
  return (
    <p className="border-b pb-2 font-sans text-[13px] text-muted-foreground">
      {children === " " ? "\u00a0" : children}
    </p>
  )
}

/**
 * One block's cell. A block inside a container region (a cautionary note, the promo card)
 * keeps that region's small print and its rule, so the aside still looks like an aside in both
 * columns; only the first row of the region carries the region's own leading.
 */
function Cell({
  section,
  first,
  tight,
  children,
}: {
  section: Section
  first: boolean
  /** A list item after the first: the list's own leading, not a new list's. */
  tight: boolean
  children: ReactNode
}) {
  const spacing = tight ? "[&>ul]:mt-[0.4em]" : undefined
  if (section.container === null)
    return <div className={spacing}>{children}</div>
  return (
    <div
      className={cn("document-container", !first && "mt-0", spacing)}
      data-kind={section.container.kind}
    >
      {children}
    </div>
  )
}

/**
 * The rows of one section. A list is one block, but its items are what the corrections land
 * on, so each item gets a row of its own: a bullet then sits beside its own correction rather
 * than beside whatever the bullet above pushed down.
 */
function rows(
  section: Section
): { group: Group; first: boolean; tight: boolean }[] {
  const out: { group: Group; first: boolean; tight: boolean }[] = []
  section.groups.forEach((group, i) => {
    if (group.type !== "list") {
      out.push({ group, first: i === 0, tight: false })
      return
    }
    for (const [j, line] of group.lines.entries())
      out.push({
        group: { type: "list", lines: [line] },
        first: i === 0 && j === 0,
        tight: j > 0,
      })
  })
  return out
}

/** The gutter has no text of its own, so it borrows the leading of the block it labels: the
 * ids sit on the row's first line rather than at the top of its box. */
function lead(
  group: Group,
  section: Section,
  first: boolean,
  tight: boolean
): string {
  if (tight) return "mt-[0.4em]"
  if (section.container !== null) return first ? "mt-[1.6em]" : "mt-0"
  if (group.type === "heading")
    return group.level <= 1 ? "mt-0" : "mt-[2em] pt-[0.1em]"
  return group.type === "list" ? "mt-[0.8em]" : "mt-[1em]"
}

/** The claims rewritten inside one block, in the order they appear. */
function rewrittenIn(
  group: Group,
  annotations: Annotations,
  rewrites: Record<string, string>
): string[] {
  const [start, end] = blockRange(group)
  const ids = annotations.marks
    .filter(
      (mark) =>
        mark.span === 0 &&
        rewrites[mark.id] !== undefined &&
        mark.start < end &&
        mark.end > start
    )
    .map((mark) => mark.id)
  return [...new Set(ids)]
}
