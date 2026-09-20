import { describe, expect, it } from "vitest"

import { diffWords, honestText, planRewrite } from "./diff"

describe("diffWords", () => {
  it("finds insertions and replacements at word level", () => {
    const ops = diffWords(
      "Reducing the net carbon intensity by 15-20% by 2030.",
      "We aim to reduce the net carbon intensity by 15-20% by 2030, a target lowered in 2024."
    )
    expect(ops).toEqual([
      { type: "delete", text: "Reducing" },
      { type: "insert", text: "We aim to reduce" },
      { type: "equal", text: "the net carbon intensity by 15-20% by" },
      { type: "delete", text: "2030." },
      { type: "insert", text: "2030, a target lowered in 2024." },
    ])
    expect(honestText(ops)).toBe(
      "We aim to reduce the net carbon intensity by 15-20% by 2030, a target lowered in 2024."
    )
  })

  it("absorbs a single kept word between two changes", () => {
    const ops = diffWords("a b c d e", "x b y d e")
    expect(ops).toEqual([
      { type: "delete", text: "a b c" },
      { type: "insert", text: "x b y" },
      { type: "equal", text: "d e" },
    ])
  })

  it("keeps the original and the rewrite recoverable", () => {
    const a = "Scope 1 and 2 emissions were down by 36% by the end of 2025."
    const b =
      "Emissions from our own operations were 36% below 2016 at the end of 2025."
    const ops = diffWords(a, b)
    expect(
      ops
        .filter((op) => op.type !== "insert")
        .map((op) => op.text)
        .join(" ")
    ).toBe(a)
    expect(honestText(ops)).toBe(b)
  })
})

describe("planRewrite", () => {
  it("uses word mode for a correction and block mode for a rewrite from scratch", () => {
    expect(
      planRewrite(
        "Reducing the net carbon intensity by 15-20% by 2030.",
        "Reducing the net carbon intensity by 15-20% by 2030, a target lowered from 20% in 2024."
      ).mode
    ).toBe("words")
    expect(
      planRewrite(
        "2-3% by 2021 - achieved",
        "Net carbon intensity was 9% below 2016 at the end of both 2024 and 2025."
      ).mode
    ).toBe("block")
    expect(planRewrite("", "anything").mode).toBe("block")
  })

  it("falls back to block mode when the change is spread over many runs", () => {
    expect(planRewrite("a b c d e f g h i j", "a X c Y e Z g W i V").mode).toBe(
      "block"
    )
  })
})
