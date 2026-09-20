import { useEffect, useRef, useState, type FormEvent } from "react"
import { LoaderCircle, Play } from "lucide-react"
import { ReactLenis } from "lenis/react"
import { useReducedMotion, useScroll, useTransform } from "motion/react"
import { toast } from "sonner"

import "lenis/dist/lenis.css"

import { ThemeToggle } from "@/components/chrome"
import { Forest } from "@/components/forest"
import { Link } from "@/components/link"
import { TitleCard } from "@/components/title-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  api,
  type AnalysisRequest,
  type AnalysisSummary,
  type DemoDocument,
  type DocumentsResponse,
} from "@/lib/api"
import {
  TEXT_TYPE_LABELS,
  formatDate,
  formatDuration,
  formatNumber,
  formatRelative,
} from "@/lib/format"
import { forestOpacity } from "@/lib/menu-scroll"
import { readPref, writePref } from "@/lib/prefs"
import { navigate, paths } from "@/lib/router"

/** Replay pace. 1 is the recorded pace; the large value jumps to the finished state. */
const PACES = [
  { value: 1, label: "1×" },
  { value: 4, label: "4×" },
  { value: 10, label: "10×" },
  { value: 1_000_000, label: "Instant" },
] as const
type Pace = (typeof PACES)[number]["value"]
const PACE_KEY = "auditor.replayPace"
const isPace = (value: unknown): value is Pace =>
  PACES.some((p) => p.value === value)

const STATUS_TEXT = {
  running: "Running",
  completed: "Complete",
  failed: "Stopped",
} as const

/**
 * The first screen: choose a document to analyse. Documents come from the backend, which
 * joins the demo texts with their recorded analyses; the interface never shows what the team
 * expects the verdict to be.
 *
 * The name says what the product does, so the screen shows it once, in order: the wash, the
 * rinse, and then what actually grew (../../menu-design.md §2). The card's own progress `p`
 * drives the rinse and the forest's arrival; `f`, the list's own approach to the top of the
 * viewport, grows the trees, so the stand is full by the time the reader is reading.
 *
 * Below the card everything is a sheet of paper on the rinsed ground, each one still carrying a
 * stripe of pigment down its edge. The only motion here answers the reader: the stripe drains
 * when a sheet is under the pointer, and again, for good, when its analysis starts.
 */
export function MenuScreen() {
  const [data, setData] = useState<DocumentsResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [recent, setRecent] = useState<AnalysisSummary[]>([])
  const [pace, setPace] = useState<Pace>(() => readPref(PACE_KEY, 1, isPace))
  const [starting, setStarting] = useState<string | null>(null)
  const reduced = useReducedMotion() ?? false
  const cardRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLElement>(null)

  // `p`: the card wrapper, 0 with its top at the top of the viewport and 1 with its bottom at
  // the bottom. `f`: the list's approach, 0 as its top enters at the bottom of the viewport and
  // 1 as that top reaches the top — one viewport of scroll, whatever the list is carrying.
  const { scrollYProgress: cardProgress } = useScroll({
    target: cardRef,
    offset: ["start start", "end end"],
  })
  const { scrollYProgress: listProgress } = useScroll({
    target: listRef,
    offset: ["start end", "start start"],
  })
  const forestFade = useTransform(cardProgress, (p) =>
    reduced ? 1 : forestOpacity(p)
  )

  useEffect(() => {
    let cancelled = false
    api
      .listDocuments()
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch((error: Error) => {
        if (!cancelled) setLoadError(error.message)
      })
    api
      .listAnalyses()
      .then((list) => {
        if (!cancelled) setRecent(list.slice(0, 6))
      })
      .catch(() => {
        // Recent analyses are a convenience; the documents list is what matters.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const choosePace = (value: string) => {
    const next = Number(value)
    if (!isPace(next)) return
    setPace(next)
    writePref(PACE_KEY, next)
  }

  const start = async (key: string, request: AnalysisRequest) => {
    setStarting(key)
    try {
      const summary = await api.createAnalysis(request)
      navigate(paths.analysis(summary.analysis_id))
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not start the analysis."
      )
      setStarting(null)
    }
  }

  const screen = (
    <div className="rinse-screen">
      <Forest progress={listProgress} opacity={forestFade} />
      <header className="rinse-header">
        <ThemeToggle />
      </header>
      <div ref={cardRef} className="rinse-card-wrapper">
        <TitleCard progress={cardProgress} />
      </div>
      <main ref={listRef} className="rinse-content">
        <div className="rinse-column">
          <section aria-labelledby="documents-heading">
            <div className="rinse-heading">
              <h2 id="documents-heading" className="rinse-heading-text">
                Documents
              </h2>
              <div className="rinse-pace">
                <span id="pace-label">Pace</span>
                <ToggleGroup
                  type="single"
                  size="sm"
                  variant="outline"
                  spacing={0}
                  value={String(pace)}
                  onValueChange={choosePace}
                  aria-labelledby="pace-label"
                >
                  {PACES.map((p) => (
                    <ToggleGroupItem
                      key={p.value}
                      value={String(p.value)}
                      className="px-2.5"
                    >
                      {p.label}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </div>
            </div>

            {loadError !== null ? (
              <p role="alert" className="rinse-sheet rinse-sheet-note">
                Could not load the documents: {loadError}
              </p>
            ) : data === null ? (
              <p className="rinse-sheet rinse-sheet-note">Loading documents</p>
            ) : data.documents.length === 0 ? (
              <p className="rinse-sheet rinse-sheet-note">
                No documents yet. Add a text to demo-documents/ or a recording
                to fixtures/.
              </p>
            ) : (
              <ul className="rinse-sheets">
                {data.documents.map((document) => (
                  <DocumentSheet
                    key={document.id}
                    document={document}
                    liveAnalysis={data.live_analysis}
                    pace={pace}
                    starting={starting}
                    onStart={start}
                  />
                ))}
              </ul>
            )}
            {data !== null && data.invalid_recordings.length > 0 && (
              <p className="rinse-aside">
                Not listed, invalid recording:{" "}
                {data.invalid_recordings.map((r) => r.file).join(", ")}. Run the
                validator for the reason.
              </p>
            )}
          </section>

          <section aria-labelledby="own-heading">
            <div className="rinse-heading">
              <h2 id="own-heading" className="rinse-heading-text">
                Your own text
              </h2>
            </div>
            {data?.live_analysis ? (
              <OwnTextForm starting={starting} onStart={start} />
            ) : (
              <p className="rinse-sheet rinse-sheet-note">
                Pasting a text or a link arrives with the live pipeline. Until
                then, the documents above open a recorded analysis.
              </p>
            )}
          </section>

          {recent.length > 0 && (
            <section aria-labelledby="recent-heading">
              <div className="rinse-heading">
                <h2 id="recent-heading" className="rinse-heading-text">
                  Recent
                </h2>
              </div>
              <ul className="rinse-recent">
                {recent.map((analysis) => (
                  <li key={analysis.analysis_id}>
                    <Link
                      className="rinse-recent-row"
                      href={paths.analysis(analysis.analysis_id)}
                    >
                      <span className="rinse-recent-title">
                        {analysis.title ?? describeSource(analysis)}
                      </span>
                      <span className="rinse-recent-meta">
                        {STATUS_TEXT[analysis.status]},{" "}
                        {formatRelative(analysis.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </main>
    </div>
  )

  // Lenis smooths the wheel on this screen only; the analysis screen has its own scroll
  // containers. It scrolls the native document, so sticky and useScroll keep working.
  if (reduced) return screen
  return (
    <ReactLenis root options={{ anchors: true }}>
      {screen}
    </ReactLenis>
  )
}

/**
 * One document, as a sheet lying on the rinsed ground. The pigment down its left edge is what
 * the analysis is about to take off: it drains under the pointer and stays gone once the
 * analysis has started.
 */
function DocumentSheet({
  document,
  liveAnalysis,
  pace,
  starting,
  onStart,
}: {
  document: DemoDocument
  liveAnalysis: boolean
  pace: Pace
  starting: string | null
  onStart: (key: string, request: AnalysisRequest) => void
}) {
  const recording = document.recordings[0]
  const meta = [
    document.text_type !== null ? TEXT_TYPE_LABELS[document.text_type] : null,
    document.words !== null ? `${formatNumber(document.words)} words` : null,
    document.retrieved !== null
      ? `retrieved ${formatDate(document.retrieved)}`
      : null,
  ].filter((part): part is string => part !== null)
  const busy = starting !== null
  const key = recording
    ? `recording:${recording.fixture}`
    : `live:${document.id}`
  const mine = starting === key

  return (
    <li className="rinse-sheet" data-rinsing={mine ? "" : undefined}>
      <span className="rinse-pigment" aria-hidden="true" />
      <div className="rinse-sheet-text">
        {document.company !== null && (
          <p className="rinse-sheet-company">{document.company}</p>
        )}
        <h3 className="rinse-sheet-title">{document.title}</h3>
        <p className="rinse-sheet-meta">
          {meta.join(", ")}
          {document.url !== null && (
            <>
              {meta.length > 0 && ", "}
              <a href={document.url} target="_blank" rel="noreferrer">
                source
              </a>
            </>
          )}
        </p>
      </div>
      <div className="rinse-sheet-action">
        {recording ? (
          <>
            <Button
              disabled={busy}
              onClick={() =>
                onStart(key, {
                  kind: "replay",
                  fixture: recording.fixture,
                  speed: pace,
                })
              }
            >
              {mine ? (
                <LoaderCircle
                  data-icon="inline-start"
                  className="animate-spin"
                />
              ) : (
                <Play data-icon="inline-start" />
              )}
              {mine ? "Starting" : "Analyse"}
            </Button>
            <p className="rinse-sheet-note">
              Recorded analysis, {formatDuration(recording.duration_ms)}
              {document.recordings.length > 1 &&
                ` (${document.recordings.length} recordings)`}
            </p>
          </>
        ) : liveAnalysis && document.url !== null ? (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              onStart(key, { kind: "url", url: document.url as string })
            }
          >
            {mine && (
              <LoaderCircle data-icon="inline-start" className="animate-spin" />
            )}
            {mine ? "Starting" : "Analyse live"}
          </Button>
        ) : (
          <p className="rinse-sheet-note">No recording yet</p>
        )}
      </div>
    </li>
  )
}

/** The sheet the reader writes on: ruled paper for the text, a plain field for a link. */
function OwnTextForm({
  starting,
  onStart,
}: {
  starting: string | null
  onStart: (key: string, request: AnalysisRequest) => void
}) {
  const [text, setText] = useState("")
  const [url, setUrl] = useState("")
  const busy = starting !== null
  const mine = starting?.startsWith("own:") === true

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (url.trim() !== "") onStart("own:url", { kind: "url", url: url.trim() })
    else if (text.trim() !== "") onStart("own:text", { kind: "text", text })
  }

  return (
    <form
      onSubmit={submit}
      className="rinse-sheet rinse-form"
      data-rinsing={mine ? "" : undefined}
    >
      <span className="rinse-pigment" aria-hidden="true" />
      <div className="rinse-field">
        <Label htmlFor="own-text">Paste a text</Label>
        <Textarea
          id="own-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          className="rinse-ruled py-[7px] leading-[26px]"
          placeholder="A label, a policy page, a claim"
        />
      </div>
      <div className="rinse-form-foot">
        <div className="rinse-field flex-1">
          <Label htmlFor="own-url">Or a link</Label>
          <Input
            id="own-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://"
          />
        </div>
        <Button
          type="submit"
          disabled={busy || (text.trim() === "" && url.trim() === "")}
        >
          {mine && (
            <LoaderCircle data-icon="inline-start" className="animate-spin" />
          )}
          {mine ? "Starting" : "Analyse"}
        </Button>
      </div>
    </form>
  )
}

function describeSource(analysis: AnalysisSummary): string {
  const source = analysis.source
  if (typeof source.fixture === "string") return source.fixture
  if (typeof source.run === "string") return `Replay of ${source.run}`
  if (typeof source.title === "string") return source.title
  return "Analysis"
}
