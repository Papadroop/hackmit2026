import { describe, expect, it } from "vitest"

import {
  OVERSHOOT,
  RIVULETS,
  SAMPLES,
  WAVES,
  frontAt,
  rivuletDepth,
  waterlinePaths,
  waterlineSamples,
  waterlineY,
} from "@/lib/waterline"

const TIMES = [0, 0.7, 2.3, 9.1, 40, 137.5]
const EDGES = [0, 0.05, 0.2, 0.5, 0.8, 0.95, 1]
/** The most the waves alone can lift or drop the line. */
const SWING = WAVES.reduce((total, wave) => total + wave.amp, 0)

const spread = (ys: number[]) => Math.max(...ys) - Math.min(...ys)

describe("the front", () => {
  it("starts a card's overshoot above the card and ends the same below it", () => {
    expect(frontAt(0)).toBeCloseTo(-OVERSHOOT, 10)
    expect(frontAt(1)).toBeCloseTo(1 + OVERSHOOT, 10)
  })

  it("only ever moves down, and clamps outside the rinse", () => {
    let previous = -Infinity
    for (let edge = -0.2; edge <= 1.2; edge += 0.01) {
      const front = frontAt(edge)
      expect(front).toBeGreaterThanOrEqual(previous)
      previous = front
    }
  })

  it("leaves the whole card wet at the start and clean at the end, whatever the waves do", () => {
    for (const time of TIMES) {
      const start = waterlineSamples(frontAt(0), time, rivuletDepth(0))
      expect(Math.max(...start)).toBeLessThan(0)
      const end = waterlineSamples(frontAt(1), time, rivuletDepth(1))
      expect(Math.min(...end)).toBeGreaterThan(1)
    }
  })

  it("never lets a wave or a rivulet reach past the overshoot", () => {
    for (const edge of EDGES) {
      for (const time of TIMES) {
        const ys = waterlineSamples(frontAt(edge), time, rivuletDepth(edge))
        expect(Math.min(...ys)).toBeGreaterThan(-OVERSHOOT - SWING)
        expect(Math.max(...ys)).toBeLessThan(1 + OVERSHOOT + SWING)
      }
    }
  })
})

describe("rivulets", () => {
  it("are gone at both ends of the rinse and deepest in the middle", () => {
    expect(rivuletDepth(0)).toBe(0)
    expect(rivuletDepth(1)).toBeCloseTo(0, 7)
    expect(rivuletDepth(0.5)).toBe(1)
  })

  it("only ever run ahead of the front, never behind it", () => {
    for (const time of TIMES) {
      for (let i = 0; i <= 60; i++) {
        const u = i / 60
        const withThem = waterlineY(u, 0, time, 1)
        const withoutThem = waterlineY(u, 0, time, 0)
        expect(withThem).toBeGreaterThanOrEqual(withoutThem - 1e-12)
      }
    }
  })

  it("reach far enough ahead to read as channels, not as more wave", () => {
    const deepest = Math.max(...RIVULETS.map((r) => r.depth))
    expect(deepest).toBeGreaterThan(SWING * 2)
    // Every rivulet is narrow next to the shortest wave, so none of them flattens the line.
    const shortest = Math.min(...WAVES.map((w) => w.length))
    for (const rivulet of RIVULETS) {
      expect(rivulet.width * 2).toBeLessThan(shortest)
    }
  })
})

describe("the line", () => {
  it("is never flat while the rinse is running", () => {
    for (const edge of [0.15, 0.35, 0.5, 0.65, 0.85]) {
      for (const time of TIMES) {
        const ys = waterlineSamples(frontAt(edge), time, rivuletDepth(edge))
        expect(spread(ys)).toBeGreaterThan(0.04)
      }
    }
  })

  it("keeps moving: no two seconds of the drift are the same line", () => {
    const at = (time: number) => waterlineSamples(frontAt(0.5), time, 1)
    const first = at(0)
    for (const time of [1, 4, 17, 60]) {
      const later = at(time)
      const moved = first.reduce(
        (most, y, i) => Math.max(most, Math.abs(y - later[i])),
        0
      )
      expect(moved).toBeGreaterThan(0.005)
    }
  })

  it("samples the whole width, ends included", () => {
    const ys = waterlineSamples(0.5, 0, 1)
    expect(ys).toHaveLength(SAMPLES + 1)
    expect(ys[0]).toBeCloseTo(waterlineY(0, 0.5, 0, 1), 10)
    expect(ys[SAMPLES]).toBeCloseTo(waterlineY(1, 0.5, 0, 1), 10)
  })
})

describe("the paths", () => {
  const paths = waterlinePaths(waterlineSamples(0.5, 3, 1), 1200, 800)

  it("draws the curve once and closes it either way round it", () => {
    expect(paths.open.startsWith("M")).toBe(true)
    expect(paths.open.endsWith("Z")).toBe(false)
    expect(paths.water.startsWith(paths.open)).toBe(true)
    expect(paths.clean.startsWith(paths.open)).toBe(true)
    expect(paths.water.endsWith("Z")).toBe(true)
    expect(paths.clean.endsWith("Z")).toBe(true)
  })

  it("closes the water to the bottom of the card and the clean sheet to the top", () => {
    const tail = (d: string) => d.slice(paths.open.length)
    expect(tail(paths.water)).toContain("802")
    expect(tail(paths.clean)).toContain("-2")
  })

  it("runs past both edges so no hairline of card shows beside the clip", () => {
    expect(paths.open.startsWith("M-2 ")).toBe(true)
    expect(paths.open).toContain("L1202 ")
  })

  it("is one curve of quadratics, with a point for every sample", () => {
    expect(paths.open.split("Q")).toHaveLength(SAMPLES)
  })
})
