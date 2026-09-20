import { Fragment } from "react"

import type { LanguageSignal, Verdict } from "@contract"

import { planRewrite, type DiffOp } from "@/lib/diff"
import {
  markKey,
  segmentRange,
  type Group,
  type Line,
  type Mark,
} from "@/lib/document-layout"
import { markVars } from "@/lib/encoding"
import { describeSignal, strongestPolarity } from "@/lib/language"

/**
 * One block of the document — a heading, a list or a paragraph — with its claim highlights and
 * its word-level language marks. Kept apart from the pane because two views draw the same
 * blocks: the sheet (components/document-pane.tsx) draws them once, and the corrected version
 * draws each one twice, as published beside as the evidence allows.
 *
 * A line is cut by claim marks and each piece by language marks, so a claim highlight stays one
 * element (one ring, one hover) and a word-level mark that straddles a claim boundary is simply
 * drawn in two pieces.
 */
export type BlockProps = {
  group: Group
  text: string
  /** Claim marks, sorted by start then longest first. */
  marks: Mark[]
  /** Language marks, sorted the same way; drawn inside or between claim highlights. */
  languageMarks: Mark[]
  /** Verdicts by claim id: sets each highlight's hue, alpha and underline. */
  verdicts: Record<string, Verdict>
  /** Signals by id: sets each language mark's polarity and tooltip. */
  signals: Record<string, LanguageSignal>
  /** Rewrites by claim id; an empty map is the document as published. */
  rewrites: Record<string, string>
  /** With the struck words, or without them. */
  redline: boolean
  selectedId: string | null
}

export function DocumentBlock({
  group,
  text,
  marks,
  languageMarks,
  verdicts,
  signals,
  rewrites,
  redline,
  selectedId,
}: BlockProps) {
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
              redline={redline}
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
            redline={redline}
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
                redline={redline}
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
                redline={redline}
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
  redline,
  selectedId,
}: {
  text: string
  line: Line
  marks: Mark[]
  languageMarks: Mark[]
  verdicts: Record<string, Verdict>
  signals: Record<string, LanguageSignal>
  rewrites: Record<string, string>
  redline: boolean
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
          <DiffText ops={plan.ops} redline={redline} />
        ) : (
          <>
            {redline && <del className="honest-del">{inner}</del>}
            {segment.end === rewritten.end && (
              <>
                {redline && " "}
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

function DiffText({ ops, redline }: { ops: DiffOp[]; redline: boolean }) {
  // Without the deletions the separators have to be recounted, or a dropped word leaves a
  // double space behind it.
  const shown = redline ? ops : ops.filter((op) => op.type !== "delete")
  return shown.map((op, i) => (
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
