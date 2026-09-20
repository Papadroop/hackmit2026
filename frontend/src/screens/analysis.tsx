import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { RotateCcw, ScrollText, Square } from "lucide-react"
import { usePanelRef } from "react-resizable-panels"
import { toast } from "sonner"

import { ThemeToggle, Wordmark } from "@/components/chrome"
import { ClaimDetail } from "@/components/claim-detail"
import { ClaimPanel } from "@/components/claim-panel"
import { DebugDrawer } from "@/components/debug-drawer"
import { DocumentPane } from "@/components/document-pane"
import { Link } from "@/components/link"
import { OmissionCards } from "@/components/omission-cards"
import { SummaryBand } from "@/components/summary-band"
import { Button } from "@/components/ui/button"
import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer"
import { Toggle } from "@/components/ui/toggle"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { api } from "@/lib/api"
import { scrollToOmission, scrollToSpan } from "@/lib/document-dom"
import { isEditableTarget } from "@/lib/keys"
import { navigate, paths } from "@/lib/router"
import { useMediaQuery } from "@/lib/use-media-query"
import {
  isFinished,
  selectDocument,
  useAnalysis,
  type AnalysisState,
} from "@/state/analysis"
import { AnalysisProvider } from "@/state/analysis-provider"
import {
  DEFAULT_LAYERS,
  LAYER_KEYS,
  useAnnotations,
  type Layers,
} from "@/state/annotations"

/** /a/<id>: one analysis. The provider is keyed by id so a new id starts clean. */
export function AnalysisScreen({ id }: { id: string }) {
  return (
    <AnalysisProvider key={id} analysisId={id}>
      <AnalysisView />
    </AnalysisProvider>
  )
}

function AnalysisView() {
  const { state, stop } = useAnalysis()
  const [drawerOpen, setDrawerOpen] = useState(true)
  const [replaying, setReplaying] = useState(false)
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS)
  const [honest, setHonest] = useState(false)
  const rewriteCount = Object.values(state.verdicts).filter(
    (v) => v.rewrite !== undefined
  ).length
  const drawerRef = usePanelRef()

  const toggleDrawer = useCallback(() => {
    const panel = drawerRef.current
    if (panel === null) return
    if (panel.isCollapsed()) panel.expand()
    else panel.collapse()
  }, [drawerRef])

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        event.key !== "`" ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        event.repeat
      )
        return
      if (isEditableTarget(event.target)) return
      event.preventDefault()
      toggleDrawer()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [toggleDrawer])

  const document = selectDocument(state.events)
  const title = document?.title ?? state.record?.title ?? null
  const source = state.record?.source ?? {}
  const canReplay =
    source.kind === "replay" && typeof source.fixture === "string"
  const running = !isFinished(state.status)

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
    <div className="flex h-svh flex-col">
      <header className="flex items-center gap-4 border-b bg-card px-4 py-2">
        <Wordmark />
        <div className="min-w-0 flex-1 border-l pl-4">
          <p className="truncate font-serif text-[15px] leading-tight">
            {title ?? "Analysis"}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {[document?.company, describePace(source)]
              .filter(Boolean)
              .join(", ")}
          </p>
        </div>
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          aria-label="Layers"
          className="hidden sm:flex"
          value={LAYER_KEYS.filter((key) => layers[key])}
          onValueChange={(value) =>
            setLayers({
              claims: value.includes("claims"),
              language: value.includes("language"),
              omissions: value.includes("omissions"),
            })
          }
        >
          <ToggleGroupItem value="claims">
            Claims
            <LayerCount n={state.claims.length} />
          </ToggleGroupItem>
          <ToggleGroupItem value="language">
            Language
            <LayerCount n={state.signals.length} />
          </ToggleGroupItem>
          <ToggleGroupItem value="omissions">
            Omissions
            <LayerCount n={state.omissions.length} />
          </ToggleGroupItem>
        </ToggleGroup>
        <Toggle
          variant="outline"
          size="sm"
          className="hidden sm:inline-flex"
          pressed={honest}
          onPressedChange={setHonest}
          disabled={rewriteCount === 0 && state.omissions.length === 0}
          aria-label="Honest version"
        >
          Honest version
          <LayerCount n={rewriteCount} />
        </Toggle>
        <span className="hidden text-sm text-muted-foreground lg:inline">
          {statusText(state)}
        </span>
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
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-pressed={drawerOpen}
              aria-label="Toggle events panel"
              onClick={toggleDrawer}
            >
              <ScrollText />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Events panel (press `)</TooltipContent>
        </Tooltip>
        <ThemeToggle />
      </header>
      <ResizablePanelGroup orientation="vertical" className="min-h-0 flex-1">
        <ResizablePanel minSize="30">
          <main className="h-full min-h-0">
            <Workspace
              state={state}
              layers={layers}
              onLayersChange={setLayers}
              honest={honest}
            />
          </main>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel
          panelRef={drawerRef}
          collapsible
          collapsedSize={0}
          defaultSize={260}
          minSize={120}
          groupResizeBehavior="preserve-pixel-size"
          onResize={(size) => setDrawerOpen(size.inPixels > 0)}
        >
          <DebugDrawer onCollapse={() => drawerRef.current?.collapse()} />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

function LayerCount({ n }: { n: number }) {
  if (n === 0) return null
  return (
    <span className="font-normal text-muted-foreground tabular-nums">{n}</span>
  )
}

function describePace(source: Record<string, unknown>): string | null {
  if (source.kind !== "replay") return null
  const speed = typeof source.speed === "number" ? source.speed : 1
  if (speed >= 1000) return "recorded analysis, instant"
  return speed === 1 ? "recorded analysis" : `recorded analysis at ${speed}×`
}

function statusText(state: AnalysisState): string {
  switch (state.status) {
    case "connecting":
      return "Connecting"
    case "streaming":
      return "Analysing"
    case "reconnecting":
      return "Reconnecting"
    case "completed":
      return "Complete"
    case "failed":
      return state.error === "cancelled" ? "Stopped" : "Failed"
    case "missing":
      return ""
  }
}

/**
 * The workspace: the document on the left, the claim panel on the right (design-plan.md).
 * Selection lives here so the pane, the panel and the keyboard agree on it. Below the width
 * where a side panel fits, the selected claim opens in a bottom sheet instead.
 */
function Workspace({
  state,
  layers,
  onLayersChange,
  honest,
}: {
  state: AnalysisState
  layers: Layers
  onLayersChange: (layers: Layers) => void
  honest: boolean
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const wide = useMediaQuery("(min-width: 56rem)")
  const paneRef = useRef<HTMLDivElement>(null)
  const { sections, claims, signals, marks, languageMarks } = useAnnotations(
    state.document,
    state.claims,
    state.verdicts,
    state.signals,
    layers
  )
  const names = useMemo(
    () => new Map(state.evidence.map((item) => [item.id, item.source.name])),
    [state.evidence]
  )
  const rewrites = useMemo(() => {
    const byClaim: Record<string, string> = {}
    for (const verdict of Object.values(state.verdicts))
      if (verdict.rewrite !== undefined)
        byClaim[verdict.claim_id] = verdict.rewrite
    return byClaim
  }, [state.verdicts])

  // Showing an omission may first have to switch its layer on; the scroll then waits for
  // the cards to be in the DOM, which the effect on the layer sees.
  const pendingOmission = useRef<string | null>(null)
  const showOmission = useCallback(
    (id?: string) => {
      const target = id ?? state.omissions[0]?.id ?? null
      if (target === null) return
      if (layers.omissions) {
        scrollToOmission(paneRef.current, target)
        return
      }
      pendingOmission.current = target
      onLayersChange({ ...layers, omissions: true })
    },
    [layers, onLayersChange, state.omissions]
  )
  useEffect(() => {
    if (!layers.omissions || pendingOmission.current === null) return
    scrollToOmission(paneRef.current, pendingOmission.current)
    pendingOmission.current = null
  }, [layers.omissions])

  const locate = useCallback((id: string, span: number) => {
    scrollToSpan(paneRef.current, id, span)
  }, [])

  const select = useCallback(
    (id: string | null, options?: { scroll?: boolean; span?: number }) => {
      setSelectedId(id)
      if (id !== null && options?.scroll)
        scrollToSpan(paneRef.current, id, options.span ?? 0)
    },
    []
  )

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape" || isEditableTarget(event.target)) return
      setSelectedId(null)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  const selected =
    selectedId === null
      ? null
      : (claims.find((c) => c.claim.id === selectedId) ?? null)

  return (
    <div className="flex h-full min-h-0 flex-col">
      {(state.document !== null || state.summary !== null) && (
        <SummaryBand
          state={state}
          selectedId={selectedId}
          onSelect={select}
          onShowOmission={showOmission}
        />
      )}
      <div className="flex min-h-0 flex-1">
        <DocumentPane
          ref={paneRef}
          className="min-w-0 flex-1 px-4 sm:px-6"
          doc={state.document}
          sections={sections}
          claims={claims}
          marks={marks}
          languageMarks={languageMarks}
          verdicts={state.verdicts}
          signals={signals}
          before={
            layers.omissions && state.omissions.length > 0 ? (
              <OmissionCards omissions={state.omissions} names={names} />
            ) : null
          }
          honest={honest}
          rewrites={rewrites}
          omissions={state.omissions}
          onShowOmission={showOmission}
          selectedId={selectedId}
          onSelect={select}
          placeholder={placeholderText(state)}
        />
        {wide ? (
          <ClaimPanel
            className="w-[22rem] shrink-0"
            state={state}
            claims={claims}
            selectedId={selectedId}
            onSelect={select}
            onLocate={locate}
          />
        ) : (
          <Drawer
            open={selected !== null}
            onOpenChange={(open) => !open && setSelectedId(null)}
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
                    onBack={() => setSelectedId(null)}
                    onShow={(span) => {
                      setSelectedId(null)
                      scrollToSpan(paneRef.current, selected.claim.id, span)
                    }}
                    onLocate={(id, span) => {
                      setSelectedId(null)
                      scrollToSpan(paneRef.current, id, span)
                    }}
                  />
                </div>
              )}
            </DrawerContent>
          </Drawer>
        )}
      </div>
    </div>
  )
}

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
