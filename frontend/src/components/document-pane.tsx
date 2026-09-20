import {
  Fragment,
  memo,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type Ref,
} from "react"

import type {
  Document as ContractDocument,
  LanguageSignal,
  Omission,
  Verdict,
} from "@contract"

import { planRewrite, type DiffOp } from "@/lib/diff"
import { placeGutterLabels } from "@/lib/document-dom"
import { markVars } from "@/lib/encoding"
import { describeSignal, strongestPolarity } from "@/lib/language"
import {
  markKey,
  segmentRange,
  type Group,
  type Line,
  type Mark,
  type Section,
} from "@/lib/document-layout"
import { cn } from "@/lib/utils"
import type { AnchoredClaim } from "@/state/annotations"

/**
 * The document pane (roadmap steps 4 and 8): the text as a sheet of paper on the desk, with
 * every claim span highlighted where it sits and its id in the margin, and the Language
 * layer's word-level marks under the words they concern. The text is rendered from the
 * layout in document-layout.ts, so a highlight is a run of segments inside a line; clicks and
 * keys are handled once at the sheet by delegation. Whatever is passed as `before` (the
 * omission cards) sits on the desk above the sheet and scrolls with it. In the honest
 * version (step 9) each claim's primary span becomes a redline of its rewrite, and what the
 * document omits is inserted at the end.
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
  before?: ReactNode
  /** The honest version: rewrites by claim id, drawn as redlines when `honest` is on. */
  honest: boolean
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
  before,
  honest,
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
  }, [sections, marks, honest, rewrites, omissions])

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
      {before}
      <article
        ref={sheetRef}
        className="relative mx-auto my-4 w-full max-w-[47rem] border bg-paper py-8 pr-5 pl-11 sm:my-8 sm:py-10 sm:pr-10 sm:pl-[4.5rem]"
        aria-label={doc?.title ?? "Document"}
        data-honest={honest || undefined}
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
                    {section.groups.map((g) =>
                      renderGroup(
                        g,
                        doc.text,
                        marks,
                        languageMarks,
                        verdicts,
                        signals,
                        honest ? rewrites : NO_REWRITES,
                        selectedId
                      )
                    )}
                  </Fragment>
                ) : (
                  <section
                    key={i}
                    className="document-container"
                    data-kind={section.container.kind}
                    aria-label={section.container.label ?? undefined}
                  >
                    {section.groups.map((g) =>
                      renderGroup(
                        g,
                        doc.text,
                        marks,
                        languageMarks,
                        verdicts,
                        signals,
                        honest ? rewrites : NO_REWRITES,
                        selectedId
                      )
                    )}
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

function renderGroup(
  group: Group,
  text: string,
  marks: Mark[],
  languageMarks: Mark[],
  verdicts: Record<string, Verdict>,
  signals: Record<string, LanguageSignal>,
  rewrites: Record<string, string>,
  selectedId: string | null
) {
  switch (group.type) {
    case "heading": {
      const key = group.line.start
      if (group.level <= 1) {
        return (
          <h1 key={key} className="document-title">
            <LineText
              text={text}
              line={group.line}
              marks={marks}
              languageMarks={languageMarks}
              verdicts={verdicts}
              signals={signals}
              rewrites={rewrites}
              selectedId={selectedId}
            />
          </h1>
        )
      }
      const Tag = group.level === 2 ? "h2" : group.level === 3 ? "h3" : "h4"
      return (
        <Tag
          key={key}
          className="document-heading"
          data-level={Math.min(group.level, 4)}
        >
          <LineText
            text={text}
            line={group.line}
            marks={marks}
            languageMarks={languageMarks}
            verdicts={verdicts}
            signals={signals}
            rewrites={rewrites}
            selectedId={selectedId}
          />
        </Tag>
      )
    }
    case "list":
      return (
        <ul key={group.lines[0].start} className="document-list">
          {group.lines.map((line) => (
            <li key={line.start}>
              <LineText
                text={text}
                line={line}
                marks={marks}
                languageMarks={languageMarks}
                verdicts={verdicts}
                signals={signals}
                rewrites={rewrites}
                selectedId={selectedId}
              />
            </li>
          ))}
        </ul>
      )
    case "paragraph": {
      const prominence = group.lines[0].prominence
      return (
        <p
          key={group.lines[0].start}
          className="document-paragraph"
          data-prominence={
            prominence !== null && prominence >= 1 ? "headline" : undefined
          }
        >
          {group.lines.map((line, i) => (
            <Fragment key={line.start}>
              {i > 0 && <br />}
              <LineText
                text={text}
                line={line}
                marks={marks}
                languageMarks={languageMarks}
                verdicts={verdicts}
                signals={signals}
                rewrites={rewrites}
                selectedId={selectedId}
              />
            </Fragment>
          ))}
        </p>
      )
    }
  }
}

function LineText({
  text,
  line,
  marks,
  languageMarks,
  verdicts,
  signals,
  rewrites,
  selectedId,
}: {
  text: string
  line: Line
  marks: Mark[]
  languageMarks: Mark[]
  verdicts: Record<string, Verdict>
  signals: Record<string, LanguageSignal>
  rewrites: Record<string, string>
  selectedId: string | null
}) {
  // Two levels: the line is cut by claim marks, and each piece by language marks, so a claim
  // highlight stays one element (one ring, one hover) and a word-level mark that straddles a
  // claim boundary is simply drawn in two pieces.
  const segments = segmentRange(line.start, line.end, marks)
  return segments.map((segment) => {
    const inner =
      languageMarks.length === 0 ? (
        text.slice(segment.start, segment.end)
      ) : (
        <LanguageText
          text={text}
          start={segment.start}
          end={segment.end}
          marks={languageMarks}
          signals={signals}
        />
      )
    if (segment.marks.length === 0)
      return <Fragment key={segment.start}>{inner}</Fragment>
    // The most specific claim (shortest span) is the click target when claims nest.
    const claim = segment.marks[segment.marks.length - 1]
    const first = segment.start === claim.start
    const verdict = verdicts[claim.id]
    // The honest version: the outermost rewritten claim whose primary span covers this
    // piece has it struck through, and its rewrite follows the last piece. A piece that is
    // the whole span may instead be shown as a word-level correction.
    const rewritten = segment.marks.find(
      (m) => m.span === 0 && rewrites[m.id] !== undefined
    )
    let content = inner
    if (rewritten !== undefined) {
      const rewrite = withoutDoubledStop(
        rewrites[rewritten.id],
        text.charAt(rewritten.end)
      )
      const whole =
        segment.start === rewritten.start && segment.end === rewritten.end
      const plan = whole
        ? planRewrite(text.slice(segment.start, segment.end), rewrite)
        : ({ mode: "block" } as const)
      content =
        plan.mode === "words" ? (
          <DiffText ops={plan.ops} />
        ) : (
          <>
            <del className="honest-del">{inner}</del>
            {segment.end === rewritten.end && (
              <>
                {" "}
                <ins className="honest-ins">{rewrite}</ins>
              </>
            )}
          </>
        )
    }
    return (
      <mark
        key={segment.start}
        className="claim-mark"
        data-claim={claim.id}
        data-verdict={verdict?.category}
        style={markVars(verdict)}
        data-anchor={first ? markKey(claim) : undefined}
        data-primary={first && claim.span === 0 ? claim.id : undefined}
        data-selected={
          segment.marks.some((m) => m.id === selectedId) || undefined
        }
        tabIndex={first ? 0 : undefined}
        role={first ? "button" : undefined}
        aria-pressed={first ? claim.id === selectedId : undefined}
      >
        {content}
      </mark>
    )
  })
}

/** A rewrite is a sentence, a span often is not: when the document's own full stop follows
 * the span, the rewrite's is dropped so the redline does not read "solutions.. As". */
function withoutDoubledStop(rewrite: string, next: string): string {
  const last = rewrite.trimEnd().slice(-1)
  return last !== "" && last === next && ".!?".includes(last)
    ? rewrite.trimEnd().slice(0, -1)
    : rewrite
}

function DiffText({ ops }: { ops: DiffOp[] }) {
  return ops.map((op, i) => (
    <Fragment key={i}>
      {i > 0 && " "}
      {op.type === "equal" ? (
        op.text
      ) : op.type === "delete" ? (
        <del className="honest-del">{op.text}</del>
      ) : (
        <ins className="honest-ins">{op.text}</ins>
      )}
    </Fragment>
  ))
}

function LanguageText({
  text,
  start,
  end,
  marks,
  signals,
}: {
  text: string
  start: number
  end: number
  marks: Mark[]
  signals: Record<string, LanguageSignal>
}) {
  return segmentRange(start, end, marks).map((segment) => {
    const slice = text.slice(segment.start, segment.end)
    if (segment.marks.length === 0)
      return <Fragment key={segment.start}>{slice}</Fragment>
    // A word can carry several signals: styled as the most notable, described by all.
    const found = segment.marks
      .map((m) => signals[m.id])
      .filter((s): s is LanguageSignal => s !== undefined)
    const first = segment.marks.find((m) => m.start === segment.start)
    return (
      <span
        key={segment.start}
        className="language-mark"
        data-polarity={
          strongestPolarity(found.map((s) => s.polarity)) ?? "flag"
        }
        data-signal={segment.marks.map((m) => m.id).join(" ")}
        data-anchor={first ? markKey(first) : undefined}
        title={found.map(describeSignal).join("\n")}
      >
        {slice}
      </span>
    )
  })
}
