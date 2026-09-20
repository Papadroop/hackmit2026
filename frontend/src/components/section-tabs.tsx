import { motion, useReducedMotion } from "motion/react"

import { Link } from "@/components/link"
import { paths } from "@/lib/router"
import {
  ANALYSIS_SECTIONS,
  SECTION_LABELS,
  type AnalysisSection,
} from "@/lib/sections"
import { cn } from "@/lib/utils"

/**
 * The dividers in the case file: Claims, Omissions, Corrected version, Verdict. The open one
 * is the divider that has been pulled forward — it takes the colour of the desk below it and
 * its bottom edge is the desk's own, so it covers the strip's rule and reads as one piece of
 * paper with the section under it. A Marker cap sits on its top edge, because Marker is what
 * "selected" means everywhere else on this screen, and it slides from divider to divider so
 * the reader sees which one moved.
 *
 * They are links, not tab widgets: each section is an address (lib/sections.ts), so the back
 * button walks them and one can be sent to someone.
 */
export function SectionTabs({
  analysisId,
  active,
  counts,
}: {
  analysisId: string
  active: AnalysisSection
  /** What each divider carries beside its name; null while there is nothing to count yet. */
  counts: Record<AnalysisSection, string | null>
}) {
  const reduced = useReducedMotion()
  return (
    <nav
      aria-label="Sections"
      className="flex gap-0.5 overflow-x-auto border-b px-2 sm:px-3"
    >
      {ANALYSIS_SECTIONS.map((section) => {
        const open = section === active
        const count = counts[section]
        return (
          <Link
            key={section}
            href={paths.analysis(analysisId, section)}
            aria-current={open ? "page" : undefined}
            className={cn(
              "relative -mb-px rounded-t-sm border border-b-transparent px-3 py-1.5 text-[15px] whitespace-nowrap outline-none",
              "focus-visible:ring-3 focus-visible:ring-ring/50",
              open
                ? "border-border border-b-background bg-background font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:bg-background/50 hover:text-foreground"
            )}
          >
            {open && (
              <motion.span
                layoutId="section-cap"
                aria-hidden
                className="absolute inset-x-2 top-0 h-[2px] rounded-full bg-primary"
                transition={
                  reduced
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 520, damping: 44 }
                }
              />
            )}
            {/* "Corrected version" is the only label too long for a phone; it loses its second
                word rather than the row losing a divider off the end. */}
            {section === "corrected" ? (
              <>
                Corrected<span className="hidden sm:inline"> version</span>
              </>
            ) : (
              SECTION_LABELS[section]
            )}
            {count !== null && (
              <span className="ml-2 text-[13px] font-normal text-muted-foreground tabular-nums">
                {count}
              </span>
            )}
          </Link>
        )
      })}
    </nav>
  )
}
