/**
 * From the folded document, claims and signals to what the document pane draws: the text's
 * layout, every span anchored to UTF-16 offsets, and the marks of each layer that is switched
 * on (claim marks and language marks stay separate lists, because the pane cuts the text by
 * claims first and by language marks inside each piece, so a claim stays one element).
 * Memoised so that events which change none of the inputs do not touch the pane.
 */
import { useMemo } from "react"

import type {
  Claim,
  Document as ContractDocument,
  LanguageSignal,
  Verdict,
} from "@contract"

import {
  anchorSpan,
  makeOffsetIndex,
  type Anchored,
  type OffsetIndex,
} from "@/lib/anchor"
import {
  layoutDocument,
  paragraphAt,
  type Mark,
  type Section,
} from "@/lib/document-layout"

/** Which layers the document pane draws (roadmap step 8). */
export type Layers = { claims: boolean; language: boolean; omissions: boolean }

export const LAYER_KEYS: readonly (keyof Layers)[] = [
  "claims",
  "language",
  "omissions",
]

/** Claims and language marks are part of the live progression; omissions are opt-in so the
 * cards do not push the sheet down while the reader is in the text. */
export const DEFAULT_LAYERS: Layers = {
  claims: true,
  language: true,
  omissions: false,
}

export type AnchoredSpan = Anchored & { paragraph: string | null }

export type AnchoredClaim = {
  claim: Claim
  /** One entry per claim span, in the claim's order; null when the span could not be placed. */
  spans: (AnchoredSpan | null)[]
  /** The claim's verdict once issued. */
  verdict: Verdict | null
}

export type AnchoredSignal = {
  signal: LanguageSignal
  spans: (Anchored | null)[]
}

export type Annotations = {
  index: OffsetIndex
  sections: Section[]
  /** Claims in document order (by primary span), unplaced ones last in arrival order. */
  claims: AnchoredClaim[]
  /** Signals by id, for the pane to style and describe a language mark. */
  signals: Record<string, LanguageSignal>
  /** Claim marks, when the Claims layer is on. */
  marks: Mark[]
  /** Word-level marks, when the Language layer is on. */
  languageMarks: Mark[]
}

const EMPTY_INDEX = makeOffsetIndex("")
const NO_MARKS: Mark[] = []

export function anchorClaims(
  doc: ContractDocument,
  index: OffsetIndex,
  claims: Claim[],
  verdicts: Record<string, Verdict> = {}
): AnchoredClaim[] {
  const anchored = claims.map((claim) => ({
    claim,
    verdict: verdicts[claim.id] ?? null,
    spans: claim.spans.map((span) => {
      const at = anchorSpan(doc.text, span, index)
      return at === null
        ? null
        : { ...at, paragraph: paragraphAt(doc.regions, index, at.start) }
    }),
  }))
  const position = (c: AnchoredClaim) =>
    c.spans[0]?.start ?? Number.POSITIVE_INFINITY
  return anchored
    .map((c, order) => ({ c, order }))
    .sort((a, b) => position(a.c) - position(b.c) || a.order - b.order)
    .map(({ c }) => c)
}

export function anchorSignals(
  doc: ContractDocument,
  index: OffsetIndex,
  signals: LanguageSignal[]
): AnchoredSignal[] {
  return signals.map((signal) => ({
    signal,
    spans: signal.spans.map((span) => anchorSpan(doc.text, span, index)),
  }))
}

export function claimMarks(claims: AnchoredClaim[]): Mark[] {
  const marks: Mark[] = []
  for (const { claim, spans } of claims) {
    spans.forEach((at, span) => {
      if (at !== null)
        marks.push({
          id: claim.id,
          layer: "claim",
          span,
          start: at.start,
          end: at.end,
        })
    })
  }
  return sortMarks(marks)
}

export function languageMarks(signals: AnchoredSignal[]): Mark[] {
  const marks: Mark[] = []
  for (const { signal, spans } of signals) {
    spans.forEach((at, span) => {
      if (at !== null)
        marks.push({
          id: signal.id,
          layer: "language",
          span,
          start: at.start,
          end: at.end,
        })
    })
  }
  return sortMarks(marks)
}

/** By start, longer first: the order segmentRange expects. */
export function sortMarks(marks: Mark[]): Mark[] {
  return marks.sort((a, b) => a.start - b.start || b.end - a.end)
}

export function useAnnotations(
  doc: ContractDocument | null,
  claims: Claim[],
  verdicts: Record<string, Verdict>,
  signals: LanguageSignal[],
  layers: Layers
): Annotations {
  const index = useMemo(
    () => (doc === null ? EMPTY_INDEX : makeOffsetIndex(doc.text)),
    [doc]
  )
  const sections = useMemo(
    () => (doc === null ? [] : layoutDocument(doc.text, doc.regions, index)),
    [doc, index]
  )
  const anchored = useMemo(
    () => (doc === null ? [] : anchorClaims(doc, index, claims, verdicts)),
    [doc, index, claims, verdicts]
  )
  const anchoredSignals = useMemo(
    () => (doc === null ? [] : anchorSignals(doc, index, signals)),
    [doc, index, signals]
  )
  const byId = useMemo(
    () => Object.fromEntries(signals.map((signal) => [signal.id, signal])),
    [signals]
  )
  const ofClaims = useMemo(() => claimMarks(anchored), [anchored])
  const ofLanguage = useMemo(
    () => languageMarks(anchoredSignals),
    [anchoredSignals]
  )
  return {
    index,
    sections,
    claims: anchored,
    signals: byId,
    marks: layers.claims ? ofClaims : NO_MARKS,
    languageMarks: layers.language ? ofLanguage : NO_MARKS,
  }
}
