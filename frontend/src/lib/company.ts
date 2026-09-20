/**
 * Words and URLs for the company view (`GET /api/company/{name}`, backend/auditor/company.py;
 * contract §4 `CompanyView`). The shapes come from the contract itself, so a change to the
 * schema breaks this build rather than the demo.
 *
 * Nothing here recomputes a number. The company's headline is a weighted Lehmer mean over its
 * documents' headlines, and the endpoint reports every document's `share` of the result, so the
 * page's job is to show the arithmetic it was handed. That is why a document row carries its
 * share: a company number that cannot be traced back to the page that caused it is the thing
 * this view exists not to be.
 */

import type { CompanyView, TrendDirection } from "@contract"

export type { CompanyView, TrendDirection }
export type CompanyDocument = CompanyView["documents"][number]
export type CompanyTrend = CompanyView["trend"]
export type CompanyIssue = CompanyView["top_issues"][number]
export type CompanyCredit = CompanyView["credit"][number]

/** Matches `company_slug` in backend/auditor/company.py: `Ørsted A/S` is `orsted-a-s`. The two
 * have to agree, or a link from this app would not find its own company. */
const TRANSLITERATE: Record<string, string> = {
  ø: "o",
  Ø: "O",
  æ: "ae",
  Æ: "ae",
  å: "a",
  Å: "A",
  đ: "d",
  Đ: "D",
  ł: "l",
  Ł: "L",
  ß: "ss",
  þ: "th",
  ð: "d",
}

export function companySlug(name: string): string {
  const swapped = [...name]
    .map((character) => TRANSLITERATE[character] ?? character)
    .join("")
  return swapped
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
}

/** How the trend reads in the tool's voice. These are problem scores, so a rising line is the
 * company getting worse, and the words say so rather than saying "up". */
export const TREND_LABELS: Record<TrendDirection, string> = {
  improving: "Improving",
  worsening: "Getting worse",
  steady: "Holding steady",
  undetermined: "Not enough to say",
}

/**
 * Where a document's date came from, when that is worth saying. Only an archived capture is:
 * `retrieved` is the default and adds nothing, and it would be a false claim on a document
 * whose run lost its `archive_url` on the way in — the date would then be the capture's while
 * the sentence said it was the fetch's.
 */
export function describeDateBasis(
  basis: string | null | undefined
): string | null {
  return basis === "archive" ? "dated from an archived capture" : null
}

/** "+0.18": a change in a problem score always carries its sign, because the sign is the
 * message. A true minus sign, not a hyphen, so it lines up in tabular figures. */
export function formatChange(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : ""
  return `${sign}${Math.abs(value).toFixed(2)}`
}
