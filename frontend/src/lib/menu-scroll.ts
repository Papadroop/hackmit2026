/**
 * The menu screen's scroll choreography as pure maths (../../menu-design.md §6.4 and §7.3).
 *
 * `p` is the title card wrapper's progress, 0 with its top at the viewport top and 1 with its
 * bottom at the viewport bottom. `f` is the content section's approach, 0 as its top enters at
 * the bottom of the viewport and 1 as that top reaches the top of it. Everything the card and the forest do is
 * a function of one of those two numbers, so it scrubs in both directions and a presenter can
 * hold any state on stage.
 */

export const clamp01 = (value: number): number =>
  value < 0 ? 0 : value > 1 ? 1 : value

/** 0 below `from`, 1 above `to`, linear between. The one shape every cue below is built from. */
export function ramp(value: number, from: number, to: number): number {
  if (to === from) return value < from ? 0 : 1
  return clamp01((value - from) / (to - from))
}

/** Where the water's edge has reached, 0 at the top of the card and 1 past its bottom. */
export const RINSE = { from: 0.1, to: 0.8 } as const
/** The shader stops once the card is clean; nothing below the card costs GPU. */
export const SHADER_PAUSE = 0.85

export const rinseEdge = (p: number): number => ramp(p, RINSE.from, RINSE.to)

/** The cue goes first: the reader has started, so it has done its job. */
export const cueOpacity = (p: number): number => 1 - ramp(p, 0, 0.08)
/** The forest arrives while the last of the pigment drains. */
export const forestOpacity = (p: number): number => ramp(p, 0.7, 0.9)
/** The clean card does not carry a stranded word down into the list. */
export const titleExitOpacity = (p: number): number => 1 - ramp(p, 0.82, 0.96)
/** svh, negative is up. */
export const titleExitY = (p: number): number => -4 * ramp(p, 0.82, 0.96)
export const shaderRunning = (p: number): boolean => p < SHADER_PAUSE

/**
 * Per-tree growth windows on `f` (§7.3), T1 to T5. `f` is the list's approach to the top of the
 * viewport, and every tree is done by 0.72 of it: the stand is full while the reader is still
 * arriving at the list, not at the bottom of the page after they have read it.
 */
export const TREE_WINDOWS = [
  { from: 0.0, to: 0.6 },
  { from: 0.05, to: 0.66 },
  { from: 0.1, to: 0.72 },
  { from: 0.03, to: 0.63 },
  { from: 0.08, to: 0.69 },
] as const

/** A tree's own progress `g`, 0 before it starts and 1 once its last leaf is out. */
export function treeProgress(f: number, index: number): number {
  const window = TREE_WINDOWS[index]
  if (window === undefined) return 0
  return ramp(f, window.from, window.to)
}
