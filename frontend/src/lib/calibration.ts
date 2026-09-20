/**
 * The calibration report, and the arithmetic the page redoes for itself.
 *
 * `GET /api/calibration` serves the artifact `python -m auditor.calibration run` wrote
 * (../../backend/auditor/calibration.py): every curated precedent with the likelihood the audit
 * gave its wording when that ruling was held out of the knowledge store, and the metrics at the
 * threshold the run used. The page recomputes those metrics from the cases so the reader can
 * move the threshold and watch what it costs — the sweep the command line prints, made
 * answerable. The definitions below follow the module exactly, including that a case counts as
 * called misleading when its likelihood is *above* the threshold and not merely at it, so the
 * page and the command line can never quietly disagree.
 */

export type CaseScore = { score: number; confidence: number }

export type CalibrationCase = {
  store_id: string
  claim_text: string
  /** The regulator's disposal: upheld, upheld_in_part, not_upheld, dismissed, settled. */
  outcome: string
  company: string
  industry: string
  /** The body that decided it, named in full. */
  body: string
  claim_type: string
  /** 1 upheld, 0 decided in the advertiser's favour, null for a settlement (no finding). */
  label: number | null
  /** What the audit predicted with this ruling held out; null if the case failed to score. */
  likelihood: number | null
  category: string
  scores: Record<string, CaseScore>
  cited: string[]
  held_out: string[]
  error: string
}

export type CalibrationReport = {
  generated: string
  method: string
  dimensions: string[]
  metrics: { threshold: number; caveat: string } & Record<string, unknown>
  cases: CalibrationCase[]
}

export type Bin = {
  low: number
  high: number
  count: number
  /** Mean likelihood the audit gave this bucket. */
  predicted: number
  /** Share of the bucket a regulator actually upheld. */
  observed: number
}

export type Metrics = {
  scored: number
  labelled: number
  positives: number
  negatives: number
  unlabelled: number
  failed: number
  threshold: number
  truePositive: number
  falsePositive: number
  trueNegative: number
  falseNegative: number
  brier: number | null
  precision: number | null
  recall: number | null
  f1: number | null
  accuracy: number | null
  bins: Bin[]
}

/** The words the outcomes are written in. A settlement is a bargain, not a finding. */
export const OUTCOME_LABELS: Record<string, string> = {
  upheld: "Upheld",
  upheld_in_part: "Upheld in part",
  not_upheld: "Not upheld",
  dismissed: "Dismissed",
  settled: "Settled",
}

/** Whether the audit called this case misleading. Above the threshold, not at it. */
export function called(
  likelihood: number | null,
  threshold: number
): boolean | null {
  return likelihood === null ? null : likelihood > threshold
}

/** True when the audit and the regulator disagree; null when the case carries no finding. */
export function isMiss(
  kase: Pick<CalibrationCase, "label" | "likelihood">,
  threshold: number
): boolean | null {
  const call = called(kase.likelihood, threshold)
  if (call === null || kase.label === null) return null
  return call !== (kase.label === 1)
}

/**
 * The curve: bucket the adjudicated cases by what the audit predicted, then see how many of
 * each bucket a regulator upheld. Well calibrated means predicted close to observed. Empty
 * buckets are dropped rather than drawn as zero, because no cases is not an observation.
 */
export function binCases(
  rows: { likelihood: number; label: number }[],
  bins = 5
): Bin[] {
  const out: Bin[] = []
  for (let i = 0; i < bins; i += 1) {
    const low = i / bins
    const high = (i + 1) / bins
    const inside = rows.filter(
      (row) =>
        (row.likelihood >= low && row.likelihood < high) ||
        (i === bins - 1 && row.likelihood === 1)
    )
    if (inside.length === 0) continue
    const mean = (values: number[]) =>
      values.reduce((sum, value) => sum + value, 0) / values.length
    out.push({
      low,
      high,
      count: inside.length,
      predicted: mean(inside.map((row) => row.likelihood)),
      observed: mean(inside.map((row) => row.label)),
    })
  }
  return out
}

export function measure(
  cases: CalibrationCase[],
  threshold: number,
  bins = 5
): Metrics {
  const scored = cases.filter((k) => k.likelihood !== null)
  const labelled = scored
    .filter((k) => k.label !== null)
    .map((k) => ({
      likelihood: k.likelihood as number,
      label: k.label as number,
    }))

  let truePositive = 0
  let falsePositive = 0
  let trueNegative = 0
  let falseNegative = 0
  for (const row of labelled) {
    const call = row.likelihood > threshold
    if (row.label === 1 && call) truePositive += 1
    else if (row.label === 1) falseNegative += 1
    else if (call) falsePositive += 1
    else trueNegative += 1
  }

  const ratio = (numerator: number, denominator: number) =>
    denominator === 0 ? null : numerator / denominator
  const precision = ratio(truePositive, truePositive + falsePositive)
  const recall = ratio(truePositive, truePositive + falseNegative)

  return {
    scored: scored.length,
    labelled: labelled.length,
    positives: labelled.filter((row) => row.label === 1).length,
    negatives: labelled.filter((row) => row.label === 0).length,
    unlabelled: scored.filter((k) => k.label === null).length,
    failed: cases.length - scored.length,
    threshold,
    truePositive,
    falsePositive,
    trueNegative,
    falseNegative,
    brier: labelled.length
      ? labelled.reduce(
          (sum, row) => sum + (row.likelihood - row.label) ** 2,
          0
        ) / labelled.length
      : null,
    precision,
    recall,
    f1:
      precision && recall && precision + recall
        ? (2 * precision * recall) / (precision + recall)
        : null,
    accuracy: ratio(truePositive + trueNegative, labelled.length),
    bins: binCases(labelled, bins),
  }
}

/** "84%", and "not yet" where a metric has nothing to divide by. */
export function formatPercent(value: number | null): string {
  return value === null ? "not yet" : `${Math.round(value * 100)}%`
}
