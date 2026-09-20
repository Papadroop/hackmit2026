/**
 * The paper of the menu (../../menu-design.md §8, third pass): the fibre that ties the sheets to
 * the ground they lie on, and the small tilt that keeps three sheets from stacking like a table.
 * Generated from fixed seeds, like the pigment in lib/pigment.ts, so it is reproducible and owes
 * nothing to a stock texture.
 *
 * Placement is pure and tested here; drawing needs a canvas, so it is checked in the browser.
 */
import { between, mulberry32 } from "@/lib/random"

export const GRAIN_SEED = 19
/** The tile is square and holds nothing but single pixels, so it repeats without a seam. */
export const GRAIN_SIZE = 220
export const GRAIN_COUNT = 9_000
export const TOOTH_COUNT = 900
export const GRAIN_DARK = 0.045
export const GRAIN_LIGHT = 0.06
export const TOOTH_ALPHA = 0.035

export interface Speck {
  x: number
  y: number
  dark: boolean
}

export interface Tooth {
  x: number
  y: number
  angle: number
  length: number
}

/** The paper's fibre, as single pixels in canvas-relative coordinates. */
export function grainSpecks(
  seed: number = GRAIN_SEED,
  count: number = GRAIN_COUNT
): Speck[] {
  const rnd = mulberry32(seed)
  const specks: Speck[] = []
  for (let i = 0; i < count; i++) {
    specks.push({ x: rnd(), y: rnd(), dark: i % 2 === 0 })
  }
  return specks
}

/** The tooth of a cold-pressed sheet: short strokes at every angle, all of them faint. */
export function grainTooth(
  seed: number = GRAIN_SEED,
  count: number = TOOTH_COUNT
): Tooth[] {
  const rnd = mulberry32(seed + 1)
  const tooth: Tooth[] = []
  for (let i = 0; i < count; i++) {
    tooth.push({
      x: rnd(),
      y: rnd(),
      angle: rnd() * Math.PI,
      length: between(rnd, 0.004, 0.016),
    })
  }
  return tooth
}

/**
 * A sheet's own tilt in degrees, from its id, so every document keeps the angle it was laid
 * down at however the list is sorted. Half a degree is the whole range: enough that three
 * sheets do not read as a table, little enough that nothing looks knocked over.
 */
export const SHEET_TILT = 0.5
export function sheetTilt(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return between(mulberry32(hash >>> 0), -SHEET_TILT, SHEET_TILT)
}

/** Draws the fibre tile: specks first, then the tooth over them. */
export function drawGrain(
  ctx: CanvasRenderingContext2D,
  size: number = GRAIN_SIZE,
  seed: number = GRAIN_SEED
): void {
  ctx.clearRect(0, 0, size, size)
  const dark = `rgba(0, 0, 0, ${GRAIN_DARK})`
  const light = `rgba(255, 255, 255, ${GRAIN_LIGHT})`
  for (const speck of grainSpecks(seed)) {
    ctx.fillStyle = speck.dark ? dark : light
    ctx.fillRect(Math.floor(speck.x * size), Math.floor(speck.y * size), 1, 1)
  }
  ctx.lineWidth = 1
  ctx.strokeStyle = `rgba(0, 0, 0, ${TOOTH_ALPHA})`
  ctx.beginPath()
  for (const tooth of grainTooth(seed)) {
    const length = tooth.length * size
    const x = tooth.x * size
    const y = tooth.y * size
    ctx.moveTo(x, y)
    ctx.lineTo(
      x + Math.cos(tooth.angle) * length,
      y + Math.sin(tooth.angle) * length
    )
  }
  ctx.stroke()
}

function toDataUrl(
  width: number,
  height: number,
  paint: (ctx: CanvasRenderingContext2D) => void
): string {
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (ctx === null) return ""
  paint(ctx)
  return canvas.toDataURL("image/png")
}

/** The fibre tile as a PNG data URL, for `--paper-grain`. */
export function paperGrain(): string {
  return toDataUrl(GRAIN_SIZE, GRAIN_SIZE, (ctx) => {
    drawGrain(ctx)
  })
}
