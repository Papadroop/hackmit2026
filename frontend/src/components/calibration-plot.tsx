import {
  useCallback,
  useEffect,
  useRef,
  type Dispatch,
  type SetStateAction,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react"

import {
  OUTCOME_LABELS,
  isMiss,
  type Bin,
  type CalibrationCase,
} from "@/lib/calibration"
import { cn } from "@/lib/utils"

/**
 * The precedent set as one picture (roadmap step 19).
 *
 * Every case sits on a single axis at the likelihood the audit gave it, above the line if a
 * regulator upheld the complaint and below it if the advertiser was cleared; settlements sit on
 * the line, because a bargain is not a finding. The threshold is a line the reader can move,
 * which makes the four cells of the confusion matrix four regions of the plot: the two where
 * the audit and the regulator disagree carry the only colour on the page, so dragging the line
 * shows what an operating point costs rather than asserting it.
 *
 * The scale runs the full 0 to 1 even though nothing is scored below 0.5, because the empty
 * half is the honest part of the picture.
 */

const WIDTH = 760
const HEIGHT = 252
const LEFT = 116
const RIGHT = 736
const UPHELD_BASE = 122
const SETTLED_Y = 145
const CLEARED_BASE = 168
const STEP = 11
const AXIS_Y = 206
const RADIUS = 4.6

const x = (value: number) => LEFT + value * (RIGHT - LEFT)

type Placed = { kase: CalibrationCase; cx: number; cy: number }

/** Cases at the same likelihood stack away from the line, in a fixed order so the picture is
 * the same on every load. */
function place(
  cases: CalibrationCase[],
  base: number,
  direction: number
): Placed[] {
  const columns = new Map<number, number>()
  return cases
    .filter((kase) => kase.likelihood !== null)
    .sort((a, b) =>
      a.likelihood === b.likelihood
        ? a.store_id.localeCompare(b.store_id)
        : (a.likelihood as number) - (b.likelihood as number)
    )
    .map((kase) => {
      const key = Math.round((kase.likelihood as number) * 100)
      const depth = columns.get(key) ?? 0
      columns.set(key, depth + 1)
      return {
        kase,
        cx: x(kase.likelihood as number),
        cy: base + direction * depth * STEP,
      }
    })
}

export function CalibrationStrip({
  cases,
  threshold,
  onThreshold,
  selectedId,
  onSelect,
}: {
  cases: CalibrationCase[]
  threshold: number
  /** Takes an updater as well as a value: a held arrow key fires faster than React renders,
   * so each press has to move the threshold the caller is holding, not the one last drawn. */
  onThreshold: Dispatch<SetStateAction<number>>
  selectedId: string | null
  onSelect: (storeId: string | null) => void
}) {
  const svg = useRef<SVGSVGElement>(null)
  const scroller = useRef<HTMLDivElement>(null)

  // Where the figure has to scroll, it opens on the cases rather than on the empty half of
  // the scale: the emptiness is worth seeing, but not before anything else.
  useEffect(() => {
    const node = scroller.current
    if (node && node.scrollWidth > node.clientWidth)
      node.scrollLeft = node.scrollWidth
  }, [])
  const upheld = place(
    cases.filter((kase) => kase.label === 1),
    UPHELD_BASE,
    -1
  )
  const cleared = place(
    cases.filter((kase) => kase.label === 0),
    CLEARED_BASE,
    1
  )
  const settled = place(
    cases.filter((kase) => kase.label === null),
    SETTLED_Y,
    0
  )

  const fromPointer = useCallback(
    (clientX: number) => {
      const box = svg.current?.getBoundingClientRect()
      if (!box || box.width === 0) return
      const inside = ((clientX - box.left) / box.width) * WIDTH
      const value = (inside - LEFT) / (RIGHT - LEFT)
      onThreshold(Math.min(1, Math.max(0, Math.round(value * 100) / 100)))
    },
    [onThreshold]
  )

  const handleDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.buttons === 0 && event.type === "pointermove") return
    event.currentTarget.setPointerCapture(event.pointerId)
    fromPointer(event.clientX)
  }

  const nudge = (event: ReactKeyboardEvent<SVGGElement>) => {
    const step = event.shiftKey ? 0.1 : 0.01
    const moves: Record<string, number> = {
      ArrowLeft: -step,
      ArrowDown: -step,
      ArrowRight: step,
      ArrowUp: step,
    }
    if (event.key in moves) {
      event.preventDefault()
      onThreshold((current) =>
        Math.min(
          1,
          Math.max(0, Math.round((current + moves[event.key]) * 100) / 100)
        )
      )
    } else if (event.key === "Home") {
      event.preventDefault()
      onThreshold(0)
    } else if (event.key === "End") {
      event.preventDefault()
      onThreshold(1)
    }
  }

  const dot = ({ kase, cx, cy }: Placed) => {
    const missed = isMiss(kase, threshold) === true
    const upheldCase = kase.label === 1
    const selected = kase.store_id === selectedId
    return (
      <circle
        key={kase.store_id}
        cx={cx}
        cy={cy}
        r={selected ? RADIUS + 2 : RADIUS}
        tabIndex={0}
        role="button"
        aria-label={`${kase.company || kase.body}, ${OUTCOME_LABELS[kase.outcome] ?? kase.outcome}, scored ${(kase.likelihood as number).toFixed(2)}`}
        onClick={() => onSelect(selected ? null : kase.store_id)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault()
            onSelect(selected ? null : kase.store_id)
          }
        }}
        className={cn(
          "cursor-pointer outline-none focus-visible:stroke-marker",
          // Filled means a finding was made, hollow means the advertiser was cleared, and the
          // only hue on the plot is a case the audit called the other way.
          missed && "fill-verdict-contradicted stroke-verdict-contradicted",
          !missed && kase.label === null && "fill-none stroke-graphite/70",
          !missed && upheldCase && "fill-ink stroke-ink",
          !missed && kase.label === 0 && "fill-paper stroke-ink",
          selected && "stroke-marker"
        )}
        strokeWidth={selected ? 2.25 : 1.5}
        fillOpacity={0.85}
      >
        <title>
          {`${kase.company || kase.body} — ${OUTCOME_LABELS[kase.outcome] ?? kase.outcome}, scored ${(kase.likelihood as number).toFixed(2)}`}
        </title>
      </circle>
    )
  }

  const line = x(threshold)

  return (
    // Below about 42rem the labels inside the plot would fall under 10px, so the figure
    // scrolls rather than shrinking past legibility.
    <div ref={scroller} className="overflow-x-auto">
      <svg
        ref={svg}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full min-w-[42rem] touch-pan-x select-none"
        role="group"
        aria-label="Every precedent at the likelihood the audit gave it"
        onPointerDown={handleDrag}
        onPointerMove={handleDrag}
      >
        <line
          x1={LEFT}
          x2={RIGHT}
          y1={SETTLED_Y}
          y2={SETTLED_Y}
          className="stroke-border"
          strokeWidth={1}
        />

        <text
          x={LEFT - 14}
          y={UPHELD_BASE - 22}
          textAnchor="end"
          className="fill-graphite text-[13px]"
        >
          Upheld
        </text>
        <text
          x={LEFT - 14}
          y={SETTLED_Y + 4}
          textAnchor="end"
          className="fill-graphite text-[13px]"
        >
          Settled
        </text>
        <text
          x={LEFT - 14}
          y={CLEARED_BASE + 18}
          textAnchor="end"
          className="fill-graphite text-[13px]"
        >
          Cleared
        </text>

        {upheld.map(dot)}
        {settled.map(dot)}
        {cleared.map(dot)}

        {/* The axis. */}
        <line
          x1={LEFT}
          x2={RIGHT}
          y1={AXIS_Y}
          y2={AXIS_Y}
          className="stroke-border"
          strokeWidth={1}
        />
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              x2={x(tick)}
              y1={AXIS_Y}
              y2={AXIS_Y + 5}
              className="stroke-border"
              strokeWidth={1}
            />
            <text
              x={x(tick)}
              y={AXIS_Y + 20}
              textAnchor="middle"
              className="fill-graphite text-[13px] tabular-nums"
            >
              {tick.toFixed(2)}
            </text>
          </g>
        ))}

        {/* The threshold, which the reader can move. */}
        <g
          role="slider"
          tabIndex={0}
          aria-label="Threshold at which a claim is called misleading"
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={threshold}
          aria-valuetext={threshold.toFixed(2)}
          onKeyDown={nudge}
          className="cursor-ew-resize outline-none [&:focus-visible>line]:stroke-[3]"
        >
          <line
            x1={line}
            x2={line}
            y1={40}
            y2={AXIS_Y}
            className="stroke-marker"
            strokeWidth={1.5}
          />
          <polygon
            points={`${line - 5},34 ${line + 5},34 ${line},42`}
            className="fill-marker"
          />
          <text
            x={line}
            y={26}
            textAnchor={
              threshold > 0.85 ? "end" : threshold < 0.15 ? "start" : "middle"
            }
            className="fill-marker text-[13px] tabular-nums"
          >
            {`called misleading above ${threshold.toFixed(2)}`}
          </text>
        </g>
      </svg>
    </div>
  )
}

/**
 * The calibration curve the report says to read: what the audit predicted against what
 * regulators decided, bucket by bucket. The diagonal is perfect. A point's area is how many
 * cases it rests on, because a bucket of one is not evidence of anything.
 */
export function ReliabilityCurve({ bins }: { bins: Bin[] }) {
  const size = 240
  const pad = { left: 52, right: 14, top: 14, bottom: 34 }
  const px = (value: number) => pad.left + value * (size - pad.left - pad.right)
  const py = (value: number) =>
    size - pad.bottom - value * (size - pad.top - pad.bottom)

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="w-full max-w-60"
      role="img"
      aria-label={bins
        .map(
          (bin) =>
            `${bin.count} cases predicted ${bin.predicted.toFixed(2)}, observed ${bin.observed.toFixed(2)}`
        )
        .join("; ")}
    >
      <line
        x1={px(0)}
        y1={py(0)}
        x2={px(1)}
        y2={py(1)}
        className="stroke-graphite/50"
        strokeWidth={1}
        strokeDasharray="3 3"
      />
      <line
        x1={px(0)}
        y1={py(0)}
        x2={px(1)}
        y2={py(0)}
        className="stroke-border"
      />
      <line
        x1={px(0)}
        y1={py(0)}
        x2={px(0)}
        y2={py(1)}
        className="stroke-border"
      />
      {[0, 0.5, 1].map((tick) => (
        <g key={tick}>
          <text
            x={px(tick)}
            y={py(0) + 16}
            textAnchor="middle"
            className="fill-graphite text-[11px] tabular-nums"
          >
            {tick}
          </text>
          <text
            x={px(0) - 7}
            y={py(tick) + 4}
            textAnchor="end"
            className="fill-graphite text-[11px] tabular-nums"
          >
            {tick}
          </text>
        </g>
      ))}
      <polyline
        points={bins
          .map((bin) => `${px(bin.predicted)},${py(bin.observed)}`)
          .join(" ")}
        className="fill-none stroke-ink"
        strokeWidth={1.25}
      />
      {bins.map((bin) => (
        <circle
          key={bin.low}
          cx={px(bin.predicted)}
          cy={py(bin.observed)}
          r={3 + Math.sqrt(bin.count)}
          className="fill-ink"
          fillOpacity={0.82}
        >
          <title>
            {`${bin.count} cases scored ${bin.low.toFixed(1)} to ${bin.high.toFixed(1)}: predicted ${bin.predicted.toFixed(2)}, upheld ${bin.observed.toFixed(2)}`}
          </title>
        </circle>
      ))}
      <text
        x={px(0.5)}
        y={size - 4}
        textAnchor="middle"
        className="fill-graphite text-[11px]"
      >
        predicted
      </text>
      <text
        x={12}
        y={py(0.5)}
        textAnchor="middle"
        transform={`rotate(-90 12 ${py(0.5)})`}
        className="fill-graphite text-[11px]"
      >
        upheld
      </text>
    </svg>
  )
}
