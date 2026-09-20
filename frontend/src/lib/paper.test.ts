import { describe, expect, it } from "vitest"

import {
  GRAIN_COUNT,
  SHEET_TILT,
  TOOTH_COUNT,
  grainSpecks,
  grainTooth,
  sheetTilt,
} from "@/lib/paper"

const inUnit = (value: number) => value >= 0 && value < 1

describe("the fibre", () => {
  it("fills the tile with an even split of light and dark specks", () => {
    const specks = grainSpecks()
    expect(specks).toHaveLength(GRAIN_COUNT)
    expect(specks.filter((s) => s.dark)).toHaveLength(GRAIN_COUNT / 2)
    expect(specks.every((s) => inUnit(s.x) && inUnit(s.y))).toBe(true)
  })

  it("draws the tooth at every angle, none of it long enough to read as a line", () => {
    const tooth = grainTooth()
    expect(tooth).toHaveLength(TOOTH_COUNT)
    expect(Math.max(...tooth.map((t) => t.angle))).toBeLessThan(Math.PI)
    expect(Math.max(...tooth.map((t) => t.length))).toBeLessThan(0.02)
  })

  it("is the same tile every time, so the paper does not change on a reload", () => {
    expect(grainSpecks(19, 20)).toEqual(grainSpecks(19, 20))
    expect(grainSpecks(19, 20)).not.toEqual(grainSpecks(20, 20))
  })
})

describe("a sheet's tilt", () => {
  const ids = ["shell-climate", "apple-carbon-neutral", "orsted-net-zero", "x"]

  it("is the same angle for the same document, every time", () => {
    for (const id of ids) expect(sheetTilt(id)).toBe(sheetTilt(id))
  })

  it("stays inside half a degree either way", () => {
    for (const id of ids) {
      expect(Math.abs(sheetTilt(id))).toBeLessThanOrEqual(SHEET_TILT)
    }
  })

  it("gives neighbouring documents different angles", () => {
    const angles = ids.map(sheetTilt)
    expect(new Set(angles.map((a) => a.toFixed(4))).size).toBe(ids.length)
  })
})
