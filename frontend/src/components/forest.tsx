import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  type AnimationPlaybackControls,
  type MotionValue,
} from "motion/react"

import {
  forestAt,
  generateTree,
  type Tree,
  type TreePlacement,
} from "@/lib/forest"
import { treeProgress } from "@/lib/menu-scroll"

/**
 * What actually grew (../../menu-design.md §7). Behind the list, trees are drawn in ink as the
 * reader scrolls: trunk, limbs, twigs, in growth order, and leaves last as green blots. Structure
 * before colour is the auditor's order of work — draw what is there, then colour only what the
 * evidence supports — which is why green appears here and nowhere else on the page.
 *
 * One CSS custom property per tree per frame drives about 1 300 elements; CSS derives every
 * dash offset and leaf scale from it, so no motion value is created per path.
 */

/** Half of the sway, in degrees. A grown tree moves; it does not wave. */
const SWAY_DEGREES = 0.5

const trees = new Map<string, Tree>()

function treeFor(placement: TreePlacement): Tree {
  const key = `${placement.seed}:${placement.maxDepth}:${placement.lean}`
  const cached = trees.get(key)
  if (cached !== undefined) return cached
  const grown = generateTree(placement.seed, {
    maxDepth: placement.maxDepth,
    lean: placement.lean,
  })
  trees.set(key, grown)
  return grown
}

/** The viewport in CSS pixels; the layer's viewBox follows it so a tree is never distorted. */
function useViewport(): { width: number; height: number } {
  const [size, setSize] = useState(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }))
  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight })
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])
  return size
}

export function Forest({
  progress,
  opacity,
}: {
  /** The content section's scroll progress: how far the reader has come down the list. */
  progress: MotionValue<number>
  /** The layer's own opacity, driven by the card's rinse. */
  opacity: MotionValue<number>
}) {
  const { width, height } = useViewport()
  const stand = useMemo(() => forestAt(width), [width])

  return (
    <motion.svg
      className="rinse-forest"
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      style={{ opacity }}
    >
      {stand.map(({ index, tree }) => (
        <TreeGroup
          key={tree.id}
          index={index}
          placement={tree}
          width={width}
          height={height}
          progress={progress}
        />
      ))}
    </motion.svg>
  )
}

function TreeGroup({
  index,
  placement,
  width,
  height,
  progress,
}: {
  index: number
  placement: TreePlacement
  width: number
  height: number
  progress: MotionValue<number>
}) {
  const reduced = useReducedMotion() ?? false
  const tree = useMemo(() => treeFor(placement), [placement])
  const root = useRef<SVGGElement>(null)
  const sway = useRef<SVGGElement>(null)
  const angle = useMotionValue(0)
  const swaying = useRef<AnimationPlaybackControls | null>(null)

  // Unit space is rooted at the origin with y up and the tree one unit tall, so one transform
  // stands it on the ground at its own size. The scale is uniform in magnitude, so dividing a
  // width by it keeps the limb that many CSS pixels wide (see index.css on why this is not
  // `vector-effect: non-scaling-stroke`).
  const scale = (placement.height / 100) * height
  const rootX = (placement.rootX / 100) * width

  useMotionValueEvent(angle, "change", (value) => {
    sway.current?.setAttribute("transform", `rotate(${value.toFixed(3)})`)
  })

  useEffect(() => {
    // Under reduced motion the forest is simply there: grown from the first paint, no sway.
    if (reduced) {
      root.current?.style.setProperty("--g", "1")
      return
    }
    const setGrowth = (f: number) => {
      const g = treeProgress(f, index)
      root.current?.style.setProperty("--g", g.toFixed(4))
      if (g >= 1 && swaying.current === null) {
        swaying.current = animate(angle, [-SWAY_DEGREES, SWAY_DEGREES], {
          duration: placement.sway,
          repeat: Infinity,
          repeatType: "mirror",
          ease: "easeInOut",
        })
      } else if (g < 1 && swaying.current !== null) {
        swaying.current.stop()
        swaying.current = null
        angle.set(0)
      }
    }
    setGrowth(progress.get())
    const unsubscribe = progress.on("change", setGrowth)
    return () => {
      unsubscribe()
      swaying.current?.stop()
      swaying.current = null
    }
  }, [angle, index, placement.sway, progress, reduced])

  return (
    <g ref={root} transform={`translate(${rootX} ${height})`}>
      <g ref={sway}>
        <g transform={`scale(${scale} ${-scale})`}>
          {tree.branches.map((branch, i) => (
            <path
              key={`b${i}`}
              className="rinse-branch"
              d={branch.d}
              pathLength={1}
              strokeWidth={branch.width / scale}
              style={
                { "--b": branch.birth, "--s": branch.span } as CSSProperties
              }
            />
          ))}
          {tree.leaves.map((leaf, i) => (
            <path
              key={`l${i}`}
              className={
                leaf.tint === "viridian"
                  ? "rinse-leaf rinse-leaf-viridian"
                  : "rinse-leaf"
              }
              d={leaf.d}
              style={{ "--b": leaf.birth, "--s": leaf.span } as CSSProperties}
            />
          ))}
        </g>
      </g>
    </g>
  )
}
