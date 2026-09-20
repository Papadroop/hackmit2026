import type { ReactElement } from "react"

import { lineAlpha } from "@/lib/encoding"
import { formatDate } from "@/lib/format"
import type { CompanyDocument } from "@/lib/company"

/**
 * The company's documents in time, each at its own headline score (contract §4 `CompanyTrend`).
 *
 * These are problem scores, so the line rising means the company is getting worse, which is
 * why the axis is not inverted and the direction is also said in words beneath it. A point's
 * alpha is its confidence, the same encoding a claim's dimension bar uses, so a tentative
 * reading looks tentative here too. With one document there is no line to draw and none is
 * drawn: the note beside it says why rather than a flat line implying steadiness.
 */

const WIDTH = 760
const HEIGHT = 190
const LEFT = 58
const RIGHT = 726
const TOP = 30
const BOTTOM = 136

type Anchor = "start" | "middle" | "end"
type Placed = {
  document: CompanyDocument
  cx: number
  cy: number
  anchor: Anchor
}

export function TrendLine({
  documents,
}: {
  documents: CompanyDocument[]
}): ReactElement | null {
  const dated = documents.filter((document) => document.date)
  // One point is not a line. An axis with a single dot on it says nothing the sentence
  // beneath does not say better, so nothing is drawn and the note does the talking.
  if (dated.length < 2) return null
  const times = dated.map((document) =>
    new Date(document.date as string).getTime()
  )
  const first = Math.min(...times)
  const last = Math.max(...times)
  const span = last - first

  const x = (time: number) =>
    span === 0
      ? (LEFT + RIGHT) / 2
      : LEFT + ((time - first) / span) * (RIGHT - LEFT)
  const y = (score: number) => BOTTOM - score * (BOTTOM - TOP)

  const points: Placed[] = dated.map((document, index) => ({
    document,
    cx: x(times[index]),
    cy: y(document.headline.score),
    // The first and last points sit on the ends of the axis, so centred labels would run off
    // the drawing. They hang inwards instead.
    anchor: (index === 0
      ? "start"
      : index === dated.length - 1
        ? "end"
        : "middle") as Anchor,
  }))

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full min-w-[34rem]"
        role="img"
        aria-label={points
          .map(
            (point) =>
              `${point.document.title}, ${point.document.date}, likelihood ${point.document.headline.score.toFixed(2)}`
          )
          .join("; ")}
      >
        {[0, 0.5, 1].map((tick) => (
          <text
            key={tick}
            x={LEFT - 12}
            y={y(tick) + 4}
            textAnchor="end"
            className="fill-graphite text-[13px] tabular-nums"
          >
            {tick.toFixed(1)}
          </text>
        ))}
        <line
          x1={LEFT}
          x2={RIGHT}
          y1={BOTTOM}
          y2={BOTTOM}
          className="stroke-border"
          strokeWidth={1}
        />

        <polyline
          points={points.map((point) => `${point.cx},${point.cy}`).join(" ")}
          className="fill-none stroke-ink"
          strokeWidth={1.5}
        />

        {points.map((point) => (
          <g key={point.document.document_id}>
            <circle
              cx={point.cx}
              cy={point.cy}
              r={5}
              className="fill-ink"
              fillOpacity={lineAlpha(
                point.document.headline.confidence
              ).toFixed(3)}
            >
              <title>
                {`${point.document.title}: likelihood ${point.document.headline.score.toFixed(2)}, confidence ${point.document.headline.confidence.toFixed(2)}`}
              </title>
            </circle>
            <text
              x={labelX(point)}
              y={point.cy - 12}
              textAnchor={point.anchor}
              className="fill-foreground text-[13px] font-medium tabular-nums"
            >
              {point.document.headline.score.toFixed(2)}
            </text>
            <text
              x={labelX(point)}
              y={BOTTOM + 20}
              textAnchor={point.anchor}
              className="fill-graphite text-[13px]"
            >
              {formatDate(point.document.date as string)}
            </text>
            <text
              x={labelX(point)}
              y={BOTTOM + 38}
              textAnchor={point.anchor}
              className="fill-graphite text-[13px]"
            >
              {truncate(point.document.title)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

/** An end label hangs from the edge of the drawing rather than from its point, so a long
 * title has the whole width to run into. */
function labelX(point: { cx: number; anchor: Anchor }): number {
  if (point.anchor === "start") return Math.max(LEFT - 8, 4)
  if (point.anchor === "end") return Math.min(RIGHT + 8, WIDTH - 4)
  return point.cx
}

/** Titles are a page's own, so they can be long; the row beneath the chart carries the whole
 * of it. */
function truncate(title: string, limit = 34): string {
  return title.length <= limit
    ? title
    : `${title.slice(0, limit - 1).trimEnd()}…`
}
