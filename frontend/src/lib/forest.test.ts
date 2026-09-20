import { describe, expect, it } from "vitest"

import {
  PHONE_T2,
  TABLET_T2,
  TREES,
  forestAt,
  generateTree,
  type Tree,
} from "@/lib/forest"

const grown = TREES.map((placement) => ({
  placement,
  tree: generateTree(placement.seed, {
    maxDepth: placement.maxDepth,
    lean: placement.lean,
  }),
}))

/** The end point of a path, which for the trunk says which way the tree leans. */
function endOf(d: string): [number, number] {
  const last = d
    .slice(d.lastIndexOf("Q") + 1)
    .trim()
    .split(/[\s,]+/)
  return [Number(last[2]), Number(last[3])]
}

describe("generateTree", () => {
  it("draws the same forest on every load", () => {
    for (const { placement, tree } of grown) {
      const again = generateTree(placement.seed, {
        maxDepth: placement.maxDepth,
        lean: placement.lean,
      })
      expect(again).toEqual(tree)
    }
    expect(generateTree(11, { maxDepth: 6, lean: 0 })).not.toEqual(
      generateTree(12, { maxDepth: 6, lean: 0 })
    )
  })

  it("stays within the budget of §7.2", () => {
    for (const { placement, tree } of grown) {
      expect(tree.branches.length, placement.id).toBeLessThanOrEqual(400)
      expect(tree.leaves.length, placement.id).toBeLessThanOrEqual(300)
      expect(tree.branches.length, placement.id).toBeGreaterThan(40)
      expect(tree.leaves.length, placement.id).toBeGreaterThan(40)
    }
  })

  it("keeps every coordinate inside the space the layer reserves", () => {
    for (const { placement, tree } of grown) {
      expect(tree.bounds.minX, placement.id).toBeGreaterThanOrEqual(-0.7)
      expect(tree.bounds.maxX, placement.id).toBeLessThanOrEqual(0.7)
      expect(tree.bounds.minY, placement.id).toBeGreaterThanOrEqual(0)
      expect(tree.bounds.maxY, placement.id).toBeLessThanOrEqual(1.05)
    }
  })

  it("grows out of the ground: the trunk starts at the root, every limb off its parent", () => {
    for (const { placement, tree } of grown) {
      expect(tree.branches[0].depth, placement.id).toBe(0)
      expect(tree.branches[0].parent, placement.id).toBe(-1)
      expect(tree.branches[0].d.startsWith("M0 0Q"), placement.id).toBe(true)
      for (const branch of tree.branches.slice(1)) {
        expect(branch.parent).toBeGreaterThanOrEqual(0)
        expect(branch.parent).toBeLessThan(tree.branches.length)
        expect(branch.depth).toBe(tree.branches[branch.parent].depth + 1)
      }
    }
  })

  it("tapers from a nine-pixel trunk and never below a hairline", () => {
    for (const { placement, tree } of grown) {
      expect(tree.branches[0].width, placement.id).toBe(9)
      for (const branch of tree.branches.slice(1)) {
        const parent = tree.branches[branch.parent]
        expect(branch.width).toBeLessThanOrEqual(parent.width)
        expect(branch.width).toBeGreaterThanOrEqual(0.8)
      }
    }
  })

  it("leans each tree toward the middle of the page", () => {
    // T1 stands at 9 % and T2 at 91 %, so one leans right and the other left.
    const t1 = grown[0]
    const t2 = grown[1]
    expect(t1.placement.rootX).toBeLessThan(50)
    expect(endOf(t1.tree.branches[0].d)[0]).toBeGreaterThan(0)
    expect(t2.placement.rootX).toBeGreaterThan(50)
    expect(endOf(t2.tree.branches[0].d)[0]).toBeLessThan(0)
    // An upright tree is upright.
    expect(endOf(grown[2].tree.branches[0].d)[0]).toBeCloseTo(0, 6)
  })

  it("never runs a limb before the one it grew from, at any depth", () => {
    for (const { placement, tree } of grown) {
      for (const branch of tree.branches) {
        if (branch.parent < 0) continue
        const parent = tree.branches[branch.parent]
        expect(
          branch.birth,
          `${placement.id} d${branch.depth}`
        ).toBeGreaterThanOrEqual(parent.birth - 1e-12)
      }
    }
  })

  it("finishes the last leaf at exactly g = 1, and nothing before g = 0", () => {
    for (const { placement, tree } of grown) {
      const ends = [
        ...tree.branches.map((b) => b.birth + b.span),
        ...tree.leaves.map((l) => l.birth + l.span),
      ]
      expect(Math.max(...ends), placement.id).toBeCloseTo(1, 12)
      expect(Math.min(...tree.branches.map((b) => b.birth))).toBe(0)
      for (const span of [
        ...tree.branches.map((b) => b.span),
        ...tree.leaves.map((l) => l.span),
      ]) {
        expect(span).toBeGreaterThan(0)
      }
    }
  })

  it("opens a leaf only once its own twig has finished drawing", () => {
    for (const { placement, tree } of grown) {
      const twigEnds = tree.branches
        .filter((b) => b.depth >= placement.maxDepth - 1)
        .map((b) => b.birth + b.span)
      const earliestTwigEnd = Math.min(...twigEnds)
      for (const leaf of tree.leaves) {
        expect(leaf.birth, placement.id).toBeGreaterThan(0.5 * earliestTwigEnd)
        expect(leaf.tint === "sap" || leaf.tint === "viridian").toBe(true)
        // A closed blot: a move, six smoothed corners, a close.
        expect(leaf.d.match(/Q/g)).toHaveLength(6)
        expect(leaf.d.startsWith("M")).toBe(true)
        expect(leaf.d.endsWith("Z")).toBe(true)
      }
      // Most of the canopy is Sap; Viridian is where the blots pool.
      const sap = tree.leaves.filter((l) => l.tint === "sap").length
      expect(sap / tree.leaves.length).toBeGreaterThan(0.55)
    }
  })

  it("draws the canopy last: leaves open after the trunk is long done", () => {
    for (const { placement, tree } of grown) {
      const trunk = tree.branches[0]
      const firstLeaf = Math.min(...tree.leaves.map((l) => l.birth))
      expect(firstLeaf, placement.id).toBeGreaterThan(trunk.birth + trunk.span)
    }
  })
})

describe("forestAt", () => {
  const ids = (width: number) => forestAt(width).map((t) => t.tree.id)

  it("shows one tree on a phone, two on a tablet, five on a desktop", () => {
    expect(ids(390)).toEqual(["T2"])
    expect(ids(1023)).toEqual(["T2", "T5"])
    expect(ids(1440)).toEqual(["T1", "T2", "T3", "T4", "T5"])
  })

  it("moves T2 nearer the corner and shorter as the viewport narrows", () => {
    expect(forestAt(390)[0].tree).toEqual(PHONE_T2)
    expect(forestAt(800)[0].tree).toEqual(TABLET_T2)
    expect(forestAt(1440)[1].tree).toEqual(TREES[1])
    expect(PHONE_T2.height).toBeLessThan(TABLET_T2.height)
    expect(TABLET_T2.height).toBeLessThan(TREES[1].height)
  })

  it("keeps each tree on its own growth window whatever the width", () => {
    for (const width of [390, 800, 1440]) {
      for (const { index, tree } of forestAt(width)) {
        expect(TREES[index].seed).toBe(tree.seed)
      }
    }
  })
})

describe("the forest as a whole", () => {
  it("fits the element budget of §13 on a desktop", () => {
    const total = (pick: (tree: Tree) => number) =>
      forestAt(1440)
        .map(({ tree }) =>
          pick(
            generateTree(tree.seed, {
              maxDepth: tree.maxDepth,
              lean: tree.lean,
            })
          )
        )
        .reduce((a, b) => a + b, 0)
    expect(total((t) => t.branches.length)).toBeLessThanOrEqual(900)
    expect(total((t) => t.leaves.length)).toBeLessThanOrEqual(900)
  })

  it("has every tree stand at a different seed, so no two are the same drawing", () => {
    expect(new Set(TREES.map((t) => t.seed)).size).toBe(TREES.length)
    expect(new Set(TREES.map((t) => t.id)).size).toBe(TREES.length)
  })
})
