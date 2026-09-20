import { Fragment } from "react"

import type { EvidenceItem } from "@contract"

import {
  RELATION_NOTES,
  TIER_LABELS,
  describeProvenance,
  describeRelations,
  describeSourceDate,
  hostOf,
  type ClaimEvidence,
} from "@/lib/evidence"
import { cn } from "@/lib/utils"

/** Evidence ids by source name, for titles on cross-references. */
export type EvidenceNames = ReadonlyMap<string, string>

/**
 * A claim's evidence as rows, not cards (design-plan.md): the relation to the claim leads,
 * the tier sits at the right, then the source, the verified quote, how it was obtained and
 * a link to the source. A quote appears only when the fold kept it as verified (D5).
 */
export function EvidenceList({
  entries,
  names,
  present,
  onCite,
}: {
  entries: ClaimEvidence[]
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
}) {
  return (
    <ol className="mt-1 divide-y">
      {entries.map(({ item, relations }) => (
        <li
          key={item.id}
          data-evidence={item.id}
          className="-mx-2 rounded-md px-2 py-3"
        >
          <div className="flex items-baseline gap-2">
            <span className="w-8 shrink-0 text-muted-foreground tabular-nums">
              {item.id}
            </span>
            <span
              className="font-medium"
              title={relations.map((r) => RELATION_NOTES[r]).join(" ")}
            >
              {describeRelations(relations)}
            </span>
            <span
              className="ml-auto shrink-0 text-xs text-muted-foreground tabular-nums"
              title={`Tier ${item.tier}: ${TIER_LABELS[item.tier] ?? "reliability not on the scale"}`}
            >
              Tier {item.tier}
            </span>
          </div>
          <p className="mt-1 leading-snug">{item.source.name}</p>
          <SourceLine item={item} />
          {item.quote !== undefined && (
            <blockquote className="mt-2 border-l-2 border-graphite/40 pl-3 font-serif text-[14px] leading-snug">
              {item.quote}
            </blockquote>
          )}
          {item.computation !== undefined && (
            <Computation
              item={item}
              names={names}
              present={present}
              onCite={onCite}
            />
          )}
          <p className="mt-1.5 text-xs leading-snug text-muted-foreground">
            {describeProvenance(item)}
            {item.url !== undefined && (
              <>
                {" "}
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xs underline underline-offset-2 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {hostOf(item.url)}
                </a>
              </>
            )}
          </p>
          {item.note !== undefined && item.note !== "" && (
            <p className="mt-1 text-xs leading-snug text-muted-foreground">
              {item.note}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}

function SourceLine({ item }: { item: EvidenceItem }) {
  const { publisher, date, locator } = item.source
  const parts = [
    publisher,
    date !== undefined && date !== "" ? describeSourceDate(date) : null,
    locator,
  ].filter((p): p is string => typeof p === "string" && p !== "")
  if (parts.length === 0) return null
  return (
    <p className="text-xs leading-snug text-muted-foreground">
      {parts.join(", ")}
    </p>
  )
}

/** "Computed as scope12 / (scope12 + scope3) with scope12_mt = 53, scope3_mt = 1065, from E4, E5." */
function Computation({
  item,
  names,
  present,
  onCite,
}: {
  item: EvidenceItem
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
}) {
  const computation = item.computation
  if (computation === undefined) return null
  const inputs = Object.entries(computation.inputs as Record<string, unknown>)
    .map(([key, value]) => `${key} = ${String(value)}`)
    .join(", ")
  const from = item.derived_from ?? []
  const showResult =
    item.quote === undefined || item.quote !== computation.result
  return (
    <p className="mt-1.5 text-xs leading-snug text-muted-foreground">
      Computed as <span className="text-foreground">{computation.formula}</span>
      {inputs !== "" && <> with {inputs}</>}
      {from.length > 0 && (
        <>
          , from{" "}
          <CiteIds ids={from} names={names} present={present} onCite={onCite} />
        </>
      )}
      .{showResult && <> Result: {computation.result}</>}
    </p>
  )
}

/**
 * Evidence ids as a comma list. An id that is in the claim's evidence list is a button that
 * scrolls to its row; one that is not (not received yet) is plain text. Each carries the
 * source name as its title.
 */
export function CiteIds({
  ids,
  names,
  present,
  onCite,
  className,
}: {
  ids: readonly string[]
  names: EvidenceNames
  present: ReadonlySet<string>
  onCite: (id: string) => void
  className?: string
}) {
  return (
    <span className={cn("tabular-nums", className)}>
      {ids.map((id, i) => (
        <Fragment key={`${id}-${i}`}>
          {i > 0 && ", "}
          {present.has(id) ? (
            <button
              type="button"
              className="rounded-xs underline decoration-dotted underline-offset-2 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
              title={names.get(id)}
              onClick={() => onCite(id)}
            >
              {id}
            </button>
          ) : (
            <span title={names.get(id)}>{id}</span>
          )}
        </Fragment>
      ))}
    </span>
  )
}
