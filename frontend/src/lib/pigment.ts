/**
 * The pigment image the Water shader refracts (../../menu-design.md §6.2): wet green pigment on
 * paper, generated in code so it is reproducible, matches the palette exactly and owes nothing to
 * stock imagery.
 *
 * Blob placement is pure and tested. Drawing needs a canvas, which the test runner does not have,
 * so the image's luminance is measured in the real browser instead (§14 step 3).
 */
import { between, mulberry32 } from "@/lib/random"

/** The four greens of §4.1, read from the CSS variables so the tokens stay the one source. */
export interface PigmentPalette {
  viridian: string
  pine: string
  sap: string
  wetPaper: string
}

/** A radial blob of pigment: the thin spots and the pools the water leaves behind. */
export interface PigmentBlob {
  /** Centre, as a fraction of the canvas. */
  x: number
  y: number
  /** Radius, as a fraction of the canvas. */
  radius: number
  tint: keyof PigmentPalette
  alpha: number
  composite: "multiply" | "screen"
}

export const PIGMENT_SEED = 7
export const PIGMENT_SIZE = 768
/** One-pixel rectangles, half white and half black at 5 %: paper tooth under the wash. */
export const GRAIN_COUNT = 24_000
export const GRAIN_ALPHA = 0.05
/** Pigment pools where the water enters, over the top of the sheet. */
export const POOL_DEPTH = 0.4
export const POOL_ALPHA = 0.35

const BLOB_KINDS = [
  {
    tint: "pine",
    count: 10,
    alpha: 0.55,
    minRadius: 0.18,
    maxRadius: 0.45,
    composite: "multiply",
  },
  {
    tint: "sap",
    count: 5,
    alpha: 0.35,
    minRadius: 0.12,
    maxRadius: 0.28,
    composite: "multiply",
  },
  {
    tint: "wetPaper",
    count: 3,
    alpha: 0.5,
    minRadius: 0.1,
    maxRadius: 0.2,
    composite: "screen",
  },
] as const satisfies readonly {
  tint: keyof PigmentPalette
  count: number
  alpha: number
  minRadius: number
  maxRadius: number
  composite: PigmentBlob["composite"]
}[]

/** The eighteen blobs of §6.2, in canvas-relative coordinates. Pure and deterministic. */
export function pigmentBlobs(seed: number = PIGMENT_SEED): PigmentBlob[] {
  const rnd = mulberry32(seed)
  const blobs: PigmentBlob[] = []
  for (const kind of BLOB_KINDS) {
    for (let i = 0; i < kind.count; i++) {
      blobs.push({
        x: rnd(),
        y: rnd(),
        radius: between(rnd, kind.minRadius, kind.maxRadius),
        tint: kind.tint,
        alpha: kind.alpha,
        composite: kind.composite,
      })
    }
  }
  return blobs
}

/** The grain's one-pixel positions, in canvas-relative coordinates. */
export function pigmentGrain(
  seed: number = PIGMENT_SEED,
  count: number = GRAIN_COUNT
): { x: number; y: number; white: boolean }[] {
  const rnd = mulberry32(seed + 1)
  const grain = []
  for (let i = 0; i < count; i++) {
    grain.push({ x: rnd(), y: rnd(), white: i % 2 === 0 })
  }
  return grain
}

/** sRGB relative luminance, for the contrast checks of §6.2 and §12. */
export function relativeLuminance(r: number, g: number, b: number): number {
  const channel = (value: number) => {
    const c = value / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** Mean luminance and the share of pixels lighter than `lighterThan` (§6.2 step 5). */
export function washStats(
  pixels: Uint8ClampedArray,
  lighterThan: number
): { meanLuminance: number; lightShare: number } {
  let total = 0
  let light = 0
  const count = pixels.length / 4
  for (let i = 0; i < pixels.length; i += 4) {
    const l = relativeLuminance(pixels[i], pixels[i + 1], pixels[i + 2])
    total += l
    if (l > lighterThan) light += 1
  }
  return { meanLuminance: total / count, lightShare: light / count }
}

function rgba(hex: string, alpha: number): string {
  const value = hex.trim().replace("#", "")
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value
  const n = Number.parseInt(full, 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** Draws the wash of §6.2 into a 2D context: fill, blobs, the pool at the top, then grain. */
export function drawPigment(
  ctx: CanvasRenderingContext2D,
  palette: PigmentPalette,
  seed: number = PIGMENT_SEED,
  size: number = PIGMENT_SIZE
): void {
  ctx.globalCompositeOperation = "source-over"
  ctx.fillStyle = palette.viridian
  ctx.fillRect(0, 0, size, size)

  for (const blob of pigmentBlobs(seed)) {
    const cx = blob.x * size
    const cy = blob.y * size
    const r = blob.radius * size
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    gradient.addColorStop(0, rgba(palette[blob.tint], blob.alpha))
    gradient.addColorStop(1, rgba(palette[blob.tint], 0))
    ctx.globalCompositeOperation = blob.composite
    ctx.fillStyle = gradient
    ctx.fillRect(cx - r, cy - r, r * 2, r * 2)
  }

  ctx.globalCompositeOperation = "multiply"
  const pool = ctx.createLinearGradient(0, 0, 0, size * POOL_DEPTH)
  pool.addColorStop(0, rgba(palette.pine, POOL_ALPHA))
  pool.addColorStop(1, rgba(palette.pine, 0))
  ctx.fillStyle = pool
  ctx.fillRect(0, 0, size, size * POOL_DEPTH)

  ctx.globalCompositeOperation = "source-over"
  const white = `rgba(255, 255, 255, ${GRAIN_ALPHA})`
  const black = `rgba(0, 0, 0, ${GRAIN_ALPHA})`
  for (const speck of pigmentGrain(seed)) {
    ctx.fillStyle = speck.white ? white : black
    ctx.fillRect(Math.floor(speck.x * size), Math.floor(speck.y * size), 1, 1)
  }
}

/** The wash as a PNG data URL, for the shader's `image` prop. Empty string with no 2D context. */
export function pigmentWash(
  palette: PigmentPalette,
  seed: number = PIGMENT_SEED,
  size: number = PIGMENT_SIZE
): string {
  const canvas = document.createElement("canvas")
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext("2d")
  if (ctx === null) return ""
  drawPigment(ctx, palette, seed, size)
  return canvas.toDataURL("image/png")
}

/** Reads the §4.1 greens off the document, so light and dark come from the tokens. */
export function readPigmentPalette(
  element: Element = document.documentElement
): PigmentPalette {
  const style = getComputedStyle(element)
  const read = (name: string) => style.getPropertyValue(name).trim()
  return {
    viridian: read("--viridian"),
    pine: read("--pine"),
    sap: read("--sap"),
    wetPaper: read("--wet-paper"),
  }
}
