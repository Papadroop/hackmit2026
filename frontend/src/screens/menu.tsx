import { useEffect, useState, type FormEvent } from "react"
import { Play } from "lucide-react"
import { toast } from "sonner"

import { ThemeToggle, Wordmark } from "@/components/chrome"
import { Link } from "@/components/link"
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
 */
export function MenuScreen() {
  const [data, setData] = useState<DocumentsResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [recent, setRecent] = useState<AnalysisSummary[]>([])
  const [pace, setPace] = useState<Pace>(() => readPref(PACE_KEY, 1, isPace))
  const [starting, setStarting] = useState<string | null>(null)

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

  return (
    <div className="min-h-svh">
      <header className="flex items-center gap-3 px-6 py-3">
        <Wordmark />
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl px-6 pt-4 pb-16">
        <p className="max-w-prose text-muted-foreground">
          Reads a corporate text, finds each environmental claim, and shows what
          the evidence supports, with its sources and how sure the finding is.
        </p>

        <section className="mt-10" aria-labelledby="documents-heading">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="documents-heading" className="text-lg font-medium">
              Documents
            </h2>
            <div className="flex items-center gap-2">
              <span id="pace-label" className="text-sm text-muted-foreground">
                Pace
              </span>
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
            <p role="alert" className="mt-3 text-destructive">
              Could not load the documents: {loadError}
            </p>
          ) : data === null ? (
            <p className="mt-3 text-muted-foreground">Loading documents</p>
          ) : data.documents.length === 0 ? (
            <p className="mt-3 text-muted-foreground">
              No documents yet. Add a text to demo-documents/ or a recording to
              fixtures/.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-border border bg-paper">
              {data.documents.map((document) => (
                <DocumentRow
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
            <p className="mt-2 text-xs text-muted-foreground">
              Not listed, invalid recording:{" "}
              {data.invalid_recordings.map((r) => r.file).join(", ")}. Run the
              validator for the reason.
            </p>
          )}
        </section>

        <section className="mt-10" aria-labelledby="own-heading">
          <h2 id="own-heading" className="text-lg font-medium">
            Your own text
          </h2>
          {data?.live_analysis ? (
            <OwnTextForm starting={starting} onStart={start} />
          ) : (
            <p className="mt-2 max-w-prose text-muted-foreground">
              Pasting a text or a link arrives with the live pipeline. Until
              then, the documents above open a recorded analysis.
            </p>
          )}
        </section>

        {recent.length > 0 && (
          <section className="mt-10" aria-labelledby="recent-heading">
            <h2 id="recent-heading" className="text-lg font-medium">
              Recent
            </h2>
            <ul className="mt-3 divide-y divide-border border-y">
              {recent.map((analysis) => (
                <li
                  key={analysis.analysis_id}
                  className="flex items-center gap-4 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-serif">
                      {analysis.title ?? describeSource(analysis)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {STATUS_TEXT[analysis.status]},{" "}
                      {formatRelative(analysis.created_at)}
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" asChild>
                    <Link href={paths.analysis(analysis.analysis_id)}>
                      Open
                    </Link>
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  )
}

function DocumentRow({
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
    document.retrieved !== null
      ? `retrieved ${formatDate(document.retrieved)}`
      : null,
    document.words !== null ? `${formatNumber(document.words)} words` : null,
  ].filter((part): part is string => part !== null)
  const busy = starting !== null
  const key = recording
    ? `recording:${recording.fixture}`
    : `live:${document.id}`

  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        {document.company !== null && (
          <p className="text-sm text-muted-foreground">{document.company}</p>
        )}
        <h3 className="font-serif text-lg leading-snug">{document.title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {meta.join(", ")}
          {document.url !== null && (
            <>
              {meta.length > 0 && ", "}
              <a
                href={document.url}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-4 hover:text-foreground"
              >
                source
              </a>
            </>
          )}
        </p>
      </div>
      <div className="shrink-0 sm:text-right">
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
              <Play data-icon="inline-start" />
              {starting === key ? "Starting" : "Analyse"}
            </Button>
            <p className="mt-1 text-xs text-muted-foreground">
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
            {starting === key ? "Starting" : "Analyse live"}
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">No recording yet</p>
        )}
      </div>
    </li>
  )
}

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

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (url.trim() !== "") onStart("own:url", { kind: "url", url: url.trim() })
    else if (text.trim() !== "") onStart("own:text", { kind: "text", text })
  }

  return (
    <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="own-text">Paste a text</Label>
        <Textarea
          id="own-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          placeholder="A label, a policy page, a claim"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="own-url">Or a link</Label>
        <Input
          id="own-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://"
        />
      </div>
      <div>
        <Button
          type="submit"
          disabled={busy || (text.trim() === "" && url.trim() === "")}
        >
          {starting?.startsWith("own:") ? "Starting" : "Analyse"}
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
