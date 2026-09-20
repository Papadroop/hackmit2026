import { useCallback, useEffect, useState } from "react"

import { ClaimDetail } from "@/components/claim-detail"
import { ClaimPanel } from "@/components/claim-panel"
import { DocumentPane } from "@/components/document-pane"
import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer"
import { scrollToSpan, type Focus } from "@/lib/document-dom"
import { useKeptScroll, type ScrollStore } from "@/lib/keep-scroll"
import { useMediaQuery } from "@/lib/use-media-query"
import { isFinished, type AnalysisState } from "@/state/analysis"
import {
  DEFAULT_MARKS,
  type Annotations,
  type Marks,
} from "@/state/annotations"

const NO_MARKS: Annotations["marks"] = []

/**
 * Claims: the document as a sheet on the desk with every claim highlighted where it sits,
 * and the claims themselves in the column beside it. This is what the screen opens on,
 * because the document is the exhibit and a verdict means nothing away from the words it is
 * about. Below the width where a column fits, a selected claim opens in a bottom sheet.
 */
export function ClaimsView({
  state,
  annotations,
  scrolls,
  selectedId,
  onSelect,
  focus,
}: {
  state: AnalysisState
  annotations: Annotations
  scrolls: ScrollStore
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** A claim another section asked for; scrolled to once this one is on screen. */
  focus: Focus | null
}) {
  const [marks, setMarks] = useState<Marks>(DEFAULT_MARKS)
  const wide = useMediaQuery("(min-width: 56rem)")
  const paneRef = useKeptScroll<HTMLDivElement>(scrolls, "claims")
  const { sections, claims, signals } = annotations

  const select = useCallback(
    (id: string | null, options?: { scroll?: boolean; span?: number }) => {
      onSelect(id)
      if (id !== null && options?.scroll)
        scrollToSpan(paneRef.current, id, options.span ?? 0)
    },
    [onSelect, paneRef]
  )

  const locate = useCallback(
    (id: string, span: number) => {
      scrollToSpan(paneRef.current, id, span)
    },
    [paneRef]
  )

  // Arriving from another section: the claim is already selected, and the sheet has just been
  // drawn, so this is the first chance to put it in view.
  useEffect(() => {
    if (focus === null) return
    scrollToSpan(paneRef.current, focus.id, focus.span)
  }, [focus, paneRef])

  const selected =
    selectedId === null
      ? null
      : (claims.find((c) => c.claim.id === selectedId) ?? null)

  return (
    <div className="flex h-full min-h-0">
      <DocumentPane
        ref={paneRef}
        className="min-w-0 flex-1 px-4 sm:px-6"
        doc={state.document}
        sections={sections}
        claims={claims}
        marks={marks.claims ? annotations.marks : NO_MARKS}
        languageMarks={marks.wording ? annotations.languageMarks : NO_MARKS}
        verdicts={state.verdicts}
        signals={signals}
        honest={false}
        rewrites={NO_REWRITES}
        omissions={NO_OMISSIONS}
        onShowOmission={noop}
        selectedId={selectedId}
        onSelect={select}
        placeholder={placeholderText(state)}
      />
      {wide ? (
        <ClaimPanel
          className="w-[20rem] shrink-0 lg:w-[22rem] xl:w-[23rem]"
          state={state}
          claims={claims}
          marks={marks}
          onMarksChange={setMarks}
          selectedId={selectedId}
          onSelect={select}
          onLocate={locate}
        />
      ) : (
        <Drawer
          open={selected !== null}
          onOpenChange={(open) => !open && onSelect(null)}
        >
          <DrawerContent aria-describedby={undefined}>
            <DrawerTitle className="sr-only">
              {selected === null ? "Claim" : `Claim ${selected.claim.id}`}
            </DrawerTitle>
            {selected !== null && (
              <div className="overflow-auto">
                <ClaimDetail
                  anchored={selected}
                  folded={state}
                  index={claims.indexOf(selected)}
                  total={claims.length}
                  analysisFinished={isFinished(state.status)}
                  onBack={() => onSelect(null)}
                  onShow={(span) => {
                    onSelect(null)
                    scrollToSpan(paneRef.current, selected.claim.id, span)
                  }}
                  onLocate={(id, span) => {
                    onSelect(null)
                    scrollToSpan(paneRef.current, id, span)
                  }}
                />
              </div>
            )}
          </DrawerContent>
        </Drawer>
      )}
    </div>
  )
}

const NO_REWRITES: Record<string, string> = {}
const NO_OMISSIONS: never[] = []
const noop = () => {}

/** What the sheet says while there is no document text to show. */
function placeholderText(state: AnalysisState): string {
  switch (state.status) {
    case "connecting":
      return "Opening the analysis."
    case "streaming":
    case "reconnecting":
      return "Reading the document."
    case "completed":
      return "The analysis finished without a document."
    case "failed":
      return state.error === "cancelled"
        ? "The analysis was stopped before the document was read."
        : (state.error ?? "The analysis failed before the document was read.")
    case "missing":
      return ""
  }
}
