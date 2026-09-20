import { describe, expect, it } from "vitest"

import type { Verdict } from "@contract"

import {
  countVerdicts,
  fillAlpha,
  formatScore,
  isVerdictCategory,
  lineAlpha,
  markVars,
} from "./encoding"

describe("verdict encoding", () => {
  it("maps confidence to a fill alpha above the pending 0.15 only when reasonably confident", () => {
    expect(fillAlpha(0)).toBeCloseTo(0.04)
    expect(fillAlpha(0.5)).toBeCloseTo(0.19)
    expect(fillAlpha(1)).toBeCloseTo(0.34)
    expect(fillAlpha(7)).toBeCloseTo(0.34)
    expect(fillAlpha(-1)).toBeCloseTo(0.04)
  })

  it("keeps the underline visible at low confidence", () => {
    expect(lineAlpha(0)).toBeCloseTo(0.3)
    expect(lineAlpha(1)).toBeCloseTo(1)
    expect(lineAlpha(0.5)).toBeGreaterThan(fillAlpha(0.5))
  })

  it("gives custom properties for a verdict and nothing for a pending claim", () => {
    expect(markVars(null)).toBeUndefined()
    expect(markVars({ confidence: 0.85 })).toEqual({
      "--mark-alpha": "0.295",
      "--mark-line-alpha": "0.895",
    })
  })

  it("formats scores with two decimals and recognises the closed category set", () => {
    expect(formatScore(0.8)).toBe("0.80")
    expect(formatScore(1.2)).toBe("1.00")
    expect(isVerdictCategory("supported")).toBe(true)
    expect(isVerdictCategory("Supported")).toBe(false)
    expect(isVerdictCategory(3)).toBe(false)
  })

  it("counts verdicts per category", () => {
    const verdict = (
      claim_id: string,
      category: Verdict["category"]
    ): Verdict => ({
      claim_id,
      category,
      likelihood: 0.5,
      confidence: 0.5,
      tags: [],
      rationale: "",
    })
    expect(
      countVerdicts({
        C1: verdict("C1", "supported"),
        C2: verdict("C2", "supported"),
        C3: verdict("C3", "contradicted"),
      })
    ).toEqual({
      contradicted: 1,
      misleading_by_framing: 0,
      unsubstantiated: 0,
      supported: 2,
    })
  })
})
