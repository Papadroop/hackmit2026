/**
 * The forest (../../menu-design.md §7.2): trees drawn in ink, in growth order, as the reader
 * scrolls. Structure before colour is the auditor's order of work — draw what is there, then
 * colour only what the evidence supports — so a tree is ink until its leaves arrive.
 *
 * Everything here is pure and generated from a fixed seed in a unit space (root at the origin,
 * height 1, y up), so the forest is identical on every load and the screenshots of §14 are
 * reproducible. components/forest.tsx places each tree and drives its `g`.
 */
import { between, mulberry32 } from "@/lib/random"

/** One limb: a quadratic Bézier in unit space, drawn on between `birth` and `birth + span`. */
export interface Branch {
  d: string
  depth: number
  /** Index of the limb this one grew out of, -1 for the trunk. */
  parent: number
  /** CSS pixels; components/forest.tsx divides it by the tree's scale when it draws. */
  width: number
  birth: number
  span: number
}

/** A leaf: a blot of watercolour, not a shape. Sap mostly, Viridian where they pool. */
export interface Leaf {
  /** A closed path: the blob's six points smoothed, so a leaf has no facets. */
  d: string
  tint: "sap" | "viridian"
  birth: number
  span: number
}

export interface TreeBounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

export interface Tree {
  branches: Branch[]
  leaves: Leaf[]
  bounds: TreeBounds
}

export interface TreeOptions {
  maxDepth: number
  /**
   * Degrees added to the trunk's 90°. In unit space the x axis runs right and the y axis runs
   * up, so a positive lean tips the tree to its left. A tree on the left of the viewport leans
   * toward the centre with a negative value, one on the right with a positive one.
   */
  lean: number
}

/** How long each depth takes to draw, in tree-progress units before normalising (§7.2). */
const SPAN_BY_DEPTH = [0.16, 0.12, 0.09, 0.07, 0.06, 0.05, 0.05]
const TRUNK_LENGTH = 0.3
const TRUNK_WIDTH = 9
const WIDTH_RATIO = 0.62
const MIN_WIDTH = 0.8
const MIN_LENGTH = 0.012
/** Past the third fork a limb may simply stop, which is what keeps a tree from looking woven. */
const EARLY_END_FROM_DEPTH = 3
const EARLY_END_CHANCE = 0.12
const THIRD_CHILD_CHANCE = 0.35
const SPREAD = { min: 15, max: 33 }
const THIRD_CHILD_OFFSET = 4
const CHILD_LENGTH = { min: 0.61, max: 0.75 }
/** Every child bends back toward the light. */
const PHOTOTROPISM = 2
const BOW = { min: 0.06, max: 0.14 }
const BOW_FLIP_CHANCE = 0.25
const SIDE_LIMB = { min: 0.6, max: 0.85 }
const LEAF_RADIUS = { min: 0.012, max: 0.02 }
const LEAF_JITTER = 0.25
const LEAF_VERTICES = 6
const LEAF_REACH = 0.4
const LEAF_SPAN = 0.06
const LEAF_BIRTH_AT = 0.9
const VIRIDIAN_LEAF_CHANCE = 0.3
/** A child starts a little before its parent has finished, so growth reads as continuous. */
const BIRTH_OVERLAP = 0.15

type Point = [number, number]

const RADIANS = Math.PI / 180
const round = (value: number): number => Math.round(value * 1e4) / 1e4

/**
 * The outline of a blot: a closed curve through the midpoints of the polygon's edges with its
 * corners as control points. A leaf keeps the six jittered points it was built from and loses
 * the facets, which read as crystals rather than as wet colour.
 */
function blob(points: Point[]): string {
  const mid = (a: Point, b: Point): Point => [
    (a[0] + b[0]) / 2,
    (a[1] + b[1]) / 2,
  ]
  const n = points.length
  const start = mid(points[n - 1], points[0])
  let d = `M${round(start[0])} ${round(start[1])}`
  for (let i = 0; i < n; i++) {
    const corner = points[i]
    const next = mid(points[i], points[(i + 1) % n])
    d += `Q${round(corner[0])} ${round(corner[1])} ${round(next[0])} ${round(next[1])}`
  }
  return `${d}Z`
}

function quadPoint(p0: Point, p1: Point, p2: Point, t: number): Point {
  const u = 1 - t
  return [
    u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
  ]
}

const spanAt = (depth: number): number =>
  SPAN_BY_DEPTH[Math.min(depth, SPAN_BY_DEPTH.length - 1)]

/**
 * Grows one tree. `seed` fixes it; `maxDepth` is how many times it forks; `lean` tips the trunk.
 * Growth windows come out normalised so the last leaf finishes at exactly g = 1.
 */
export function generateTree(seed: number, options: TreeOptions): Tree {
  const rnd = mulberry32(seed)
  const branches: Branch[] = []
  const leaves: Leaf[] = []
  const bounds: TreeBounds = {
    minX: 0,
    maxX: 0,
    minY: 0,
    maxY: 0,
  }

  const see = (point: Point) => {
    if (point[0] < bounds.minX) bounds.minX = point[0]
    if (point[0] > bounds.maxX) bounds.maxX = point[0]
    if (point[1] < bounds.minY) bounds.minY = point[1]
    if (point[1] > bounds.maxY) bounds.maxY = point[1]
  }

  const growLeaves = (
    start: Point,
    control: Point,
    end: Point,
    birth: number,
    span: number
  ) => {
    const count = 1 + Math.floor(rnd() * 3)
    for (let i = 0; i < count; i++) {
      // The first sits at the tip; the rest run back along the last of the twig.
      const t = i === 0 ? 1 : between(rnd, 1 - LEAF_REACH, 1)
      const [cx, cy] = quadPoint(start, control, end, t)
      const radius = between(rnd, LEAF_RADIUS.min, LEAF_RADIUS.max)
      const rotation = rnd() * 2 * Math.PI
      const vertices: Point[] = []
      for (let v = 0; v < LEAF_VERTICES; v++) {
        const angle = rotation + (v / LEAF_VERTICES) * 2 * Math.PI
        const r = radius * between(rnd, 1 - LEAF_JITTER, 1 + LEAF_JITTER)
        const point: Point = [
          cx + Math.cos(angle) * r,
          cy + Math.sin(angle) * r,
        ]
        see(point)
        vertices.push(point)
      }
      leaves.push({
        d: blob(vertices),
        tint: rnd() < VIRIDIAN_LEAF_CHANCE ? "viridian" : "sap",
        birth: birth + LEAF_BIRTH_AT * span,
        span: LEAF_SPAN,
      })
    }
  }

  const grow = (
    origin: Point,
    angle: number,
    length: number,
    width: number,
    depth: number,
    birth: number,
    parent: number
  ) => {
    const span = spanAt(depth)
    const direction: Point = [
      Math.cos(angle * RADIANS),
      Math.sin(angle * RADIANS),
    ]
    const end: Point = [
      origin[0] + direction[0] * length,
      origin[1] + direction[1] * length,
    ]
    // The bow: the control point at the midpoint, pushed off the chord. The side alternates
    // with depth so a limb answers the one it came from, and is flipped now and then.
    const sign = (depth % 2 === 0 ? 1 : -1) * (rnd() < BOW_FLIP_CHANCE ? -1 : 1)
    const bow = between(rnd, BOW.min, BOW.max) * length * sign
    const control: Point = [
      (origin[0] + end[0]) / 2 - direction[1] * bow,
      (origin[1] + end[1]) / 2 + direction[0] * bow,
    ]
    see(origin)
    see(control)
    see(end)
    branches.push({
      d: `M${round(origin[0])} ${round(origin[1])}Q${round(control[0])} ${round(control[1])} ${round(end[0])} ${round(end[1])}`,
      depth,
      parent,
      width: Math.max(width, MIN_WIDTH),
      birth,
      span,
    })
    const self = branches.length - 1

    const spent = depth >= EARLY_END_FROM_DEPTH && rnd() < EARLY_END_CHANCE
    let forked = false
    if (depth < options.maxDepth && !spent) {
      const children = rnd() < THIRD_CHILD_CHANCE ? 3 : 2
      const spread = between(rnd, SPREAD.min, SPREAD.max)
      // At the first two forks one child leaves the limb partway along, as a side limb.
      const sideLimb = depth <= 1 ? Math.floor(rnd() * children) : -1
      for (let i = 0; i < children; i++) {
        const offset =
          i === 0
            ? spread
            : i === 1
              ? -spread
              : between(rnd, -THIRD_CHILD_OFFSET, THIRD_CHILD_OFFSET)
        const aimed = angle + offset
        const childAngle = aimed + (aimed < 90 ? PHOTOTROPISM : -PHOTOTROPISM)
        const childLength =
          length * between(rnd, CHILD_LENGTH.min, CHILD_LENGTH.max)
        const attachT =
          i === sideLimb ? between(rnd, SIDE_LIMB.min, SIDE_LIMB.max) : 1
        if (childLength < MIN_LENGTH) continue
        const childBirth = Math.max(
          birth,
          birth + span * attachT - BIRTH_OVERLAP * span
        )
        forked = true
        grow(
          quadPoint(origin, control, end, attachT),
          childAngle,
          childLength,
          width * WIDTH_RATIO,
          depth + 1,
          childBirth,
          self
        )
      }
    }

    // Leaves go on the tips of the canopy, never where a limb forks: a branch deep enough to
    // bear them that has stopped growing. Leaving them on every branch at that depth doubles
    // the count past §7.2's own budget of roughly 150 and its 300-leaf assertion.
    if (!forked && depth >= options.maxDepth - 1) {
      growLeaves(origin, control, end, birth, span)
    }
  }

  grow([0, 0], 90 + options.lean, TRUNK_LENGTH, TRUNK_WIDTH, 0, 0, -1)

  const last = Math.max(
    ...branches.map((b) => b.birth + b.span),
    ...leaves.map((l) => l.birth + l.span)
  )
  for (const branch of branches) {
    branch.birth /= last
    branch.span /= last
  }
  for (const leaf of leaves) {
    leaf.birth /= last
    leaf.span /= last
  }

  return { branches, leaves, bounds }
}

/** Where a tree stands and how big it is. Percentages of the viewport (§7.1). */
export interface TreePlacement {
  id: string
  seed: number
  rootX: number
  height: number
  maxDepth: number
  lean: number
  /** Seconds for one half of the sway, seeded per tree so the forest never breathes in step. */
  sway: number
}

/**
 * The five trees of §7.1. `lean` is in generator units, where negative tips a tree to the right:
 * T1 stands on the left and T2 on the right, so both lean toward the centre of the page.
 */
export const TREES = [
  { id: "T1", seed: 11, rootX: 9, height: 92, maxDepth: 6, lean: -4, sway: 7 },
  {
    id: "T2",
    seed: 23,
    rootX: 91,
    height: 85,
    maxDepth: 6,
    lean: 3,
    sway: 8.5,
  },
  {
    id: "T3",
    seed: 37,
    rootX: 22,
    height: 60,
    maxDepth: 5,
    lean: 0,
    sway: 6.2,
  },
  {
    id: "T4",
    seed: 41,
    rootX: 78,
    height: 68,
    maxDepth: 5,
    lean: 0,
    sway: 7.8,
  },
  {
    id: "T5",
    seed: 59,
    rootX: 50,
    height: 46,
    maxDepth: 4,
    lean: 0,
    sway: 5.5,
  },
] as const satisfies readonly TreePlacement[]

/** A phone shows one tree, rooted nearer the corner and shorter (§7.1, §11). */
export const PHONE_T2: TreePlacement = { ...TREES[1], rootX: 88, height: 70 }
/** A tablet's T2 stands a little further out and shorter than on a desktop. */
export const TABLET_T2: TreePlacement = { ...TREES[1], rootX: 92, height: 80 }

/** Which trees stand at a given viewport width, in their T1–T5 order (§7.1, §11). */
export function forestAt(
  width: number
): { index: number; tree: TreePlacement }[] {
  if (width < 640) return [{ index: 1, tree: PHONE_T2 }]
  if (width < 1024) {
    return [
      { index: 1, tree: TABLET_T2 },
      { index: 4, tree: TREES[4] },
    ]
  }
  return TREES.map((tree, index) => ({ index, tree }))
}
