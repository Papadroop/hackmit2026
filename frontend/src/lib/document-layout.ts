/**
 * Turns Document.text plus its regions into something a renderer can walk, and cuts each line
 * into segments wherever an annotation starts or ends.
 *
 * The text is the ground truth for structure: the contract guarantees canonical plain text
 * (blocks separated by one blank line, `\n` inside a block), so every document splits into
 * blocks and lines without any regions at all. Regions only classify lines (title, heading,
 * list item), group them into containers (a cautionary note, a promo card, a footnote) and
 * carry prominence. A document with sparse or missing regions therefore still renders as
 * paragraphs, and a claim never depends on region data to be drawn.
 *
 * All offsets in this module are UTF-16 indices into the text; contract offsets are converted
 * on the way in with an OffsetIndex (see anchor.ts).
 */
import type { Region } from "@contract"

import type { OffsetIndex } from "./anchor"

export type LineKind = "title" | "heading" | "list_item" | "caption" | "text"
export type ContainerKind = "cautionary_note" | "promo" | "footnote" | "quote"

export type Line = {
  start: number
  end: number
  kind: LineKind
  /** Heading level for headings; 1 for the title. */
  level: number | null
  /** Label of the paragraph region the line sits in (P1, P2, ...). */
  paragraph: string | null
  /** Prominence of the most specific region that states one. */
  prominence: number | null
  /** Index of the blank-line-separated block the line belongs to. */
  block: number
}

export type Group =
  | { type: "heading"; line: Line; level: number }
  | { type: "list"; lines: Line[] }
  | { type: "paragraph"; lines: Line[] }

/** Where a group sits in the text: the start of its first line to the end of its last. Also
 * its key, since no two groups start at the same offset. */
export function blockRange(group: Group): [number, number] {
  if (group.type === "heading") return [group.line.start, group.line.end]
  const lines = group.lines
  return [lines[0].start, lines[lines.length - 1].end]
}

export type Section = {
  /** The innermost container region around these groups, or null for plain body text. */
  container: { kind: ContainerKind; label: string | null; start: number } | null
  groups: Group[]
}

const LINE_KINDS: Record<string, LineKind> = {
  list_item: "list_item",
  title: "title",
  heading: "heading",
  caption: "caption",
}
/** Highest priority first, when several regions of these kinds contain one line. */
const LINE_KIND_PRIORITY: LineKind[] = [
  "list_item",
  "title",
  "heading",
  "caption",
]

const CONTAINER_KINDS = new Set<string>([
  "cautionary_note",
  "promo",
  "footnote",
  "quote",
])

type Reg = Region & { ustart: number; uend: number }

function contains(region: Reg, line: { start: number; end: number }): boolean {
  return region.ustart <= line.start && line.end <= region.uend
}

/** Blocks and lines of canonical text, with UTF-16 offsets. Empty lines are dropped. */
export function splitLines(
  text: string
): { start: number; end: number; block: number }[] {
  const lines: { start: number; end: number; block: number }[] = []
  let pos = 0
  let block = 0
  let previousBlank = false
  for (const raw of text.split("\n")) {
    const start = pos
    const end = pos + raw.length
    pos = end + 1
    if (raw === "") {
      if (!previousBlank && lines.length > 0) block += 1
      previousBlank = true
      continue
    }
    previousBlank = false
    lines.push({ start, end, block })
  }
  return lines
}

export function layoutDocument(
  text: string,
  regions: Region[],
  index: OffsetIndex
): Section[] {
  const regs: Reg[] = regions
    .filter(
      (r) =>
        Number.isInteger(r.start) && Number.isInteger(r.end) && r.start < r.end
    )
    .map((r) => ({
      ...r,
      ustart: index.toUnit(r.start),
      uend: index.toUnit(r.end),
    }))

  const lines: (Line & {
    containerKey: string | null
    container: Section["container"]
  })[] = []
  for (const raw of splitLines(text)) {
    const covering = regs.filter((r) => contains(r, raw))
    let kind: LineKind = "text"
    let kindRegion: Reg | null = null
    for (const candidate of LINE_KIND_PRIORITY) {
      const found = covering.find((r) => LINE_KINDS[r.kind] === candidate)
      if (found) {
        kind = candidate
        kindRegion = found
        break
      }
    }
    const paragraphRegion = innermost(
      covering.filter((r) => r.kind === "paragraph")
    )
    const containerRegion = innermost(
      covering.filter((r) => CONTAINER_KINDS.has(r.kind))
    )
    const prominence =
      firstNumber([
        kindRegion?.prominence,
        paragraphRegion?.prominence,
        containerRegion?.prominence,
      ]) ?? null
    const level =
      kind === "title"
        ? 1
        : kind === "heading"
          ? (kindRegion?.level ?? 2)
          : null
    lines.push({
      start: raw.start,
      end: raw.end,
      kind,
      level,
      paragraph: paragraphRegion?.label ?? null,
      prominence,
      block: raw.block,
      containerKey: containerRegion
        ? `${containerRegion.kind}:${containerRegion.ustart}`
        : null,
      container: containerRegion
        ? {
            kind: containerRegion.kind as ContainerKind,
            label: containerRegion.label ?? null,
            start: containerRegion.ustart,
          }
        : null,
    })
  }

  const sections: Section[] = []
  let section: (Section & { key: string | null }) | null = null
  for (const line of lines) {
    if (section === null || section.key !== line.containerKey) {
      section = {
        key: line.containerKey,
        container: line.container,
        groups: [],
      }
      sections.push(section)
    }
    const { containerKey: _key, container: _container, ...plain } = line
    void _key
    void _container
    const last = section.groups.at(-1)
    if (plain.kind === "title" || plain.kind === "heading") {
      section.groups.push({
        type: "heading",
        line: plain,
        level: plain.level ?? 2,
      })
    } else if (plain.kind === "list_item") {
      // One list per paragraph region: items separated only by a blank line stay together,
      // but a new paragraph starts a new list even when its first line is an item.
      if (
        last?.type === "list" &&
        last.lines.at(-1)?.paragraph === plain.paragraph
      )
        last.lines.push(plain)
      else section.groups.push({ type: "list", lines: [plain] })
    } else if (
      last?.type === "paragraph" &&
      last.lines.at(-1)?.block === plain.block
    ) {
      last.lines.push(plain)
    } else {
      section.groups.push({ type: "paragraph", lines: [plain] })
    }
  }
  return sections
}

function innermost(regions: Reg[]): Reg | null {
  let best: Reg | null = null
  for (const r of regions) {
    if (best === null || r.uend - r.ustart < best.uend - best.ustart) best = r
  }
  return best
}

function firstNumber(values: (number | undefined)[]): number | undefined {
  return values.find((v) => typeof v === "number")
}

/** The label of the paragraph region containing a UTF-16 offset, if any. */
export function paragraphAt(
  regions: Region[],
  index: OffsetIndex,
  offset: number
): string | null {
  let best: Region | null = null
  for (const r of regions) {
    if (r.kind !== "paragraph" || typeof r.label !== "string") continue
    if (index.toUnit(r.start) <= offset && offset < index.toUnit(r.end)) {
      if (best === null || r.end - r.start < best.end - best.start) best = r
    }
  }
  return best?.label ?? null
}

/** Something drawn over a range of the text: a claim span now, language marks later. */
export type Mark = {
  /** Entity id (claim id). */
  id: string
  layer: "claim" | "language"
  /** Index of the span within the entity: 0 is the primary span. */
  span: number
  start: number
  end: number
}

/** Anchor key of a mark: what a renderer puts in data-anchor and a scroll-to looks up. */
export function markKey(mark: Pick<Mark, "id" | "span">): string {
  return `${mark.id}:${mark.span}`
}

export type Segment = {
  start: number
  end: number
  /** Marks covering the whole segment, outermost first (longest range first). */
  marks: Mark[]
}

/**
 * Cut [start, end) at every mark boundary inside it. Adjacent segments differ in which marks
 * cover them, so partial overlaps (a word-level mark straddling a claim boundary) come out as
 * flat neighbours rather than nested elements.
 */
export function segmentRange(
  start: number,
  end: number,
  marks: Mark[]
): Segment[] {
  const active = marks.filter(
    (m) => m.start < end && m.end > start && m.start < m.end
  )
  if (active.length === 0) return [{ start, end, marks: [] }]
  const cuts = new Set<number>([start, end])
  for (const m of active) {
    if (m.start > start && m.start < end) cuts.add(m.start)
    if (m.end > start && m.end < end) cuts.add(m.end)
  }
  const points = [...cuts].sort((a, b) => a - b)
  const segments: Segment[] = []
  for (let i = 0; i + 1 < points.length; i += 1) {
    const s = points[i]
    const e = points[i + 1]
    const covering = active
      .filter((m) => m.start <= s && e <= m.end)
      .sort((a, b) => b.end - b.start - (a.end - a.start) || a.start - b.start)
    segments.push({ start: s, end: e, marks: covering })
  }
  return segments
}
