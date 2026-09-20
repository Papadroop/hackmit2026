const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
})
const numberFormat = new Intl.NumberFormat("en-GB")
const relativeFormat = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" })

/** "19 Sep 2026" from an ISO date or date-time. Unparseable input is returned as is. */
export function formatDate(iso: string): string {
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(date.getTime()) ? iso : dateFormat.format(date)
}

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

/** "24 s" or "1 min 5 s" from milliseconds. */
export function formatDuration(ms: number): string {
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds} s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`
}

/** "just now", "3 minutes ago", "yesterday". */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const seconds = Math.round((then - now) / 1000)
  if (Math.abs(seconds) < 45) return "just now"
  if (Math.abs(seconds) < 3600)
    return relativeFormat.format(Math.round(seconds / 60), "minute")
  if (Math.abs(seconds) < 86400)
    return relativeFormat.format(Math.round(seconds / 3600), "hour")
  return relativeFormat.format(Math.round(seconds / 86400), "day")
}

/** The contract's TextType, in the tool's words. */
export const TEXT_TYPE_LABELS: Record<string, string> = {
  label: "Product label",
  policy: "Policy page",
  claim: "Claim",
  press_release: "Press release",
  web_page: "Web page",
  report: "Report",
}

/** The contract's ClaimType, in the tool's words. */
export const CLAIM_TYPE_LABELS: Record<string, string> = {
  factual: "Factual claim",
  commitment: "Commitment",
  comparative: "Comparative claim",
  vague_attribute: "Vague attribute",
  certification: "Certification",
}

/** The contract's Scope, in the tool's words. */
export const SCOPE_LABELS: Record<string, string> = {
  product: "products",
  packaging: "packaging",
  operations: "operations",
  supply_chain: "the supply chain",
  company: "the whole company",
  other: "other scope",
}

/** Where a claim sits on the page, from its region's prominence (contract §3). */
export function describeProminence(
  prominence: number | null | undefined
): string | null {
  if (typeof prominence !== "number") return null
  if (prominence >= 1) return "headline"
  if (prominence >= 0.5) return "body text"
  return "small print"
}
