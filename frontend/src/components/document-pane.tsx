import {
  Fragment,
  memo,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type Ref,
} from "react"

import type {
  Document as ContractDocument,
  LanguageSignal,
  Omission,
  Verdict,
} from "@contract"

import { DocumentBlock } from "@/components/document-blocks"
import { placeGutterLabels } from "@/lib/document-dom"
import { blockRange, type Mark, type Section } from "@/lib/document-layout"
import { cn } from "@/lib/utils"
import type { AnchoredClaim } from "@/state/annotations"

/**
 * The document pane (roadmap steps 4 and 8): the text as a sheet of paper on the desk, with
 * every claim span highlighted where it sits and its id in the margin, and the Language
 * layer's word-level marks under the words they concern. The text is rendered from the
 * layout in document-layout.ts, so a highlight is a run of segments inside a line; clicks and
 * keys are handled once at the sheet by delegation.
 *
 * The same pane draws the corrected version (step 9, design-doc D6's honest version): each
 * claim's primary span becomes a redline of its rewrite and what the document omits is
 * inserted at the end. `redline` off drops the struck words, which leaves the corrected text
 * as it would read — the same sheet, with the tool's wording in italic where the document's
 * own could not stand.
 */
type Props = {
  ref?: Ref<HTMLDivElement>
  doc: ContractDocument | null
  sections: Section[]
  claims: AnchoredClaim[]
  /** Claim marks, sorted by start then longest first. */
  marks: Mark[]
  /** Language marks, sorted the same way; drawn inside or between claim highlights. */
  languageMarks: Mark[]
  /** Verdicts by claim id: sets each highlight's hue, alpha and underline. */
  verdicts: Record<string, Verdict>
  /** Signals by id: sets each language mark's polarity and tooltip. */
  signals: Record<string, LanguageSignal>
  /** The corrected version: rewrites by claim id, drawn where `honest` is on. */
  honest: boolean
  /** With the struck words (a redline), or without them (the corrected text as it reads). */
  redline?: boolean
  rewrites: Record<string, string>
  omissions: Omission[]
  onShowOmission: (id: string) => void
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** Shown in place of the text while there is no document. */
  placeholder: string
  className?: string
}

export const DocumentPane = memo(function DocumentPane({
  ref,
  doc,
  sections,
  claims,
  marks,
  languageMarks,
  verdicts,
  signals,
  honest,
  redline = true,
  rewrites,
  omissions,
  onShowOmission,
  selectedId,
  onSelect,
  placeholder,
  className,
}: Props) {
  const sheetRef = useRef<HTMLElement>(null)

  // Margin labels sit beside the first line of each claim's primary span. Geometry is measured
  // after layout and written straight to the label elements; React owns the elements, the
  // effect owns their positions. Re-measured when the text, the marks or the sheet's size change.
  useLayoutEffect(() => {
    const sheet = sheetRef.current
    if (sheet === null) return
    const place = () => placeGutterLabels(sheet)
    place()
    const observer = new ResizeObserver(place)
    observer.observe(sheet)
    void globalThis.document.fonts?.ready.then(place)
    return () => observer.disconnect()
  }, [sections, marks, honest, redline, rewrites, omissions])

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    const selection = window.getSelection()
    if (selection !== null && !selection.isCollapsed) return // the reader is selecting text
    const insert = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-omission-text]"
    )
    if (insert !== null) {
      onShowOmission(insert.dataset.omissionText ?? "")
      return
    }
    const target = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-claim]"
    )
    if (target === null) return
    const id = target.dataset.claim ?? null
    onSelect(id === selectedId ? null : id)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return
    const target = (event.target as HTMLElement).closest<HTMLElement>(
      "[data-claim][tabindex]"
    )
    if (target === null) return
    event.preventDefault()
    const id = target.dataset.claim ?? null
    onSelect(id === selectedId ? null : id)
  }

  return (
    <div ref={ref} className={cn("@container h-full overflow-auto", className)}>
      <article
        ref={sheetRef}
        className="relative mx-auto my-4 w-full max-w-[47rem] border bg-paper py-8 pr-5 pl-11 sm:my-8 sm:py-10 sm:pr-10 sm:pl-[4.5rem]"
        aria-label={doc?.title ?? "Document"}
        data-honest={honest ? (redline ? "redline" : "clean") : undefined}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        {doc === null ? (
          <p className="document text-graphite">{placeholder}</p>
        ) : (
          <>
            <div className="document max-w-[68ch]">
              {sections.map((section, i) =>
                section.container === null ? (
                  <Fragment key={i}>
                    {section.groups.map((g) => (
                      <DocumentBlock
                        key={blockRange(g)[0]}
                        group={g}
                        text={doc.text}
                        marks={marks}
                        languageMarks={languageMarks}
                        verdicts={verdicts}
                        signals={signals}
                        rewrites={honest ? rewrites : NO_REWRITES}
                        redline={redline}
                        selectedId={selectedId}
                      />
                    ))}
                  </Fragment>
                ) : (
                  <section
                    key={i}
                    className="document-container"
                    data-kind={section.container.kind}
                    aria-label={section.container.label ?? undefined}
                  >
                    {section.groups.map((g) => (
                      <DocumentBlock
                        key={blockRange(g)[0]}
                        group={g}
                        text={doc.text}
                        marks={marks}
                        languageMarks={languageMarks}
                        verdicts={verdicts}
                        signals={signals}
                        rewrites={honest ? rewrites : NO_REWRITES}
                        redline={redline}
                        selectedId={selectedId}
                      />
                    ))}
                  </section>
                )
              )}
              {honest &&
                omissions.map((omission) =>
                  omission.complete_text === undefined ? null : (
                    <p
                      key={omission.id}
                      className="document-paragraph document-insert"
                      data-omission-text={omission.id}
                      title={`Not mentioned: ${omission.topic}`}
                    >
                      <ins className="honest-ins" data-primary={omission.id}>
                        {omission.complete_text}
                      </ins>
                    </p>
                  )
                )}
            </div>
            {honest &&
              omissions.map((omission) =>
                omission.complete_text === undefined ? null : (
                  <button
                    key={omission.id}
                    type="button"
                    tabIndex={-1}
                    aria-hidden="true"
                    className="document-gutter-label"
                    data-label-for={omission.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      onShowOmission(omission.id)
                    }}
                  >
                    {omission.id}
                  </button>
                )
              )}
            {claims.map(({ claim, spans, verdict }) =>
              spans[0] === null ? null : (
                <button
                  key={claim.id}
                  type="button"
                  tabIndex={-1}
                  aria-hidden="true"
                  className="document-gutter-label"
                  data-label-for={claim.id}
                  data-verdict={verdict?.category}
                  data-selected={claim.id === selectedId || undefined}
                  onClick={(event) => {
                    event.stopPropagation()
                    onSelect(claim.id === selectedId ? null : claim.id)
                  }}
                >
                  {claim.id}
                </button>
              )
            )}
          </>
        )}
      </article>
    </div>
  )
})

const NO_REWRITES: Record<string, string> = {}
