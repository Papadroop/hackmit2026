/**
 * The analysis screen's four sections, the dividers in the case file (design-plan.md, "The
 * analysis screen"). Each is part of the address, so a section can be linked to, the back
 * button walks them, and a reload during the demo keeps the one that was open.
 *
 * There is no events section: the raw log is a developer's tool, not one of the file's
 * dividers. It is still served at `GET /api/analyses/<id>/log`.
 */
export const ANALYSIS_SECTIONS = [
  "claims",
  "omissions",
  "corrected",
  "verdict",
] as const

export type AnalysisSection = (typeof ANALYSIS_SECTIONS)[number]

/** The section a bare /a/<id> opens: the document with its claims, which is the screen's job. */
export const DEFAULT_SECTION: AnalysisSection = "claims"

/** Divider labels, in the tool's voice. "Corrected version" is what the reader asked for, not
 * "honest version", which was the toggle's name when it was a layer over the document. */
export const SECTION_LABELS: Record<AnalysisSection, string> = {
  claims: "Claims",
  omissions: "Omissions",
  corrected: "Corrected version",
  verdict: "Verdict",
}

export function isAnalysisSection(value: unknown): value is AnalysisSection {
  return (
    typeof value === "string" &&
    (ANALYSIS_SECTIONS as readonly string[]).includes(value)
  )
}
