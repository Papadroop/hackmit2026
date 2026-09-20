import { useCallback, useEffect, useMemo, useState } from "react"
import { RotateCcw, Square } from "lucide-react"
import { toast } from "sonner"

import { ThemeToggle, Wordmark } from "@/components/chrome"
import { ClaimsView } from "@/components/claims-view"
import { CorrectedView } from "@/components/corrected-view"
import { Link } from "@/components/link"
import { OmissionsView } from "@/components/omissions-view"
import { Pipeline } from "@/components/pipeline"
import { SectionTabs } from "@/components/section-tabs"
import { VerdictView } from "@/components/verdict-view"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { Focus } from "@/lib/document-dom"
import { formatScore } from "@/lib/encoding"
import { isEditableTarget } from "@/lib/keys"
import { navigate, paths } from "@/lib/router"
import {
  ANALYSIS_SECTIONS,
  SECTION_LABELS,
  type AnalysisSection,
} from "@/lib/sections"
import { isFinished, selectDocument, useAnalysis } from "@/state/analysis"
import { AnalysisProvider } from "@/state/analysis-provider"
import { useAnnotations } from "@/state/annotations"

/** /a/<id>: one analysis. The provider is keyed by id so a new id starts clean. */
export function AnalysisScreen({
  id,
  section,
}: {
  id: string
  section: AnalysisSection
}) {
  return (
    <AnalysisProvider key={id} analysisId={id}>
      <AnalysisView section={section} />
    </AnalysisProvider>
  )
}

/**
 * The analysis as a case file: the document and its claims, what the page leaves out, the
 * corrected version, and the verdict, each behind its own divider and its own address
 * (lib/sections.ts). One thing is on screen at a time, because each of the four is a whole
 * argument and the old screen showed all of them at once, in strips.
 *
 * Selection and the file's cross-references live here: a top issue on the verdict names a
 * claim, a redline in the corrected version names one too, and either has to open the
 * section that can show it and put it in view.
 */
function AnalysisView({ section }: { section: AnalysisSection }) {
  const { state, stop } = useAnalysis()
  const [replaying, setReplaying] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focus, setFocus] = useState<{
    section: AnalysisSection
    at: Focus
  } | null>(null)
  const scrolls = useMemo(() => new Map<string, number>(), [])

  // One annotation pass for the whole file: the Claims section and the corrected version draw
  // the same anchored spans, so switching between them does not re-anchor the document.
  const annotations = useAnnotations(
    state.document,
    state.claims,
    state.verdicts,
    state.signals
  )

  const open = useCallback(
    (to: AnalysisSection) => {
      if (to !== section) navigate(paths.analysis(state.analysisId, to))
    },
    [section, state.analysisId]
  )

  const showClaim = useCallback(
    (id: string, span = 0) => {
      setSelectedId(id)
      setFocus({ section: "claims", at: { id, span, key: Date.now() } })
      open("claims")
    },
    [open]
  )

  const showOmission = useCallback(
    (id: string) => {
      setFocus({ section: "omissions", at: { id, span: 0, key: Date.now() } })
      open("omissions")
    },
    [open]
  )

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return
      if (isEditableTarget(event.target)) return
      if (event.key === "Escape") {
        setSelectedId(null)
        return
      }
      // 1 to 4 open the dividers, in the order they are printed.
      const at = ANALYSIS_SECTIONS[Number(event.key) - 1]
      if (event.key !== "" && at !== undefined) {
        event.preventDefault()
        navigate(paths.analysis(state.analysisId, at))
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [state.analysisId])

  const document = selectDocument(state.events)
  const title = document?.title ?? state.record?.title ?? null
  const source = state.record?.source ?? {}
  const canReplay =
    source.kind === "replay" && typeof source.fixture === "string"
  const running = !isFinished(state.status)
  const rewritten = Object.values(state.verdicts).filter(
    (verdict) => verdict.rewrite !== undefined
  ).length

  const replay = async () => {
    if (!canReplay) return
    setReplaying(true)
    try {
      const summary = await api.createAnalysis({
        kind: "replay",
        fixture: source.fixture as string,
        speed: typeof source.speed === "number" ? source.speed : 1,
      })
      navigate(paths.analysis(summary.analysis_id))
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not start the replay."
      )
      setReplaying(false)
    }
  }

  if (state.status === "missing") {
    return (
      <div className="flex min-h-svh flex-col">
        <header className="flex items-center gap-3 px-6 py-3">
          <Wordmark />
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-prose px-6 py-10">
          <h1 className="text-2xl font-medium">Analysis not found</h1>
          <p className="mt-2 text-muted-foreground">{state.error}</p>
          <Button className="mt-6" asChild>
            <Link href={paths.menu()}>Choose a document</Link>
          </Button>
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-svh flex-col bg-background">
      <header className="shrink-0 bg-card">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 sm:px-4">
          <Wordmark />
          <div className="min-w-0 flex-1 border-l pl-3">
            <h1 className="truncate font-serif text-[15px] leading-tight">
              {title ?? "Analysis"}
            </h1>
            <p className="truncate text-xs text-muted-foreground">
              {/* The demo narrative's last move: open a document, click a claim, zoom out to
                  the company (design-doc D2, D7). */}
              {document?.company && (
                <>
                  <Link
                    href={paths.company(document.company)}
                    className="rounded-sm underline decoration-border decoration-dotted underline-offset-2 outline-none hover:decoration-marker focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    {document.company}
                  </Link>
                  {describePace(source) ? ", " : ""}
                </>
              )}
              {describePace(source)}
            </p>
          </div>
          {/* Below the small breakpoint the controls take a line of their own, or the title
              is squeezed out of the row by buttons that cannot shrink. */}
          <div className="flex w-full items-center gap-2 sm:w-auto">
            <Pipeline state={state} />
            {running ? (
              <Button
                variant="outline"
                onClick={() => void stop()}
                disabled={state.status === "connecting"}
              >
                <Square data-icon="inline-start" />
                Stop
              </Button>
            ) : (
              canReplay && (
                <Button
                  variant="outline"
                  onClick={() => void replay()}
                  disabled={replaying}
                >
                  <RotateCcw data-icon="inline-start" />
                  {replaying ? "Starting" : "Replay"}
                </Button>
              )
            )}
            <Button variant="ghost" asChild>
              <Link href={paths.menu()}>New analysis</Link>
            </Button>
            <ThemeToggle />
          </div>
        </div>
        <SectionTabs
          analysisId={state.analysisId}
          active={section}
          counts={{
            claims: count(state.claims.length),
            omissions: count(state.omissions.length),
            corrected: count(rewritten),
            verdict:
              state.summary === null
                ? null
                : formatScore(state.summary.headline.score),
          }}
        />
      </header>
      <main
        className="min-h-0 flex-1"
        aria-label={SECTION_LABELS[section]}
        key={section}
      >
        {section === "claims" && (
          <ClaimsView
            state={state}
            annotations={annotations}
            scrolls={scrolls}
            selectedId={selectedId}
            onSelect={setSelectedId}
            focus={focus?.section === "claims" ? focus.at : null}
          />
        )}
        {section === "omissions" && (
          <OmissionsView
            state={state}
            scrolls={scrolls}
            focus={focus?.section === "omissions" ? focus.at : null}
          />
        )}
        {section === "corrected" && (
          <CorrectedView
            state={state}
            annotations={annotations}
            scrolls={scrolls}
            onShowClaim={showClaim}
            onShowOmission={showOmission}
          />
        )}
        {section === "verdict" && (
          <VerdictView
            state={state}
            scrolls={scrolls}
            onShowClaim={showClaim}
            onShowOmission={showOmission}
          />
        )}
      </main>
    </div>
  )
}

const count = (n: number) => (n === 0 ? null : String(n))

function describePace(source: Record<string, unknown>): string | null {
  if (source.kind !== "replay") return null
  const speed = typeof source.speed === "number" ? source.speed : 1
  if (speed >= 1000) return "recorded analysis, instant"
  return speed === 1 ? "recorded analysis" : `recorded analysis at ${speed}×`
}
