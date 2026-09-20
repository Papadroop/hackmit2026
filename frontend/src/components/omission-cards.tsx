import type { Omission } from "@contract"

import { CiteIds, type EvidenceNames } from "@/components/evidence-list"
import { ScoreBar } from "@/components/score-bar"
import { formatScore } from "@/lib/encoding"

const NONE: ReadonlySet<string> = new Set()
const noop = () => {}

/**
 * The Omissions layer (design-doc D4 Q3, contract §8): what the document does not say, as
 * slips of paper on the desk above the sheet, since an omission has no place in the text.
 * Each shows the topic, why it is material, what the page would say, the materiality score
 * with its confidence, the reference and the evidence behind it.
 */
export function OmissionCards({
  omissions,
  names,
}: {
  omissions: Omission[]
  names: EvidenceNames
}) {
  return (
    <section
      aria-label="Not mentioned"
      className="mx-auto mt-4 grid w-full max-w-[47rem] gap-3 text-[13px] leading-snug sm:mt-8 @3xl:grid-cols-2"
    >
      {omissions.map((omission) => (
        <article
          key={omission.id}
          data-omission={omission.id}
          tabIndex={-1}
          className="rounded-sm border bg-paper p-3 outline-none sm:p-4"
        >
          <p className="flex items-baseline justify-between text-muted-foreground">
            <span>Not mentioned</span>
            <span className="tabular-nums">{omission.id}</span>
          </p>
          <h3 className="mt-0.5 text-[15px] leading-snug font-medium">
            {omission.topic}
          </h3>
          {omission.why_material !== "" && (
            <p className="mt-1.5">{omission.why_material}</p>
          )}
          {omission.complete_text !== undefined && (
            <>
              <p className="mt-2 text-muted-foreground">
                What the page would say
              </p>
              <blockquote className="mt-0.5 border-l-2 border-graphite/40 pl-3 font-serif text-[15px] leading-snug">
                {omission.complete_text}
              </blockquote>
            </>
          )}
          <p className="mt-2 flex items-center gap-2 tabular-nums">
            <span className="text-muted-foreground">Materiality</span>
            <ScoreBar score={omission.score} confidence={omission.confidence} />
            <span>
              {formatScore(omission.score)}
              <span className="text-muted-foreground">
                , confidence {formatScore(omission.confidence)}
              </span>
            </span>
          </p>
          {omission.materiality_reference !== undefined && (
            <p className="mt-1 text-xs text-muted-foreground">
              {omission.materiality_reference}
            </p>
          )}
          {omission.evidence_ids !== undefined &&
            omission.evidence_ids.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Evidence{" "}
                <CiteIds
                  ids={omission.evidence_ids}
                  names={names}
                  present={NONE}
                  onCite={noop}
                />
              </p>
            )}
        </article>
      ))}
    </section>
  )
}
