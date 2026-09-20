/**
 * The fold from events to contract entities (contract/CONTRACT.md §4, "the frontend's reducer
 * is a fold over the events"). Each domain event adds or replaces one entity; the result
 * mirrors the contract's Analysis object: document, claims, signals, evidence, scores,
 * arguments, verdicts, omissions and the summary.
 *
 * Payloads arrive as unknown JSON. Each one is checked for the fields a view relies on before
 * it is admitted; a malformed payload is skipped rather than allowed to break the screen, and
 * it stays visible in the events panel as received.
 */
import type {
  Argument,
  Claim,
  Dimension,
  DimensionScore,
  Document as ContractDocument,
  EvidenceItem,
  LanguageSignal,
  Omission,
  Region,
  Span,
  Summary,
  Verdict,
} from "@contract"

import { isVerdictCategory } from "@/lib/encoding"
import { PROFILE_ORDER } from "@/lib/evidence"
import { DOCUMENT_INGESTED, type Envelope } from "@/lib/events"

export const CLAIM_EXTRACTED = "claim.extracted"
export const EVIDENCE_ADDED = "evidence.added"
export const DIMENSION_SCORED = "dimension.scored"
export const ARGUMENT_MADE = "argument.made"
export const VERDICT_ISSUED = "verdict.issued"
export const SUMMARY_UPDATED = "summary.updated"
export const LANGUAGE_SIGNAL = "language.signal"
export const OMISSION_FOUND = "omission.found"

/**
 * The document summary as folded: the contract's Summary with the profile entries that were
 * well-formed, counts that may be unknown, and whether the summary stage called it final.
 */
export type SummaryState = Omit<
  Summary,
  "dimensions" | "claim_count" | "omission_count"
> & {
  dimensions: Partial<Summary["dimensions"]>
  claim_count: number | null
  omission_count: number | null
  final: boolean
}

/** One claim's dimension scores, at most one per dimension (contract §2, rule 4). */
export type ClaimScores = Partial<Record<Dimension, DimensionScore>>

export type Folded = {
  document: ContractDocument | null
  /** Claims in order of arrival; a repeated id replaces the earlier claim. */
  claims: Claim[]
  /** Language signals in order of arrival; a repeated id replaces the earlier signal. */
  signals: LanguageSignal[]
  /** Evidence items in order of arrival; a repeated id replaces the earlier item in place. */
  evidence: EvidenceItem[]
  /** Dimension scores by claim id, then by dimension; a repeat replaces (last wins). */
  scores: Record<string, ClaimScores>
  /** Prosecutor, defence and judge turns by claim id, in order of arrival. */
  arguments: Record<string, Argument[]>
  /** Verdicts by claim id; a repeated id replaces the earlier verdict (last wins). */
  verdicts: Record<string, Verdict>
  /** Omissions in order of arrival; a repeated id replaces the earlier omission. */
  omissions: Omission[]
  /** The latest document summary; provisional until one arrives with `final: true`. */
  summary: SummaryState | null
}

export const emptyFolded: Folded = {
  document: null,
  claims: [],
  signals: [],
  evidence: [],
  scores: {},
  arguments: {},
  verdicts: {},
  omissions: [],
  summary: null,
}

/** The folded entities out of a larger state object, so a fold step copies nothing else. */
export function pickFolded(state: Folded): Folded {
  return {
    document: state.document,
    claims: state.claims,
    signals: state.signals,
    evidence: state.evidence,
    scores: state.scores,
    arguments: state.arguments,
    verdicts: state.verdicts,
    omissions: state.omissions,
    summary: state.summary,
  }
}

export function foldEvent(folded: Folded, event: Envelope): Folded {
  switch (event.type) {
    case DOCUMENT_INGESTED: {
      const document = asDocument(event.payload.document)
      return document === null ? folded : { ...folded, document }
    }
    case CLAIM_EXTRACTED: {
      const claim = asClaim(event.payload.claim)
      if (claim === null) return folded
      return { ...folded, claims: replaceById(folded.claims, claim) }
    }
    case LANGUAGE_SIGNAL: {
      const signal = asSignal(event.payload.signal)
      if (signal === null) return folded
      return { ...folded, signals: replaceById(folded.signals, signal) }
    }
    case OMISSION_FOUND: {
      const omission = asOmission(event.payload.omission)
      if (omission === null) return folded
      return { ...folded, omissions: replaceById(folded.omissions, omission) }
    }
    case EVIDENCE_ADDED: {
      const item = asEvidence(event.payload.evidence)
      if (item === null) return folded
      return { ...folded, evidence: replaceById(folded.evidence, item) }
    }
    case DIMENSION_SCORED: {
      const score = asScore(event.payload.score)
      if (score === null) return folded
      return {
        ...folded,
        scores: {
          ...folded.scores,
          [score.claim_id]: {
            ...folded.scores[score.claim_id],
            [score.dimension]: score,
          },
        },
      }
    }
    case ARGUMENT_MADE: {
      const argument = asArgument(event.payload.argument)
      if (argument === null) return folded
      const turns = folded.arguments[argument.claim_id] ?? []
      return {
        ...folded,
        arguments: {
          ...folded.arguments,
          [argument.claim_id]: [...turns, argument],
        },
      }
    }
    case VERDICT_ISSUED: {
      const verdict = asVerdict(event.payload.verdict)
      if (verdict === null) return folded
      return {
        ...folded,
        verdicts: { ...folded.verdicts, [verdict.claim_id]: verdict },
      }
    }
    case SUMMARY_UPDATED: {
      const summary = asSummary(event.payload.summary, event.payload.final)
      return summary === null ? folded : { ...folded, summary }
    }
    default:
      return folded
  }
}

function replaceById<T extends { id: string }>(list: T[], item: T): T[] {
  const at = list.findIndex((x) => x.id === item.id)
  const next = [...list]
  if (at >= 0) next[at] = item
  else next.push(item)
  return next
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

const isString = (value: unknown): value is string => typeof value === "string"

const isOffset = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0

const isScore = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value)

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter(isString) : []
}

function isRegion(value: unknown): value is Region {
  return (
    isRecord(value) &&
    typeof value.kind === "string" &&
    isOffset(value.start) &&
    isOffset(value.end)
  )
}

/** Accepts a Document with at least an id, a text and a regions list (invalid regions dropped). */
export function asDocument(value: unknown): ContractDocument | null {
  if (!isRecord(value)) return null
  if (typeof value.id !== "string" || typeof value.text !== "string")
    return null
  const regions = Array.isArray(value.regions)
    ? value.regions.filter(isRegion)
    : []
  return { ...(value as unknown as ContractDocument), regions }
}

function isSpan(value: unknown): value is Span {
  return (
    isRecord(value) &&
    typeof value.text === "string" &&
    value.text !== "" &&
    isOffset(value.start) &&
    isOffset(value.end)
  )
}

/** Accepts a Claim with an id, at least one well-formed span, and the routing fields. */
export function asClaim(value: unknown): Claim | null {
  if (!isRecord(value)) return null
  if (typeof value.id !== "string" || value.id === "") return null
  if (
    !Array.isArray(value.spans) ||
    value.spans.length === 0 ||
    !value.spans.every(isSpan)
  )
    return null
  if (typeof value.type !== "string" || typeof value.scope !== "string")
    return null
  if (typeof value.attribute !== "string") return null
  return value as unknown as Claim
}

type Link = EvidenceItem["links"][number]

function isLink(value: unknown): value is Link {
  return (
    isRecord(value) &&
    typeof value.target === "string" &&
    value.target !== "" &&
    typeof value.relation === "string"
  )
}

/**
 * Accepts an EvidenceItem with an id, a named source, a tier on the 1–5 scale and at least
 * one well-formed link. Citation integrity (contract §4, design-doc D5) is enforced here
 * rather than in each view: the quote is kept only when the item says it is verified by a
 * method other than `unverified`, so no view can show an unverified quote by mistake.
 */
export function asEvidence(value: unknown): EvidenceItem | null {
  if (!isRecord(value)) return null
  if (typeof value.id !== "string" || value.id === "") return null
  if (!isRecord(value.source) || typeof value.source.name !== "string")
    return null
  const tier = value.tier
  if (!Number.isInteger(tier) || (tier as number) < 1 || (tier as number) > 5)
    return null
  const links = Array.isArray(value.links) ? value.links.filter(isLink) : []
  if (links.length === 0) return null
  const quote =
    typeof value.quote === "string" && value.quote !== ""
      ? value.quote
      : undefined
  const verification =
    typeof value.verification === "string" ? value.verification : "unverified"
  const verified =
    value.verified === true &&
    quote !== undefined &&
    verification !== "unverified"
  return {
    ...(value as unknown as EvidenceItem),
    kind: (typeof value.kind === "string"
      ? value.kind
      : "other") as EvidenceItem["kind"],
    links: links as EvidenceItem["links"],
    quote: verified ? quote : undefined,
    verified,
    verification: verification as EvidenceItem["verification"],
    derived_from: stringList(value.derived_from),
  }
}

export const DIMENSIONS: readonly Dimension[] = [
  "clarity",
  "support",
  "materiality",
  "consistency",
]

export function isDimension(value: unknown): value is Dimension {
  return (
    typeof value === "string" &&
    (DIMENSIONS as readonly string[]).includes(value)
  )
}

/** Accepts a DimensionScore with a claim id, a known dimension and numeric score and confidence. */
export function asScore(value: unknown): DimensionScore | null {
  if (!isRecord(value)) return null
  if (typeof value.claim_id !== "string" || value.claim_id === "") return null
  if (!isDimension(value.dimension)) return null
  if (!isScore(value.score) || !isScore(value.confidence)) return null
  return {
    ...(value as unknown as DimensionScore),
    basis: typeof value.basis === "string" ? value.basis : "",
    evidence_ids: stringList(value.evidence_ids),
  }
}

const ROLES: readonly Argument["role"][] = ["prosecutor", "defence", "judge"]

/** Accepts an Argument with a claim id, a known role and some text. */
export function asArgument(value: unknown): Argument | null {
  if (!isRecord(value)) return null
  if (typeof value.claim_id !== "string" || value.claim_id === "") return null
  if (!(ROLES as readonly unknown[]).includes(value.role)) return null
  if (typeof value.text !== "string" || value.text === "") return null
  return {
    ...(value as unknown as Argument),
    evidence_ids: stringList(value.evidence_ids),
  }
}

/** Accepts a Verdict with a claim id, a known category and numeric likelihood and confidence. */
export function asVerdict(value: unknown): Verdict | null {
  if (!isRecord(value)) return null
  if (typeof value.claim_id !== "string" || value.claim_id === "") return null
  if (!isVerdictCategory(value.category)) return null
  if (!isScore(value.likelihood) || !isScore(value.confidence)) return null
  const text = (field: unknown) =>
    typeof field === "string" && field !== "" ? field : undefined
  return {
    ...(value as unknown as Verdict),
    tags: stringList(value.tags) as Verdict["tags"],
    rationale: typeof value.rationale === "string" ? value.rationale : "",
    fix: text(value.fix),
    rewrite: text(value.rewrite),
    evidence_ids: stringList(value.evidence_ids),
  }
}

function asEntry(value: unknown): Summary["headline"] | null {
  if (!isRecord(value)) return null
  if (!isScore(value.score) || !isScore(value.confidence)) return null
  return { score: value.score, confidence: value.confidence }
}

function isTarget(
  value: unknown
): value is { target: string; title: string; rank?: unknown } {
  return (
    isRecord(value) &&
    typeof value.target === "string" &&
    value.target !== "" &&
    typeof value.title === "string"
  )
}

const asCount = (value: unknown): number | null =>
  Number.isInteger(value) && (value as number) >= 0 ? (value as number) : null

/**
 * Accepts a Summary with a numeric headline. Profile entries, issues and credits that are
 * malformed are dropped individually; a missing distribution counts as zeros.
 */
export function asSummary(value: unknown, final: unknown): SummaryState | null {
  if (!isRecord(value)) return null
  const headline = asEntry(value.headline)
  if (headline === null) return null
  const dimensions: SummaryState["dimensions"] = {}
  if (isRecord(value.dimensions)) {
    for (const key of PROFILE_ORDER) {
      const entry = asEntry(value.dimensions[key])
      if (entry !== null) dimensions[key] = entry
    }
  }
  const given = isRecord(value.verdict_distribution)
    ? value.verdict_distribution
    : {}
  const verdict_distribution: Summary["verdict_distribution"] = {
    supported: asCount(given.supported) ?? 0,
    unsubstantiated: asCount(given.unsubstantiated) ?? 0,
    misleading_by_framing: asCount(given.misleading_by_framing) ?? 0,
    contradicted: asCount(given.contradicted) ?? 0,
  }
  const top_issues = (Array.isArray(value.top_issues) ? value.top_issues : [])
    .filter(isTarget)
    .map((issue, i) => ({
      ...issue,
      rank: Number.isInteger(issue.rank) ? (issue.rank as number) : i + 1,
    }))
    .sort((a, b) => a.rank - b.rank)
  const credit = (Array.isArray(value.credit) ? value.credit : []).filter(
    isTarget
  )
  return {
    ...(value as unknown as Summary),
    headline,
    dimensions,
    verdict_distribution,
    top_issues,
    credit,
    claim_count: asCount(value.claim_count),
    omission_count: asCount(value.omission_count),
    narrative:
      typeof value.narrative === "string" && value.narrative !== ""
        ? value.narrative
        : undefined,
    final: final === true,
  }
}

const LEVELS: readonly LanguageSignal["level"][] = ["claim", "document"]
const POLARITIES: readonly LanguageSignal["polarity"][] = [
  "flag",
  "benign",
  "credit",
]

/** Accepts a LanguageSignal with an id, a known level and polarity, and a kind. Malformed
 * spans are dropped; a claim-level signal left without spans is kept for the panel. */
export function asSignal(value: unknown): LanguageSignal | null {
  if (!isRecord(value)) return null
  if (typeof value.id !== "string" || value.id === "") return null
  if (!(LEVELS as readonly unknown[]).includes(value.level)) return null
  if (!(POLARITIES as readonly unknown[]).includes(value.polarity)) return null
  if (typeof value.kind !== "string" || value.kind === "") return null
  return {
    ...(value as unknown as LanguageSignal),
    spans: Array.isArray(value.spans) ? value.spans.filter(isSpan) : [],
    note: typeof value.note === "string" ? value.note : "",
    claim_ids: stringList(value.claim_ids),
    strength: isScore(value.strength) ? value.strength : undefined,
  }
}

/** Accepts an Omission with an id, a topic and numeric score and confidence. */
export function asOmission(value: unknown): Omission | null {
  if (!isRecord(value)) return null
  if (typeof value.id !== "string" || value.id === "") return null
  if (typeof value.topic !== "string" || value.topic === "") return null
  if (!isScore(value.score) || !isScore(value.confidence)) return null
  const text = (field: unknown) =>
    typeof field === "string" && field !== "" ? field : undefined
  return {
    ...(value as unknown as Omission),
    why_material:
      typeof value.why_material === "string" ? value.why_material : "",
    materiality_reference: text(value.materiality_reference),
    complete_text: text(value.complete_text),
    evidence_ids: stringList(value.evidence_ids),
  }
}
