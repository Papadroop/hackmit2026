/**
 * The verdict encoding (design-plan.md "Verdict scale", design-doc D7). Hue is the category,
 * highlight alpha is the confidence, underline style is the second channel so the category
 * survives greyscale and colour-blindness. The hues and underline styles live in index.css
 * under `[data-verdict=...]`; this module owns the numbers.
 */
import type { CSSProperties } from "react"

import type { Verdict, VerdictCategory } from "@contract"

/** Worst first: the order the interface lists categories in. */
export const VERDICT_ORDER: readonly VerdictCategory[] = [
  "contradicted",
  "misleading_by_framing",
  "unsubstantiated",
  "supported",
]

export const VERDICT_LABELS: Record<VerdictCategory, string> = {
  contradicted: "Contradicted",
  misleading_by_framing: "Misleading by framing",
  unsubstantiated: "Unsubstantiated",
  supported: "Supported",
}

/** The seven sins plus greenrinsing (contract `Tag`), in the tool's words. */
export const TAG_LABELS: Record<string, string> = {
  hidden_trade_off: "Hidden trade-off",
  no_proof: "No proof",
  vagueness: "Vagueness",
  irrelevance: "Irrelevance",
  lesser_of_two_evils: "Lesser of two evils",
  fibbing: "Fibbing",
  false_labels: "False labels",
  greenrinsing: "Greenrinsing",
}

export function isVerdictCategory(value: unknown): value is VerdictCategory {
  return (
    typeof value === "string" &&
    (VERDICT_ORDER as readonly string[]).includes(value)
  )
}

const clamp01 = (n: number) => Math.min(1, Math.max(0, n))

/** Fill alpha of a highlight: 0.04 at no confidence, 0.34 at full. A pending claim sits at 0.15
 * in Graphite, so a low-confidence verdict is a hue barely stronger than "not decided". */
export function fillAlpha(confidence: number): number {
  return 0.04 + 0.3 * clamp01(confidence)
}

/** Underline alpha: 0.3 at no confidence, 1 at full. The line carries the category, so it
 * stays visible even when the fill is faint. */
export function lineAlpha(confidence: number): number {
  return 0.3 + 0.7 * clamp01(confidence)
}

/** Custom properties for a mark carrying a verdict; undefined leaves the pending style. */
export function markVars(
  verdict: Pick<Verdict, "confidence"> | null | undefined
): CSSProperties | undefined {
  if (!verdict) return undefined
  return {
    "--mark-alpha": fillAlpha(verdict.confidence).toFixed(3),
    "--mark-line-alpha": lineAlpha(verdict.confidence).toFixed(3),
  } as CSSProperties
}

/** "0.85": two decimals, as the contract's scores are written. */
export function formatScore(value: number): string {
  return clamp01(value).toFixed(2)
}

export function countVerdicts(
  verdicts: Record<string, Verdict>
): Record<VerdictCategory, number> {
  const counts: Record<VerdictCategory, number> = {
    contradicted: 0,
    misleading_by_framing: 0,
    unsubstantiated: 0,
    supported: 0,
  }
  for (const verdict of Object.values(verdicts)) counts[verdict.category] += 1
  return counts
}
