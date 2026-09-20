import { useEffect, useMemo, useRef, useState, type RefObject } from "react"
import { Water } from "@paper-design/shaders-react"
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
  type MotionValue,
} from "motion/react"

import { useTheme } from "@/components/theme-provider"
import {
  cueOpacity,
  rinseEdge,
  shaderRunning,
  taglineOpacity,
  titleExitOpacity,
  titleExitY,
} from "@/lib/menu-scroll"
import {
  pigmentWash,
  readPigmentPalette,
  type PigmentPalette,
} from "@/lib/pigment"
import { useMediaQuery } from "@/lib/use-media-query"
import {
  frontAt,
  rivuletDepth,
  verticalScale,
  waterlinePaths,
  waterlineSamples,
} from "@/lib/waterline"

/**
 * The first viewport of the menu: wet green pigment on white paper, moving as if under running
 * water, with the word "rinse" the only other thing on it. Scrolling drains the pigment from the
 * top down, and the wordmark is white where the water still covers it and ink where the sheet has
 * come clean (../../menu-design.md §6).
 *
 * The word is drawn twice, once in each colour, and the waterline clips the ink copy: the water
 * itself uncovers the letters rather than a crossfade turning them grey halfway. That also means
 * the word never sits at a colour that fails contrast against whatever is behind it.
 *
 * `progress` is the card wrapper's scroll progress, 0 with its top at the top of the viewport and
 * 1 with its bottom at the bottom. Everything here is a function of that one number, so it
 * scrubs both ways and a presenter can hold any state on stage.
 */

const LETTERS = ["r", "i", "n", "s", "e"]
const LETTER_STAGGER = 0.07
const LETTER_DURATION = 0.9
const LETTER_EASE = [0.2, 0.7, 0.2, 1] as const
const TAGLINE =
  "Every environmental claim in a corporate text, rinsed down to its evidence."
const TAGLINE_DELAY = 0.7
const CUE_DELAY = 1.4
/** The title settles out of the water over the length of the letter sequence. */
const RIPPLE_MS = 1400
/** §6.6's displacement, and the title size it was chosen for (the cap of the clamp in
 *  index.css). Held at 28 px it melts a phone title into an unreadable blot, so it scales with
 *  the type and the largest title keeps exactly the displacement §6.6 gives. */
const RIPPLE_SCALE = 28
const RIPPLE_AT = 264

/** The rendered title size: the same clamp as `.rinse-title` in index.css. */
function titleSize(): number {
  return Math.min(Math.max(76, 0.17 * window.innerWidth), RIPPLE_AT)
}

/**
 * §6.3, tuned by screenshot at 1440x900 from the starting values there. Caustic, highlights and
 * layering came a long way down: at the starting values the shader read as the floor of a
 * swimming pool, which §6.3 names as the thing to avoid. What is left is a slow wet mottling
 * over the pigment rather than a net of bright cells.
 *
 * `scale` and the offsets are not in §6.3; they are how its fourth target and §12's contrast
 * floor are met. The shader offsets the image's own UV by up to 0.1 x `waves`, and anything past
 * the edge of the image is filled with `colorBack`, which showed as two vertical seams down the
 * card: cropping in gives the distortion room at every viewport aspect. The offsets then move the
 * brightest thin spot of the wash out from under the title, which at the centred crop held the
 * worst pixel under it to 2.9:1.
 */
const WATER = {
  highlights: 0.04,
  caustic: 0.1,
  waves: 0.4,
  layering: 0.05,
  edges: 0.1,
  size: 0.35,
  scale: 1.6,
  offsetX: 0.08,
  offsetY: -0.2,
  speed: 0.6,
  minPixelRatio: 1,
  maxPixelCount: 1_200_000,
  /** The phase the still wash holds under reduced motion. */
  frozenFrame: 2400,
} as const

const washes = new Map<string, { image: string; palette: PigmentPalette }>()

function useResolvedTheme(): "light" | "dark" {
  const { theme } = useTheme()
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)")
  if (theme === "system") return systemDark ? "dark" : "light"
  return theme
}

/** The pigment image and the greens it was made from, generated once per theme and kept. */
function usePigment(theme: "light" | "dark") {
  const [, redraw] = useState(0)
  useEffect(() => {
    if (washes.has(theme)) return
    // A frame after the theme class lands, so the CSS variables read as the new theme.
    const frame = requestAnimationFrame(() => {
      const palette = readPigmentPalette()
      washes.set(theme, { image: pigmentWash(palette), palette })
      redraw((n) => n + 1)
    })
    return () => cancelAnimationFrame(frame)
  }, [theme])
  return washes.get(theme) ?? null
}

/** True once the italic Literata face is in, which is when the title may surface. */
function useFontsReady(skip: boolean): boolean {
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (skip) return
    let cancelled = false
    const done = () => {
      if (!cancelled) setLoaded(true)
    }
    document.fonts
      .load('italic 400 96px "Literata Variable"')
      .then(() => document.fonts.ready)
      .then(done, done)
    return () => {
      cancelled = true
    }
  }, [skip])
  return skip || loaded
}

/** True for the length of the ripple, so the filter pass does not survive into scrolling. */
function useRipple(active: boolean): boolean {
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => setSettled(true), RIPPLE_MS + 100)
    return () => clearTimeout(timer)
  }, [active])
  return active && !settled
}

/** The card's own box, which is the coordinate space every waterline path is written in. */
function useElementSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const element = ref.current
    if (element === null) return
    const observer = new ResizeObserver(([entry]) => {
      const box = entry.contentRect
      setSize({ width: box.width, height: box.height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return size
}

export function TitleCard({ progress }: { progress: MotionValue<number> }) {
  const reduced = useReducedMotion() ?? false
  const theme = useResolvedTheme()
  const pigment = usePigment(theme)
  const ready = useFontsReady(reduced)
  const rippling = useRipple(ready && !reduced)
  const webgl2 = useMemo(() => hasWebGl2(), [])

  const card = useRef<HTMLDivElement>(null)
  const { width, height } = useElementSize(card)

  const titleOpacity = useTransform(progress, titleExitOpacity)
  const titleY = useTransform(progress, (p) =>
    reduced ? "0svh" : `${titleExitY(p)}svh`
  )
  const tagline = useTransform(progress, taglineOpacity)
  const cue = useTransform(progress, cueOpacity)

  // Nothing below the card should cost GPU, so the shader and the waterline's own drift stop
  // once the card is clean and start again if the reader scrolls back above it.
  const [running, setRunning] = useState(true)
  useMotionValueEvent(progress, "change", (p) => {
    setRunning(shaderRunning(p))
  })

  // The waterline. Its shape is written straight to the four paths rather than through React:
  // one is the meniscus, two clip the wash and the ink wordmark, and all three change every
  // frame while the water moves. Still under reduced motion, where the reader's own scrolling
  // is the only thing that moves it.
  const water = useRef<SVGPathElement>(null)
  const clean = useRef<SVGPathElement>(null)
  const edge = useRef<SVGPathElement>(null)
  const glow = useRef<SVGPathElement>(null)
  const drifting = running && !reduced
  useEffect(() => {
    if (width === 0 || height === 0) return
    const started = performance.now()
    const scale = verticalScale(width, height)
    const draw = () => {
      const e = rinseEdge(progress.get())
      const time = drifting ? (performance.now() - started) / 1000 : 0
      const ys = waterlineSamples(frontAt(e), time, rivuletDepth(e), scale)
      const paths = waterlinePaths(ys, width, height)
      water.current?.setAttribute("d", paths.water)
      clean.current?.setAttribute("d", paths.clean)
      edge.current?.setAttribute("d", paths.open)
      glow.current?.setAttribute("d", paths.open)
    }
    draw()
    if (!drifting) return progress.on("change", draw)
    let frame = requestAnimationFrame(function loop() {
      draw()
      frame = requestAnimationFrame(loop)
    })
    return () => cancelAnimationFrame(frame)
  }, [width, height, drifting, progress])

  const wordStyle = { opacity: titleOpacity, y: titleY }
  const measured = width > 0 && height > 0
  /** The meniscus is drawn in card pixels, so its weight follows the smaller of the two. */
  const unit = Math.min(width, height)

  return (
    <div className="rinse-card" ref={card}>
      <div
        className="rinse-wash"
        aria-hidden="true"
        style={{ clipPath: measured ? "url(#rinse-water)" : undefined }}
      >
        {pigment === null ? null : webgl2 ? (
          <Water
            className="rinse-shader"
            image={pigment.image}
            fit="cover"
            colorBack={pigment.palette.pine}
            colorHighlight={pigment.palette.wetPaper}
            highlights={WATER.highlights}
            caustic={WATER.caustic}
            waves={WATER.waves}
            layering={WATER.layering}
            edges={WATER.edges}
            size={WATER.size}
            scale={WATER.scale}
            offsetX={WATER.offsetX}
            offsetY={WATER.offsetY}
            speed={reduced || !running ? 0 : WATER.speed}
            frame={reduced ? WATER.frozenFrame : undefined}
            minPixelRatio={WATER.minPixelRatio}
            maxPixelCount={WATER.maxPixelCount}
            style={{ visibility: running ? "visible" : "hidden" }}
          />
        ) : (
          <div
            className="rinse-wash-still"
            style={{ backgroundImage: `url(${pigment.image})` }}
          />
        )}
      </div>

      {measured && (
        <svg
          className="rinse-waterline"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <clipPath id="rinse-water" clipPathUnits="userSpaceOnUse">
              <path ref={water} />
            </clipPath>
            <clipPath id="rinse-clean" clipPathUnits="userSpaceOnUse">
              <path ref={clean} />
            </clipPath>
          </defs>
          <path
            ref={glow}
            className="rinse-waterline-glow"
            strokeWidth={unit * 0.05}
            style={{ filter: `blur(${(unit * 0.018).toFixed(1)}px)` }}
          />
          <path
            ref={edge}
            className="rinse-waterline-edge"
            strokeWidth={Math.max(1, unit / 600)}
          />
        </svg>
      )}

      {/* The word as the water leaves it: white, over the whole card. */}
      <div className="rinse-card-inner">
        <Wordmark
          label="rinse"
          ready={ready}
          reduced={reduced}
          rippling={rippling}
          style={wordStyle}
        />
        {/* The rinse drives the outer opacity and the load sequence the inner one: Motion
            lets a style value win over an animation on the same element, so the two have to
            sit on elements of their own. */}
        <motion.div style={{ opacity: tagline }}>
          <motion.p
            className="rinse-tagline"
            initial={reduced ? false : { opacity: 0, y: "0.3em" }}
            animate={ready ? { opacity: 1, y: "0em" } : { opacity: 0 }}
            transition={{
              duration: 0.6,
              delay: TAGLINE_DELAY,
              ease: LETTER_EASE,
            }}
          >
            {TAGLINE}
          </motion.p>
        </motion.div>
        <motion.div className="rinse-cue" style={{ opacity: cue }}>
          <motion.p
            initial={reduced ? false : { opacity: 0 }}
            animate={ready ? { opacity: 1 } : { opacity: 0 }}
            transition={{ duration: 0.4, delay: CUE_DELAY }}
          >
            Choose a document
          </motion.p>
        </motion.div>
      </div>

      {/* The same word in ink, clipped to the part of the sheet the water has already left.
          The hidden tagline is what keeps the two words in the same place: the block is
          centred on both of them together. */}
      <div
        className="rinse-card-inner rinse-card-ink"
        aria-hidden="true"
        style={{ clipPath: measured ? "url(#rinse-clean)" : "inset(100% 0 0)" }}
      >
        <Wordmark
          ready={ready}
          reduced={reduced}
          rippling={rippling}
          style={wordStyle}
        />
        <div className="rinse-tagline-ghost">
          <p className="rinse-tagline">{TAGLINE}</p>
        </div>
      </div>

      {rippling && (
        <RippleFilter scale={(RIPPLE_SCALE * titleSize()) / RIPPLE_AT} />
      )}
    </div>
  )
}

/** The wordmark, letter by letter as it surfaces. Drawn twice, so it takes its colour from a class. */
function Wordmark({
  label,
  ready,
  reduced,
  rippling,
  style,
}: {
  label?: string
  ready: boolean
  reduced: boolean
  rippling: boolean
  style: { opacity: MotionValue<number>; y: MotionValue<string> }
}) {
  return (
    <motion.h1
      className="wordmark rinse-title"
      aria-label={label}
      aria-hidden={label === undefined ? "true" : undefined}
      style={{ ...style, filter: rippling ? "url(#rinse-ripple)" : "none" }}
    >
      {LETTERS.map((letter, i) => (
        <motion.span
          key={letter + String(i)}
          className="rinse-letter"
          aria-hidden="true"
          initial={
            reduced ? false : { opacity: 0, y: "0.4em", filter: "blur(10px)" }
          }
          animate={
            ready
              ? { opacity: 1, y: "0em", filter: "blur(0px)" }
              : { opacity: 0, y: "0.4em", filter: "blur(10px)" }
          }
          transition={{
            duration: LETTER_DURATION,
            delay: i * LETTER_STAGGER,
            ease: LETTER_EASE,
          }}
        >
          {letter}
        </motion.span>
      ))}
    </motion.h1>
  )
}

/**
 * The letters settle out of the water: a turbulence displacement that falls to nothing over the
 * load sequence. Mounted only while it runs, so no filter pass survives into scrolling.
 */
function RippleFilter({ scale }: { scale: number }) {
  const animation = useRef<SVGAnimationElement>(null)
  useEffect(() => {
    animation.current?.beginElement()
  }, [])
  return (
    <svg
      width="0"
      height="0"
      aria-hidden="true"
      style={{ position: "absolute" }}
    >
      <filter id="rinse-ripple" x="-15%" y="-15%" width="130%" height="130%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.012 0.03"
          numOctaves="2"
          seed="7"
          result="water"
        />
        <feDisplacementMap
          in="SourceGraphic"
          in2="water"
          scale={scale}
          xChannelSelector="R"
          yChannelSelector="G"
        >
          <animate
            ref={animation}
            attributeName="scale"
            values={`${scale.toFixed(1)};0`}
            keyTimes="0;1"
            calcMode="spline"
            keySplines="0.2 0.7 0.2 1"
            dur={`${RIPPLE_MS}ms`}
            fill="freeze"
            begin="indefinite"
          />
        </feDisplacementMap>
      </filter>
    </svg>
  )
}

function hasWebGl2(): boolean {
  try {
    return document.createElement("canvas").getContext("webgl2") !== null
  } catch {
    return false
  }
}
