import { Fragment } from "react"

import type { LanguageSignal } from "@contract"

import { formatScore } from "@/lib/encoding"
import { POLARITY_LABELS, signalKindLabel } from "@/lib/language"

/**
 * One language signal in the panel: its kind set in the Language layer's own mark style, its
 * polarity and strength, the words it marks (each a button that shows them in the text), and
 * the evaluator's note.
 */
export function SignalRow({
  signal,
  onLocate,
}: {
  signal: LanguageSignal
  onLocate?: (id: string, span: number) => void
}) {
  return (
    <li>
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="w-8 shrink-0 text-muted-foreground tabular-nums">
          {signal.id}
        </span>
        <span
          className="language-mark shrink-0"
          data-polarity={signal.polarity}
        >
          {signalKindLabel(signal.kind)}
        </span>
        <span className="text-xs text-muted-foreground">
          {POLARITY_LABELS[signal.polarity]}
          {signal.strength !== undefined && (
            <span className="tabular-nums">
              , strength {formatScore(signal.strength)}
            </span>
          )}
          {signal.level === "document" && ", document-level"}
        </span>
      </p>
      {signal.spans.length > 0 && (
        <p className="mt-0.5 pl-10 text-xs text-muted-foreground">
          {signal.spans.map((span, i) => (
            <Fragment key={i}>
              {i > 0 && ", "}
              {onLocate === undefined ? (
                <span className="font-serif text-[13px] text-foreground">
                  “{span.text}”
                </span>
              ) : (
                <button
                  type="button"
                  className="rounded-xs text-left font-serif text-[13px] text-foreground underline decoration-border decoration-dotted underline-offset-2 outline-none hover:decoration-marker focus-visible:ring-3 focus-visible:ring-ring/50"
                  onClick={() => onLocate(signal.id, i)}
                >
                  “{span.text}”
                </button>
              )}
            </Fragment>
          ))}
        </p>
      )}
      {signal.note !== "" && (
        <p className="mt-0.5 pl-10 text-xs leading-snug text-muted-foreground">
          {signal.note}
        </p>
      )}
    </li>
  )
}
