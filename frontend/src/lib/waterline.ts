/**
 * The waterline: the edge the rinse leaves across the card (../../menu-design.md §6.4, rebuilt
 * 2026-09-20). The first build drained the pigment behind a straight mask edge, which read as a
 * horizontal band rather than as water leaving a sheet. The edge is a curve now: three drifting
 * waves and four rivulets that run ahead of the front and strip a channel down through the
 * pigment. Sampled across the card and emitted as one path, which clips the wash on one side and
 * the ink wordmark on the other.
 *
 * Pure maths, so it is tested away from the browser, scrubs in both directions, and holds still
 * at any scroll position a presenter stops on.
 *
 * `u` runs 0 to 1 across the card, `y` is a fraction of the card's height measured down from its
 * top, and `time` is seconds since the card mounted.
 */
import { clamp01 } from "@/lib/menu-scroll"

/** Slack past each end of the card, so the line starts wholly above it and ends wholly below. */
export const OVERSHOOT = 0.28
/** Points sampled across the card. Enough that the quadratic smoothing keeps the narrowest
 *  rivulet narrow, which is what separates a channel of water from a rolling hill. */
export const SAMPLES = 72

export interface Wave {
  /** Height, as a fraction of the card's height. */
  amp: number
  /** Wavelength, in card widths. */
  length: number
  /** Drift along the card, in wavelengths per second; negative runs the other way. */
  speed: number
  phase: number
}

export interface Rivulet {
  /** Where it starts, as a fraction of the card's width. */
  x: number
  /** Half-width of the channel, as a fraction of the card's width. */
  width: number
  /** How far ahead of the front it reaches, as a fraction of the card's height. */
  depth: number
  /** Sideways drift, in card widths per second. */
  drift: number
  phase: number
}

/** Four waves, no wavelength a multiple of another, so the line never repeats across a card.
 *  The shortest is the chop that keeps the line from reading as a smooth hill. */
export const WAVES: readonly Wave[] = [
  { amp: 0.032, length: 1.37, speed: 0.05, phase: 0 },
  { amp: 0.018, length: 0.53, speed: -0.083, phase: 1.9 },
  { amp: 0.0085, length: 0.21, speed: 0.131, phase: 3.4 },
  { amp: 0.0035, length: 0.083, speed: -0.19, phase: 5.1 },
]

/** Where the water runs ahead of its own front and takes the pigment with it. Narrow next to
 *  the waves: a channel cut down through the pigment, not another trough in the surface. */
export const RIVULETS: readonly Rivulet[] = [
  { x: 0.13, width: 0.026, depth: 0.2, drift: 0.011, phase: 0.4 },
  { x: 0.31, width: 0.015, depth: 0.09, drift: -0.006, phase: 5 },
  { x: 0.46, width: 0.019, depth: 0.12, drift: -0.008, phase: 2.2 },
  { x: 0.68, width: 0.03, depth: 0.21, drift: 0.006, phase: 1.1 },
  { x: 0.88, width: 0.016, depth: 0.14, drift: -0.014, phase: 3.9 },
]

/** The viewport the amplitudes above are drawn for: a laptop, a little wider than it is tall. */
export const REFERENCE_ASPECT = 1.6
const TAU = Math.PI * 2
/** A rivulet is steep on the side it is moving into and drags a tail behind it. */
const LEADING = 0.66
const TRAILING = 1.5

/** The front's own height, from `OVERSHOOT` above the card to `OVERSHOOT` below it. */
export const frontAt = (edge: number): number =>
  clamp01(edge) * (1 + 2 * OVERSHOOT) - OVERSHOOT

/** Rivulets build as the rinse runs and are gone at both ends, where the line is off the card. */
export const rivuletDepth = (edge: number): number =>
  Math.sin(Math.PI * clamp01(edge)) ** 0.5

/**
 * Every height above is a fraction of the card's height and every width a fraction of its width,
 * so a card taller than it is wide would stretch the same line into icicles. This flattens the
 * waves and the rivulets until their slopes are roughly what they are on a laptop.
 */
export const verticalScale = (width: number, height: number): number => {
  if (height <= 0) return 1
  return Math.min(1, Math.max(0.34, width / height / REFERENCE_ASPECT))
}

/** The signed distance from `u` to `x` the short way round the card. */
function wrapped(u: number, x: number): number {
  const at = ((x % 1) + 1) % 1
  const d = u - at
  return d > 0.5 ? d - 1 : d < -0.5 ? d + 1 : d
}

/**
 * The line's height at `u`. `front` is where it would sit with no waves at all and `depth` is
 * how much of the rivulets' reach is in play.
 */
export function waterlineY(
  u: number,
  front: number,
  time: number,
  depth: number,
  scale: number = 1
): number {
  let y = front
  for (const wave of WAVES) {
    y +=
      wave.amp *
      scale *
      Math.sin(TAU * (u / wave.length + time * wave.speed) + wave.phase)
  }
  if (depth <= 0) return y
  for (const rivulet of RIVULETS) {
    const d = wrapped(u, rivulet.x + time * rivulet.drift)
    const width = rivulet.width * (d < 0 ? LEADING : TRAILING)
    const breath = 0.62 + 0.38 * Math.sin(TAU * time * 0.11 + rivulet.phase)
    y += rivulet.depth * scale * depth * breath * Math.exp(-((d / width) ** 2))
  }
  return y
}

/** The line as `samples + 1` heights, evenly spaced from the left edge to the right. */
export function waterlineSamples(
  front: number,
  time: number,
  depth: number,
  scale: number = 1,
  samples: number = SAMPLES
): number[] {
  const ys: number[] = []
  for (let i = 0; i <= samples; i++) {
    ys.push(waterlineY(i / samples, front, time, depth, scale))
  }
  return ys
}

/** The three paths the card needs: the line itself, and the card closed off either side of it. */
export interface WaterlinePaths {
  /** The open curve, for the meniscus stroke. */
  open: string
  /** Closed to the bottom of the card: where the water still is, which clips the wash. */
  water: string
  /** Closed to the top: where the sheet is clean, which clips the ink wordmark. */
  clean: string
}

const round = (value: number): number => Math.round(value * 10) / 10
/** The paths run past both edges so no hairline of card shows beside the clip. */
const BLEED = 2

/**
 * One smooth curve through the samples, in px, closed both ways. Corners are rounded by taking
 * each sample as the control point of a quadratic and each midpoint as an anchor, the same
 * smoothing the leaves use in lib/forest.ts.
 */
export function waterlinePaths(
  ys: number[],
  width: number,
  height: number
): WaterlinePaths {
  const last = ys.length - 1
  const x = (i: number) => round((i / last) * width)
  const y = (i: number) => round(ys[i] * height)
  const left = round(-BLEED)
  const right = round(width + BLEED)

  let open = `M${left} ${y(0)}L${x(0)} ${y(0)}`
  for (let i = 1; i < last; i++) {
    const nextX = round((x(i) + x(i + 1)) / 2)
    const nextY = round((y(i) + y(i + 1)) / 2)
    open += `Q${x(i)} ${y(i)} ${nextX} ${nextY}`
  }
  open += `L${x(last)} ${y(last)}L${right} ${y(last)}`

  const bottom = round(height + BLEED)
  const top = round(-BLEED)
  return {
    open,
    water: `${open}L${right} ${bottom}L${left} ${bottom}Z`,
    clean: `${open}L${right} ${top}L${left} ${top}Z`,
  }
}
