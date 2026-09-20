import type { ReactNode } from "react"

import type { VerdictCategory } from "@contract"

import { VERDICT_LABELS, markVars } from "@/lib/encoding"
import { cn } from "@/lib/utils"

/**
 * A word set in the same encoding as a highlight in the document: the category's hue and
 * underline style, the confidence as fill alpha. Used wherever the panel names a verdict, so
 * the legend, the list and the document all read the same way.
 */
export function VerdictMark({
  category,
  confidence,
  className,
  children,
}: {
  category: VerdictCategory
  confidence: number
  className?: string
  children?: ReactNode
}) {
  return (
    <span
      className={cn("claim-mark cursor-default", className)}
      data-verdict={category}
      style={markVars({ confidence })}
    >
      {children ?? VERDICT_LABELS[category]}
    </span>
  )
}
