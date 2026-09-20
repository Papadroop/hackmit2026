import { useMemo, useState } from "react"

import { CorrectedSplit } from "@/components/corrected-split"
import { DocumentPane } from "@/components/document-pane"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useKeptScroll, type ScrollStore } from "@/lib/keep-scroll"
import { useMediaQuery } from "@/lib/use-media-query"
import { isFinished, type AnalysisState } from "@/state/analysis"
import type { Annotations } from "@/state/annotations"

const NO_MARKS: Annotations["languageMarks"] = []

/**
 * The corrected version (design-doc D6's honest version, roadmap step 9): what the evidence
 * allows the page to say. It was a toggle over the Claims view; as a section of its own it can
 * be read two ways.
 *
 * Side by side is the default: the page as published on the left, corrected on the right, block
 * beside block (components/corrected-split.tsx). The redline is the same thing in one column,
 * which is what a narrow screen gets, and it is worth keeping on a wide one because it is the
 * only view that shows a change of two words as two words.
 *
 * The wording marks are left off in both. A dotted line under a hedge and a line through the
 * whole phrase are two different arguments, and together they are unreadable.
 */
export function CorrectedView({
  state,
  annotations,
  scrolls,
  onShowClaim,
  onShowOmission,
}: {
  state: AnalysisState
  annotations: Annotations
  scrolls: ScrollStore
  onShowClaim: (id: string) => void
  onShowOmission: (id: string) => void
}) {
  const [asked, setAsked] = useState<"split" | "redline">("split")
  // Two columns of prose need the width for two measures; under that the redline is the same
  // information in one column, so the choice is not offered rather than offered and broken.
  const wide = useMediaQuery("(min-width: 68rem)")
  const split = wide && asked === "split"
  const paneRef = useKeptScroll<HTMLDivElement>(scrolls, "corrected")
  const rewrites = useMemo(() => {
    const byClaim: Record<string, string> = {}
    for (const verdict of Object.values(state.verdicts))
      if (verdict.rewrite !== undefined)
        byClaim[verdict.claim_id] = verdict.rewrite
    return byClaim
  }, [state.verdicts])
  const added = state.omissions.filter(
    (omission) => omission.complete_text !== undefined
  )
  const rewritten = Object.keys(rewrites).length
  const nothing = rewritten === 0 && added.length === 0

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 px-4 pt-4 pb-3 sm:px-6">
        <div
          className={`mx-auto flex w-full items-start justify-between gap-6 ${split ? "max-w-[76rem]" : "max-w-[47rem]"}`}
        >
          <div className="min-w-0 flex-1">
            <p className="text-[15px] leading-snug">
              The page as the evidence allows it to be written.
            </p>
            <p className="mt-1 text-[13px] leading-snug text-muted-foreground">
              {nothing ? (
                isFinished(state.status) ? (
                  "Nothing needed correcting: every claim the page makes is supported, and nothing material is missing."
                ) : (
                  "The corrections follow the verdicts."
                )
              ) : split ? (
                <>
                  Beside the page as published, block for block, with{" "}
                  <ins className="honest-ins">the tool&rsquo;s wording</ins> in
                  italic. {describe(rewritten, added.length)}
                </>
              ) : (
                <>
                  <del className="honest-del">
                    What the evidence does not support
                  </del>{" "}
                  is struck through, and{" "}
                  <ins className="honest-ins">the tool&rsquo;s wording</ins>{" "}
                  follows it in italic. {describe(rewritten, added.length)}
                </>
              )}
            </p>
          </div>
          {!nothing && wide && (
            <ToggleGroup
              className="shrink-0"
              type="single"
              variant="outline"
              size="sm"
              aria-label="How to show the corrections"
              value={asked}
              onValueChange={(value) =>
                value !== "" && setAsked(value as "split" | "redline")
              }
            >
              <ToggleGroupItem value="split">Side by side</ToggleGroupItem>
              <ToggleGroupItem value="redline">Redline</ToggleGroupItem>
            </ToggleGroup>
          )}
        </div>
      </div>
      {split ? (
        <CorrectedSplit
          ref={paneRef}
          className="min-h-0 flex-1 px-4 sm:px-6"
          state={state}
          annotations={annotations}
          rewrites={rewrites}
          onShowClaim={onShowClaim}
          onShowOmission={onShowOmission}
        />
      ) : (
        <DocumentPane
          ref={paneRef}
          className="min-h-0 flex-1 px-4 sm:px-6"
          doc={state.document}
          sections={annotations.sections}
          claims={annotations.claims}
          marks={annotations.marks}
          languageMarks={NO_MARKS}
          verdicts={state.verdicts}
          signals={annotations.signals}
          honest
          redline
          rewrites={rewrites}
          omissions={state.omissions}
          onShowOmission={onShowOmission}
          selectedId={null}
          onSelect={(id) => id !== null && onShowClaim(id)}
          placeholder="There is no document to correct yet."
        />
      )}
    </div>
  )
}

/** "12 claims rewritten, 4 topics added." Either half is left out when it is nothing. */
function describe(rewritten: number, added: number): string {
  const parts = [
    rewritten === 0
      ? null
      : `${rewritten} ${rewritten === 1 ? "claim" : "claims"} rewritten`,
    added === 0 ? null : `${added} ${added === 1 ? "topic" : "topics"} added`,
  ].filter(Boolean)
  return parts.length === 0 ? "" : `${parts.join(", ")}.`
}
