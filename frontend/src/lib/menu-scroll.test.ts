import { describe, expect, it } from "vitest"

import {
  TREE_WINDOWS,
  cueOpacity,
  forestOpacity,
  ramp,
  rinseEdge,
  shaderRunning,
  titleExitOpacity,
  titleExitY,
  treeProgress,
} from "@/lib/menu-scroll"
import { frontAt } from "@/lib/waterline"

describe("ramp", () => {
  it("clamps at both ends and is linear between", () => {
    expect(ramp(-1, 0.2, 0.6)).toBe(0)
    expect(ramp(0.2, 0.2, 0.6)).toBe(0)
    expect(ramp(0.4, 0.2, 0.6)).toBeCloseTo(0.5, 10)
    expect(ramp(0.6, 0.2, 0.6)).toBe(1)
    expect(ramp(9, 0.2, 0.6)).toBe(1)
  })

  it("is a step when the window has no width", () => {
    expect(ramp(0.49, 0.5, 0.5)).toBe(0)
    expect(ramp(0.5, 0.5, 0.5)).toBe(1)
  })
})

describe("the rinse", () => {
  it("travels monotonically down the card as the reader scrolls", () => {
    let previous = -Infinity
    for (let p = 0; p <= 1.0001; p += 0.02) {
      const front = frontAt(rinseEdge(p))
      expect(front).toBeGreaterThanOrEqual(previous)
      previous = front
    }
  })

  it("starts moving at p 0.10 and is done by p 0.80", () => {
    expect(rinseEdge(0.1)).toBe(0)
    expect(rinseEdge(0.45)).toBeCloseTo(0.5, 10)
    expect(rinseEdge(0.8)).toBe(1)
    expect(rinseEdge(0.95)).toBe(1)
  })
})

describe("the card's cues", () => {
  it("clears the cue as soon as the reader moves", () => {
    expect(cueOpacity(0)).toBe(1)
    expect(cueOpacity(0.08)).toBe(0)
  })

  it("crosses the tagline early, while the reader is still at the top of the card", () => {
    // The tagline sits at 40 svh and runs two lines, so the water is through it by p 0.25.
    expect(frontAt(rinseEdge(0.1))).toBeLessThan(0.4)
    expect(frontAt(rinseEdge(0.25))).toBeGreaterThan(0.47)
  })

  it("takes the title away once the card is clean, and not before", () => {
    expect(titleExitOpacity(0.8)).toBe(1)
    expect(titleExitY(0.8)).toBeCloseTo(0, 10)
    expect(titleExitOpacity(0.96)).toBe(0)
    expect(titleExitY(0.96)).toBe(-4)
    // The sheet is clean before the word starts to leave, so it leaves in ink.
    expect(rinseEdge(0.82)).toBe(1)
  })

  it("brings the forest in while the last pigment drains, and stops the shader after", () => {
    expect(forestOpacity(0.7)).toBe(0)
    expect(forestOpacity(0.9)).toBe(1)
    expect(shaderRunning(0.84)).toBe(true)
    expect(shaderRunning(0.85)).toBe(false)
  })
})

describe("treeProgress", () => {
  it("runs each tree over its own window and holds at the ends", () => {
    TREE_WINDOWS.forEach((window, i) => {
      expect(treeProgress(window.from, i)).toBe(0)
      expect(treeProgress(0, i)).toBe(0)
      expect(treeProgress(window.to, i)).toBe(1)
      expect(treeProgress(1, i)).toBe(1)
      const middle = (window.from + window.to) / 2
      expect(treeProgress(middle, i)).toBeCloseTo(0.5, 10)
    })
  })

  it("never grows backwards", () => {
    for (let i = 0; i < TREE_WINDOWS.length; i++) {
      let previous = -Infinity
      for (let f = 0; f <= 1.0001; f += 0.01) {
        const g = treeProgress(f, i)
        expect(g).toBeGreaterThanOrEqual(previous)
        previous = g
      }
    }
  })

  it("has every tree fully grown by the end of the page", () => {
    for (const window of TREE_WINDOWS) expect(window.to).toBeLessThanOrEqual(1)
    expect(treeProgress(1, TREE_WINDOWS.length)).toBe(0)
  })
})
