import { lineAlpha } from "@/lib/encoding"
import { cn } from "@/lib/utils"

const clamp01 = (n: number) => Math.min(1, Math.max(0, n))

/**
 * A short bar for a problem score (design-plan.md): length is the score, the fill's alpha is
 * the confidence, and the fill is Ink so a score is never mistaken for a verdict category.
 * With no score the track is empty.
 */
export function ScoreBar({
  score,
  confidence,
  className,
}: {
  score: number | null
  confidence: number
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block h-1.5 w-14 overflow-hidden rounded-xs bg-muted align-middle",
        className
      )}
    >
      {score !== null && (
        <span
          className="block h-full bg-ink"
          style={{
            width: `${Math.round(clamp01(score) * 100)}%`,
            opacity: lineAlpha(confidence).toFixed(3),
          }}
        />
      )}
    </span>
  )
}
