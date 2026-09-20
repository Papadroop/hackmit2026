import { describe, expect, it } from "vitest"

import {
  GRAIN_COUNT,
  PIGMENT_SEED,
  pigmentBlobs,
  pigmentGrain,
  relativeLuminance,
  washStats,
} from "@/lib/pigment"

// The drawing needs a canvas, which the test runner does not have, so the image's own
// luminance is measured in the real browser (menu-design.md §14 step 3) with the same
// washStats() tested here. What is pure — where the blobs land, how bright a pixel is — is
// tested here.

describe("pigmentBlobs", () => {
  it("is the same image on every load", () => {
    expect(pigmentBlobs()).toEqual(pigmentBlobs(PIGMENT_SEED))
    expect(pigmentBlobs(7)).not.toEqual(pigmentBlobs(8))
  })

  it("places ten pools, five veins and three thin spots", () => {
    const blobs = pigmentBlobs()
    expect(blobs).toHaveLength(18)
    expect(blobs.filter((b) => b.tint === "pine")).toHaveLength(10)
    expect(blobs.filter((b) => b.tint === "sap")).toHaveLength(5)
    expect(blobs.filter((b) => b.tint === "wetPaper")).toHaveLength(3)
  })

  it("keeps every blob inside the canvas and in its own size band", () => {
    const bands = {
      pine: { alpha: 0.55, min: 0.18, max: 0.45, composite: "multiply" },
      sap: { alpha: 0.35, min: 0.12, max: 0.28, composite: "multiply" },
      wetPaper: { alpha: 0.5, min: 0.1, max: 0.2, composite: "screen" },
      viridian: null,
    } as const
    for (const blob of pigmentBlobs()) {
      const band = bands[blob.tint]
      expect(band).not.toBeNull()
      expect(blob.x).toBeGreaterThanOrEqual(0)
      expect(blob.x).toBeLessThan(1)
      expect(blob.y).toBeGreaterThanOrEqual(0)
      expect(blob.y).toBeLessThan(1)
      expect(blob.radius).toBeGreaterThanOrEqual(band!.min)
      expect(blob.radius).toBeLessThan(band!.max)
      expect(blob.alpha).toBe(band!.alpha)
      expect(blob.composite).toBe(band!.composite)
    }
  })
})

describe("pigmentGrain", () => {
  it("is deterministic, in range, and half white", () => {
    const grain = pigmentGrain()
    expect(grain).toHaveLength(GRAIN_COUNT)
    expect(grain).toEqual(pigmentGrain(PIGMENT_SEED))
    expect(grain.filter((speck) => speck.white)).toHaveLength(GRAIN_COUNT / 2)
    for (const speck of grain) {
      expect(speck.x).toBeGreaterThanOrEqual(0)
      expect(speck.x).toBeLessThan(1)
      expect(speck.y).toBeGreaterThanOrEqual(0)
      expect(speck.y).toBeLessThan(1)
    }
  })

  it("does not repeat the blob sequence", () => {
    const grain = pigmentGrain(PIGMENT_SEED, 18)
    const blobs = pigmentBlobs(PIGMENT_SEED)
    expect(grain[0].x).not.toBeCloseTo(blobs[0].x, 6)
  })
})

describe("relativeLuminance", () => {
  it("matches the sRGB definition at the ends of the scale", () => {
    expect(relativeLuminance(0, 0, 0)).toBe(0)
    expect(relativeLuminance(255, 255, 255)).toBeCloseTo(1, 10)
  })

  it("puts the pigment greens where the contrast maths of §4.1 assumes", () => {
    // Viridian #1E7566, Pine #0F3B2E, Sap #6F9B3A: white type is 4.5:1 or better on all three.
    const contrast = (l: number) => 1.05 / (l + 0.05)
    expect(relativeLuminance(0x1e, 0x75, 0x66)).toBeCloseTo(0.1396, 3)
    expect(relativeLuminance(0x0f, 0x3b, 0x2e)).toBeCloseTo(0.0343, 3)
    expect(relativeLuminance(0x6f, 0x9b, 0x3a)).toBeCloseTo(0.2713, 3)
    expect(contrast(relativeLuminance(0x1e, 0x75, 0x66))).toBeGreaterThan(5)
    expect(contrast(relativeLuminance(0x0f, 0x3b, 0x2e))).toBeGreaterThan(12)
    expect(contrast(relativeLuminance(0x6f, 0x9b, 0x3a))).toBeGreaterThan(3)
  })
})

describe("washStats", () => {
  it("averages luminance and counts the light pixels", () => {
    // Two black pixels and two white ones: mean 0.5, half of them lighter than Sap.
    const pixels = new Uint8ClampedArray([
      0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255,
    ])
    const stats = washStats(pixels, 0.2713)
    expect(stats.meanLuminance).toBeCloseTo(0.5, 6)
    expect(stats.lightShare).toBe(0.5)
  })
})
