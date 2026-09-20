/**
 * Words and orderings for what the claim panel shows below the verdict (contract §4 and §8,
 * design-doc D5 and D6): the four dimensions, the evidence tiers, kinds, verification methods
 * and relations, the debate roles, and how a claim's evidence list is assembled.
 */
import type {
  Argument,
  Dimension,
  DimensionScore,
  EvidenceItem,
  Relation,
  Summary,
  Verdict,
} from "@contract"

import { formatDate } from "@/lib/format"

export const DIMENSION_ORDER: readonly Dimension[] = [
  "clarity",
  "support",
  "materiality",
  "consistency",
]

export const DIMENSION_LABELS: Record<Dimension, string> = {
  clarity: "Clarity",
  support: "Support",
  materiality: "Materiality",
  consistency: "Consistency",
}

/** The question each dimension answers (design-doc D6). A high score is a problem. */
export const DIMENSION_QUESTIONS: Record<Dimension, string> = {
  clarity: "Is the claim specific and checkable, or vague and hedged?",
  support: "Does evidence contradict it, fail to back it, or support it?",
  materiality: "How much of the real environmental impact does it address?",
  consistency:
    "Does it match the company's other statements and its past ones?",
}

/** The document profile (design-doc D6): the four claim dimensions plus Completeness. */
export type ProfileDimension = keyof Summary["dimensions"]

export const PROFILE_ORDER: readonly ProfileDimension[] = [
  "clarity",
  "support",
  "materiality",
  "consistency",
  "completeness",
]

export const PROFILE_LABELS: Record<ProfileDimension, string> = {
  ...DIMENSION_LABELS,
  completeness: "Completeness",
}

export const PROFILE_QUESTIONS: Record<ProfileDimension, string> = {
  ...DIMENSION_QUESTIONS,
  completeness: "Are material impacts addressed at all?",
}

/** The reliability tiers (design-doc D5), tier 1 being the most reliable. */
export const TIER_LABELS: Record<number, string> = {
  1: "regulator ruling, court judgment or law",
  2: "audited or assured filing, or government data",
  3: "independent dataset or standard",
  4: "news",
  5: "the company's own material",
}

export const KIND_LABELS: Record<string, string> = {
  ruling: "Ruling",
  law: "Law",
  filing: "Filing",
  report: "Report",
  dataset: "Dataset",
  standard: "Standard",
  company_page: "Company page",
  press_release: "Press release",
  news: "News",
  archive: "Archived page",
  computation: "Computation",
  other: "Source",
}

/** How the quote was checked (contract `Verification`), as a clause after the kind. */
export const VERIFICATION_LABELS: Record<string, string> = {
  fetched_exact: "quote matched against the fetched source",
  fetched_by_eye: "quote read from the fetched source",
  second_party_fetch: "quote confirmed by a second, separate fetch",
  computed: "recomputed from other evidence items",
  unverified: "not verified, so no quote is shown",
}

/** Which evaluator found the item, from `EvidenceItem.stage`. */
export const STAGE_ACTORS: Record<string, string> = {
  language: "the Linguistic evaluator",
  substantiate: "the Substantiation evaluator",
  verify: "the External verification evaluator",
  consistency: "the Self-consistency evaluator",
  omissions: "the omissions search",
}

/**
 * A claim's relation to an evidence item, from the claim's point of view (contract §4), plus
 * `cited` for an item a score, an argument or the verdict names without a direct link.
 */
export type ClaimRelation = Relation | "cited"

/** Most consequential first: what an analyst defending the finding reads first. */
export const RELATION_ORDER: readonly ClaimRelation[] = [
  "contradicts",
  "contradicts_framing",
  "supports",
  "criteria",
  "precedent",
  "context",
  "cited",
]

export const RELATION_LABELS: Record<ClaimRelation, string> = {
  contradicts: "Contradicts",
  contradicts_framing: "Contradicts the framing",
  supports: "Supports",
  criteria: "Criteria",
  precedent: "Precedent",
  context: "Context",
  cited: "Cited",
}

export const RELATION_NOTES: Record<ClaimRelation, string> = {
  contradicts: "The literal content of the claim is contradicted.",
  contradicts_framing:
    "The literal content stands, but the impression it gives does not.",
  supports: "The literal content of the claim is supported.",
  criteria: "A rule the claim is measured against.",
  precedent: "A ruling on similar wording.",
  context: "Background, or how much of the impact the claim covers.",
  cited: "Named by a score, an argument or the verdict, without a direct link.",
}

export const ROLE_LABELS: Record<Argument["role"], string> = {
  prosecutor: "Prosecutor",
  defence: "Defence",
  judge: "Judge",
}

export type ClaimEvidence = {
  item: EvidenceItem
  /** The item's relations to the claim, most consequential first; at least one. */
  relations: ClaimRelation[]
}

/** Every evidence id a claim's scores, arguments and verdict name. */
export function citedIds(
  scores: Iterable<DimensionScore>,
  turns: Iterable<Argument>,
  verdict: Verdict | null
): Set<string> {
  const ids = new Set<string>()
  for (const score of scores)
    for (const id of score.evidence_ids ?? []) ids.add(id)
  for (const turn of turns)
    for (const id of turn.evidence_ids ?? []) ids.add(id)
  for (const id of verdict?.evidence_ids ?? []) ids.add(id)
  return ids
}

/**
 * The evidence list for one claim: every item linked to the claim, with all of its relations
 * to it, then every cited item that is not linked. Ordered by the strongest relation, then by
 * tier (most reliable first), then by arrival.
 */
export function evidenceForClaim(
  claimId: string,
  evidence: readonly EvidenceItem[],
  cited: ReadonlySet<string> = new Set()
): ClaimEvidence[] {
  const rank = (relation: string) => {
    const at = RELATION_ORDER.indexOf(relation as ClaimRelation)
    return at < 0 ? RELATION_ORDER.length : at
  }
  const list: ClaimEvidence[] = []
  for (const item of evidence) {
    const relations = [
      ...new Set(
        item.links
          .filter((link) => link.target === claimId)
          .map((link) => link.relation as ClaimRelation)
      ),
    ].sort((a, b) => rank(a) - rank(b))
    if (relations.length === 0 && cited.has(item.id)) relations.push("cited")
    if (relations.length > 0) list.push({ item, relations })
  }
  return list
    .map((entry, order) => ({ entry, order }))
    .sort(
      (a, b) =>
        rank(a.entry.relations[0]) - rank(b.entry.relations[0]) ||
        a.entry.item.tier - b.entry.item.tier ||
        a.order - b.order
    )
    .map(({ entry }) => entry)
}

/** "Contradicts the framing, supports": the relation words as one phrase. */
export function describeRelations(relations: readonly ClaimRelation[]): string {
  return relations
    .map((relation, i) => {
      const label = RELATION_LABELS[relation] ?? relation
      return i === 0 ? label : label.toLowerCase()
    })
    .join(", ")
}

/** "sec.gov" from a url, for the link text; the url itself if it does not parse. */
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** A source date is an ISO date or free text ("2026-03", "applies from 2026-09-27"); only a
 * full date is reformatted, so a month is not shown as its first day. */
export function describeSourceDate(date: string): string {
  return ISO_DATE.test(date) ? formatDate(date) : date
}

/** "Filing. Quote matched against the fetched source. Retrieved 19 Sep 2026 by the
 * Self-consistency evaluator." One sentence per fact, in the tool's voice. */
export function describeProvenance(item: EvidenceItem): string {
  const kind = KIND_LABELS[item.kind] ?? KIND_LABELS.other
  const how =
    VERIFICATION_LABELS[item.verification] ?? VERIFICATION_LABELS.unverified
  const actor = item.stage ? STAGE_ACTORS[item.stage] : undefined
  const when = describeSourceDate(item.retrieved)
  const retrieved = actor
    ? `Retrieved ${when} by ${actor}.`
    : `Retrieved ${when}.`
  return `${kind}. ${capitalise(how)}. ${retrieved}`
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
