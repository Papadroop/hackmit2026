import { describe, expect, it } from "vitest"

// The artifact the backend publishes, imported so this file has no Node API in it: the app's
// TypeScript project types `src` for the browser only.
import artifact from "../../../backend/data/calibration.json"

import {
  binCases,
  called,
  isMiss,
  measure,
  type Bin,
  type CalibrationCase,
  type CalibrationReport,
} from "./calibration"

const report = artifact as unknown as CalibrationReport

function kase(
  likelihood: number | null,
  label: number | null,
  id = `p${likelihood}-${label}`
): CalibrationCase {
  return {
    store_id: id,
    claim_text: "",
    outcome: label === 1 ? "upheld" : label === 0 ? "not_upheld" : "settled",
    company: "",
    industry: "",
    body: "",
    claim_type: "factual",
    label,
    likelihood,
    category: "",
    scores: {},
    cited: [],
    held_out: [],
    error: "",
  }
}

describe("measure", () => {
  it("reproduces the published metrics from the cases alone", () => {
    // The page recomputes rather than trusting the artifact's own summary, so this is the
    // check that it agrees with backend/auditor/calibration.py at the threshold it ran at.
    const published = report.metrics as Record<string, number>
    const metrics = measure(report.cases, published.threshold)
    expect(metrics.scored).toBe(published.scored)
    expect(metrics.labelled).toBe(published.labelled)
    expect(metrics.positives).toBe(published.positives)
    expect(metrics.negatives).toBe(published.negatives)
    expect(metrics.unlabelled).toBe(published.unlabelled)
    expect(metrics.truePositive).toBe(published.true_positive)
    expect(metrics.falsePositive).toBe(published.false_positive)
    expect(metrics.trueNegative).toBe(published.true_negative)
    expect(metrics.falseNegative).toBe(published.false_negative)
    expect(metrics.precision).toBeCloseTo(published.precision, 10)
    expect(metrics.recall).toBeCloseTo(published.recall, 10)
    expect(metrics.f1).toBeCloseTo(published.f1, 10)
    expect(metrics.accuracy).toBeCloseTo(published.accuracy, 10)
    expect(metrics.brier).toBeCloseTo(published.brier, 4)
  })

  it("reproduces the published calibration curve", () => {
    const published = report.metrics.bins as Bin[]
    const bins = measure(report.cases, report.metrics.threshold).bins
    expect(bins).toHaveLength(published.length)
    bins.forEach((bin, index) => {
      expect(bin.low).toBeCloseTo(published[index].low, 3)
      expect(bin.count).toBe(published[index].count)
      expect(bin.predicted).toBeCloseTo(published[index].predicted, 3)
      expect(bin.observed).toBeCloseTo(published[index].observed, 3)
    })
  })

  it("calls a claim misleading above the threshold, never at it", () => {
    expect(called(0.5, 0.5)).toBe(false)
    expect(called(0.51, 0.5)).toBe(true)
    expect(called(null, 0.5)).toBeNull()
    const metrics = measure([kase(0.5, 1), kase(0.51, 1)], 0.5)
    expect(metrics.truePositive).toBe(1)
    expect(metrics.falseNegative).toBe(1)
  })

  it("leaves settlements out of every metric but still counts them", () => {
    const metrics = measure([kase(0.9, 1), kase(0.9, null)], 0.5)
    expect(metrics.labelled).toBe(1)
    expect(metrics.unlabelled).toBe(1)
    expect(metrics.precision).toBe(1)
    expect(metrics.brier).toBeCloseTo(0.01, 10)
  })

  it("reports a metric with nothing to divide by as null, not as zero", () => {
    const metrics = measure([kase(0.2, 1)], 0.5)
    expect(metrics.precision).toBeNull()
    expect(metrics.recall).toBe(0)
    expect(metrics.f1).toBeNull()
  })

  it("counts a case that failed to score as failed, not as wrong", () => {
    const metrics = measure([kase(null, 1), kase(0.9, 1)], 0.5)
    expect(metrics.failed).toBe(1)
    expect(metrics.scored).toBe(1)
    expect(metrics.labelled).toBe(1)
  })

  it("raising the threshold trades recall for precision", () => {
    const cases = report.cases
    const low = measure(cases, 0.5)
    const high = measure(cases, 0.8)
    expect(high.precision).toBeGreaterThan(low.precision as number)
    expect(high.recall).toBeLessThan(low.recall as number)
  })
})

describe("binCases", () => {
  it("drops empty buckets rather than drawing them as zero", () => {
    const bins = binCases([{ likelihood: 0.9, label: 1 }], 5)
    expect(bins).toHaveLength(1)
    expect(bins[0].low).toBeCloseTo(0.8, 10)
  })

  it("puts a likelihood of exactly 1 in the last bucket", () => {
    const bins = binCases([{ likelihood: 1, label: 0 }], 5)
    expect(bins).toHaveLength(1)
    expect(bins[0].high).toBe(1)
    expect(bins[0].observed).toBe(0)
  })
})

describe("isMiss", () => {
  it("is a miss only where the audit and the regulator disagree", () => {
    expect(isMiss({ label: 1, likelihood: 0.9 }, 0.5)).toBe(false)
    expect(isMiss({ label: 0, likelihood: 0.9 }, 0.5)).toBe(true)
    expect(isMiss({ label: 1, likelihood: 0.2 }, 0.5)).toBe(true)
    expect(isMiss({ label: null, likelihood: 0.9 }, 0.5)).toBeNull()
    expect(isMiss({ label: 1, likelihood: null }, 0.5)).toBeNull()
  })
})
